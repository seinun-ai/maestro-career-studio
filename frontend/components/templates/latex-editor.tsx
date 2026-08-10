"use client";

import Editor from "@/components/monaco";

export function LatexEditor({
  value,
  onChange,
  height = "100%",
  readOnly = false,
}: {
  value: string;
  onChange: (next: string) => void;
  height?: string;
  readOnly?: boolean;
}) {
  return (
    <div className="h-full overflow-hidden rounded-md border">
      <Editor
        height={height}
        language="latex"
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
