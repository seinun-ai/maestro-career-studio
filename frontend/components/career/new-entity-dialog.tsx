"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { createKbEntity } from "@/lib/api";
import type { KBEntityKind, KBEntityStatus } from "@/lib/types";

const KINDS: { value: KBEntityKind; label: string }[] = [
  { value: "experience", label: "Experience" },
  { value: "project", label: "Project" },
  { value: "education", label: "Education" },
  { value: "certification", label: "Certification" },
];

const STATUSES: { value: KBEntityStatus; label: string }[] = [
  { value: "ongoing", label: "Ongoing" },
  { value: "completed", label: "Completed" },
  { value: "archived", label: "Archived" },
];

export function NewEntityDialog({
  open,
  onOpenChange,
  defaultKind = "experience",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultKind?: KBEntityKind;
}) {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<KBEntityKind>(defaultKind);
  const [title, setTitle] = useState("");
  const [org, setOrg] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [status, setStatus] = useState<KBEntityStatus>("ongoing");

  const reset = () => {
    setKind(defaultKind);
    setTitle("");
    setOrg("");
    setStartDate("");
    setEndDate("");
    setStatus("ongoing");
  };

  const create = useMutation({
    mutationFn: () =>
      createKbEntity({
        kind,
        title: title.trim(),
        org: org.trim() || null,
        start_date: startDate.trim() || null,
        end_date: endDate.trim() || null,
        status,
      }),
    onSuccess: (entity) => {
      toast.success(`${entity.title} added to Career KB`);
      void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
      onOpenChange(false);
      reset();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (title.trim()) create.mutate();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next && !create.isPending) reset();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New career item</DialogTitle>
          <DialogDescription>
            Add a career record manually.
          </DialogDescription>
        </DialogHeader>
        <form id="new-career-entity" className="grid gap-4" onSubmit={submit}>
          <div className="grid gap-1.5">
            <Label htmlFor="career-entity-kind">Type</Label>
            <Select
              value={kind}
              onValueChange={(value) =>
                value && setKind(value as KBEntityKind)
              }
              disabled={create.isPending}
            >
              <SelectTrigger id="career-entity-kind" className="w-full">
                <SelectValue>{KINDS.find((item) => item.value === kind)?.label}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {KINDS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="career-entity-title">Title</Label>
            <Input
              id="career-entity-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={kind === "project" ? "Project name" : "Role or title"}
              autoFocus
              required
              disabled={create.isPending}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="career-entity-org">
              Organization <span className="text-muted-foreground">· optional</span>
            </Label>
            <Input
              id="career-entity-org"
              value={org}
              onChange={(event) => setOrg(event.target.value)}
              placeholder="Company, institution, or issuer"
              disabled={create.isPending}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="career-entity-start">
                Start date <span className="text-muted-foreground">· optional</span>
              </Label>
              <Input
                id="career-entity-start"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
                placeholder="Jan 2025"
                disabled={create.isPending}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="career-entity-end">
                End date <span className="text-muted-foreground">· optional</span>
              </Label>
              <Input
                id="career-entity-end"
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
                placeholder="Present"
                disabled={create.isPending}
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="career-entity-status">Status</Label>
            <Select
              value={status}
              onValueChange={(value) =>
                value && setStatus(value as KBEntityStatus)
              }
              disabled={create.isPending}
            >
              <SelectTrigger id="career-entity-status" className="w-full">
                <SelectValue>{STATUSES.find((item) => item.value === status)?.label}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {STATUSES.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </form>
        <DialogFooter>
          <Button
            variant="outline"
            type="button"
            className="rounded-full"
            onClick={() => {
              reset();
              onOpenChange(false);
            }}
            disabled={create.isPending}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            form="new-career-entity"
            className="rounded-full px-4"
            disabled={!title.trim() || create.isPending}
          >
            {create.isPending ? "Adding…" : "Add career item"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
