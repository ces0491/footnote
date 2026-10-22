"use client";

import { Bot } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { AgentRunSummary, DeskRefusal, Insight, InsightDetail, InsightMessage } from "@/lib/live/contract";
import { asLines, edited, fill } from "@/lib/live/draft";

async function loadDetail(runId: string, insightId: string): Promise<InsightDetail> {
  const response = await fetch(`/api/runs/${runId}/insights/${insightId}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as InsightDetail;
}

/**
 * The producer's own wording for a card. Figures go in as placeholders, `{fact.key}`, filled in by
 * code; the desk checks an edit as it checks an agent's draft, and says what failed. The console
 * owns the dialog, so it stays open while the card moves on the shortlist or leaves it. The wording
 * is loaded once each time it opens: if the card changes meanwhile (a correction, a new draft), the
 * dialog says so and keeps what the producer typed.
 */
export function EditDialog({
  runId,
  insight,
  viewer,
  open,
  onOpenChange,
  onSaved,
}: {
  runId: string;
  insight: Insight | null; // the card being edited, as it now stands
  viewer: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (message: InsightMessage) => void;
}) {
  const [detail, setDetail] = useState<InsightDetail | null>(null);
  const [loadedVersion, setLoadedVersion] = useState<number | null>(null);
  const [reloads, setReloads] = useState(0);
  const [headline, setHeadline] = useState("");
  const [casual, setCasual] = useState("");
  const [analyst, setAnalyst] = useState("");
  const [problems, setProblems] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const insightId = insight?.insight_id ?? null;
  // The card's version as it renders, read when the wording loads without reloading on each change.
  const version = useRef<number | null>(insight?.version ?? null);
  useEffect(() => {
    version.current = insight?.version ?? null;
  });

  // The console mounts a fresh dialog for each card, so there is nothing to reset here.
  useEffect(() => {
    if (!open || insightId === null) return;
    let live = true;
    const asked = version.current;
    loadDetail(runId, insightId)
      .then((loaded) => {
        if (!live) return;
        setDetail(loaded);
        setLoadedVersion(asked);
        setHeadline(loaded.draft.headline);
        setCasual(asLines(loaded.draft.casual));
        setAnalyst(asLines(loaded.draft.analyst));
      })
      .catch((cause) => live && setError(`Couldn't load the card: ${cause instanceof Error ? cause.message : cause}`));
    return () => {
      live = false;
    };
  }, [open, runId, insightId, reloads]);

  const fields = Object.fromEntries((detail?.facts ?? []).map((f) => [f.key, f.display]));
  const changed = detail !== null && insight !== null && loadedVersion !== null && insight.version !== loadedVersion;

  async function save() {
    if (!detail || insightId === null) return;
    setSaving(true);
    setProblems([]);
    setError(null);
    try {
      const response = await fetch(`/api/runs/${runId}/insights/${insightId}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "edit", viewer, draft: edited(detail.draft, headline, casual, analyst) }),
      });
      const body = (await response.json()) as InsightMessage | DeskRefusal;
      if (!response.ok || "error" in body) {
        const refusal = body as DeskRefusal;
        setError(refusal.error);
        setProblems(refusal.problems ?? []);
        return;
      }
      onSaved(body);
      onOpenChange(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open && insight !== null} onOpenChange={onOpenChange}>
      {/* The console moves focus to the card when the dialog closes. */}
      <DialogContent className="max-w-2xl" onCloseAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Edit the card</DialogTitle>
          <DialogDescription>
            Put figures in as placeholders, such as {"{moment.minute}"}: code fills them in, and the edit passes the same
            checks as an agent&apos;s draft. One sentence a line.
            {detail?.draft_from === "template" && " The agent's draft used figures beyond the moment's own, so this starts from the template."}
          </DialogDescription>
        </DialogHeader>
        {changed && (
          <Alert>
            <AlertTitle>The card has changed since you opened it</AlertTitle>
            <AlertDescription>
              <p>A correction or a new draft came in. Your text stays here, and it is checked against the card as it now stands.</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() => {
                  setDetail(null);
                  setProblems([]);
                  setError(null);
                  setReloads((n) => n + 1);
                }}
              >
                Start again from the new wording
              </Button>
            </AlertDescription>
          </Alert>
        )}
        {!detail && !error && <p className="text-muted-foreground">Loading…</p>}
        {detail && (
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="edit-headline">Headline</Label>
              <Textarea id="edit-headline" value={headline} onChange={(e) => setHeadline(e.target.value)} rows={1} />
              <p className="text-xs text-muted-foreground">Reads: {fill(headline, fields)}</p>
            </div>
            <div className="grid gap-1.5">
              {/* A recap tells a half's story, so it gets more room (src/footnote/insights/draft.py, limits_for). */}
              <Label htmlFor="edit-casual">
                For casual fans ({insight?.kind === "recap" ? "one to three sentences" : "one or two sentences"})
              </Label>
              <Textarea id="edit-casual" value={casual} onChange={(e) => setCasual(e.target.value)} rows={2} />
              <p className="text-xs text-muted-foreground">Reads: {fill(casual.replaceAll("\n", " "), fields)}</p>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="edit-analyst">For analysts (one to three sentences)</Label>
              <Textarea id="edit-analyst" value={analyst} onChange={(e) => setAnalyst(e.target.value)} rows={3} />
              <p className="text-xs text-muted-foreground">Reads: {fill(analyst.replaceAll("\n", " "), fields)}</p>
            </div>
            <details className="text-xs">
              <summary className="cursor-pointer font-medium">The moment&apos;s facts ({detail.facts.length})</summary>
              <dl className="mt-2 grid max-h-48 grid-cols-[auto_1fr] gap-x-3 gap-y-1 overflow-y-auto">
                {detail.facts.map((f) => (
                  <div key={f.key} className="contents">
                    <dt>
                      <code>{`{${f.key}}`}</code>
                    </dt>
                    <dd className="text-muted-foreground">
                      {f.display} <span className="opacity-70">({f.about})</span>
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          </div>
        )}
        {(error || problems.length > 0) && (
          <Alert variant="destructive">
            <AlertTitle>{error ?? "The edit didn't pass the checks"}</AlertTitle>
            {problems.length > 0 && (
              <AlertDescription>
                <ul className="list-disc pl-4">
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </AlertDescription>
            )}
          </Alert>
        )}
        <DialogFooter>
          <Button onClick={save} disabled={!detail || saving}>
            {saving ? "Checking…" : "Check and save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const OUTCOME: Record<string, string> = {
  accepted: "Accepted",
  rejected: "Failed the checks",
  timeout: "Too slow",
  error: "Failed",
  superseded: "Superseded by a correction",
};

/** What the agents did on a card: each run's outcome, cost, the tools it called and what failed. */
export function AgentRunsDialog({ runId, insight }: { runId: string; insight: Insight }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<InsightDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    loadDetail(runId, insight.insight_id)
      .then((loaded) => live && setDetail(loaded))
      .catch((cause) => live && setError(cause instanceof Error ? cause.message : String(cause)));
    return () => {
      live = false;
    };
  }, [open, runId, insight.insight_id, insight.version, insight.agent_state]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="xs" className="-mx-1 px-1 font-normal text-muted-foreground hover:bg-transparent">
          <Bot /> Agent runs
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>The agents on “{insight.card.headline}”</DialogTitle>
          <DialogDescription>
            Each run read the match through the MCP match tools and drafted with placeholders; code checked every
            draft before it could replace the template.
          </DialogDescription>
        </DialogHeader>
        {error && <p className="text-destructive">Couldn&apos;t load the runs: {error}</p>}
        {!detail && !error && <p className="text-muted-foreground">Loading…</p>}
        {detail && detail.agent_runs.length === 0 && !detail.reused_run && (
          <p className="text-muted-foreground">
            No agent has run on this card{insight.provenance.cached ? ": its draft was reused from an earlier replay." : "."}
          </p>
        )}
        {detail && detail.agent_runs.length > 0 && (
          <ol className="space-y-3">
            {detail.agent_runs.map((r) => (
              <RunEntry key={r.agent_run_id} run={r} />
            ))}
          </ol>
        )}
        {detail?.reused_run && (
          <section className="space-y-2">
            <h3 className="text-sm font-medium">The run in an earlier replay that wrote the draft reused here</h3>
            <ol>
              <RunEntry run={detail.reused_run} />
            </ol>
          </section>
        )}
      </DialogContent>
    </Dialog>
  );
}

function RunEntry({ run: r }: { run: AgentRunSummary }) {
  return (
    <li className="space-y-1.5 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={r.outcome === "accepted" ? "secondary" : "outline"}>{r.outcome ? OUTCOME[r.outcome] : "Drafting"}</Badge>
        <span className="text-xs text-muted-foreground tabular-nums">
          {[
            r.attempts !== null && `${r.attempts} ${r.attempts === 1 ? "attempt" : "attempts"}`,
            r.latency_ms !== null && `${(r.latency_ms / 1000).toFixed(1)} s`,
            r.input_tokens !== null && `${r.input_tokens.toLocaleString()} tokens in`,
            r.output_tokens !== null && `${r.output_tokens.toLocaleString()} out`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </div>
      {r.tool_calls && r.tool_calls.length > 0 && (
        <ul className="space-y-0.5 text-xs">
          {r.tool_calls.map((call, i) => (
            <li key={i} className="font-mono">
              {call.name}({Object.entries(call.arguments ?? {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})
            </li>
          ))}
        </ul>
      )}
      {r.problems && r.problems.length > 0 && (
        <ul className="list-disc pl-4 text-xs text-muted-foreground">
          {r.problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
      {r.error && <p className="text-xs text-muted-foreground">{r.error}</p>}
    </li>
  );
}
