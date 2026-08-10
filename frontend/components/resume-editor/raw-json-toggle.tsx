"use client";

import { useState } from "react";

import { JsonEditor } from "@/components/json-editor";
import { Button } from "@/components/ui/button";
import { resumeDataSchema } from "@/lib/resume-schema";
import type { ResumeData } from "@/lib/types";

export function RawJsonToggle({
  value,
  onChange,
  onClose,
}: {
  value: ResumeData;
  onChange: (next: ResumeData) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);

  const apply = () => {
    try {
      const parsed = JSON.parse(text);
      const result = resumeDataSchema.safeParse(parsed);
      if (!result.success) {
        setError(result.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("\n"));
        return;
      }
      setError(null);
      onChange(result.data as ResumeData);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="space-y-3">
      <JsonEditor value={text} onChange={setText} />
      {error && (
        <pre className="text-destructive rounded-md bg-destructive/10 p-2 text-xs whitespace-pre-wrap">
          {error}
        </pre>
      )}
      <div className="flex gap-2">
        <Button onClick={apply}>Apply JSON</Button>
        <Button variant="outline" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
