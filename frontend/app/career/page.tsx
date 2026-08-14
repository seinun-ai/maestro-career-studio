"use client";

import { useState } from "react";

import { useFocusSection } from "@/lib/use-focus-section";
import { useQuery } from "@tanstack/react-query";
import { Plus, Upload } from "lucide-react";

import { CaptureBox } from "@/components/career/capture-box";
import { EntityCard } from "@/components/career/entity-card";
import { InboxPanel } from "@/components/career/inbox-panel";
import { NewEntityDialog } from "@/components/career/new-entity-dialog";
import { ProfilePanel } from "@/components/career/profile-panel";
import { CareerExportsCard } from "@/components/career/exports-card";
import { Badge } from "@/components/ui/badge";
import { FirstRunImportCard } from "@/components/career/first-run-import-card";
import { UploadDialog } from "@/components/setup/upload-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { listKbDrafts, listKbEntities } from "@/lib/api";
import type { KBEntityKind, KBEntitySummary } from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";

const ENTITY_TABS: { kind: KBEntityKind; value: string; title: string; singular: string }[] = [
  { kind: "experience", value: "experience", title: "Experience", singular: "experience" },
  { kind: "project", value: "project", title: "Projects", singular: "project" },
  { kind: "education", value: "education", title: "Education", singular: "education" },
  { kind: "certification", value: "certification", title: "Certifications", singular: "certification" },
  { kind: "extra", value: "extra", title: "Custom sections", singular: "custom section" },
];

export default function CareerPage() {
  const [activeTab, setActiveTab] = useState("profile");
  const [newEntity, setNewEntity] = useState<{ open: boolean; kind: KBEntityKind }>({
    open: false,
    kind: "experience",
  });

  const entities = useQuery({
    queryKey: ["kb", "entities"],
    queryFn: () => listKbEntities(),
  });
  const drafts = useQuery({
    queryKey: ["kb", "drafts"],
    queryFn: listKbDrafts,
  });

  const openNewEntity = (kind: KBEntityKind) => setNewEntity({ open: true, kind });
  // On an entity tab, "New entity" defaults to that kind; on Profile, to experience.
  const activeKind = ENTITY_TABS.find((tab) => tab.value === activeTab)?.kind ?? "experience";

  const [importOpen, setImportOpen] = useState(false);
  useFocusSection();

  const countFor = (kind: KBEntityKind) =>
    (entities.data ?? []).filter((entity) => entity.kind === kind).length;

  return (
    <PageShell>
      <PageHeader
        className="animate-fade-rise"
        title="Career Knowledge Base"
        subtitle="Your living record of roles, projects, education, and credentials."
        actions={
          <>
            {/* Same endpoint as the first-run card — one pipeline, two entry
                points. Available forever, not just on first run: the KB seed is
                once-per-install, so without this a user adding a fourth resume
                later would have no path. */}
            <Button
              variant="outline"
              className="rounded-full px-4"
              onClick={() => setImportOpen(true)}
            >
              <Upload aria-hidden="true" /> Add documents
            </Button>
            <Button
              className="rounded-full px-4"
              onClick={() => openNewEntity(activeKind)}
            >
              <Plus aria-hidden="true" /> New entity
            </Button>
          </>
        }
      />

      <div className="grid gap-6">
        <FirstRunImportCard />
        <CaptureBox />
        {/* Anchor: the document lane's summary links here to review drafts. */}
        <div id="kb-inbox">
        <InboxPanel
          drafts={drafts.data ?? []}
          entities={entities.data ?? []}
          isLoading={drafts.isLoading}
          error={drafts.error}
          onRetry={() => void drafts.refetch()}
        />
        </div>
      </div>

      {/* Anchor: the "Import resumes" setup step links here. */}
      <Tabs id="kb-entities" value={activeTab} onValueChange={setActiveTab} className="gap-5">
        <TabsList className="h-auto flex-wrap rounded-full bg-muted/70 p-1">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          {ENTITY_TABS.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value} className="gap-1.5">
              {tab.title}
              {countFor(tab.kind) > 0 ? (
                <Badge variant="secondary" className="px-1.5">
                  {countFor(tab.kind)}
                </Badge>
              ) : null}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="profile" className="space-y-4">
          <ProfilePanel />
          <CareerExportsCard />
        </TabsContent>

        {ENTITY_TABS.map((tab) => (
          <TabsContent key={tab.value} value={tab.value}>
            {tab.kind === "extra" ? (
              <CustomSectionsTab
                items={(entities.data ?? []).filter((entity) => entity.kind === tab.kind)}
                isLoading={entities.isLoading}
                error={entities.error}
                onRetry={() => void entities.refetch()}
                onAdd={() => openNewEntity("extra")}
              />
            ) : (
              <EntityTab
                title={tab.title}
                singular={tab.singular}
                items={(entities.data ?? []).filter((entity) => entity.kind === tab.kind)}
                isLoading={entities.isLoading}
                error={entities.error}
                onRetry={() => void entities.refetch()}
                onAdd={() => openNewEntity(tab.kind)}
              />
            )}
          </TabsContent>
        ))}
      </Tabs>

      <NewEntityDialog
        key={newEntity.kind}
        open={newEntity.open}
        defaultKind={newEntity.kind}
        onOpenChange={(open) => setNewEntity((current) => ({ ...current, open }))}
      />
      <UploadDialog open={importOpen} onOpenChange={setImportOpen} />
    </PageShell>
  );
}

function CustomSectionsTab({
  items,
  isLoading,
  error,
  onRetry,
  onAdd,
}: {
  items: KBEntitySummary[];
  isLoading: boolean;
  error: Error | null;
  onRetry: () => void;
  onAdd: () => void;
}) {
  const groups: { key: string; title: string; type: string; entities: KBEntitySummary[] }[] = [];
  const groupMap = new Map<string, (typeof groups)[0]>();

  for (const item of items) {
    const sKey = item.section_key || "other";
    const sTitle = item.section_title || sKey;
    const sType = item.section_type || "entries";
    let g = groupMap.get(sKey);
    if (!g) {
      g = { key: sKey, title: sTitle, type: sType, entities: [] };
      groupMap.set(sKey, g);
      groups.push(g);
    }
    g.entities.push(item);
  }

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-muted-foreground text-sm">
          Custom sections (publications, awards, volunteer work, certifications) and the career facts connected to them.
        </p>
        <Button className="rounded-full" size="sm" variant="secondary" onClick={onAdd}>
          <Plus aria-hidden="true" /> Add custom section
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Loading custom sections">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full" />
          ))}
        </div>
      ) : error ? (
        <div role="alert" className="rounded-2xl bg-destructive/10 p-5">
          <p className="text-sm font-medium">Couldn&apos;t load custom sections.</p>
          <p className="text-muted-foreground mt-1 text-xs">{error.message}</p>
          <Button className="mt-3" size="sm" variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl bg-muted/45 p-10 text-center">
          <p className="text-sm font-medium">No custom sections yet</p>
          <p className="text-muted-foreground mx-auto mt-1 max-w-md text-xs">
            Add custom sections like publications, awards, presentations, or clearances to your Career Knowledge Base.
          </p>
          <Button className="mt-4 rounded-full" size="sm" onClick={onAdd}>
            <Plus aria-hidden="true" /> Add custom section
          </Button>
        </div>
      ) : (
        <div className="space-y-6">
          {groups.map((group) => (
            <div key={group.key} className="space-y-3">
              <div className="flex items-center gap-2 border-b pb-1.5">
                <h3 className="text-sm font-semibold tracking-tight text-foreground">
                  {group.title}
                </h3>
                <Badge variant="outline" className="text-[11px] font-normal uppercase tracking-wider">
                  {group.type}
                </Badge>
                <span className="text-xs text-muted-foreground ml-auto">
                  {group.entities.length} {group.entities.length === 1 ? "item" : "items"}
                </span>
              </div>
              <div className="animate-fade-rise grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {group.entities.map((entity) => (
                  <EntityCard key={entity.id} entity={entity} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function EntityTab({
  title,
  singular,
  items,
  isLoading,
  error,
  onRetry,
  onAdd,
}: {
  title: string;
  singular: string;
  items: KBEntitySummary[];
  isLoading: boolean;
  error: Error | null;
  onRetry: () => void;
  onAdd: () => void;
}) {
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-muted-foreground text-sm">
          {title} and the career facts connected to them.
        </p>
        <Button className="rounded-full" size="sm" variant="secondary" onClick={onAdd}>
          <Plus aria-hidden="true" /> Add {singular}
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label={`Loading ${title}`}>
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full" />
          ))}
        </div>
      ) : error ? (
        <div role="alert" className="rounded-2xl bg-destructive/10 p-5">
          <p className="text-sm font-medium">Couldn&apos;t load {title.toLowerCase()}.</p>
          <p className="text-muted-foreground mt-1 text-xs">{error.message}</p>
          <Button className="mt-3" size="sm" variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl bg-muted/45 p-10 text-center">
          <p className="text-sm font-medium">No {title.toLowerCase()} yet</p>
          <p className="text-muted-foreground mx-auto mt-1 max-w-md text-xs">
            Capture a career update and let the AI create one, or add your first {singular} manually.
          </p>
          <Button className="mt-4 rounded-full" size="sm" onClick={onAdd}>
            <Plus aria-hidden="true" /> Add {singular}
          </Button>
        </div>
      ) : (
        <div className="animate-fade-rise grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((entity) => (
            <EntityCard key={entity.id} entity={entity} />
          ))}
        </div>
      )}
    </section>
  );
}
