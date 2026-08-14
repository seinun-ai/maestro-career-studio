"""Multi-turn, tool-calling, streaming chat agent.

Separate from `llm.call_openai` (single-shot, JSON-mode, Gemini-capable): chat
needs a message array, a tools loop, and token streaming. Chat therefore
requires an endpoint that speaks the OpenAI streaming tool-call wire shape
(OpenAI or Gemini's compat layer).

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
from app.services import model_settings, persona as persona_service, prompts
from app.services.chat_tools import ToolContext, execute_tool, openai_tool_specs
from app.services.llm import completion_extras, get_chat_client

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8


def _system_prompt(db: Session) -> str:
    template = prompts.get_prompt("chat_system", db)
    persona = (persona_service.get_persona(db) or "").strip()
    persona_block = f"CANDIDATE PERSONA:\n{persona}" if persona else ""
    return StringTemplate(template).safe_substitute(persona=persona_block).strip()


def _describe_selection(sel: dict[str, Any]) -> str:
    path = sel.get("section", "?")
    if sel.get("index") is not None:
        path += f"[{sel['index']}]"
    if sel.get("bullet_index") is not None:
        path += f".bullets[{sel['bullet_index']}]"
    label = sel.get("label")
    return f"{path} ({label})" if label else path


def _context_block(db: Session, context: dict[str, Any] | None) -> str | None:
    """Ephemeral system message describing pinned target/selections/attachments."""
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


def _replay_messages(session_row: ChatSession) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for m in session_row.messages:
        entry: dict[str, Any] = {"role": m.role, "content": m.content or ""}
        if m.role == "assistant" and m.tool_calls:
            entry["tool_calls"] = m.tool_calls
            entry["content"] = m.content or None
        if m.role == "tool":
            entry["tool_call_id"] = m.tool_call_id
        messages.append(entry)
    return messages


def _persist(db: Session, session_row: ChatSession, **kwargs) -> ChatMessage:
    row = ChatMessage(session_id=session_row.id, **kwargs)
    db.add(row)
    db.flush()
    return row


def _accumulate_stream(stream) -> Iterator[dict[str, Any]]:
    """Yield delta events; final yield is {"type": "_final", content, tool_calls}."""
    content_parts: list[str] = []
    tool_calls: dict[int, dict[str, Any]] = {}
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta is None:
            continue
        if delta.content:
            content_parts.append(delta.content)
            yield {"type": "delta", "text": delta.content}
        for tc in delta.tool_calls or []:
            slot = tool_calls.setdefault(
                tc.index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
            )
            if tc.id:
                slot["id"] = tc.id
            if tc.function:
                if tc.function.name:
                    slot["function"]["name"] = tc.function.name
                if tc.function.arguments:
                    slot["function"]["arguments"] += tc.function.arguments
    yield {
        "type": "_final",
        "content": "".join(content_parts),
        "tool_calls": [tool_calls[i] for i in sorted(tool_calls)] or None,
    }


def run_turn(
    db: Session,
    session_row: ChatSession,
    user_content: str,
    context: dict[str, Any] | None = None,
    *,
    client: Any = None,
    model: str | None = None,
) -> Iterator[dict[str, Any]]:
    model = model or model_settings.get_chat_model(db)
    client = client or get_chat_client(model)

    user_msg = _persist(
        db, session_row, role="user", content=user_content, meta_json=context or None
    )
    if not session_row.title:
        session_row.title = user_content.strip()[:60] or "New chat"
    db.commit()
    yield {"type": "message", "id": str(user_msg.id), "role": "user"}

    messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt(db)}]
    messages.extend(_replay_messages(session_row))
    context_block = _context_block(db, context)
    if context_block:
        # Ephemeral: injected each turn from the message's meta, never persisted.
        messages.insert(-1, {"role": "system", "content": context_block})

    ctx = ToolContext(
        db=db, message_id=str(user_msg.id), selections=(context or {}).get("selections") or []
    )

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=openai_tool_specs(),
                stream=True,
                **completion_extras(model),
            )
            final: dict[str, Any] = {}
            for event in _accumulate_stream(stream):
                if event["type"] == "_final":
                    final = event
                else:
                    yield event

            if not final.get("tool_calls"):
                assistant = _persist(
                    db, session_row, role="assistant", content=final.get("content") or ""
                )
                db.commit()
                yield {"type": "message", "id": str(assistant.id), "role": "assistant"}
                yield {"type": "done", "session_id": str(session_row.id)}
                return

            assistant = _persist(
                db,
                session_row,
                role="assistant",
                content=final.get("content") or None,
                tool_calls=final["tool_calls"],
            )
            db.commit()
            messages.append(
                {
                    "role": "assistant",
                    "content": final.get("content") or None,
                    "tool_calls": final["tool_calls"],
                }
            )

            for call in final["tool_calls"]:
                name = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    arguments = None
                yield {"type": "tool_start", "name": name, "arguments": arguments}

                if arguments is None:
                    result: Any = {"error": "Tool arguments were not valid JSON"}
                else:
                    result = execute_tool(ctx, name, arguments)

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
                # Persist BEFORE emitting the card so the event can carry the
                # tool row's id — the handle card_state resolutions stamp onto.
                tool_msg = _persist(
                    db,
                    session_row,
                    role="tool",
                    content=result_text,
                    tool_call_id=call["id"],
                    meta_json=meta,
                )
                db.commit()
                if card_key:
                    yield {
                        "type": card_key,
                        **result[card_key],
                        "message_id": str(tool_msg.id),
                    }
                yield {"type": "message", "id": str(tool_msg.id), "role": "tool"}
                messages.append(
                    {"role": "tool", "content": result_text, "tool_call_id": call["id"]}
                )

        # Tool-round budget exhausted: surface it rather than looping forever.
        assistant = _persist(
            db,
            session_row,
            role="assistant",
            content="(Stopped: too many consecutive tool calls in one turn.)",
        )
        db.commit()
        yield {"type": "message", "id": str(assistant.id), "role": "assistant"}
        yield {"type": "done", "session_id": str(session_row.id)}
    except Exception as exc:  # noqa: BLE001 — stream must end with an error event, not a broken pipe
        logger.exception("chat turn failed for session %s", session_row.id)
        db.rollback()
        yield {"type": "error", "detail": str(exc)}
