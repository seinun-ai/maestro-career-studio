"use client";

import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Code2,
  Globe2,
  Link2,
  Lock,
  Mail,
  MapPin,
  Pencil,
  Phone,
  Plus,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChipListInput } from "@/components/ui/chip-input";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useDiscardableEditor } from "@/hooks/use-confirm-discard";
import { getKbProfile, patchKbProfile } from "@/lib/api";
import { couldnt, errorDetail } from "@/lib/error-text";
import type { ContactInfo, KBProfileOut, KBProfilePatch } from "@/lib/types";

export function ProfilePanel() {
  const profile = useQuery({
    queryKey: ["kb", "profile"],
    queryFn: getKbProfile,
  });

  if (profile.isLoading) return <Skeleton className="h-72 w-full rounded-corner-md" />;
  if (profile.error) {
    return (
      <div role="alert" className="rounded-corner-md bg-destructive/10 p-5">
        <p className="text-title-small">Couldn&apos;t load your profile.</p>
        {errorDetail(profile.error) ? (
          <p className="text-muted-foreground mt-1 text-body-small">{errorDetail(profile.error)}</p>
        ) : null}
        <Button className="mt-3" size="sm" variant="tonal" onClick={() => void profile.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  if (!profile.data) return null;

  // Not keyed by updated_at: a save in one section would remount the card and close an edit open in another.
  return <ProfileView profile={profile.data} />;
}

const SECTION_HEADING = "text-muted-foreground text-title-small";

function contactDraft(profile: KBProfileOut): ContactInfo {
  return {
    name: profile.contact.name ?? "",
    email: profile.contact.email ?? "",
    phone: profile.contact.phone ?? "",
    location: profile.contact.location ?? "",
    linkedin: profile.contact.linkedin ?? "",
    github: profile.contact.github ?? "",
    website: profile.contact.website ?? "",
  };
}

function ProfileView({ profile }: { profile: KBProfileOut }) {
  const contactItems = [
    { label: "Name", value: profile.contact.name, icon: UserRound },
    { label: "Email", value: profile.contact.email, icon: Mail },
    { label: "Phone", value: profile.contact.phone, icon: Phone },
    { label: "Location", value: profile.contact.location, icon: MapPin },
    { label: "LinkedIn", value: profile.contact.linkedin, icon: Link2 },
    { label: "GitHub", value: profile.contact.github, icon: Code2 },
    { label: "Website", value: profile.contact.website, icon: Globe2 },
  ].filter((item) => item.value);

  return (
    <Card className="animate-fade-rise">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-primary">
            <UserRound className="size-4" aria-hidden="true" />
          </span>
          Career profile
        </CardTitle>
        <p className="text-muted-foreground mt-1 text-body-medium">Your contact details and skills. Resumes built from your career history start from these.</p>
      </CardHeader>
      {/* Each section edits on its own, as the resume editor's cards do: one Edit per section, always shown
          (a hover-only "Edit profile" read as a card you couldn't change). */}
      <CardContent className="divide-y divide-foreground/10">
        <ProfileSection
          title="Contact"
          className="pb-5"
          initial={() => contactDraft(profile)}
          toPatch={(contact) => ({
            contact: {
              ...contact,
              phone: contact.phone || null,
              location: contact.location || null,
              linkedin: contact.linkedin || null,
              github: contact.github || null,
              website: contact.website || null,
            },
          })}
          read={
            contactItems.length > 0 ? (
              <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                {contactItems.map(({ label, value, icon: Icon }) => (
                  <div key={label} className="flex min-w-0 items-start gap-2.5">
                    <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden="true" />
                    <div className="min-w-0">
                      <dt className="text-muted-foreground text-body-small">{label}</dt>
                      <dd className="truncate text-body-medium" title={value ?? undefined}>{value}</dd>
                    </div>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-muted-foreground text-body-medium">No contact details added.</p>
            )
          }
          edit={(contact, setContact) => {
            const update = (field: keyof ContactInfo, value: string) =>
              setContact({ ...contact, [field]: value });
            return (
              <div className="grid gap-3 sm:grid-cols-2">
                <ContactField label="Name" field="name" value={contact.name} onChange={update} autoFocus />
                <ContactField label="Email" field="email" value={contact.email} onChange={update} />
                <ContactField label="Phone" field="phone" value={contact.phone ?? ""} onChange={update} optional />
                <ContactField label="Location" field="location" value={contact.location ?? ""} onChange={update} optional />
                <ContactField label="LinkedIn" field="linkedin" value={contact.linkedin ?? ""} onChange={update} optional />
                <ContactField label="GitHub" field="github" value={contact.github ?? ""} onChange={update} optional />
                <div className="sm:col-span-2">
                  <ContactField label="Website" field="website" value={contact.website ?? ""} onChange={update} optional />
                </div>
              </div>
            );
          }}
        />

        <ProfileSection
          title="Summary"
          className="py-5"
          initial={() => profile.summary}
          toPatch={(summary) => ({ summary })}
          read={
            profile.summary.trim() ? (
              <p className="max-w-4xl text-body-medium leading-7 whitespace-pre-wrap">{profile.summary}</p>
            ) : (
              <p className="text-muted-foreground text-body-medium">No summary added.</p>
            )
          }
          edit={(summary, setSummary) => (
            <>
              <Label htmlFor="kb-profile-summary" className="sr-only">
                Summary
              </Label>
              <Textarea
                id="kb-profile-summary"
                rows={4}
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                autoFocus
              />
            </>
          )}
        />

        <ProfileSection
          title="Skills"
          className="py-5"
          initial={() => profile.skills}
          toPatch={(skills) => ({ skills: skills.filter((group) => group.category.trim()) })}
          read={
            profile.skills.length > 0 ? (
              // Each group's name over its pills, the groups flowed into balanced columns. A name beside its
              // pills gave every row the height of its longest group, so a group that wrapped to a second line
              // left a gap its neighbours didn't; stacked, a long group only makes its own block taller.
              <dl className="gap-x-8 sm:columns-2 xl:columns-3">
                {profile.skills.map((group, index) => (
                  <div key={`${group.category}-${index}`} className="mb-4 break-inside-avoid">
                    <dt className="mb-1.5 text-title-small">{group.category}</dt>
                    <dd className="flex flex-wrap gap-1.5">
                      {group.items.map((item) => (
                        <Badge key={item} variant="secondary" className="text-body-small">
                          {item}
                        </Badge>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-muted-foreground text-body-medium">No skill groups added.</p>
            )
          }
          edit={(skills, setSkills) => (
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-muted-foreground text-body-small">Group your skills. You can add a group to any resume.</p>
                <Button
                  type="button"
                  size="sm"
                  variant="tonal"
                  onClick={() => setSkills([...skills, { category: "", items: [] }])}
                >
                  <Plus aria-hidden="true" /> Add group
                </Button>
              </div>
              {skills.length === 0 ? (
                <p className="text-muted-foreground rounded-corner-md bg-surface-container-low p-4 text-center text-body-small">No skill groups yet.</p>
              ) : (
                skills.map((group, index) => (
                  <div key={index} className="grid gap-2 rounded-corner-md bg-surface-container-low p-3 sm:grid-cols-[12rem_1fr_auto] sm:items-start">
                    <div className="grid gap-1.5">
                      <Label htmlFor={`kb-skill-category-${index}`}>Group name</Label>
                      <Input
                        id={`kb-skill-category-${index}`}
                        value={group.category}
                        autoFocus={index === 0}
                        onChange={(event) =>
                          setSkills(skills.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, category: event.target.value } : item,
                          ))
                        }
                      />
                    </div>
                    <div className="grid gap-1.5">
                      <Label htmlFor={`kb-skill-items-${index}`}>Skills</Label>
                      <ChipListInput
                        id={`kb-skill-items-${index}`}
                        value={group.items}
                        onChange={(items) =>
                          setSkills(skills.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, items } : item,
                          ))
                        }
                        placeholder="Add skills…"
                      />
                    </div>
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      className="sm:mt-6"
                      aria-label={`Remove ${group.category || "skill"} group`}
                      onClick={() => setSkills(skills.filter((_, itemIndex) => itemIndex !== index))}
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          )}
        />

        <ProfileSection
          title="Notes for the AI"
          icon={<Lock className="size-3" aria-hidden="true" />}
          className="pt-5"
          initial={() => profile.notes}
          toPatch={(notes) => ({ notes })}
          read={<FoldedNotes notes={profile.notes} />}
          edit={(notes, setNotes) => (
            <div className="grid gap-1.5">
              <Label htmlFor="kb-profile-notes" className="sr-only">
                Notes for the AI
              </Label>
              <p id="kb-profile-notes-hint" className="text-muted-foreground text-body-small">
                Only you and the AI see these, such as visa timing or where you can work. Details about one job or project go in that item&apos;s own notes.
              </p>
              <Textarea
                aria-describedby="kb-profile-notes-hint"
                id="kb-profile-notes"
                rows={8}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                autoFocus
              />
            </div>
          )}
        />
      </CardContent>
    </Card>
  );
}

/**
 * One section of the profile: its read view with an Edit button, or its own small form. A save sends this
 * section's field alone (PATCH /api/kb/profile leaves omitted fields as they are). Cancel and Escape ask
 * before dropping typed changes, and closing returns focus to Edit (`useDiscardableEditor`).
 */
function ProfileSection<T>({
  title,
  icon,
  className,
  initial,
  toPatch,
  read,
  edit,
}: {
  title: string;
  icon?: ReactNode;
  className?: string;
  initial: () => T;
  toPatch: (draft: T) => KBProfilePatch;
  read: ReactNode;
  edit: (draft: T, setDraft: (next: T) => void) => ReactNode;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<T | null>(null);
  const editing = draft !== null;
  const close = () => setDraft(null);

  const save = useMutation({
    mutationFn: (value: T) => patchKbProfile(toPatch(value)),
    onSuccess: (updated) => {
      queryClient.setQueryData(["kb", "profile"], updated);
      close();
      toast.success(`${title} saved`);
    },
    onError: (error: Error) => toast.error(couldnt(`save your ${title.toLowerCase()}`, error)),
  });

  const { editRef, onCancel, onKeyDown, onSave } = useDiscardableEditor({
    editing,
    // Compared as JSON: the drafts are plain data (strings, the contact record, skill groups).
    changed: editing && JSON.stringify(draft) !== JSON.stringify(initial()),
    close,
    busy: save.isPending,
  });

  return (
    <section className={className}>
      <div className="mb-3 flex min-h-8 items-center justify-between gap-2">
        <h3 className={`${SECTION_HEADING} flex items-center gap-1.5`}>
          {title}
          {icon}
        </h3>
        {!editing ? (
          <Button
            ref={editRef}
            size="sm"
            variant="ghost"
            className="text-muted-foreground"
            aria-label={`Edit ${title.toLowerCase()}`}
            onClick={() => setDraft(initial())}
          >
            <Pencil aria-hidden="true" /> Edit
          </Button>
        ) : null}
      </div>
      {editing ? (
        <form
          className="space-y-4"
          onKeyDown={onKeyDown}
          onSubmit={(event) => {
            event.preventDefault();
            onSave(() => save.mutate(draft));
          }}
        >
          {edit(draft, setDraft)}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => void onCancel()}
              disabled={save.isPending}
            >
              <X aria-hidden="true" /> Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              className="px-4 data-disabled:pointer-events-none data-disabled:opacity-50"
              disabled={save.isPending}
              focusableWhenDisabled
            >
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      ) : (
        read
      )}
    </section>
  );
}

/** How many of the notes' lines show before "Show all notes". */
const FOLDED_LINES = 2;

/** The profile's notes, folded to their first lines: they are for the AI, and ran the length of the page. */
function FoldedNotes({ notes }: { notes: string }) {
  const [open, setOpen] = useState(false);
  // Blank lines between the notes' own lines are spacing, not content: they neither show nor count.
  const lines = notes.split("\n").filter((line) => line.trim());
  if (lines.length === 0) return <p className="text-muted-foreground text-body-medium">No notes yet.</p>;
  const folds = lines.length > FOLDED_LINES;
  const shown = open || !folds ? lines : lines.slice(0, FOLDED_LINES);
  return (
    <div className="max-w-4xl space-y-1.5">
      <ul id="kb-profile-notes-read" className="space-y-1 text-body-medium">
        {shown.map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>
      {folds ? (
        <Button
          size="sm"
          variant="link"
          className="h-auto px-0"
          aria-expanded={open}
          aria-controls="kb-profile-notes-read"
          onClick={() => setOpen((current) => !current)}
        >
          {open ? "Show less" : `Show all ${lines.length} notes`}
        </Button>
      ) : null}
    </div>
  );
}

function ContactField({
  label,
  field,
  value,
  onChange,
  optional = false,
  autoFocus = false,
}: {
  label: string;
  field: keyof ContactInfo;
  value: string;
  onChange: (field: keyof ContactInfo, value: string) => void;
  optional?: boolean;
  autoFocus?: boolean;
}) {
  const id = `kb-profile-${field}`;
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} optional={optional}>
        {label}
      </Label>
      <Input id={id} value={value} onChange={(event) => onChange(field, event.target.value)} autoFocus={autoFocus} />
    </div>
  );
}
