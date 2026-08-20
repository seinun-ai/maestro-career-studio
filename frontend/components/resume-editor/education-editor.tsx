"use client";

import { Trash2 } from "lucide-react";

import { BulletList } from "@/components/resume-editor/bullet-list";
import { EditableCard } from "@/components/resume-editor/editable-card";
import { AddEntryButton, useEntryEditing } from "@/components/resume-editor/editor-scaffold";
import { Button } from "@/components/ui/button";
import { ChipListInput } from "@/components/ui/chip-input";
import { Label } from "@/components/ui/label";
import type { EducationEntry } from "@/lib/types";
import { Field } from "@/components/resume-editor/field";

const EMPTY: EducationEntry = {
  institution: "",
  degree: "",
  field: "",
  location: "",
  start_date: "",
  end_date: "",
  graduation_date: "",
  gpa: "",
  coursework: [],
  bullets: [],
};

export function EducationEditor({
  value,
  onChange,
}: {
  value: EducationEntry[];
  onChange: (next: EducationEntry[]) => void;
}) {
  const { setEditingIndex, entryEditingProps, update } = useEntryEditing(
    value,
    onChange,
    (e) => !e.institution && !e.degree,
  );

  return (
    <div className="flex flex-col gap-2">
      {value.map((entry, i) => {
        const title = [entry.degree, entry.field].filter(Boolean).join(" · ");
        const dateLine = entry.graduation_date
          ? entry.graduation_date
          : [entry.start_date, entry.end_date].filter(Boolean).join(" – ");
        const subLine = [entry.location, entry.gpa ? `GPA: ${entry.gpa}` : null]
          .filter(Boolean)
          .join(" · ");
        return (
          <EditableCard
            key={i}
            {...entryEditingProps(i)}
            read={
              <div className="flex flex-col gap-2 pr-16">
                <div className="flex items-baseline justify-between gap-4">
                  <div className="text-foreground text-sm font-semibold">
                    {title || (
                      <em className="opacity-60">Untitled degree</em>
                    )}
                    {entry.institution && (
                      <>
                        {" · "}
                        <span className="font-medium">{entry.institution}</span>
                      </>
                    )}
                  </div>
                  <div className="text-muted-foreground text-xs whitespace-nowrap">
                    {dateLine || "—"}
                  </div>
                </div>
                {subLine && (
                  <div className="text-muted-foreground text-xs">{subLine}</div>
                )}
                {entry.coursework.length > 0 && (
                  <div className="text-foreground/90 text-sm">
                    <span className="text-muted-foreground">Coursework: </span>
                    {entry.coursework.join(" · ")}
                  </div>
                )}
                {entry.bullets.length > 0 && (
                  <ul className="text-foreground/90 ml-4 list-disc space-y-1 text-sm">
                    {entry.bullets.map((b, bi) => (
                      <li key={bi}>{b}</li>
                    ))}
                  </ul>
                )}
              </div>
            }
            edit={() => (
              <div className="grid gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <Field
                    label="Institution"
                    value={entry.institution}
                    onChange={(v) => update(i, { institution: v })}
                  />
                  <Field
                    label="Degree"
                    value={entry.degree ?? ""}
                    onChange={(v) => update(i, { degree: v })}
                  />
                  <Field
                    label="Field"
                    value={entry.field ?? ""}
                    onChange={(v) => update(i, { field: v })}
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
                  />
                  <Field
                    label="End date"
                    value={entry.end_date ?? ""}
                    onChange={(v) => update(i, { end_date: v })}
                  />
                  <Field
                    label="Graduation"
                    value={entry.graduation_date ?? ""}
                    onChange={(v) => update(i, { graduation_date: v })}
                  />
                  <Field
                    label="GPA"
                    value={entry.gpa ?? ""}
                    onChange={(v) => update(i, { gpa: v })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <div className="flex items-center justify-between">
                    <Label htmlFor={`edu_coursework_${i}`}>Coursework</Label>
                    {entry.coursework.length > 0 && (
                      <Button
                        type="button"
                        size="icon-sm"
                        variant="ghost"
                        aria-label="Delete coursework"
                        onClick={() => update(i, { coursework: [] })}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    )}
                  </div>
                  <ChipListInput
                    id={`edu_coursework_${i}`}
                    value={entry.coursework}
                    onChange={(coursework) => update(i, { coursework })}
                    placeholder="Add course…"
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
        label="Add education"
        onClick={() => {
          onChange([...value, EMPTY]);
          setEditingIndex(value.length);
        }}
      />
    </div>
  );
}

