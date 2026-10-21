"use client";

import { Ban, Check, History, PenLine, RefreshCw, Undo2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

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

/** The element a card is drawn in, for keyboard focus after an action on it. */
const cardId = (insightId: string) => `card-${insightId}`;

function Actions({
  runId,
  insight,
  viewer,
  canProduce,
  onChange,
  onEdit,
}: {
  runId: string;
  insight: Insight;
  viewer: string;
  canProduce: boolean;
  onChange: (message: InsightMessage) => void;
  onEdit: (insightId: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const drafting = insight.agent_state === "pending" || insight.agent_state === "drafting";
  // What the producer approved is the wording they saw: an agent's draft on its way would replace it,
  // so approving waits for the draft, and a card on air with approved wording comes off air before a
  // redraft (the desk refuses both otherwise).
  const approvedByHand = insight.status === "approved" && insight.status_by === "producer";

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
            <Button size="sm" onClick={() => run("approve")} disabled={busy || drafting}>
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
          <Button size="sm" variant="outline" onClick={() => run("approve")} disabled={busy || drafting}>
            <Check /> Approve again
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={() => onEdit(insight.insight_id)} disabled={busy || drafting}>
          <PenLine /> Edit
        </Button>
        {insight.agent_state !== "off" && !approvedByHand && (
          <Button size="sm" variant="ghost" onClick={() => run("redraft")} disabled={busy || drafting}>
            <RefreshCw /> Redraft
          </Button>
        )}
      </div>
      {drafting && insight.status !== "approved" && (
        <p className="text-xs text-muted-foreground">An agent is drafting it: approve it once its draft is in.</p>
      )}
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
  onEdit,
}: {
  runId: string;
  insight: Insight;
  position: number;
  roster: Roster;
  viewer: string;
  canProduce: boolean;
  onChange: (message: InsightMessage) => void;
  onEdit: (insightId: string) => void;
}) {
  const airs = insight.status === "approved";
  return (
    <li
      id={cardId(insight.insight_id)}
      tabIndex={-1}
      className={cn(
        "space-y-1.5 rounded-lg border p-3 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
        airs && "border-emerald-600/40",
      )}
    >
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
      <Actions runId={runId} insight={insight} viewer={viewer} canProduce={canProduce} onChange={onChange} onEdit={onEdit} />
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
  // The card being edited. The dialog belongs to the console, not to the card, so it stays open with
  // the producer's text when the card drops off the shortlist or a stronger one pushes it down.
  const [editing, setEditing] = useState<string | null>(null);
  // After an action or an edit, keyboard focus goes to the card, or to the shortlist when the card
  // has left it, rather than falling back to the top of the page.
  const [focusTo, setFocusTo] = useState<{ id: string; n: number } | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const all = Object.values(insights);
  const top = shortlist(all, clock ? { period: clock.period, t: clock.t } : null);
  const alerts = corrections(all);

  useEffect(() => {
    if (focusTo) (document.getElementById(cardId(focusTo.id)) ?? list.current)?.focus();
  }, [focusTo]);

  const focusOn = useCallback((id: string) => setFocusTo((f) => ({ id, n: (f?.n ?? 0) + 1 })), []);
  const acted = useCallback(
    (message: InsightMessage) => {
      onChange(message);
      focusOn(message.insight.insight_id);
    },
    [onChange, focusOn],
  );

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
                  <li
                    key={i.insight_id}
                    id={cardId(i.insight_id)}
                    tabIndex={-1}
                    className="space-y-1 rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
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
                    <Actions runId={runId} insight={i} viewer={viewer} canProduce={canProduce} onChange={acted} onEdit={setEditing} />
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        <div ref={list} tabIndex={-1} aria-label="Shortlist" className="rounded-lg outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
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
                  onChange={acted}
                  onEdit={setEditing}
                />
              ))}
            </ol>
          )}
        </div>
      </CardContent>
      <EditDialog
        key={editing ?? ""}
        runId={runId}
        insight={editing ? (insights[editing] ?? null) : null}
        viewer={viewer}
        open={editing !== null}
        onOpenChange={(open) => {
          if (open || editing === null) return;
          focusOn(editing);
          setEditing(null);
        }}
        onSaved={acted}
      />
    </Card>
  );
}
