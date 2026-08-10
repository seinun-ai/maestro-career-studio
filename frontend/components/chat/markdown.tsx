"use client";

import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

/**
 * Assistant-message markdown, pinned to the app's type scale. Raw HTML stays
 * disabled (react-markdown default) — the content is model-generated.
 * remark-breaks keeps single newlines as line breaks: transcripts written
 * before markdown rendering relied on whitespace-pre-wrap line structure.
 */
export function ChatMarkdown({ children }: { children: string }) {
  return (
    <div className="text-sm leading-relaxed [&>*+*]:mt-2">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

const COMPONENTS: ComponentProps<typeof ReactMarkdown>["components"] = {
  h1: ({ children }) => <p className="text-base font-medium">{children}</p>,
  h2: ({ children }) => <p className="text-base font-medium">{children}</p>,
  h3: ({ children }) => <p className="text-sm font-medium">{children}</p>,
  h4: ({ children }) => <p className="text-sm font-medium">{children}</p>,
  ul: ({ children }) => <ul className="ml-5 list-disc space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="ml-5 list-decimal space-y-1">{children}</ol>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-2"
    >
      {children}
    </a>
  ),
  code: ({ className, children }) =>
    className ? (
      // Block code (has a language- class): rendered inside our pre below.
      <code className={className}>{children}</code>
    ) : (
      <code className="bg-muted rounded px-1 py-0.5 font-mono text-[0.85em]">
        {children}
      </code>
    ),
  pre: ({ children }) => (
    // Neutralize the inline-code chip styling for any <code> inside: fences
    // without a language tag have no className, so the code component can't
    // tell them apart from inline code (react-markdown v9+ dropped `inline`).
    <pre className="bg-muted overflow-x-auto rounded-xl p-3 font-mono text-xs leading-relaxed [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-[1em]">
      {children}
    </pre>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-muted-foreground/30 text-muted-foreground border-l-2 pl-3">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-foreground/10 border-b px-2 py-1.5 text-xs font-medium">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-foreground/5 border-b px-2 py-1.5 align-top">{children}</td>
  ),
  hr: () => <hr className="border-foreground/10" />,
};
