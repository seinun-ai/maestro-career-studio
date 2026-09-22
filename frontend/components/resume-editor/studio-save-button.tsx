"use client";

import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useModKey } from "@/hooks/use-mod-key";
import { useSaveShortcut } from "@/hooks/use-save-shortcut";
import { shortcutLabel } from "@/lib/shortcuts";

/**
 * The studios' ONE Save button, for `StudioToolbar`'s `primary` slot.
 *
 * It owns Cmd/Ctrl+S as well as the click, so the key and the button cannot
 * disagree: both read the one `canSave`. The studios used to wire the
 * shortcut and the button side by side, twice, and a studio could change one
 * without the other. It is mounted exactly while the studio's toolbar is,
 * which is every state of an open studio (raw JSON and a collapsed preview
 * included), so the shortcut lives exactly as long as the button it presses.
 *
 * `sm`, like the rest of the toolbar row (template picker, ⋯ opener). While a
 * save runs it keeps its label and spins: the header's status line carries
 * the words, and a longer label here widened the button from 52 to 89px.
 */
export function StudioSaveButton({
  onSave,
  canSave,
  pending,
}: {
  onSave: () => void;
  /** The button's enabled state, and so the shortcut's. */
  canSave: boolean;
  pending: boolean;
}) {
  useSaveShortcut(onSave, canSave);
  const mod = useModKey();
  return (
    <Button
      size="sm"
      onClick={() => onSave()}
      disabled={!canSave}
      title={`Save (${shortcutLabel(mod, "S")})`}
      aria-keyshortcuts="Meta+S Control+S"
    >
      {pending && <Loader2 className="animate-spin" aria-hidden="true" />}
      Save
    </Button>
  );
}
