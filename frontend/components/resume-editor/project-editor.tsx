import { useId, useState } from "react";
import { Share2 } from "lucide-react";

import { BulletList } from "@/components/resume-editor/bullet-list";
import { EditableCard } from "@/components/resume-editor/editable-card";
import {
  ActiveArchivedCount,
  AddEntryButton,
  useEntryEditing,
  createEnableAction,
  isEntryEnabled,
} from "@/components/resume-editor/editor-scaffold";
import { ProjectPortDialog } from "@/components/resume-editor/project-port-dialog";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ProjectEntry } from "@/lib/types";

const EMPTY: ProjectEntry = {
  name: "",
  enabled: true,
  tech: "",
  link: "",
  date: "",
  bullets: [],
};

export function ProjectEditor({
  value,
  onChange,
  sourceSlug,
}: {
  value: ProjectEntry[];
  onChange: (next: ProjectEntry[]) => void;
  /** When set (base resume editor), each project can be ported to another base resume. */
  sourceSlug?: string;
  /** Location keys of the recruiter/ATS "hot zone" (from lib/health-zones). */
}) {
  const [portIndex, setPortIndex] = useState<number | null>(null);

  const { setEditingIndex, entryEditingProps, update } = useEntryEditing(
    value,
    onChange,
    (e) => !e.name,
  );

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <ActiveArchivedCount items={value} />
      </div>

      {value.map((entry, i) => {
        const enabled = isEntryEnabled(entry);
        return (
          <EditableCard
            key={i}
            muted={!enabled}
            {...entryEditingProps(i)}
            extraActions={[
              createEnableAction(enabled, () => update(i, { enabled: !enabled })),
              ...(sourceSlug
                ? [
                    {
                      label: "Port to another base resume",
                      icon: <Share2 className="size-3.5" />,
                      onClick: () => setPortIndex(i),
                    },
                  ]
                : []),
            ]}
            read={
              <div className="flex flex-col gap-2 pr-16">
                <div className="flex items-baseline justify-between gap-4">
                  <div className="flex items-center gap-2">
                    <span className="text-foreground text-sm font-semibold">
                      {entry.name || (
                        <em className="opacity-60">Untitled project</em>
                      )}
                    </span>
                    {!enabled && (
                      <Badge variant="secondary" className="text-xs">
                        Archived
                      </Badge>
                    )}
                  </div>
                  <div className="text-muted-foreground text-xs whitespace-nowrap">
                    {entry.date || "—"}
                  </div>
                </div>
                {entry.tech && (
                  <div className="text-muted-foreground text-xs">
                    {entry.tech}
                  </div>
                )}
                {entry.bullets.length > 0 ? (
                  <ul className="text-foreground/90 ml-4 list-disc space-y-1 text-sm">
                    {entry.bullets.map((b, bi) => (
                      <li
                        key={bi}
                        className="rounded-sm"
                      >
                        {b}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground text-xs italic">
                    No bullets
                  </p>
                )}
              </div>
            }
            edit={() => (
              <div className="grid gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <ProjField
                    label="Name"
                    value={entry.name}
                    onChange={(v) => update(i, { name: v })}
                  />
                  <ProjField
                    label="Tech"
                    value={entry.tech ?? ""}
                    onChange={(v) => update(i, { tech: v })}
                  />
                  <ProjField
                    label="Link"
                    value={entry.link ?? ""}
                    onChange={(v) => update(i, { link: v })}
                  />
                  <ProjField
                    label="Date"
                    value={entry.date ?? ""}
                    onChange={(v) => update(i, { date: v })}
                  />
                </div>
                <BulletList
                  value={entry.bullets}
                  onChange={(bullets) => update(i, { bullets })}
                />
              </div>
            )}
          />
        );
      })}
      <AddEntryButton
        label="Add project"
        onClick={() => {
          onChange([...value, EMPTY]);
          setEditingIndex(value.length);
        }}
      />

      {sourceSlug && portIndex !== null && (
        <ProjectPortDialog
          open
          onOpenChange={(open) => !open && setPortIndex(null)}
          sourceSlug={sourceSlug}
          projectIndex={portIndex}
          projectName={value[portIndex]?.name ?? ""}
        />
      )}
    </div>
  );
}

function ProjField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  // Per-instance id — several project cards can be in edit mode at once, and
  // `proj_${label}` gave every one of them the same id. See field.tsx.
  const id = useId();
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
