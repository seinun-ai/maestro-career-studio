"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Handshake, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { CompanyMonogram } from "@/components/company-monogram";
import { EmptyState, TableFrame } from "@/components/empty-state";
import { useConfirm } from "@/components/confirm-dialog";
import { IconButton } from "@/components/icon-button";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { apiFetch } from "@/lib/api";
import type { Referral, ReferralCreate, ReferralPatch } from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";

const REFERRALS_KEY = ["referrals"] as const;

export default function ReferralsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Referrals"
        subtitle="Companies where someone can refer you."
      />
      <CreateReferralCard />
      <ReferralsTableCard />
    </PageShell>
  );
}

function CreateReferralCard() {
  const qc = useQueryClient();
  const [company, setCompany] = useState("");
  const [careersUrl, setCareersUrl] = useState("");
  const [contactName, setContactName] = useState("");
  const [notes, setNotes] = useState("");

  const reset = () => {
    setCompany("");
    setCareersUrl("");
    setContactName("");
    setNotes("");
  };

  const create = useMutation({
    mutationFn: (payload: ReferralCreate) =>
      apiFetch<Referral>("/api/referrals", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (created) => {
      qc.setQueryData<Referral[]>(REFERRALS_KEY, (prev) =>
        prev ? [created, ...prev] : [created],
      );
      toast.success(`Added referral for ${created.company}`);
      reset();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const canSubmit =
    company.trim().length > 0 && careersUrl.trim().length > 0 && !create.isPending;

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;
    const payload: ReferralCreate = {
      company: company.trim(),
      careers_url: careersUrl.trim(),
      contact_name: contactName.trim() ? contactName.trim() : null,
      notes: notes.trim() ? notes.trim() : null,
    };
    create.mutate(payload);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add referral</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="referral-company">Company</Label>
              <Input
                id="referral-company"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="Acme Corp"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="referral-careers-url">Careers URL</Label>
              <Input
                id="referral-careers-url"
                type="url"
                value={careersUrl}
                onChange={(e) => setCareersUrl(e.target.value)}
                placeholder="https://example.com/careers"
                required
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="referral-contact-name">
                Contact name{" "}
                <span className="text-muted-foreground font-normal">
                  · optional
                </span>
              </Label>
              <Input
                id="referral-contact-name"
                value={contactName}
                onChange={(e) => setContactName(e.target.value)}
                placeholder="Jane Doe"
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="referral-notes">
                Notes{" "}
                <span className="text-muted-foreground font-normal">
                  · optional
                </span>
              </Label>
              <Textarea
                id="referral-notes"
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Met at the AWS meetup"
              />
            </div>
          </div>
          <div className="flex justify-end">
            <Button type="submit" disabled={!canSubmit}>
              {create.isPending ? "Adding…" : "Add referral"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function ReferralsTableCard() {
  const referrals = useQuery({
    queryKey: REFERRALS_KEY,
    queryFn: () => apiFetch<Referral[]>("/api/referrals"),
  });

  return (
    <>
        {referrals.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : referrals.isError ? (
          <p className="text-destructive text-sm">
            Failed to load referrals: {(referrals.error as Error).message}
          </p>
        ) : !referrals.data || referrals.data.length === 0 ? (
          // Same device as Applications. This was a bare muted sentence with
          // no box and nothing to act on.
          <EmptyState
            icon={Handshake}
            title="No referrals yet"
            description="Add a company above where someone can refer you."
          />
        ) : (
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
              {referrals.data.map((referral) => (
                <ReferralRow key={referral.id} referral={referral} />
              ))}
            </TableBody>
          </Table>
          </TableFrame>
        )}
    </>
  );
}

function ReferralRow({ referral }: { referral: Referral }) {
  const [editing, setEditing] = useState(false);

  return editing ? (
    <ReferralEditRow referral={referral} onDone={() => setEditing(false)} />
  ) : (
    <ReferralViewRow referral={referral} onEdit={() => setEditing(true)} />
  );
}

function ReferralViewRow({
  referral,
  onEdit,
}: {
  referral: Referral;
  onEdit: () => void;
}) {
  const qc = useQueryClient();
  const confirm = useConfirm();

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
    <TableRow className="group">
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
            className="opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
          />
        </div>
      </TableCell>
    </TableRow>
  );
}

function ReferralEditRow({
  referral,
  onDone,
}: {
  referral: Referral;
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
    <TableRow>
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
          placeholder="Jane Doe"
        />
      </TableCell>
      <TableCell>
        <Textarea
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          aria-label="Notes"
          placeholder="Met at the AWS meetup"
        />
      </TableCell>
      <TableCell className="text-right tabular-nums text-muted-foreground">
        {referral.applications_count}
      </TableCell>
      <TableCell>
        <div className="flex justify-end gap-2">
          <Button size="sm" onClick={save} disabled={!canSave}>
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
