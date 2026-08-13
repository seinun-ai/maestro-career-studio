"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  FileText,
  History,
  Loader2,
  Paperclip,
  Plus,
  Trash2,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";

import { ChangeCard } from "@/components/chat/change-card";
import { EditProposalCard } from "@/components/chat/edit-proposal-card";
import { KbCaptureCard } from "@/components/chat/kb-capture-card";
import { ChatMarkdown } from "@/components/chat/markdown";
import { ProposalCard } from "@/components/chat/proposal-card";
import { ScopePickerDialog, SelectionChip } from "@/components/chat/scope-picker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useIsMobile } from "@/hooks/use-mobile";
import {
  apiFetch,
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  streamChatMessage,
  uploadChatAttachment,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  BaseResumeDetail,
  BaseResumeSummary,
  ChatAttachmentInfo,
  ChatChangeCard,
  ChatKbCapture,
  ChatMessage,
  ChatProposal,
  ChatProposalOps,
  ChatSelection,
  ChatSessionSummary,
  UUID,
} from "@/lib/types";

const NO_TARGET = "__none__";
const HISTORY_COLLAPSED_KEY = "chatPage.historyCollapsed";

interface StreamingState {
  text: string;
  tools: string[];
  cards: ChatChangeCard[];
  proposals: (ChatProposal & { message_id?: UUID })[];
  proposalOps: (ChatProposalOps & { message_id?: UUID })[];
  captures: ChatKbCapture[];
}

export function ChatPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  // The URL is the single source of truth for which chat is open. This used to
  // be component state alone, so leaving /chat and coming back — or a reload —
  // silently reset you to "no session", and the next message (a follow-up, as
  // far as you were concerned) opened a second chat in the rail. Deriving also
  // makes back/forward and deep links work.
  const sessionId = searchParams.get("session") as UUID | null;
  const openSession = (id: UUID | null) =>
    router.replace(id ? `/chat?session=${id}` : "/chat", { scroll: false });

  const [input, setInput] = useState("");
  const [target, setTarget] = useState<string>(NO_TARGET);
  const [selections, setSelections] = useState<ChatSelection[]>([]);
  const [attachments, setAttachments] = useState<ChatAttachmentInfo[]>([]);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  // Desktop rail tuck-in. Mirrors EditorShell's collapsed/hydrated pattern:
  // the default (false, i.e. open) matches what a first paint without
  // localStorage renders, so hydrating in an effect — rather than reading
  // localStorage during render — never produces a client/server mismatch.
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const [historyHydrated, setHistoryHydrated] = useState(false);
  // Mobile session list, shown in a Sheet instead of the (hidden) rail. Which
  // surface is live is decided by CSS (`md:` breakpoints), not this hook —
  // useIsMobile() resolves in an effect and would render the desktop rail
  // for one frame on a mobile first paint; a Tailwind media query has no
  // such flash, so it is what gates the rail/trigger split below. The hook
  // is still used (see effect below) to close the Sheet when the viewport
  // crosses to md+, since it is a portal and no `md:` class reaches it.
  const [historySheetOpen, setHistorySheetOpen] = useState(false);
  const isMobile = useIsMobile();
  // False until the pin has been resolved for the open session (see below).
  // Gates the auto-seed so it never overwrites a real choice — including an
  // explicit "No pinned resume".
  const [pinResolved, setPinResolved] = useState(false);
  const sendingRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Mirrors `target` for the streaming callback, which closes over the value
  // captured when the send started — without it, a turn that edits two resumes
  // compares the second card against a stale pin. Synced in an effect because
  // refs must not be read or written during render.
  const targetRef = useRef(target);
  useEffect(() => {
    targetRef.current = target;
  }, [target]);

  // Hydrate the rail's collapsed state from localStorage after mount, same
  // as EditorShell's preview pane — reading it during render would disagree
  // with the server-rendered (always-open) markup and trigger a hydration
  // mismatch.
  useEffect(() => {
    const stored = window.localStorage.getItem(HISTORY_COLLAPSED_KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrating from localStorage after mount
    if (stored === "1") setHistoryCollapsed(true);
    setHistoryHydrated(true);
  }, []);

  useEffect(() => {
    if (!historyHydrated) return;
    window.localStorage.setItem(
      HISTORY_COLLAPSED_KEY,
      historyCollapsed ? "1" : "0",
    );
  }, [historyCollapsed, historyHydrated]);

  // The Sheet is a portal (renders under <body>, not this tree), so no
  // `md:` class on its trigger or the rail reaches it — crossing to desktop
  // width does not itself close it. Opened at 400px then resized to 1200px,
  // it would otherwise sit on top of the now-visible desktop rail with no
  // trigger left to dismiss it from (Escape and the backdrop still would,
  // but nothing here should depend on that). Close it explicitly on the
  // crossing instead.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing React state to a matchMedia crossing, not derivable during render
    if (!isMobile) setHistorySheetOpen(false);
  }, [isMobile]);

  // Event-handler-only (it reads the ref). Selections are paths into the resume
  // they were picked from, so a real switch drops them; an unchanged pin is a
  // no-op and keeps them.
  const applyTarget = (next: string) => {
    if (targetRef.current === next) return;
    targetRef.current = next;
    setTarget(next);
    // Keep identity stable when already empty, so repeat cards in one stream
    // do not each force a pointless re-render.
    setSelections((prev) => (prev.length > 0 ? [] : prev));
  };

  // The pin is a hint, not a guard: the model can edit a resume other than the
  // pinned one when the user names it in prose ("in my Data Analyst resume, …").
  // Follow whichever resume actually changed, so the picker shows what moved and
  // the next message targets the same one. Both paths that land ops come here —
  // a streamed change card, and a staged proposal the user applies (which
  // PATCHes directly and produces no stream event). Application-scoped edits are
  // ignored: the picker only lists base resumes.
  const followEditedResume = (kind: "base" | "application", key: string) => {
    if (kind === "base") applyTarget(key);
  };

  // Composer context belongs to one session: attachments are uploaded under a
  // session id and the server resolves `attachment_ids` unscoped, so a stale
  // one must not survive a switch — including back/forward, which runs no
  // handler. null -> id is this draft being saved, not a switch, so the chips
  // the user set up before the first send are kept.
  const [contextSession, setContextSession] = useState(sessionId);
  if (contextSession !== sessionId) {
    const switched = contextSession !== null;
    setContextSession(sessionId);
    if (switched) {
      setSelections([]);
      setAttachments([]);
      // The session we moved to owns its own pin; re-resolve it below.
      setPinResolved(false);
    }
  }

  const sessions = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: listChatSessions,
  });

  const detail = useQuery({
    queryKey: ["chat-session", sessionId],
    queryFn: () => getChatSession(sessionId as UUID),
    enabled: sessionId !== null,
  });

  const resumes = useQuery({
    queryKey: ["base-resumes"],
    queryFn: () => apiFetch<BaseResumeSummary[]>("/api/base-resumes"),
  });

  const pinned = useQuery({
    queryKey: ["base-resumes", target],
    queryFn: () => apiFetch<BaseResumeDetail>(`/api/base-resumes/${target}`),
    enabled: target !== NO_TARGET,
  });

  // The pin resolves once per session: the session's own stored target if it
  // has one, else the most recently touched base resume. It used to start at
  // NO_TARGET always, which cost two clicks before any edit could be asked for
  // AND silently dropped a saved pin when you reopened a session — the composer
  // read `context_json` on the way out but never on the way back in.
  const sessionTarget =
    detail.data?.context_json?.target_kind === "base"
      ? detail.data.context_json.target_key
      : undefined;
  const resumeList = resumes.data;
  // Resolved during render, like the context reset above: an effect here would
  // commit a NO_TARGET frame first and flash the empty pin.
  if (!pinResolved) {
    // An open session's own pin wins, so wait for it rather than seeding a
    // default we would immediately overwrite. A session with no stored pin
    // falls through to the recency seed and needs the resume list instead.
    // isPending, not isSuccess: a thread that fails to load should still fall
    // through to the seed rather than leave the pin stuck on NO_TARGET.
    const waiting = sessionId !== null && detail.isPending;
    if (!waiting && (sessionTarget || resumeList)) {
      // The list endpoint already excludes archived resumes.
      const newest = resumeList?.reduce<BaseResumeSummary | undefined>(
        (best, r) => (!best || r.updated_at > best.updated_at ? r : best),
        undefined,
      );
      setPinResolved(true);
      // Not applyTarget: that reads the ref, and selections are already empty
      // here (a session switch clears them, a fresh mount has none).
      setTarget(sessionTarget ?? newest?.slug ?? NO_TARGET);
    }
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [
    detail.data?.messages.length,
    streaming?.text,
    streaming?.cards.length,
    streaming?.proposals.length,
    streaming?.proposalOps.length,
    streaming?.captures.length,
  ]);

  const newSession = useMutation({
    mutationFn: () =>
      createChatSession(
        target !== NO_TARGET
          ? { target_kind: "base", target_key: target }
          : undefined,
      ),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["chat-sessions"] });
      openSession(created.id);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const removeSession = useMutation({
    mutationFn: (id: UUID) => deleteChatSession(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["chat-sessions"] });
      if (sessionId === id) openSession(null);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Shared by the desktop rail and the mobile sheet's session list, so
  // picking a session behaves identically from either surface.
  const selectSession = (s: ChatSessionSummary) => {
    openSession(s.id);
    // Adopt the session's stored default target.
    const stored = s.context_json?.target_key;
    if (stored) setTarget(stored);
    setHistorySheetOpen(false);
  };

  const send = async () => {
    const content = input.trim();
    // The re-entry guard has to be synchronous. `streaming` is only set below,
    // after the session-create round trip, so two quick Enters both cleared it
    // and each created its own chat — the send button's `disabled` reads the
    // same stale state, so it did not stop this either.
    if (!content || sendingRef.current) return;
    sendingRef.current = true;

    let activeSession = sessionId;
    try {
      if (activeSession === null) {
        const created = await createChatSession(
          target !== NO_TARGET
            ? { target_kind: "base", target_key: target }
            : undefined,
        );
        qc.invalidateQueries({ queryKey: ["chat-sessions"] });
        openSession(created.id);
        activeSession = created.id;
      }

      const context =
        target !== NO_TARGET || attachments.length > 0 || selections.length > 0
          ? {
              ...(target !== NO_TARGET
                ? { target_kind: "base" as const, target_key: target }
                : {}),
              ...(selections.length > 0 ? { selections } : {}),
              ...(attachments.length > 0
                ? { attachment_ids: attachments.map((a) => a.id) }
                : {}),
            }
          : null;

      setInput("");
      setAttachments([]);
      setStreaming({
        text: "",
        tools: [],
        cards: [],
        proposals: [],
        proposalOps: [],
        captures: [],
      });

      await streamChatMessage(activeSession, content, context, (event) => {
        if (event.type === "delta") {
          setStreaming((s) =>
            s ? { ...s, text: s.text + event.text } : s,
          );
        } else if (event.type === "tool_start") {
          setStreaming((s) =>
            // A new LLM round begins after tool calls; its text streams fresh.
            s ? { ...s, text: "", tools: [...s.tools, event.name] } : s,
          );
        } else if (event.type === "change_card") {
          const card: ChatChangeCard = {
            resume_kind: event.resume_kind,
            resume_key: event.resume_key,
            version_number: event.version_number,
            summary: event.summary,
            ops_count: event.ops_count,
          };
          setStreaming((s) => (s ? { ...s, cards: [...s.cards, card] } : s));
          followEditedResume(event.resume_kind, event.resume_key);
        } else if (event.type === "proposal") {
          const proposal: ChatProposal & { message_id?: UUID } = {
            target_kind: event.target_kind,
            target_key: event.target_key,
            project: event.project,
            message_id: event.message_id,
          };
          setStreaming((s) =>
            s ? { ...s, proposals: [...s.proposals, proposal] } : s,
          );
        } else if (event.type === "proposal_ops") {
          const proposal: ChatProposalOps & { message_id?: UUID } = {
            target_kind: event.target_kind,
            target_key: event.target_key,
            ops: event.ops,
            ops_count: event.ops_count,
            summary: event.summary,
            message_id: event.message_id,
          };
          setStreaming((s) =>
            s ? { ...s, proposalOps: [...s.proposalOps, proposal] } : s,
          );
        } else if (event.type === "kb_capture") {
          const capture: ChatKbCapture = {
            entity_id: event.entity_id,
            entity_title: event.entity_title,
            point_count: event.point_count,
          };
          setStreaming((s) =>
            s ? { ...s, captures: [...s.captures, capture] } : s,
          );
        } else if (event.type === "error") {
          toast.error(event.detail);
        }
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Chat failed");
    } finally {
      sendingRef.current = false;
      setStreaming(null);
      // Null when the create itself failed — there is no thread to refetch.
      if (activeSession !== null) {
        qc.invalidateQueries({ queryKey: ["chat-session", activeSession] });
      }
      qc.invalidateQueries({ queryKey: ["chat-sessions"] });
      qc.invalidateQueries({ queryKey: ["resume-versions"] });
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
    }
  };

  const onPickFile = async (file: File) => {
    let activeSession = sessionId;
    try {
      if (activeSession === null) {
        const created = await createChatSession();
        qc.invalidateQueries({ queryKey: ["chat-sessions"] });
        openSession(created.id);
        activeSession = created.id;
      }
      const info = await uploadChatAttachment(activeSession, file);
      setAttachments((a) => [...a, info]);
      toast.success(`Attached ${info.filename} (${info.chars.toLocaleString()} chars)`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    }
  };

  // Gemini-style: while the thread is empty the composer floats centered
  // under a greeting; once messages exist it docks to the bottom.
  const hasThread = (detail.data?.messages.length ?? 0) > 0 || !!streaming;

  const composer = (
    <div className="bg-card focus-within:border-ring/60 rounded-3xl border p-2 shadow-sm transition-[border-color,box-shadow] duration-150 focus-within:shadow-md">
      {(selections.length > 0 || attachments.length > 0) && (
        <div className="flex flex-wrap items-center gap-1.5 px-2 pt-1.5">
          {selections.map((s, i) => (
            <SelectionChip
              key={i}
              selection={s}
              onRemove={() =>
                setSelections((prev) => prev.filter((_, j) => j !== i))
              }
            />
          ))}
          {attachments.map((a) => (
            <Badge key={a.id} variant="secondary" className="gap-1 font-normal">
              <Paperclip className="size-3" />
              <span className="max-w-40 truncate">{a.filename}</span>
            </Badge>
          ))}
        </div>
      )}
      <Textarea
        rows={hasThread ? 1 : 2}
        aria-label="Message"
        placeholder="Ask about your resume…"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void send();
          }
        }}
        className="min-h-0 resize-none border-0 bg-transparent px-3 py-2 shadow-none focus-visible:ring-0 dark:bg-transparent"
      />
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.md,.txt,.tex,.png,.jpg,.jpeg,.webp"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void onPickFile(file);
          e.target.value = "";
        }}
      />
      <div className="flex items-center gap-1 px-1 pb-0.5">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Attach file"
          className="text-muted-foreground rounded-full"
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip className="size-4" />
        </Button>
        <Select
          value={target}
          onValueChange={(v) => applyTarget(v ?? NO_TARGET)}
        >
          <SelectTrigger
            size="sm"
            aria-label="Pinned resume"
            className="text-muted-foreground h-8 w-auto gap-1.5 rounded-full border-0 bg-transparent px-2.5 text-xs shadow-none hover:bg-muted"
          >
            <FileText className="size-3.5" />
            <SelectValue>
              {target === NO_TARGET
                ? "No pinned resume"
                : (resumes.data?.find((r) => r.slug === target)?.display_name ??
                  target)}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_TARGET}>No pinned resume</SelectItem>
            {resumes.data?.map((r) => (
              <SelectItem key={r.slug} value={r.slug}>
                {r.display_name || r.slug}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground h-8 rounded-full px-2.5 text-xs"
          onClick={() => setScopeOpen(true)}
        >
          <Plus className="size-3.5" />
          Context
        </Button>
        <div className="flex-1" />
        <Button
          size="icon"
          aria-label="Send"
          disabled={!input.trim() || !!streaming}
          className="rounded-full"
          onClick={() => void send()}
        >
          {streaming ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <ArrowUp className="size-4" />
          )}
        </Button>
      </div>
    </div>
  );

  return (
    // relative: anchors the floating "Show chat history" edge button that
    // appears once the rail is collapsed (mirrors EditorShell's preview pane).
    <div className="relative flex h-[calc(100svh-1rem)] gap-4 p-4">
      {/* Sessions rail — desktop only (md+); below that, the same list lives
          in the Sheet opened from the thread's "Chat history" button. The
          rail itself is `hidden md:flex` gated further by `historyCollapsed`,
          so it never flashes on a mobile first paint (a CSS media query has
          no client/server mismatch to resolve, unlike useIsMobile()). The
          Sheet is a portal, though, so its open state is independent React
          state, not gated by these classes — it is closed on the md
          crossing by the effect above instead. */}
      {!historyCollapsed && (
        <aside className="hidden w-64 shrink-0 flex-col gap-3 md:flex">
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              onClick={() => newSession.mutate()}
              disabled={newSession.isPending}
              className="bg-primary/10 text-primary hover:bg-primary/15 h-10 flex-1 justify-start gap-2 rounded-full px-4"
            >
              <Plus className="size-4" /> New chat
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Hide chat history"
              onClick={() => setHistoryCollapsed(true)}
            >
              <ChevronLeft className="size-4" />
            </Button>
          </div>
          <SessionList
            sessions={sessions.data}
            activeId={sessionId}
            onSelect={selectSession}
            onDelete={(id) => removeSession.mutate(id)}
          />
        </aside>
      )}
      {historyCollapsed && (
        <button
          type="button"
          aria-label="Show chat history"
          onClick={() => setHistoryCollapsed(false)}
          className="bg-background hover:bg-muted text-muted-foreground hover:text-foreground absolute top-1/2 left-0 z-10 hidden h-20 w-7 -translate-y-1/2 items-center justify-center gap-1 rounded-r-md border border-l-0 shadow-md transition-colors md:flex"
        >
          <ChevronRight className="size-4" />
        </button>
      )}

      {/* Thread + composer. This is the page's <main> — the chat layout has an
          <aside> of past sessions beside it, so the landmark belongs on the
          conversation column, not on the two-column wrapper. */}
      <main className="flex min-w-0 flex-1 flex-col">
        {/* Below md, the rail is `hidden` outright (see above), so this is
            the only way back to past sessions — without it, chats would be
            completely unreachable on mobile. */}
        <div className="flex items-center pb-2 md:hidden">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Chat history"
            onClick={() => setHistorySheetOpen(true)}
          >
            <History className="size-4" />
          </Button>
        </div>
        {hasThread ? (
          <>
            <div className="flex-1 overflow-y-auto pr-1">
              <div className="mx-auto w-full max-w-3xl space-y-4 py-2">
                {detail.data?.messages.map((m) => (
                  <MessageRow
                    key={m.id}
                    message={m}
                    onProposalApplied={followEditedResume}
                  />
                ))}
                {streaming && (
                  <div className="space-y-2">
                    {streaming.tools.map((name, i) => (
                      <div
                        key={i}
                        className="text-muted-foreground flex items-center gap-1.5 text-xs"
                      >
                        <Wrench className="size-3" /> {name}
                      </div>
                    ))}
                    {streaming.cards.map((card, i) => (
                      <ChangeCard key={i} card={card} />
                    ))}
                    {streaming.proposals.map((proposal, i) => (
                      <ProposalCard
                        key={i}
                        proposal={proposal}
                        messageId={proposal.message_id}
                      />
                    ))}
                    {streaming.proposalOps.map((proposal, i) => (
                      <EditProposalCard
                        key={i}
                        proposal={proposal}
                        messageId={proposal.message_id}
                        onApplied={followEditedResume}
                      />
                    ))}
                    {streaming.captures.map((capture, i) => (
                      <KbCaptureCard key={i} capture={capture} />
                    ))}
                    <div className="flex items-start gap-2">
                      <Loader2 className="text-muted-foreground mt-1 size-3.5 shrink-0 animate-spin" />
                      <div className="min-w-0 flex-1">
                        <ChatMarkdown>{streaming.text}</ChatMarkdown>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>
            </div>
            <div className="mx-auto mt-3 w-full max-w-3xl">{composer}</div>
          </>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-8 px-4">
            <div className="animate-fade-rise text-center">
              <h1 className="from-primary bg-gradient-to-r via-violet-500 to-rose-400 bg-clip-text text-3xl font-medium tracking-tight text-transparent">
                What are we working on?
              </h1>
              <p className="text-muted-foreground mt-2 text-sm">
                Edit a resume, draft project points, or work on a template. Every edit is versioned.
              </p>
            </div>
            <div className="w-full max-w-3xl">{composer}</div>
          </div>
        )}
      </main>

      <ScopePickerDialog
        open={scopeOpen}
        onOpenChange={setScopeOpen}
        data={target !== NO_TARGET ? pinned.data?.data : undefined}
        resumeState={
          target === NO_TARGET
            ? "none"
            : pinned.isLoading
              ? "loading"
              : pinned.error
                ? "error"
                : "ready"
        }
        selections={selections}
        onAdd={(s) => setSelections((prev) => [...prev, s])}
      />

      {/* Mobile session list — same data, same row markup as the desktop
          rail (via SessionList), just hosted in a Sheet instead of a
          persistent column. Its trigger lives in the thread header above. */}
      <Sheet open={historySheetOpen} onOpenChange={setHistorySheetOpen}>
        {/* showCloseButton=false: the default close X sits top-3 right-3,
            over the rightmost ~40px of the full-width "New chat" button
            below, and would swallow taps meant for it. Same call as
            ui/sidebar.tsx's mobile Sheet. Escape and a backdrop tap still
            dismiss the sheet. */}
        <SheetContent
          side="left"
          className="w-72 p-0 sm:max-w-72"
          showCloseButton={false}
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Chat history</SheetTitle>
            <SheetDescription>
              Browse and switch between past chats.
            </SheetDescription>
          </SheetHeader>
          <div className="flex h-full flex-col gap-3 p-3">
            <Button
              variant="ghost"
              onClick={() => {
                newSession.mutate();
                setHistorySheetOpen(false);
              }}
              disabled={newSession.isPending}
              className="bg-primary/10 text-primary hover:bg-primary/15 h-10 justify-start gap-2 rounded-full px-4"
            >
              <Plus className="size-4" /> New chat
            </Button>
            <SessionList
              sessions={sessions.data}
              activeId={sessionId}
              onSelect={selectSession}
              onDelete={(id) => removeSession.mutate(id)}
            />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function SessionList({
  sessions,
  activeId,
  onSelect,
  onDelete,
}: {
  sessions: ChatSessionSummary[] | undefined;
  activeId: UUID | null;
  onSelect: (session: ChatSessionSummary) => void;
  onDelete: (id: UUID) => void;
}) {
  return (
    <div className="flex-1 space-y-0.5 overflow-y-auto">
      {(sessions?.length ?? 0) > 0 && (
        <p className="text-muted-foreground px-3 pb-1 text-xs font-medium">
          Recent
        </p>
      )}
      {sessions?.map((s) => (
        <div
          key={s.id}
          className={cn(
            "group flex items-center gap-1 rounded-full px-3 py-1.5 transition-colors duration-150",
            activeId === s.id ? "bg-primary/10 text-primary" : "hover:bg-muted",
          )}
        >
          <button
            type="button"
            className="min-w-0 flex-1 truncate text-left text-sm"
            onClick={() => onSelect(s)}
          >
            {s.title || "Untitled chat"}
          </button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Delete chat"
            className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
            onClick={() => onDelete(s.id)}
          >
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      ))}
    </div>
  );
}

function MessageRow({
  message,
  onProposalApplied,
}: {
  message: ChatMessage;
  onProposalApplied?: (kind: "base" | "application", key: string) => void;
}) {
  if (message.role === "tool") {
    const card = message.meta_json?.change_card;
    const proposal = message.meta_json?.proposal;
    const proposalOps = message.meta_json?.proposal_ops;
    const capture = message.meta_json?.kb_capture;
    const cardState = message.meta_json?.card_state;
    if (card) return <ChangeCard card={card} />;
    if (proposal)
      return (
        <ProposalCard
          proposal={proposal}
          messageId={message.id}
          cardState={cardState}
        />
      );
    if (proposalOps)
      return (
        <EditProposalCard
          proposal={proposalOps}
          messageId={message.id}
          cardState={cardState}
          onApplied={onProposalApplied}
        />
      );
    if (capture) return <KbCaptureCard capture={capture} />;
    return null; // raw tool payloads stay out of the transcript
  }

  if (message.role === "assistant") {
    // Content-less tool-call stubs render nothing: the live streaming block
    // already shows named tool chips, and a persisted "using tools…" row
    // reads like a permanent hang in the transcript.
    if (!message.content) return null;
    return (
      <div className="max-w-[85%]">
        <ChatMarkdown>{message.content}</ChatMarkdown>
      </div>
    );
  }

  const selections = message.meta_json?.selections ?? [];
  return (
    <div className="ml-auto max-w-[85%]">
      <div className="bg-muted rounded-2xl rounded-br-md px-4 py-2.5 text-sm whitespace-pre-wrap">
        {message.content}
      </div>
      {selections.length > 0 && (
        <div className="mt-1 flex flex-wrap justify-end gap-1">
          {selections.map((s, i) => (
            <SelectionChip key={i} selection={s} />
          ))}
        </div>
      )}
    </div>
  );
}
