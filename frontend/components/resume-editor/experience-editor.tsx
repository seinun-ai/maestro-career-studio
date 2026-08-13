import { BulletList } from "@/components/resume-editor/bullet-list";
import { EditableCard } from "@/components/resume-editor/editable-card";
import {
  ActiveArchivedCount,
  AddEntryButton,
  cardReorderProps,
  createEnableAction,
  isEntryEnabled,
} from "@/components/resume-editor/editor-scaffold";
import { Badge } from "@/components/ui/badge";
import type { ExperienceEntry } from "@/lib/types";
import { Field } from "@/components/resume-editor/field";

const EMPTY: ExperienceEntry = {
  company: "",
  role: "",
  location: "",
  start_date: "",
  end_date: "",
  enabled: true,
  bullets: [],
};

export function ExperienceEditor({
  value,
  onChange,
}: {
  value: ExperienceEntry[];
  onChange: (next: ExperienceEntry[]) => void;
  /** Location keys of the recruiter/ATS "hot zone" (from lib/health-zones). */
}) {
  const update = (i: number, patch: Partial<ExperienceEntry>) =>
    onChange(value.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));

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
            initialEditing={!entry.company && !entry.role}
            {...cardReorderProps(value, i, onChange)}
            extraActions={[
              createEnableAction(enabled, () => update(i, { enabled: !enabled })),
            ]}
            read={
              <div className="flex flex-col gap-2 pr-16">
                <div className="flex items-baseline justify-between gap-4">
                  <div className="text-foreground flex items-center gap-2 text-sm font-semibold">
                    <span>
                      {entry.role || (
                        <em className="opacity-60">Untitled role</em>
                      )}
                      {entry.company && (
                        <>
                          {" · "}
                          <span className="font-medium">{entry.company}</span>
                        </>
                      )}
                    </span>
                    {!enabled && (
                      <Badge variant="secondary" className="text-xs">
                        Archived
                      </Badge>
                    )}
                  </div>
                  <div className="text-muted-foreground text-xs whitespace-nowrap">
                    {[entry.start_date, entry.end_date || "Present"]
                      .filter(Boolean)
                      .join(" – ") || "—"}
                  </div>
                </div>
                {entry.location && (
                  <div className="text-muted-foreground text-xs">
                    {entry.location}
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
                  <Field
                    label="Company"
                    value={entry.company}
                    onChange={(v) => update(i, { company: v })}
                  />
                  <Field
                    label="Role"
                    value={entry.role}
                    onChange={(v) => update(i, { role: v })}
                  />
                  <Field
                    label="Location"
                    value={entry.location ?? ""}
                    onChange={(v) => update(i, { location: v })}
                  />
                  <Field
                    label="Start date"
                    value={entry.start_date ?? ""}
                    onChange={(v) => update(i, { start_date: v })}
                    placeholder="Jan 2023"
                  />
                  <Field
                    label="End date"
                    value={entry.end_date ?? ""}
                    onChange={(v) => update(i, { end_date: v })}
                    placeholder="Present"
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
        label="Add experience"
        onClick={() => onChange([...value, EMPTY])}
      />
    </div>
  );
}

