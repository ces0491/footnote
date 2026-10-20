"use client";

import { Ban, Check, History, RefreshCw, Undo2 } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { Clock, DeskAction, DeskRefusal, Insight, InsightMessage, ProducerMode } from "@/lib/live/contract";
import type { Roster } from "@/lib/live/describe";
import { corrections, provenanceLabel, shortlist, statusLabel } from "@/lib/live/shortlist";
import { cn } from "@/lib/utils";

import { Evidence } from "./evidence";
import { AgentRunsDialog, EditDialog } from "./producer-dialogs";

/** A producer's action on a card through the desk; resolves to the changed card, or why not. */
async function act(runId: string, insightId: string, viewer: string, action: Exclude<DeskAction, "edit">) {
  const response = await fetch(`/api/runs/${runId}/insights/${insightId}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ action, viewer }),
  });
  return (await response.json()) as InsightMessage | DeskRefusal;
}

function Actions({
  runId,
  insight,
  viewer,
  canProduce,
  onChange,
}: {
  runId: string;
  insight: Insight;
  viewer: string;
  canProduce: boolean;
  onChange: (message: InsightMessage) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const drafting = insight.agent_state === "pending" || insight.agent_state === "drafting";

  async function run(action: Exclude<DeskAction, "edit">) {
    setBusy(true);
    setRefusal(null);
    try {
      const result = await act(runId, insight.insight_id, viewer, action);
      if ("error" in result) setRefusal(result.error);
      else onChange(result);
    } catch (cause) {
      setRefusal(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  if (!canProduce) return null;
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        {insight.status === "drafted" && (
          <>
            <Button size="sm" onClick={() => run("approve")} disabled={busy}>
              <Check /> Approve
            </Button>
            <Button size="sm" variant="outline" onClick={() => run("kill")} disabled={busy}>
              <Ban /> Kill
            </Button>
          </>
        )}
        {insight.status === "approved" && (
          <Button size="sm" variant="outline" onClick={() => run("withdraw")} disabled={busy}>
            <Undo2 /> Withdraw
          </Button>
        )}
        {(insight.status === "killed" || insight.status === "withdrawn") && (
          <Button size="sm" variant="outline" onClick={() => run("approve")} disabled={busy}>
            <Check /> Approve again
          </Button>
        )}
        <EditDialog runId={runId} insight={insight} viewer={viewer} disabled={busy || drafting} onSaved={onChange} />
        {insight.agent_state !== "off" && (
          <Button size="sm" variant="ghost" onClick={() => run("redraft")} disabled={busy || drafting}>
            <RefreshCw /> Redraft
          </Button>
        )}
      </div>
      {refusal && <p className="text-xs text-destructive">{refusal}</p>}
    </div>
  );
}

function Item({
  runId,
  insight,
  position,
  roster,
  viewer,
  canProduce,
  onChange,
}: {
  runId: string;
  insight: Insight;
  position: number;
  roster: Roster;
  viewer: string;
  canProduce: boolean;
  onChange: (message: InsightMessage) => void;
}) {
  const airs = insight.status === "approved";
  return (
    <li className={cn("space-y-1.5 rounded-lg border p-3", airs && "border-emerald-600/40")}>
      <div className="flex items-start justify-between gap-3">
        <div className="font-medium">
          <span className="mr-2 text-muted-foreground tabular-nums">{position}</span>
          {insight.card.headline}
        </div>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums" title="Rank, from the match-state model">
          rank {insight.rank.toFixed(2)}
        </span>
      </div>
      <p className="text-sm">{insight.card.casual}</p>
      <p className="text-xs text-muted-foreground">{insight.card.analyst}</p>
      <p className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Why it&apos;s here: </span>
        {insight.reason}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={airs ? "default" : "outline"}>{statusLabel(insight)}</Badge>
        <Badge variant={insight.source === "template" ? "outline" : "secondary"}>{provenanceLabel(insight)}</Badge>
        {insight.agent_note && <span className="text-xs text-muted-foreground">{insight.agent_note}</span>}
      </div>
      <Actions runId={runId} insight={insight} viewer={viewer} canProduce={canProduce} onChange={onChange} />
      <div className="flex flex-wrap items-center gap-1">
        <Evidence runId={runId} insight={insight} roster={roster} />
        {insight.agent_state !== "off" && <AgentRunsDialog runId={runId} insight={insight} />}
      </div>
    </li>
  );
}

/**
 * The producer's console (docs/experience.md): the strongest moments still current, each with its
 * reason, evidence, provenance and the controls to approve, edit, kill or withdraw it, and the
 * corrections that need attention. Nothing reaches fans without approval unless the producer lets
 * graphics through automatically. Only the viewer who started the replay produces it; anyone else
 * sees the console as it stands.
 */
export function ProducerConsole({
  runId,
  insights,
  clock,
  roster,
  viewer,
  canProduce,
  mode,
  onMode,
  onChange,
}: {
  runId: string;
  insights: Record<string, Insight>;
  clock: Clock | null;
  roster: Roster;
  viewer: string;
  canProduce: boolean;
  mode: ProducerMode;
  onMode: (mode: ProducerMode) => Promise<string | null>;
  onChange: (message: InsightMessage) => void;
}) {
  const [modeError, setModeError] = useState<string | null>(null);
  const all = Object.values(insights);
  const top = shortlist(all, clock ? { period: clock.period, t: clock.t } : null);
  const alerts = corrections(all);

  async function switchMode(auto: boolean) {
    setModeError(await onMode(auto ? "auto" : "manual"));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Producer console</CardTitle>
        <CardDescription>
          The strongest moments still current, ranked with the match-state model. A card shows its template wording until
          an agent&apos;s checked draft replaces it; fans see a card once it&apos;s approved and their stream reaches it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2">
          <div className="flex items-center gap-2">
            <Switch
              id="auto-approve"
              checked={mode === "auto"}
              onCheckedChange={switchMode}
              disabled={!canProduce}
              aria-describedby="auto-approve-note"
            />
            <Label htmlFor="auto-approve">Approve automatically</Label>
          </div>
          <p id="auto-approve-note" className="text-xs text-muted-foreground">
            {mode === "auto"
              ? "Every checked card airs as it's found."
              : "Nothing airs until you approve it."}{" "}
            {!canProduce && "Only the browser that started this replay can produce it."}
          </p>
          {modeError && <p className="w-full text-xs text-destructive">{modeError}</p>}
        </div>
        {alerts.length > 0 && (
          <Alert>
            <History aria-hidden />
            <AlertTitle>Corrections</AlertTitle>
            <AlertDescription>
              <ul className="space-y-2">
                {alerts.map((i) => (
                  <li key={i.insight_id} className="space-y-1">
                    {i.kind === "correction" ? (
                      <span className="font-medium">{i.card.casual}</span>
                    ) : (
                      <span>
                        <span className="font-medium">{i.card.headline}</span>: {i.flag?.reason}
                      </span>
                    )}
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{statusLabel(i)}</Badge>
                    </div>
                    <Actions runId={runId} insight={i} viewer={viewer} canProduce={canProduce} onChange={onChange} />
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        {top.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing on the shortlist yet.</p>
        ) : (
          <ol className="space-y-3">
            {top.map((insight, n) => (
              <Item
                key={insight.insight_id}
                runId={runId}
                insight={insight}
                position={n + 1}
                roster={roster}
                viewer={viewer}
                canProduce={canProduce}
                onChange={onChange}
              />
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
