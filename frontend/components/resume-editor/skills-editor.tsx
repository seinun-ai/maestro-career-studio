"use client";

import { EditableCard } from "@/components/resume-editor/editable-card";
import { AddEntryButton, useEntryEditing } from "@/components/resume-editor/editor-scaffold";
import { ChipListInput } from "@/components/ui/chip-input";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SkillGroup } from "@/lib/types";

export function SkillsEditor({
  value,
  onChange,
}: {
  value: SkillGroup[];
  onChange: (next: SkillGroup[]) => void;
}) {
  const { setEditingIndex, entryEditingProps, update } = useEntryEditing(
    value,
    onChange,
    (g) => !g.category,
  );

  return (
    <div className="flex flex-col">
      {value.map((group, i) => (
        <EditableCard
          key={i}
          {...entryEditingProps(i)}
          read={
            <div className="grid grid-cols-[10rem_1fr] items-baseline gap-4 pr-16">
              <span className="text-muted-foreground text-sm font-medium">
                {group.category || (
                  <span className="italic opacity-60">Untitled</span>
                )}
              </span>
              <span className="text-foreground/90 text-sm">
                {group.items.length ? (
                  <span className="flex flex-wrap gap-1.5">
                    {group.items.map((item, idx) => (
                      <span
                        key={`${item}-${idx}`}
                        className="bg-muted text-foreground/90 inline-flex items-center rounded-md px-2 py-0.5 text-xs"
                      >
                        {item}
                      </span>
                    ))}
                  </span>
                ) : (
                  <span className="text-muted-foreground italic">No items</span>
                )}
              </span>
            </div>
          }
          edit={() => (
            <div className="grid gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor={`skill_cat_${i}`}>Category</Label>
                <Input
                  id={`skill_cat_${i}`}
                  value={group.category}
                  onChange={(e) => update(i, { category: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={`skill_items_${i}`}>Items</Label>
                <ChipListInput
                  id={`skill_items_${i}`}
                  value={group.items}
                  onChange={(items) => update(i, { items })}
                  placeholder="Add skill…"
                />
              </div>
            </div>
          )}
        />
      ))}
      <AddEntryButton
        label="Add skill group"
        onClick={() => {
          onChange([...value, { category: "", items: [] }]);
          setEditingIndex(value.length);
        }}
      />
    </div>
  );
}
