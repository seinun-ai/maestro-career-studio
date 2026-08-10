"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Bar,
  BarChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  CHART_COLORS as COLORS,
  ChartCard,
} from "@/components/charts/chart-kit";
import { useConfirm } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { AutofillTelemetrySummary } from "@/lib/types";

function Tile({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl bg-muted/40 p-4">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-foreground mt-0.5 text-xl font-medium">{value}</p>
      {sub ? <p className="text-muted-foreground mt-0.5 text-xs">{sub}</p> : null}
    </div>
  );
}

function RateTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{
    payload?: { kind: string; rate: number; success: number; failure: number };
  }>;
}) {
  const row = active ? payload?.[0]?.payload : undefined;
  if (!row) return null;
  return (
    <div className="bg-background rounded-md border p-2 text-xs shadow-sm">
      <p className="font-medium">{row.kind}</p>
      <p className="text-muted-foreground">
        {row.rate.toFixed(0)}% · {row.success} filled or corrected vs {row.failure} failed
      </p>
    </div>
  );
}

export function AutofillCoverageCard() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const { data, isLoading, error } = useQuery({
    queryKey: ["autofill-telemetry-summary"],
    queryFn: () =>
      apiFetch<AutofillTelemetrySummary>("/api/autofill/telemetry/summary"),
  });

  const clear = useMutation({
    mutationFn: () =>
      apiFetch<{ deleted: number }>("/api/autofill/telemetry", {
        method: "DELETE",
      }),
    onSuccess: ({ deleted }) => {
      qc.invalidateQueries({ queryKey: ["autofill-telemetry-summary"] });
      toast.success(
        deleted === 1 ? "Cleared 1 captured field" : `Cleared ${deleted} captured fields`
      );
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const hosts = data?.totals.hosts ?? 0;
  const signatures = data?.totals.signatures ?? 0;

  async function onClear() {
    // Name the sites count in the prompt, not just the field count. The field
    // count is what the card shows; the sites count is what makes this personal
    // — it is the number of employers this table remembers you visiting — and a
    // confirm that hides the actual stake is not informed consent.
    const ok = await confirm({
      title: "Clear captured autofill data?",
      description:
        `This deletes ${signatures} recorded field ${signatures === 1 ? "shape" : "shapes"}` +
        ` across ${hosts} ${hosts === 1 ? "site" : "sites"}, including which sites they were` +
        " seen on and when. It cannot be undone. Capture stays on — turn it off in the" +
        " extension card's ⋯ menu.",
      confirmLabel: "Clear data",
      destructive: true,
    });
    if (ok) clear.mutate();
  }

  const rates = (data?.by_kind ?? [])
    .filter((kind) => kind.success_rate !== null)
    .map((kind) => ({
      kind: kind.kind,
      rate: (kind.success_rate as number) * 100,
      success: kind.success,
      failure: kind.failure,
    }));

  return (
    <ChartCard
      title="Autofill coverage"
      description="What real application forms ask, and where the extension's fill pipeline fails."
      isLoading={isLoading}
      error={error as Error | null}
      empty={signatures === 0}
      emptyText="No telemetry yet. Fill an application with the extension to start capturing."
      action={
        signatures > 0 ? (
          <Button
            variant="outline"
            size="xs"
            onClick={onClear}
            disabled={clear.isPending}
          >
            {clear.isPending ? "Clearing…" : "Clear data"}
          </Button>
        ) : null
      }
    >
      {!data ? null : (
        <div className="grid gap-4">
          <div className="grid grid-cols-3 gap-3">
            <Tile label="Unique fields" value={String(data.totals.signatures)} />
            <Tile label="Observations" value={String(data.totals.observations)} />
            <Tile label="Sites" value={String(data.totals.hosts)} />
          </div>

          {rates.length > 0 ? (
            <ResponsiveContainer
              width="100%"
              height={Math.max(160, rates.length * 36 + 30)}
            >
              <BarChart
                data={rates}
                layout="vertical"
                margin={{ left: 8, right: 24 }}
              >
                <XAxis
                  type="number"
                  domain={[0, 100]}
                  tickFormatter={(value) => `${value}%`}
                />
                <YAxis
                  type="category"
                  dataKey="kind"
                  width={90}
                  tick={{ fontSize: 12 }}
                  interval={0}
                />
                <Tooltip content={<RateTooltip />} cursor={{ opacity: 0.1 }} />
                <Bar
                  dataKey="rate"
                  name="Fill success"
                  fill={COLORS[0]}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : null}

          {data.top_failures.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground text-left text-xs">
                    <th className="py-1.5 pr-3 font-normal">Field</th>
                    <th className="py-1.5 pr-3 font-normal">Kind</th>
                    <th className="py-1.5 pr-3 font-normal">Site</th>
                    <th className="py-1.5 pr-3 text-right font-normal">Seen</th>
                    <th className="py-1.5 text-right font-normal">
                      Failure share
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_failures.map((row) => (
                    <tr key={row.signature_hash} className="border-t">
                      <td className="max-w-56 truncate py-1.5 pr-3">
                        {row.label}
                      </td>
                      <td className="text-muted-foreground py-1.5 pr-3">
                        {row.kind}
                      </td>
                      <td className="text-muted-foreground max-w-40 truncate py-1.5 pr-3">
                        {row.host}
                      </td>
                      <td className="py-1.5 pr-3 text-right">{row.seen_count}</td>
                      <td className="py-1.5 text-right">
                        {Math.round(row.failure_share * 100)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {data.novelty.length > 0 ? (
            <div className="flex items-center gap-3">
              <div className="h-12 w-40 shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.novelty}>
                    <Line
                      type="monotone"
                      dataKey="share"
                      stroke={COLORS[0]}
                      strokeWidth={1.5}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="text-muted-foreground text-xs">
                New-field share, last {data.novelty.length} capture sessions.{" "}
                {data.recommendation}
              </p>
            </div>
          ) : null}
        </div>
      )}
    </ChartCard>
  );
}
