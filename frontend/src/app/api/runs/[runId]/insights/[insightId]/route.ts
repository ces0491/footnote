import type { NextRequest } from "next/server";

import { deskActionRequest, type Draft, type InsightDetail, runIdPattern } from "@/lib/live/contract";
import { placeholders } from "@/lib/live/draft";
import { jsonBody } from "@/lib/server/body";
import { db } from "@/lib/server/db";
import { desk } from "@/lib/server/desk";

const INSIGHT_ID = /^[a-z0-9][a-z0-9_.-]{0,80}$/; // goal-e1586, distance-sal-10-10.0

function valid(runId: string, insightId: string): boolean {
  return runIdPattern.test(runId) && INSIGHT_ID.test(insightId);
}

/** Whether every placeholder in the draft names one of the moment's own facts. */
function usesOnly(draft: Draft, facts: Record<string, unknown>): boolean {
  const texts = [draft.headline, ...draft.casual.map((s) => s.text), ...draft.analyst.map((s) => s.text)];
  return texts.every((text) => placeholders(text).every((key) => key in facts));
}

// What the producer console needs for one card: the wording to start an edit from, with its
// placeholders, the moment's facts an edit may use, and the agents' runs on it, newest first, with
// the run in an earlier replay that wrote a draft this one reused. Agent runs outlive their replays.
// An agent's draft can use figures its match tools fetched beyond the moment's own facts; an edit
// can't, so an edit of such a draft starts from the template's wording.
export async function GET(_request: NextRequest, ctx: RouteContext<"/api/runs/[runId]/insights/[insightId]">) {
  const { runId, insightId } = await ctx.params;
  if (!valid(runId, insightId)) return Response.json({ error: "not a run or insight ID" }, { status: 400 });
  const { rows } = await db().query(
    `select i.facts, i.template, v.draft,
            coalesce((select jsonb_agg(to_jsonb(a) - 'run_id' - 'insight_id' - 'cache_key' - 'draft'
                                       order by a.started_at desc)
                        from agent_runs a where a.run_id = i.run_id and a.insight_id = i.insight_id), '[]'::jsonb)
              as agent_runs,
            (select to_jsonb(a) - 'run_id' - 'insight_id' - 'cache_key' - 'draft'
               from agent_runs a
              where (v.provenance ->> 'cached')::boolean and a.agent_run_id = v.provenance ->> 'agent_run_id'
                and a.run_id <> i.run_id) as reused_run
       from insights i
       join insight_versions v on v.run_id = i.run_id and v.insight_id = i.insight_id and v.version = i.version
      where i.run_id = $1 and i.insight_id = $2`,
    [runId, insightId],
  );
  const row = rows[0];
  if (!row) return Response.json({ error: "no such insight" }, { status: 404 });
  const facts = row.facts as Record<string, { display: string; about: string }>;
  const current = usesOnly(row.draft, facts);
  const body: InsightDetail = {
    draft: current ? row.draft : row.template,
    draft_from: current ? "current" : "template",
    facts: Object.entries(facts).map(([key, fact]) => ({ key, display: fact.display, about: fact.about })),
    agent_runs: row.agent_runs,
    reused_run: row.reused_run ?? null,
  };
  return Response.json(body, { headers: { "cache-control": "no-store" } });
}

// A producer's action on the card: { viewer, action: approve | kill | withdraw | redraft | edit,
// draft for an edit }. The desk decides whether this viewer may produce the replay, checks an edit
// as it checks an agent's draft, and pushes the changed card to every viewer of the run.
export async function POST(request: NextRequest, ctx: RouteContext<"/api/runs/[runId]/insights/[insightId]">) {
  const { runId, insightId } = await ctx.params;
  if (!valid(runId, insightId)) return Response.json({ error: "not a run or insight ID", problems: [] }, { status: 400 });
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return Response.json({ error: "send the request as application/json", problems: [] }, { status: 415 });
  }
  const body = await jsonBody(request);
  if ("response" in body) return body.response;
  const parsed = deskActionRequest.safeParse(body.value);
  if (!parsed.success) {
    return Response.json({ error: "an action and the viewer taking it are needed", problems: [] }, { status: 422 });
  }
  return desk(`/runs/${runId}/insights/${insightId}`, parsed.data);
}
