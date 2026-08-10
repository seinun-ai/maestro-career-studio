"use client";

/**
 * Last-resort boundary for a throw in the ROOT layout itself, where
 * `app/error.tsx` cannot render because the shell it lives inside is the thing
 * that failed. It therefore has to supply its own <html>/<body>, and it cannot
 * use the app's components or Tailwind tokens — those load through the layout
 * that just broke. Inline styles are the point here, not an oversight.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "0.75rem",
          padding: "1.5rem",
          textAlign: "center",
          font: "16px/1.5 system-ui, sans-serif",
        }}
      >
        <h1 style={{ fontSize: "1.125rem", fontWeight: 500, margin: 0 }}>
          Maestro CS failed to start
        </h1>
        <p style={{ margin: 0, opacity: 0.7, fontSize: "0.875rem" }}>
          The application shell could not render. Reloading is safe.
        </p>
        {error.digest && (
          <p style={{ margin: 0, opacity: 0.6, fontSize: "0.75rem" }}>
            Reference: <code>{error.digest}</code>
          </p>
        )}
        <button
          type="button"
          onClick={reset}
          style={{
            font: "inherit",
            fontSize: "0.875rem",
            padding: "0.5rem 1rem",
            borderRadius: "0.5rem",
            border: "1px solid currentColor",
            background: "transparent",
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
