"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type Dispatch,
  type Ref,
  type SetStateAction,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Handshake, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { CompanyMonogram } from "@/components/company-monogram";
import { TableFrame } from "@/components/empty-state";
import { useConfirm } from "@/components/confirm-dialog";
import { IconButton } from "@/components/icon-button";
import { LoadErrorState } from "@/components/load-error-state";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useEditToggle, useFocusHandoff } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { isLoadFailure } from "@/lib/query-state";
import type { Referral, ReferralCreate, ReferralPatch } from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";

const REFERRALS_KEY = ["referrals"] as const;

type ReferralDraft = {
  company: string;
  careersUrl: string;
  contactName: string;
  notes: string;
};

const EMPTY_DRAFT: ReferralDraft = {
  company: "",
  careersUrl: "",
  contactName: "",
  notes: "",
};

export default function ReferralsPage() {
  const qc = useQueryClient();
  const referrals = useQuery({
    queryKey: REFERRALS_KEY,
    queryFn: () => apiFetch<Referral[]>("/api/referrals"),
  });
  const [addOpen, setAddOpen] = useState(false);
  // The draft lives here, not in the form: closing the dialog unmounts its
  // content, and Esc or an overlay click must not throw typed text away. Only
  // a successful create clears it.
  const [draft, setDraft] = useState<ReferralDraft>(EMPTY_DRAFT);
  const companyRef = useRef<HTMLInputElement>(null);
  const addButtonRef = useRef<HTMLButtonElement>(null);
  // Set in the create's success handler, before the cache update renders the
  // header button. The effect runs after that commit; reading the ref during
  // render is what the compiler forbids.
  const focusAddAfterCreate = useRef(false);
  const rows = referrals.data ?? [];
  // Rows held are rows shown, even when a later refresh failed: that failure
  // keeps the loaded table (isLoadFailure), and `!isError` here swapped it for
  // the first-referral form, as if there were none.
  const populated = rows.length > 0;

  // One create for the page, not one per form: the dialog's form unmounts on
  // close, and a create it owned kept running with nothing left to say so. A
  // reopened dialog then offered an enabled submit, and a second POST.
  const create = useMutation({
    mutationFn: (payload: ReferralCreate) =>
      apiFetch<Referral>("/api/referrals", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (created) => {
      // An empty cache means this create swaps the inline form for the table,
      // unmounting the focused submit; the effect focuses the header button.
      if (!qc.getQueryData<Referral[]>(REFERRALS_KEY)?.length) {
        focusAddAfterCreate.current = true;
      }
      qc.setQueryData<Referral[]>(REFERRALS_KEY, (prev) =>
        prev ? [created, ...prev] : [created],
      );
      toast.success(`Added referral for ${created.company}`);
      setDraft(EMPTY_DRAFT);
      setAddOpen(false);
    },
    onError: (err: Error) => toast.error(err.message),
  });
  // Both forms submit through this: `isPending` re-renders a tick late, so an
  // instant double click (or Enter twice) read it false and made two rows.
  const add = useSingleFlight(create.mutate);

  useEffect(() => {
    if (!populated || !focusAddAfterCreate.current) return;
    addButtonRef.current?.focus();
    focusAddAfterCreate.current = false;
  }, [populated]);

  return (
    <PageShell>
      <PageHeader
        title="Referrals"
        subtitle="Companies where someone can refer you."
        actions={
          populated ? (
            <Button ref={addButtonRef} onClick={() => setAddOpen(true)}>
              <Plus aria-hidden="true" /> Add referral
            </Button>
          ) : undefined
        }
      />
      {isLoadFailure(referrals) ? (
        <LoadErrorState
          title="Couldn't load referrals."
          detail={(referrals.error as Error | null)?.message}
          retrying={referrals.isFetching}
          onRetry={() => void referrals.refetch()}
        />
      ) : referrals.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : populated ? (
        <ReferralsTable rows={rows} />
      ) : (
        <FirstReferralCard
          draft={draft}
          onDraftChange={setDraft}
          adding={create.isPending}
          onAdd={add}
        />
      )}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent initialFocus={companyRef}>
          <DialogHeader>
            <DialogTitle>Add referral</DialogTitle>
            <DialogDescription>
              A company where someone can refer you.
            </DialogDescription>
          </DialogHeader>
          <ReferralForm
            draft={draft}
            onDraftChange={setDraft}
            adding={create.isPending}
            onAdd={add}
            companyRef={companyRef}
            inDialog
          />
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

type DraftProps = {
  draft: ReferralDraft;
  onDraftChange: Dispatch<SetStateAction<ReferralDraft>>;
  /** The page's one create is in flight, whichever form started it. */
  adding: boolean;
  onAdd: (payload: ReferralCreate) => void;
};

function FirstReferralCard(draftProps: DraftProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Handshake className="size-4" aria-hidden="true" />
          Add your first referral
        </CardTitle>
        <CardDescription>A company where someone can refer you.</CardDescription>
      </CardHeader>
      <CardContent>
        <ReferralForm {...draftProps} />
      </CardContent>
    </Card>
  );
}

function ReferralForm({
  draft,
  onDraftChange,
  adding,
  onAdd,
  companyRef,
  inDialog = false,
}: DraftProps & {
  companyRef?: Ref<HTMLInputElement>;
  inDialog?: boolean;
}) {
  const formId = useId();
  const companyId = useId();
  const careersUrlId = useId();
  const contactId = useId();
  const notesId = useId();
  const { company, careersUrl, contactName, notes } = draft;

  const edit =
    (field: keyof ReferralDraft) =>
    (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const value = event.target.value;
      onDraftChange((prev) => ({ ...prev, [field]: value }));
    };

  const canSubmit =
    company.trim().length > 0 && careersUrl.trim().length > 0 && !adding;

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;
    onAdd({
      company: company.trim(),
      careers_url: careersUrl.trim(),
      contact_name: contactName.trim() ? contactName.trim() : null,
      notes: notes.trim() ? notes.trim() : null,
    });
  };

  const submitButton = (
    <Button
      type="submit"
      form={inDialog ? formId : undefined}
      disabled={!canSubmit}
    >
      {adding ? "Adding…" : "Add referral"}
    </Button>
  );

  return (
    <>
      <form id={formId} onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor={companyId}>Company</Label>
            <Input
              id={companyId}
              ref={companyRef}
              value={company}
              onChange={edit("company")}
              placeholder="e.g. Acme Corp"
              required
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={careersUrlId}>Careers URL</Label>
            <Input
              id={careersUrlId}
              type="url"
              value={careersUrl}
              onChange={edit("careersUrl")}
              placeholder="e.g. https://example.com/careers"
              required
            />
          </div>
          <div className="grid gap-1.5 sm:col-span-2">
            <Label htmlFor={contactId} optional>
              Contact name
            </Label>
            <Input
              id={contactId}
              value={contactName}
              onChange={edit("contactName")}
              placeholder="e.g. Jane Doe"
            />
          </div>
          <div className="grid gap-1.5 sm:col-span-2">
            <Label htmlFor={notesId} optional>
              Notes
            </Label>
            <Textarea
              id={notesId}
              rows={3}
              value={notes}
              onChange={edit("notes")}
              placeholder="e.g. Met at the AWS meetup"
            />
          </div>
        </div>
        {inDialog ? null : (
          <div className="mt-4 flex justify-end">{submitButton}</div>
        )}
      </form>
      {inDialog ? <DialogFooter>{submitButton}</DialogFooter> : null}
    </>
  );
}

function ReferralsTable({ rows }: { rows: Referral[] }) {
  // A deleted row hands focus here (the nearest container that survived it),
  // and deleting the LAST row unmounts the table for the first-referral form,
  // so the table hands it on to the main area.
  const rootRef = useRef<HTMLDivElement>(null);
  useFocusHandoff(rootRef);
  return (
    <div ref={rootRef} tabIndex={-1} className="outline-none">
      <TableFrame>
        <Table className="min-w-[48rem] table-fixed">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Company</TableHead>
              <TableHead>Careers URL</TableHead>
              <TableHead>Contact</TableHead>
              <TableHead>Notes</TableHead>
              <TableHead className="text-right">Apps</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((referral) => (
              <ReferralRow key={referral.id} referral={referral} />
            ))}
          </TableBody>
        </Table>
      </TableFrame>
    </div>
  );
}

function ReferralRow({ referral }: { referral: Referral }) {
  // Edit, Save and Cancel each unmount the row they sit in: Edit lands on
  // Company, Save and Cancel back on the row's Edit.
  const { editing, editRef, openerRef, open, close } =
    useEditToggle<HTMLTableRowElement>();

  return editing ? (
    <ReferralEditRow referral={referral} rowRef={editRef} onDone={close} />
  ) : (
    <ReferralViewRow
      referral={referral}
      editButtonRef={openerRef}
      onEdit={open}
    />
  );
}

function ReferralViewRow({
  referral,
  editButtonRef,
  onEdit,
}: {
  referral: Referral;
  editButtonRef: Ref<HTMLButtonElement>;
  onEdit: () => void;
}) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  // A delete removes this row with focus on its Delete button.
  const rowRef = useRef<HTMLTableRowElement>(null);
  useFocusHandoff(rowRef);

  const remove = useMutation({
    mutationFn: () =>
      apiFetch<void>(`/api/referrals/${referral.id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.setQueryData<Referral[]>(REFERRALS_KEY, (prev) =>
        prev ? prev.filter((r) => r.id !== referral.id) : prev,
      );
      toast.success(`Deleted referral for ${referral.company}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const onDelete = async () => {
    if (remove.isPending) return;
    const ok = await confirm({
      title: "Delete this referral?",
      description: `Referral for ${referral.company} will be removed. Applications already linked to it are unaffected.`,
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!ok) return;
    remove.mutate();
  };

  return (
    <TableRow ref={rowRef} className="group">
      <TableCell className="font-medium">
        <div className="flex items-center gap-3">
          <CompanyMonogram name={referral.company} />
          <span className="truncate">{referral.company}</span>
        </div>
      </TableCell>
      <TableCell className="max-w-[16rem] truncate" title={referral.careers_url}>
        <a
          href={referral.careers_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 underline underline-offset-2 hover:text-blue-700"
        >
          {referral.careers_url}
        </a>
      </TableCell>
      <TableCell className="text-muted-foreground">
        {referral.contact_name || "—"}
      </TableCell>
      <TableCell
        className="text-muted-foreground max-w-[14rem] truncate"
        title={referral.notes ?? undefined}
      >
        {referral.notes || "—"}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {referral.applications_count}
      </TableCell>
      <TableCell>
        <div className="flex justify-end gap-1">
          <IconButton
            ref={editButtonRef}
            label="Edit"
            icon={<Pencil />}
            onClick={onEdit}
            className="opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
          />
          <IconButton
            label="Delete referral"
            icon={<Trash2 />}
            onClick={onDelete}
            disabled={remove.isPending}
            // Disabled while the delete runs, and the confirm returns focus
            // here: a disabled <button> would drop it to <body>.
            focusableWhenDisabled
            className="opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100 data-disabled:pointer-events-none data-disabled:opacity-50"
          />
        </div>
      </TableCell>
    </TableRow>
  );
}

function ReferralEditRow({
  referral,
  rowRef,
  onDone,
}: {
  referral: Referral;
  rowRef: Ref<HTMLTableRowElement>;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [company, setCompany] = useState(referral.company);
  const [careersUrl, setCareersUrl] = useState(referral.careers_url);
  const [contactName, setContactName] = useState(referral.contact_name ?? "");
  const [notes, setNotes] = useState(referral.notes ?? "");

  const update = useMutation({
    mutationFn: (payload: ReferralPatch) =>
      apiFetch<Referral>(`/api/referrals/${referral.id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    onSuccess: (updated) => {
      qc.setQueryData<Referral[]>(REFERRALS_KEY, (prev) =>
        prev ? prev.map((r) => (r.id === updated.id ? updated : r)) : prev,
      );
      toast.success(`Updated referral for ${updated.company}`);
      onDone();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const canSave =
    company.trim().length > 0 &&
    careersUrl.trim().length > 0 &&
    !update.isPending;

  const save = () => {
    if (!canSave) return;
    const payload: ReferralPatch = {
      company: company.trim(),
      careers_url: careersUrl.trim(),
      contact_name: contactName.trim() ? contactName.trim() : null,
      notes: notes.trim() ? notes.trim() : null,
    };
    update.mutate(payload);
  };

  return (
    <TableRow ref={rowRef}>
      <TableCell>
        <Input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          aria-label="Company"
        />
      </TableCell>
      <TableCell>
        <Input
          type="url"
          value={careersUrl}
          onChange={(e) => setCareersUrl(e.target.value)}
          aria-label="Careers URL"
        />
      </TableCell>
      <TableCell>
        <Input
          value={contactName}
          onChange={(e) => setContactName(e.target.value)}
          aria-label="Contact name"
          placeholder="e.g. Jane Doe"
          // The table scrolls sideways when narrow; this keeps the example whole.
          className="min-w-32"
        />
      </TableCell>
      <TableCell>
        <Textarea
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          aria-label="Notes"
          placeholder="e.g. Met at the AWS meetup"
        />
      </TableCell>
      <TableCell className="text-right tabular-nums text-muted-foreground">
        {referral.applications_count}
      </TableCell>
      <TableCell>
        <div className="flex justify-end gap-2">
          <Button
            size="sm"
            onClick={save}
            disabled={!canSave}
            // Disables itself while saving; focus stays until the row closes.
            focusableWhenDisabled
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
          >
            {update.isPending ? "Saving…" : "Save"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onDone}
            disabled={update.isPending}
          >
            Cancel
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}
