"use client";

import { Copy } from "lucide-react";
import { toast } from "sonner";

import { IconButton } from "@/components/icon-button";
import { SettingCard } from "@/components/settings/setting-card";
import { useVersion } from "@/hooks/use-version";
import { FRONTEND_VERSION } from "@/lib/version";

const UPDATE_COMMAND = "./scripts/update.sh";

function CopyUpdateCommand() {
  return (
    <div className="flex items-center gap-2">
      <code className="bg-muted rounded-md px-2 py-1 font-mono text-sm">
        {UPDATE_COMMAND}
      </code>
      <IconButton
        label="Copy update command"
        icon={<Copy />}
        onClick={() => {
          void navigator.clipboard
            .writeText(UPDATE_COMMAND)
            .then(() => toast.success("Copied"));
        }}
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 px-3 py-2.5">
      <span className="text-muted-foreground text-sm">{label}</span>
      <span className="font-mono text-sm">{value}</span>
    </div>
  );
}

export function AboutSection() {
  const version = useVersion();

  return (
    <SettingCard
      id="about"
      title="About"
      description={
        <>
          What this install is running. A local build reads{" "}
          <code className="font-mono text-[0.85em]">dev</code> here.
        </>
      }
      errorTitle="Couldn't load version info."
      skeleton="h-24 w-full"
      query={version}
    >
      {(data) => (
        <div className="divide-y">
          <Row label="Frontend" value={FRONTEND_VERSION} />
          <Row label="Backend" value={data.version} />
          <Row label="Schema revision" value={data.schema_revision} />
          <Row label="Git SHA" value={data.git_sha ?? "not recorded"} />
          <div className="flex items-center justify-between gap-4 px-3 py-2.5">
            <span className="text-muted-foreground text-sm">Update</span>
            <CopyUpdateCommand />
          </div>
          <div className="flex items-center justify-between gap-4 px-3 py-2.5">
            <span className="text-muted-foreground text-sm">What&apos;s new</span>
            {/* A static link, deliberately: the app itself never asks GitHub
                anything — clicking this is the user opening their browser. */}
            <a
              href="https://github.com/seinun-ai/maestro-career-studio/releases"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm underline underline-offset-4 hover:no-underline"
            >
              Release notes
            </a>
          </div>
        </div>
      )}
    </SettingCard>
  );
}
