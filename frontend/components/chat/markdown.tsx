"use client";

import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

import { NewTabCue } from "@/components/new-tab-link";

/**
 * Assistant-message markdown, pinned to the app's type scale. Raw HTML stays
 * disabled (react-markdown default) — the content is model-generated.
 * remark-breaks keeps single newlines as line breaks: transcripts written
 * before markdown rendering relied on whitespace-pre-wrap line structure.
 */
export function ChatMarkdown({ children }: { children: string }) {
  return (
    <div className="text-body-medium leading-6 [&>*+*]:mt-2">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

const COMPONENTS: ComponentProps<typeof ReactMarkdown>["components"] = {
  h1: ({ children }) => <p className="text-title-medium">{children}</p>,
  h2: ({ children }) => <p className="text-title-medium">{children}</p>,
  h3: ({ children }) => <p className="text-title-small">{children}</p>,
  h4: ({ children }) => <p className="text-title-small">{children}</p>,
  ul: ({ children }) => <ul className="ml-5 list-disc space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="ml-5 list-decimal space-y-1">{children}</ol>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary inline-flex items-center gap-0.5 underline underline-offset-2"
    >
      {children}
      <NewTabCue />
    </a>
  ),
  code: ({ className, children }) =>
    className ? (
      // Block code (has a language- class): rendered inside our pre below.
      <code className={className}>{children}</code>
    ) : (
      <code className="bg-muted rounded-corner-xs px-1 py-0.5 font-mono text-[0.85em]">
        {children}
      </code>
    ),
  pre: ({ children }) => (
    // Neutralize the inline-code chip styling for any <code> inside: fences
    // without a language tag have no className, so the code component can't
    // tell them apart from inline code (react-markdown v9+ dropped `inline`).
    <pre className="bg-muted overflow-x-auto rounded-corner-md p-3 font-mono text-body-small leading-5 [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-[1em]">
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
      <table className="w-full border-collapse text-left text-body-medium">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-foreground/10 border-b px-2 py-1.5 text-label-medium">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-foreground/5 border-b px-2 py-1.5 align-top">{children}</td>
  ),
  hr: () => <hr className="border-foreground/10" />,
};
