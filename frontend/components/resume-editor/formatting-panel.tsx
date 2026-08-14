"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import {
  ChevronDown,
  ChevronUp,
  RotateCcw,
  SlidersHorizontal,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  BULLET_ICON_OPTIONS,
  DATE_FORMAT_OPTIONS,
  EDUCATION_ORDER_OPTIONS,
  FONT_SIZE_OPTIONS,
  FORMATTING_DEFAULTS,
  HEADER_ALIGN_OPTIONS,
  SECTION_ORDER_FALLBACK,
  SECTION_ORDER_LABELS,
  SKILLS_LAYOUT_OPTIONS,
  SLIDER_RANGES,
  diffFrom,
  type ResumeFormatting,
  type SectionKey,
} from "@/lib/formatting";
import { cn, move } from "@/lib/utils";

const UNSUPPORTED = "Selected template doesn't support this";

/**
 * Jobright-style collapsible formatting controls rendered inside the preview
 * pane. Edits are stored as the *diff from defaults* (`onChange(null)` when the
 * resume falls back to the plain Classic look), so an untouched resume keeps a
 * null `formatting` and inherits/merges correctly on the backend.
 *
 * `supportedKeys` (from the selected template's `supported_fmt_keys`) greys out
 * any knob the template doesn't consume. In the studio, `inherited` +
 * `onRevertToBase` surface the base-resume override relationship, and `baseline`
 * carries the inherited layer (defaults merged with the base resume's
 * formatting) so the controls show the *effective* values and edits store only
 * genuine overrides of what is inherited.
 */
export function FormattingPanel({
  value,
  onChange,
  supportedKeys,
  inherited,
  onRevertToBase,
  baseline = FORMATTING_DEFAULTS,
  defaultOpen = false,
  collapsible = true,
}: {
  value: Partial<ResumeFormatting> | null;
  onChange: (next: Partial<ResumeFormatting> | null) => void;
  supportedKeys?: string[];
  inherited?: boolean;
  onRevertToBase?: () => void;
  baseline?: ResumeFormatting;
  defaultOpen?: boolean;
  collapsible?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen || !collapsible);
  // Namespaces this panel's label ids — the studio renders it beside another
  // copy in the base-resume editor, so bare `${key}-label` would collide.
  const uid = useId();
  // Drag source index for the section-order list (chip-input's drag pattern).
  const sectionDragFrom = useRef<number | null>(null);

  const effective: ResumeFormatting = { ...baseline, ...(value ?? {}) };
  const customized = value != null && Object.keys(value).length > 0;

  function setKey<K extends keyof ResumeFormatting>(
    key: K,
    next: ResumeFormatting[K],
  ) {
    onChange(diffFrom(baseline, { ...effective, [key]: next }));
  }

  const isDisabled = (key: keyof ResumeFormatting) =>
    supportedKeys ? !supportedKeys.includes(key) : false;

  // Wrap a disabled control so hovering it explains why it's greyed out.
  const withTooltip = (disabled: boolean, control: ReactNode) =>
    disabled ? (
      <Tooltip>
        <TooltipTrigger render={<span className="inline-flex">{control}</span>} />
        <TooltipContent side="left">{UNSUPPORTED}</TooltipContent>
      </Tooltip>
    ) : (
      control
    );

  // Every row's visible text IS the control's accessible name, wired by id.
  // The controls here are a Switch, a Slider and a Select — all of them render
  // as buttons or as a widget with no <input> to wrap, so a plain adjacent
  // <span> (what this used to be) left them announced as "switch, not checked"
  // with no name at all. Passing the label's id down means the string is
  // written once and cannot drift from what is on screen.
  const rowLabelId = (key: keyof ResumeFormatting) => `${uid}-${key}-label`;

  const choiceRow = (
    key: keyof ResumeFormatting,
    label: string,
    control: (labelId: string) => ReactNode,
  ) => {
    const disabled = isDisabled(key);
    const labelId = rowLabelId(key);
    return (
      <div className="flex items-center justify-between gap-3 py-1">
        <span
          id={labelId}
          className={cn("text-sm", disabled && "text-muted-foreground/60")}
        >
          {label}
        </span>
        {withTooltip(disabled, control(labelId))}
      </div>
    );
  };

  const segmented = <T extends string | number>(
    key: keyof ResumeFormatting,
    labelId: string,
    current: T,
    options: readonly { value: T; label: string }[],
    onSelect: (v: T) => void,
  ) => {
    const disabled = isDisabled(key);
    return (
      <div
        role="group"
        aria-labelledby={labelId}
        className="border-input inline-flex rounded-md border p-0.5"
      >
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(o.value)}
            className={cn(
              "rounded px-2 py-0.5 text-xs transition-colors disabled:pointer-events-none disabled:opacity-50",
              current === o.value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    );
  };

  const sliderRow = (
    key: keyof typeof SLIDER_RANGES,
    label: string,
    display: (n: number) => string,
  ) => {
    const disabled = isDisabled(key);
    const range = SLIDER_RANGES[key];
    const current = effective[key];
    const labelId = rowLabelId(key);
    return (
      <div className={cn("grid gap-1", disabled && "opacity-50")}>
        <div className="flex items-center justify-between">
          <span id={labelId} className="text-sm">
            {label}
          </span>
          <span className="text-muted-foreground text-xs tabular-nums">
            {display(current)}
          </span>
        </div>
        {withTooltip(
          disabled,
          <Slider
            aria-labelledby={labelId}
            className={disabled ? "pointer-events-none" : undefined}
            disabled={disabled}
            value={current}
            min={range.min}
            max={range.max}
            step={range.step}
            onValueChange={(v) =>
              setKey(
                key,
                (Array.isArray(v) ? v[0] : v) as ResumeFormatting[typeof key],
              )
            }
          />,
        )}
      </div>
    );
  };

  // A fourth control shape: an ordered list, reordered with up/down buttons
  // rather than drag-and-drop (no new dependency, and it is keyboard-reachable
  // by construction). `null` means "the template's own order", so the rows show
  // the inherited order and the first move stores the whole explicit list —
  // there is no half-specified state to reason about.
  const sectionOrderRow = () => {
    const key: keyof ResumeFormatting = "section_order";
    const disabled = isDisabled(key);
    const labelId = rowLabelId(key);
    const order: SectionKey[] = effective.section_order ?? SECTION_ORDER_FALLBACK;
    return (
      <div className={cn("grid gap-1", disabled && "opacity-50")}>
        <span id={labelId} className="text-sm">
          Section order
        </span>
        {withTooltip(
          disabled,
          <ul className="border-input grid gap-0.5 rounded-md border p-1">
            {order.map((section, index) => (
              <li
                key={section}
                draggable={!disabled}
                onDragStart={() => (sectionDragFrom.current = index)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const from = sectionDragFrom.current;
                  sectionDragFrom.current = null;
                  if (from !== null && from !== index) {
                    setKey(key, move(order, from, index));
                  }
                }}
                className={cn(
                  "flex items-center justify-between gap-2 rounded px-1.5 py-0.5 text-xs",
                  !disabled && "cursor-grab active:cursor-grabbing",
                )}
              >
                <span className="min-w-0 truncate">
                  {SECTION_ORDER_LABELS[section] ?? section}
                </span>
                <span className="flex shrink-0 items-center">
                  {(
                    [
                      ["up", ChevronUp, index - 1, index > 0],
                      ["down", ChevronDown, index + 1, index < order.length - 1],
                    ] as const
                  ).map(([direction, Icon, target, enabled]) => (
                    <button
                      key={direction}
                      type="button"
                      disabled={disabled || !enabled}
                      aria-label={`Move ${
                        SECTION_ORDER_LABELS[section] ?? section
                      } ${direction}`}
                      onClick={() => setKey(key, move(order, index, target))}
                      className="text-muted-foreground hover:text-foreground rounded p-0.5 transition-colors disabled:pointer-events-none disabled:opacity-30"
                    >
                      <Icon className="size-3.5" />
                    </button>
                  ))}
                </span>
              </li>
            ))}
          </ul>,
        )}
      </div>
    );
  };

  const showContent = collapsible ? open : true;

  return (
    <div className={cn("bg-background/60 shrink-0", collapsible && "border-b")}>
      {collapsible && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="hover:bg-muted/50 flex w-full items-center justify-between px-3 py-2 text-sm font-medium transition-colors"
        >
          <span className="flex items-center gap-2">
            <SlidersHorizontal className="size-3.5" />
            Formatting
            {customized && (
              <span className="bg-primary/10 text-primary rounded-full px-1.5 py-0.5 text-[0.65rem] font-medium">
                Customized
              </span>
            )}
          </span>
          <ChevronDown
            className={cn("size-4 transition-transform", open && "rotate-180")}
          />
        </button>
      )}

      {showContent && (
        <div className="space-y-4 px-3 pt-1 pb-3">
          {onRevertToBase && (
            <div className="text-muted-foreground bg-muted/40 flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-xs">
              <span>
                {inherited && !customized
                  ? "Inherited from base resume"
                  : "Overriding base resume formatting"}
              </span>
              {customized && (
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => onRevertToBase()}
                >
                  Revert to base
                </Button>
              )}
            </div>
          )}

          <Group title="Content Style">
            {choiceRow(
              "date_format",
              "Date format",
              (labelId) => (
              <Select
                value={effective.date_format}
                onValueChange={(v) =>
                  setKey(
                    "date_format",
                    (v ?? FORMATTING_DEFAULTS.date_format) as ResumeFormatting["date_format"],
                  )
                }
                disabled={isDisabled("date_format")}
              >
                <SelectTrigger size="sm" className="w-32" aria-labelledby={labelId}>
                  {/* Without children this showed the stored key — the date
                      picker read "short_month" instead of "Jun 2026". */}
                  <SelectValue>
                    {(value) =>
                      DATE_FORMAT_OPTIONS.find((o) => o.value === value)
                        ?.label ?? String(value ?? "")
                    }
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {DATE_FORMAT_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              ),
            )}
            {choiceRow(
              "bullet_icon",
              "Bullet style",
              (labelId) =>
                segmented(
                "bullet_icon",
                labelId,
                effective.bullet_icon,
                BULLET_ICON_OPTIONS,
                (v) => setKey("bullet_icon", v),
              ),
            )}
            {choiceRow(
              "hide_divider",
              "Hide section divider",
              (labelId) => (
                <Switch
                  aria-labelledby={labelId}
                  disabled={isDisabled("hide_divider")}
                  checked={effective.hide_divider}
                  onCheckedChange={(c) => setKey("hide_divider", c)}
                />
              ),
            )}
          </Group>

          <Group title="Layout">
            {sectionOrderRow()}
            {choiceRow(
              "header_align",
              "Header alignment",
              (labelId) =>
                segmented(
                "header_align",
                labelId,
                effective.header_align,
                HEADER_ALIGN_OPTIONS,
                (v) => setKey("header_align", v),
              ),
            )}
            {choiceRow(
              "education_order",
              "Education order",
              (labelId) =>
                segmented(
                "education_order",
                labelId,
                effective.education_order,
                EDUCATION_ORDER_OPTIONS,
                (v) => setKey("education_order", v),
              ),
            )}
            {choiceRow(
              "skills_layout",
              "Skills layout",
              (labelId) =>
                segmented(
                "skills_layout",
                labelId,
                effective.skills_layout,
                SKILLS_LAYOUT_OPTIONS,
                (v) => setKey("skills_layout", v),
              ),
            )}
          </Group>

          <Group title="Spacing & Margin">
            {choiceRow(
              "font_size",
              "Font size",
              (labelId) =>
                segmented(
                "font_size",
                labelId,
                effective.font_size,
                FONT_SIZE_OPTIONS,
                (v) => setKey("font_size", v),
              ),
            )}
            {sliderRow("section_spacing", "Section spacing", (n) => `${n}pt`)}
            {sliderRow("entry_spacing", "Entry spacing", (n) => `${n}pt`)}
            {sliderRow("line_spacing", "Line spacing", (n) => n.toFixed(1))}
            {sliderRow(
              "top_bottom_margin",
              "Top & bottom margin",
              (n) => `${n.toFixed(2)}in`,
            )}
            {sliderRow("side_margins", "Side margins", (n) => `${n.toFixed(2)}in`)}
            {choiceRow(
              "justify",
              "Align text left & right",
              (labelId) => (
                <Switch
                  aria-labelledby={labelId}
                  disabled={isDisabled("justify")}
                  checked={effective.justify}
                  onCheckedChange={(c) => setKey("justify", c)}
                />
              ),
            )}
          </Group>

          <div className="flex justify-end border-t pt-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!customized}
              onClick={() => onChange(null)}
            >
              <RotateCcw />
              Reset formatting
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-muted-foreground text-[0.7rem] font-semibold tracking-wide uppercase">
        {title}
      </div>
      {children}
    </div>
  );
}
