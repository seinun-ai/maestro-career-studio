"use client";

import Editor from "@/components/monaco";

export function JsonEditor({
  value,
  onChange,
  height = "60vh",
  readOnly = false,
}: {
  value: string;
  onChange: (next: string) => void;
  height?: string;
  readOnly?: boolean;
}) {
  return (
    <div className="overflow-hidden rounded-md border">
      <Editor
        height={height}
        language="json"
        value={value}
        onChange={(v: string | undefined) => onChange(v ?? "")}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 12,
          tabSize: 2,
          wordWrap: "on",
          scrollBeyondLastLine: false,
        }}
      />
    </div>
  );
}
