"""Multi-turn, tool-calling, streaming chat agent.

Separate from `llm.call_openai` (single-shot, JSON-mode): chat needs a message
array, a tools loop, and token streaming. It runs on any provider through
`llm_providers` (OpenAI-compatible, Claude, Gemini): history is neutral parts
(`transcript`), re-shaped per target by `replay`, and sent through the adapter's `stream`.

`run_turn` is a sync generator of event dicts; the router formats them as SSE:
  {"type": "delta", "text": ...}                    streamed assistant tokens
  {"type": "tool_start", "name": ..., "arguments": {...}}
  {"type": "change_card", ...} / {"type": "proposal", ...} /
  {"type": "proposal_ops", ...} / {"type": "kb_capture", ...}
    card events; each carries message_id (its persisted tool row — the id
    the frontend stamps card_state resolutions onto)
  {"type": "message", "id": ..., "role": ...}       a message row was persisted
  {"type": "done", "session_id": ...}
  {"type": "error", "detail": ...}
"""

import json
import logging
from string import Template as StringTemplate
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.models.chat import ChatAttachment, ChatMessage, ChatSession
from app.services import (
    model_settings,
    persona as persona_service,
    prompts,
    resume_voice,
    tracing,
    transcript,
)
from app.services.chat_tools import TOOL_SPECS, ToolContext, execute_tool
from app.services.llm_providers import registry, replay
from app.services.llm_providers.types import (
    Finish,
    Message,
    Part,
    Provider,
    Request,
    TextDelta,
    TextPart,
    ToolResultPart,
    ToolSpec,
    dump_parts,
    is_anthropic_thinking_part,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8


def _system_prompt(db: Session) -> str:
    template = prompts.get_prompt("chat_system", db)
    persona = (persona_service.get_persona(db) or "").strip()
    persona_block = f"CANDIDATE PERSONA:\n{persona}" if persona else ""
    body = StringTemplate(template).safe_substitute(persona=persona_block).strip()
    return f"{resume_voice.CHAT_VOICE_RULE}\n\n{body}"


def _describe_selection(sel: dict[str, Any]) -> str:
    path = sel.get("section", "?")
    if sel.get("index") is not None:
        path += f"[{sel['index']}]"
    if sel.get("bullet_index") is not None:
        path += f".bullets[{sel['bullet_index']}]"
    label = sel.get("label")
    return f"{path} ({label})" if label else path


def _context_block(db: Session, context: dict[str, Any] | None) -> str | None:
    """Text describing pinned target/selections/attachments; persisted as the user row's first part."""
    if not context:
        return None
    parts: list[str] = []
    kind, key = context.get("target_kind"), context.get("target_key")
    if kind and key:
        parts.append(f"Pinned resume: kind={kind} key={key}. Use it as the edit target.")
    selections = context.get("selections") or []
    # Kind-tagged references: resume-path chips constrain edits; other kinds
    # are pinned context. Missing kind = legacy resume chip.
    resume_selections = [s for s in selections if s.get("kind") in (None, "resume")]
    if resume_selections:
        described = "; ".join(_describe_selection(s) for s in resume_selections)
        parts.append(f"User-selected scope (edit ONLY within these paths): {described}")
    for sel in selections:
        if sel.get("kind") == "kb_entity" and sel.get("entity_id"):
            label = sel.get("label") or "entity"
            parts.append(
                f"Pinned Career KB entity: {label} (id={sel['entity_id']}) — read it "
                "with kb_get_entity before answering about it; ground claims in its "
                "points and notes."
            )
    for attachment_id in context.get("attachment_ids") or []:
        row = db.get(ChatAttachment, attachment_id)
        if row is not None:
            parts.append(
                f"Attached document: {row.filename!r} (id={row.id}) — "
                "use read_attachment to read it."
            )
    return "\n".join(parts) if parts else None


def _persist(db: Session, session_row: ChatSession, **kwargs) -> ChatMessage:
    row = ChatMessage(session_id=session_row.id, **kwargs)
    db.add(row)
    db.flush()
    return row


def run_turn(
    db: Session,
    session_row: ChatSession,
    user_content: str,
    context: dict[str, Any] | None = None,
    *,
    provider: Provider | None = None,
    model: str | None = None,
) -> Iterator[dict[str, Any]]:
    model = model or model_settings.get_chat_model(db)
    ref = registry.resolve(model)
    provider = provider or registry.get(ref.provider)

    # The context block is PERSISTED as the first part of this user row and replayed unchanged on
    # every later turn: replayed history is append-only (editing an earlier turn invalidates
    # Claude thinking). `content` stays the raw text the UI shows.
    context_block = _context_block(db, context)
    user_parts: list[Part] = ([TextPart(context_block + "\n\n")] if context_block else [])
    user_parts.append(TextPart(user_content))
    user_msg = _persist(
        db, session_row, role="user", content=user_content, meta_json=context or None,
        parts=dump_parts(user_parts),
    )
    if not session_row.title:
        session_row.title = user_content.strip()[:60] or "New chat"
    db.commit()
    yield {"type": "message", "id": str(user_msg.id), "role": "user"}

    history = transcript.history(session_row)
    system = _system_prompt(db)
    tools = [ToolSpec(s["name"], s["description"], s["parameters"]) for s in TOOL_SPECS]
    ctx = ToolContext(
        db=db, message_id=str(user_msg.id), selections=(context or {}).get("selections") or []
    )

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            request = Request(
                model=ref, system=system, tools=tools, cache=True,
                messages=replay.for_provider(history, ref),
            )
            # Gemini's stream is a generator that raises a missing key only when first pulled.
            provider.ready()
            finish: Finish | None = None
            with tracing.generation(
                "chat-step", model=model, prompt=user_content, metadata={"provider": ref.provider}
            ) as record:
                for event in provider.stream(request):
                    if isinstance(event, TextDelta):
                        yield {"type": "delta", "text": event.text}
                    else:
                        finish = event
                record(
                    finish.message.text if finish else "",
                    finish.usage.as_langfuse() if finish and finish.usage else None,
                )
            if finish is None:
                raise RuntimeError("The model's reply ended without finishing. Try again.")

            if finish.reasoning_dropped:
                # The provider rejected stored reasoning signatures and the adapter retried
                # without them: strip them from this session so the 400 is paid once.
                transcript.drop_reasoning(db, session_row)
                db.commit()  # drop_reasoning only flushes
                history = [
                    Message(m.role, [p for p in m.parts if not is_anthropic_thinking_part(p)])
                    for m in history
                ]
            reply = finish.message
            # Tools run when the reply holds calls, whatever the stop reason says (OpenAI
            # "tool_calls", Claude "tool_use", Gemini "stop").
            calls = reply.tool_calls
            assistant = _persist(
                db, session_row, role="assistant",
                content=(reply.text or None) if calls else reply.text,
                parts=dump_parts(reply.parts), provider=ref.provider, model=finish.model,
            )
            db.commit()
            history.append(reply)

            if not calls:
                yield {"type": "message", "id": str(assistant.id), "role": "assistant"}
                yield {"type": "done", "session_id": str(session_row.id)}
                return

            for call in calls:
                yield {"type": "tool_start", "name": call.name, "arguments": call.arguments}

                if call.arguments is None:
                    result: Any = {"error": "Tool arguments were not valid JSON"}
                else:
                    result = execute_tool(ctx, call.name, call.arguments)

                card_key = next(
                    (
                        k
                        for k in ("change_card", "proposal", "proposal_ops", "kb_capture")
                        if isinstance(result, dict) and k in result
                    ),
                    None,
                )
                meta = {card_key: result[card_key]} if card_key else None

                result_text = json.dumps(result, default=str)
                result_part = ToolResultPart(call.id, result_text)
                # Persist BEFORE emitting the card so the event can carry the
                # tool row's id — the handle card_state resolutions stamp onto.
                # The call id stays the provider's own; `replay` normalizes on the way out.
                tool_msg = _persist(
                    db, session_row, role="tool", content=result_text, meta_json=meta,
                    parts=dump_parts([result_part]),
                )
                db.commit()
                if card_key:
                    yield {
                        "type": card_key,
                        **result[card_key],
                        "message_id": str(tool_msg.id),
                    }
                yield {"type": "message", "id": str(tool_msg.id), "role": "tool"}
                history.append(Message("tool", [result_part]))

        # Tool-round budget exhausted: surface it rather than looping forever.
        budget_text = (
            "I stopped because this took too many steps. Try asking for one thing at a time."
        )
        assistant = _persist(
            db, session_row, role="assistant", content=budget_text,
            parts=dump_parts([TextPart(budget_text)]),
        )
        db.commit()
        yield {"type": "message", "id": str(assistant.id), "role": "assistant"}
        yield {"type": "done", "session_id": str(session_row.id)}
    except Exception as exc:  # noqa: BLE001 — stream must end with an error event, not a broken pipe
        logger.exception("chat turn failed for session %s", session_row.id)
        db.rollback()
        yield {"type": "error", "detail": str(exc)}
