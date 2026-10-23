"use client";

import { Ban, Bot, Check, PenLine, RefreshCw, Undo2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { Clock, DeskAction, DeskRefusal, Insight, InsightMessage, ProducerMode } from "@/lib/live/contract";
import type { Roster } from "@/lib/live/describe";
import { undone } from "@/lib/live/fan";
import { corrections, provenanceLabel, SHORTLIST_SIZE, shortlist, statusLabel, translatedLabel } from "@/lib/live/shortlist";
import { cn } from "@/lib/utils";

import { KindIcon } from "./card-kind";
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
            {/* Red at rest; chalk on hover, where the lighter ground leaves the red short of 4.5:1. */}
            <Button size="sm" variant="outline" className="text-tally" onClick={() => run("kill")} disabled={busy}>
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
        <Button variant="ghost" size="sm" onClick={() => onEdit(insight.insight_id)} disabled={busy || drafting}>
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
      {refusal && <p className="text-xs text-tally">{refusal}</p>}
    </div>
  );
}

/** Whether a card airs, in the colour of what it waits for: go once approved, amend after a correction. */
function statusTone(insight: Insight): string {
  if (insight.status === "approved") return "bg-go/15 text-go";
  if (insight.status === "drafted") return insight.status_by === "correction" ? "bg-amend/15 text-amend" : "bg-foreground/10 text-foreground";
  return "bg-secondary text-muted-foreground";
}

/** Whether a card airs, where its wording came from, and the languages it's ready in. */
function Labels({ insight }: { insight: Insight }) {
  const agent = insight.source === "agent";
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      <span className={cn("inline-flex h-6 items-center gap-1 rounded-full px-2.5 font-medium", statusTone(insight))}>
        {insight.status === "approved" && <Check aria-hidden className="size-3" />}
        {statusLabel(insight)}
      </span>
      <span
        className={cn(
          "inline-flex h-6 items-center gap-1 rounded-full px-2.5 font-medium",
          agent ? "bg-secondary text-foreground ring-1 ring-edge ring-inset" : "bg-secondary text-muted-foreground",
        )}
      >
        {agent && <Bot aria-hidden className="size-3" />}
        {provenanceLabel(insight)}
      </span>
      {translatedLabel(insight) && (
        <span className="text-muted-foreground" title="Translated by Azure AI Translator and checked by code">
          {translatedLabel(insight)}
        </span>
      )}
      {insight.agent_note && <span className="w-full text-muted-foreground">{insight.agent_note}</span>}
    </div>
  );
}

/** The events behind a card, and the agents' runs on it. */
function Sources({ runId, insight, roster }: { runId: string; insight: Insight; roster: Roster }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
      <Evidence runId={runId} insight={insight} roster={roster} />
      {insight.agent_state !== "off" && <AgentRunsDialog runId={runId} insight={insight} />}
    </div>
  );
}

/** The card's rank as a meter of five, with the figure. */
function Rank({ rank }: { rank: number }) {
  const lit = Math.round(rank * 5);
  return (
    <span
      className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground"
      title="Rank: a base for the kind of moment, raised by the match state and the moment's figures"
    >
      <span aria-hidden className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <span key={n} className={cn("h-3 w-1.5 rounded-xs", n <= lit ? "bg-foreground" : "bg-secondary")} />
        ))}
      </span>
      <span className="figures">rank {rank.toFixed(2)}</span>
    </span>
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
  return (
    <li
      id={cardId(insight.insight_id)}
      tabIndex={-1}
      className="relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3 border-b px-5 py-5 outline-none last:border-0 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:ring-inset"
    >
      {insight.status === "approved" && <span aria-hidden className="absolute inset-y-0 left-0 w-0.75 bg-go" />}
      <div className="flex flex-col items-center gap-2">
        <span className="text-2xl leading-none font-bold text-muted-foreground figures">{position}</span>
        <KindIcon insight={insight} />
      </div>
      <div className="min-w-0 space-y-2.5">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <h4 className="text-[17px] leading-snug font-semibold font-stretch-90%">{insight.card.headline}</h4>
          <Rank rank={insight.rank} />
        </div>
        <div className="space-y-1">
          <p className="font-serif text-[15px] leading-relaxed">{insight.card.casual}</p>
          <p className="font-serif text-sm leading-relaxed text-muted-foreground">{insight.card.analyst}</p>
        </div>
        <p className="text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">Why it&apos;s here: </span>
          {insight.reason}
        </p>
        <Labels insight={insight} />
        <Actions runId={runId} insight={insight} viewer={viewer} canProduce={canProduce} onChange={onChange} onEdit={onEdit} />
        <Sources runId={runId} insight={insight} roster={roster} />
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
  // The card being edited. The dialog lives in the console, so it stays open with the producer's text
  // when the card drops off the shortlist or a stronger one pushes it down.
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
    <section aria-labelledby="console-title" className="overflow-hidden rounded-xl bg-card ring-1 ring-border">
      <div className="border-b px-5 py-4">
        <h2 id="console-title" className="text-xl font-bold tracking-tight font-stretch-75%">
          Producer console
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          The strongest moments still current, by rank. A card shows its template wording until an
          agent&apos;s checked draft replaces it; fans see a card once it&apos;s approved and their stream reaches it.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b bg-secondary/50 px-5 py-3">
        <div className="flex items-center gap-2.5">
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
          {mode === "auto" ? "Each card is approved as it's found." : "Nothing airs until you approve it."}{" "}
          {!canProduce && "Only the browser that started this replay can produce it."}
        </p>
        {modeError && <p className="w-full text-xs text-tally">{modeError}</p>}
      </div>
      {alerts.length > 0 && (
        <div role="alert" className="border-b border-l-4 border-l-amend bg-amend/10 px-5 py-4">
          <h3 className="flex items-center gap-2 font-semibold text-amend">
            <PenLine aria-hidden className="size-4" />
            Corrections
          </h3>
          <ul className="mt-3 space-y-4">
            {alerts.map((i) => {
              // A card a correction restated has new wording, shown here as on the shortlist: what
              // the producer approves is what they read.
              const restated = undone(i) === "corrected";
              return (
                <li
                  key={i.insight_id}
                  id={cardId(i.insight_id)}
                  tabIndex={-1}
                  className="space-y-2 rounded-md text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  {i.kind === "correction" ? (
                    <span className="font-semibold">{i.card.casual}</span>
                  ) : (
                    <span className="text-muted-foreground">
                      <span className="font-semibold text-foreground">{i.card.headline}</span>: {i.flag?.reason}
                    </span>
                  )}
                  {restated ? (
                    <>
                      <div className="font-serif text-[15px] leading-relaxed">{i.card.casual}</div>
                      <div className="font-serif text-sm leading-relaxed text-muted-foreground">{i.card.analyst}</div>
                      <Labels insight={i} />
                    </>
                  ) : (
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className={cn("inline-flex h-6 items-center rounded-full px-2.5 font-medium", statusTone(i))}>{statusLabel(i)}</span>
                    </div>
                  )}
                  <Actions runId={runId} insight={i} viewer={viewer} canProduce={canProduce} onChange={acted} onEdit={setEditing} />
                  {restated && <Sources runId={runId} insight={i} roster={roster} />}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <div ref={list} tabIndex={-1} aria-labelledby="shortlist-title" className="outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:ring-inset">
        <div className="flex items-baseline justify-between gap-2 px-5 pt-4">
          <h3 id="shortlist-title" className="font-semibold">
            Shortlist
          </h3>
          <span className="text-xs text-muted-foreground">The top {SHORTLIST_SIZE} by rank</span>
        </div>
        {top.length === 0 ? (
          <p className="px-5 pt-2 pb-5 text-sm text-muted-foreground">Nothing on the shortlist yet.</p>
        ) : (
          <ol>
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
    </section>
  );
}
