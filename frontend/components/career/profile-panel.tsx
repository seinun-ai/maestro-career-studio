"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Code2,
  Globe2,
  Link2,
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
import { getKbProfile, patchKbProfile } from "@/lib/api";
import type { ContactInfo, KBProfileOut, SkillGroup } from "@/lib/types";

export function ProfilePanel() {
  const profile = useQuery({
    queryKey: ["kb", "profile"],
    queryFn: getKbProfile,
  });

  if (profile.isLoading) return <Skeleton className="h-72 w-full rounded-2xl" />;
  if (profile.error) {
    return (
      <div role="alert" className="rounded-2xl bg-destructive/10 p-5">
        <p className="text-sm font-medium">Couldn&apos;t load your KB profile.</p>
        <p className="text-muted-foreground mt-1 text-xs">{profile.error.message}</p>
        <Button className="mt-3 rounded-full" size="sm" variant="secondary" onClick={() => void profile.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  if (!profile.data) return null;

  return <ProfileView key={profile.data.updated_at} profile={profile.data} />;
}

function ProfileView({ profile }: { profile: KBProfileOut }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [summary, setSummary] = useState(profile.summary);
  const [notes, setNotes] = useState(profile.notes);
  const [contact, setContact] = useState<ContactInfo>({
    name: profile.contact.name ?? "",
    email: profile.contact.email ?? "",
    phone: profile.contact.phone ?? "",
    location: profile.contact.location ?? "",
    linkedin: profile.contact.linkedin ?? "",
    github: profile.contact.github ?? "",
    website: profile.contact.website ?? "",
  });
  const [skills, setSkills] = useState<SkillGroup[]>(profile.skills);

  const reset = () => {
    setSummary(profile.summary);
    setNotes(profile.notes);
    setContact({
      name: profile.contact.name ?? "",
      email: profile.contact.email ?? "",
      phone: profile.contact.phone ?? "",
      location: profile.contact.location ?? "",
      linkedin: profile.contact.linkedin ?? "",
      github: profile.contact.github ?? "",
      website: profile.contact.website ?? "",
    });
    setSkills(profile.skills);
    setEditing(false);
  };

  const save = useMutation({
    mutationFn: () =>
      patchKbProfile({
        contact: {
          ...contact,
          phone: contact.phone || null,
          location: contact.location || null,
          linkedin: contact.linkedin || null,
          github: contact.github || null,
          website: contact.website || null,
        },
        summary,
        notes,
        skills: skills.filter((group) => group.category.trim()),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["kb", "profile"], updated);
      setEditing(false);
      toast.success("Career profile saved");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const updateContact = (field: keyof ContactInfo, value: string) =>
    setContact((current) => ({ ...current, [field]: value }));

  if (editing) {
    return (
      <Card className="animate-fade-rise rounded-2xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-primary">
              <UserRound className="size-4" aria-hidden="true" />
            </span>
            Edit career profile
          </CardTitle>
          <p className="text-muted-foreground text-sm">Shared identity, skills, and generation context.</p>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-6"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate();
            }}
          >
            <section className="rounded-xl bg-muted/35 p-4">
              <h3 className="mb-3 text-sm font-semibold">Contact</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <ContactField label="Name" field="name" value={contact.name} onChange={updateContact} autoFocus />
                <ContactField label="Email" field="email" value={contact.email} onChange={updateContact} />
                <ContactField label="Phone" field="phone" value={contact.phone ?? ""} onChange={updateContact} optional />
                <ContactField label="Location" field="location" value={contact.location ?? ""} onChange={updateContact} optional />
                <ContactField label="LinkedIn" field="linkedin" value={contact.linkedin ?? ""} onChange={updateContact} optional />
                <ContactField label="GitHub" field="github" value={contact.github ?? ""} onChange={updateContact} optional />
                <div className="sm:col-span-2">
                  <ContactField label="Website" field="website" value={contact.website ?? ""} onChange={updateContact} optional />
                </div>
              </div>
            </section>

            <div className="grid gap-1.5">
              <Label htmlFor="kb-profile-summary">
                Summary <span className="text-muted-foreground">· optional</span>
              </Label>
              <Textarea id="kb-profile-summary" rows={4} value={summary} onChange={(event) => setSummary(event.target.value)} />
            </div>

            <section className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <Label>Skill inventory</Label>
                  <p className="text-muted-foreground text-xs">Named groups can be merged into base resumes.</p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="rounded-full"
                  onClick={() => setSkills((current) => [...current, { category: "", items: [] }])}
                >
                  <Plus aria-hidden="true" /> Add group
                </Button>
              </div>
              {skills.length === 0 ? (
                <p className="text-muted-foreground rounded-xl bg-muted/45 p-4 text-center text-xs">No skill groups yet.</p>
              ) : (
                skills.map((group, index) => (
                  <div key={index} className="grid gap-2 rounded-xl bg-muted/35 p-3 sm:grid-cols-[12rem_1fr_auto] sm:items-start">
                    <div className="grid gap-1.5">
                      <Label htmlFor={`kb-skill-category-${index}`}>Category</Label>
                      <Input
                        id={`kb-skill-category-${index}`}
                        value={group.category}
                        onChange={(event) =>
                          setSkills((current) => current.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, category: event.target.value } : item,
                          ))
                        }
                        placeholder="ML Ops"
                      />
                    </div>
                    <div className="grid gap-1.5">
                      <Label htmlFor={`kb-skill-items-${index}`}>Skills</Label>
                      <ChipListInput
                        id={`kb-skill-items-${index}`}
                        value={group.items}
                        onChange={(items) =>
                          setSkills((current) => current.map((item, itemIndex) =>
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
                      onClick={() => setSkills((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  </div>
                ))
              )}
            </section>

            <div className="grid gap-1.5">
              <Label htmlFor="kb-profile-notes">
                Identity notes <span className="text-muted-foreground">· optional</span>
              </Label>
              <Textarea
                id="kb-profile-notes"
                rows={5}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Visa timeline, target roles, location constraints, and other private context…"
              />
            </div>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" className="rounded-full" onClick={reset} disabled={save.isPending}>
                <X aria-hidden="true" /> Cancel
              </Button>
              <Button type="submit" className="rounded-full px-4" disabled={save.isPending}>
                {save.isPending ? "Saving…" : "Save profile"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    );
  }

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
    <Card className="group/profile animate-fade-rise rounded-2xl">
      <CardHeader className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-primary">
              <UserRound className="size-4" aria-hidden="true" />
            </span>
            Career profile
          </CardTitle>
          <p className="text-muted-foreground mt-1 text-sm">Shared identity, skills, and generation context.</p>
        </div>
        <Button
          size="sm"
          variant="ghost"
          className="rounded-full opacity-0 transition-opacity duration-150 group-hover/profile:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
          onClick={() => setEditing(true)}
        >
          <Pencil aria-hidden="true" /> Edit profile
        </Button>
      </CardHeader>
      <CardContent className="divide-y divide-foreground/10">
        <section className="pb-5">
          <h3 className="text-muted-foreground mb-3 text-xs font-semibold uppercase tracking-[0.12em]">Contact</h3>
          {contactItems.length > 0 ? (
            <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
              {contactItems.map(({ label, value, icon: Icon }) => (
                <div key={label} className="flex min-w-0 items-start gap-2.5">
                  <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden="true" />
                  <div className="min-w-0">
                    <dt className="text-muted-foreground text-xs">{label}</dt>
                    <dd className="truncate text-sm" title={value ?? undefined}>{value}</dd>
                  </div>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-muted-foreground text-sm">No contact details added.</p>
          )}
        </section>

        <section className="py-5">
          <h3 className="text-muted-foreground mb-2 text-xs font-semibold uppercase tracking-[0.12em]">Summary</h3>
          {profile.summary.trim() ? (
            <p className="max-w-4xl text-sm leading-7 whitespace-pre-wrap">{profile.summary}</p>
          ) : (
            <p className="text-muted-foreground text-sm">No summary added.</p>
          )}
        </section>

        <section className="py-5">
          <h3 className="text-muted-foreground mb-3 text-xs font-semibold uppercase tracking-[0.12em]">Skills</h3>
          {profile.skills.length > 0 ? (
            // A definition list on a two-column grid, not a flex row.
            //
            // The old row was `flex flex-wrap` around a fixed-width label and a
            // nested wrapping pill group, so a group whose pills were wider than
            // the remaining space dropped BELOW its label while narrower groups
            // stayed inline. With twenty-odd groups that read as one ragged wall
            // rather than a list. A grid gives every category the same column,
            // so the eye has a single left edge to scan, and the rules between
            // rows say where one group ends.
            <dl className="divide-border/60 divide-y">
              {profile.skills.map((group, index) => (
                <div
                  key={`${group.category}-${index}`}
                  className="grid gap-x-4 gap-y-1.5 py-2.5 sm:grid-cols-[11rem_1fr]"
                >
                  <dt className="text-sm font-medium">{group.category}</dt>
                  <dd className="flex flex-wrap gap-1.5">
                    {group.items.map((item) => (
                      <Badge key={item} variant="secondary" className="rounded-full font-normal">
                        {item}
                      </Badge>
                    ))}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-muted-foreground text-sm">No skill groups added.</p>
          )}
        </section>

        <section className="pt-5">
          <h3 className="text-muted-foreground mb-2 text-xs font-semibold uppercase tracking-[0.12em]">Identity notes</h3>
          {profile.notes.trim() ? (
            <p className="max-w-4xl text-sm leading-7 whitespace-pre-wrap">{profile.notes}</p>
          ) : (
            <p className="text-muted-foreground text-sm">No private identity notes added.</p>
          )}
        </section>
      </CardContent>
    </Card>
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
      <Label htmlFor={id}>
        {label} {optional ? <span className="text-muted-foreground">· optional</span> : null}
      </Label>
      <Input id={id} value={value} onChange={(event) => onChange(field, event.target.value)} autoFocus={autoFocus} />
    </div>
  );
}
