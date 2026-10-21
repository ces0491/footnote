"""End-to-end check of the deployed pipeline, from outside, the way a browser follows a replay.

    uv run python scripts/smoke_live.py https://<web app> [--minute 81] [--speed 4]

Starts a run through the web app's API, waits until the processor has recorded it, joins the run's
Web PubSub group with the URL the API issues, fetches the snapshot, and listens until the run ends. It then checks that every event after
the snapshot arrived, in order (repeats from at-least-once delivery are counted and dropped, as the
browser drops them), that the run finished, that the stored state agrees with the last push, and
that the match-state timeline a browser builds from the pushes is the stored one. It reports the
largest push against Web PubSub's 2 KB billing unit and the time from the replayer publishing
each event to this machine receiving it. Latency is measured against the web app's clock (offset
from the quickest of a few round trips), so it includes the network path to wherever this runs.

For insights it checks that folding the insight pushes into the joined snapshot gives the versions
the store ends with, and reports how many cards the agents drafted, how long their drafts took to
replace the template's as this machine received them, and which fell back and why. It waits
`--settle` seconds after the run ends before the final snapshot, so drafts still in flight land.
It also times the template overlay: from the replayer publishing the feed message behind each
processor insight push (its `shown_seq`) to this machine receiving the push.

For delivery held to a viewer's playback it checks that the pushes the web app serves from the store
are the ones that were pushed, starting from the backfill's snapshot, and that the tracking for the
pitch view is served up to the live point and not beyond it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time

import aiohttp

from footnote.live.analysis import timeline_after

BILLING_UNIT = 2048  # bytes per Web PubSub outbound message unit


async def clock_offset(session: aiohttp.ClientSession, base: str) -> float:
    best = (float("inf"), 0.0)
    for _ in range(5):
        sent = time.time() * 1000
        async with session.get(f"{base}/api/time") as response:
            now = (await response.json())["now"]
        received = time.time() * 1000
        best = min(best, (received - sent, now - (sent + received) / 2))
    return best[1]


async def snapshot(session: aiohttp.ClientSession, base: str, run_id: str) -> dict:
    for _ in range(30):
        async with session.get(f"{base}/api/runs/{run_id}") as response:
            if response.status == 200:
                return await response.json()
        await asyncio.sleep(0.5)
    raise RuntimeError(f"run {run_id} never appeared in the store")


async def stored_pushes(session: aiohttp.ClientSession, base: str, run_id: str) -> list[dict]:
    """Every push the web app serves from the store for the run, page by page."""
    pushes: list[dict] = []
    after = 0
    while True:
        async with session.get(f"{base}/api/runs/{run_id}/pushes", params={"after": after}) as response:
            page = await response.json()
        pushes += page["pushes"]
        if not page["more"] or not page["pushes"]:
            return pushes
        after = page["pushes"][-1]["seq"]


async def tracking_frames(
    session: aiohttp.ClientSession, base: str, run_id: str, layout: dict, period: int, t: float
) -> int:
    """How many frames the web app serves of the tracking chunk holding `t` seconds into `period`."""
    chunk = int(t * layout["frame_rate"]) // layout["frames_per_chunk"]
    async with session.get(f"{base}/api/runs/{run_id}/tracking/{period}/{chunk}") as response:
        if response.status != 200:
            return -1
        return len(await response.read()) // (layout["values_per_frame"] * 2)


def moment(replay: float, timeline: dict) -> tuple[int, float]:
    """The period and seconds into it of a replay second, as lib/live/timeline.ts has it."""
    if replay <= timeline["first_half_end"]:
        return 1, max(0.0, replay)
    return 2, max(0.0, replay - timeline["first_half_end"] - timeline["half_time"])


async def listen(ws: aiohttp.ClientWebSocketResponse, offset: float, sizes: list[int]) -> list[tuple[dict, float]]:
    """Every message with when it arrived, on the web app's clock (epoch ms); `sizes` gets each
    message's length in bytes as sent."""
    received: list[tuple[dict, float]] = []
    async for frame in ws:
        if frame.type != aiohttp.WSMsgType.TEXT:
            continue
        envelope = json.loads(frame.data)
        if envelope.get("type") != "message":
            continue
        data = envelope["data"]
        message = json.loads(data) if isinstance(data, str) else data  # pushes travel as JSON text
        received.append((message, time.time() * 1000 + offset))
        # The message as sent, which is what Web PubSub bills; the frame around it escapes its quotes.
        sizes.append(len(data.encode()) if isinstance(data, str) else len(json.dumps(data, separators=(",", ":"))))
        if message["type"] == "run_end":
            break
    return received


def summary(label: str, values: list[float]) -> str:
    if not values:
        return f"{label}: no samples"
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    return f"{label}: median {statistics.median(ordered):.0f} ms, p95 {p95:.0f} ms, max {ordered[-1]:.0f} ms ({len(ordered)})"


def report_insights(joined: dict, final: dict, timed: list[tuple[dict, float]], failures: list[str]) -> None:
    """Insight pushes against the store: versions, agent drafts and their timing, fallbacks."""
    pushes = [(m, arrived) for m, arrived in timed if m["type"] == "insight"]
    stored = {i["insight_id"]: i for i in final.get("insights", []) if i["live"]}
    held = {i["insight_id"]: i for i in joined.get("insights", [])}
    rev = joined.get("insight_rev", 0)
    # Timed from the template version a draft replaced: a restated insight's clock starts again. A
    # version's later pushes (its translations arriving, say) aren't another draft.
    template_at: dict[str, float] = {}
    to_agent: list[float] = []
    timed_versions: set[tuple[str, int]] = set()
    for m, arrived in pushes:
        insight = m["insight"]
        version = (insight["insight_id"], insight["version"])
        if insight["source"] == "template":
            template_at[insight["insight_id"]] = arrived
        elif (
            not insight["provenance"].get("cached")
            and insight["insight_id"] in template_at
            and version not in timed_versions
        ):
            to_agent.append(arrived - template_at[insight["insight_id"]])
            timed_versions.add(version)
    for m, _ in sorted(pushes, key=lambda p: p[0]["rev"]):
        if m["rev"] > rev:
            held[m["insight"]["insight_id"]] = m["insight"]
            rev = m["rev"]
    revs = [m["rev"] for m, _ in pushes]
    out_of_order = sum(b < a for a, b in zip(revs, revs[1:], strict=False))
    behind = [k for k, v in stored.items() if held.get(k, {}).get("version") != v["version"]]
    if behind:
        failures.append(f"insights folded from the pushes behind the store: {behind[:6]}")
    states: dict[str, int] = {}
    for insight in stored.values():
        key = (
            "agent, reused"
            if insight["source"] == "agent" and insight["provenance"].get("cached")
            else ("agent" if insight["source"] == "agent" else f"template ({insight['agent_state']})")
        )
        states[key] = states.get(key, 0) + 1
    print(
        f"insights: {len(pushes)} pushed ({out_of_order} out of revision order), {len(stored)} live in the store: {states}"
    )
    print(summary("  template to agent draft, as received here", to_agent))
    for insight in stored.values():
        if insight["agent_state"] == "fallback":
            print(f"  fell back: {insight['insight_id']}: {insight['agent_note']}")


def report_overlay_latency(received: list[tuple[dict, float]], started_at: float) -> None:
    """The template overlay: from the replayer publishing the feed message behind a processor insight
    push to this machine receiving the push.

    The processor pushes an insight change straight after the events of the batch that caused it,
    with the template's wording; only its pushes carry timing (the agents' and the desk's come later,
    by design). An insight's first push is the card arriving, found at its `shown_seq`. A later one
    is VAR or a correction flagging or restating it, or a decision ending it early, which doesn't move
    `shown_seq`: it is timed from the last event that arrived before it, the batch's.
    """
    published = {
        m["seq"]: m["timing"]["published_at"]
        for m, _ in received
        if m["type"] == "event" and m.get("timing", {}).get("published_at")
    }
    first: list[float] = []
    later: list[float] = []
    early: list[float] = []
    seen: set[str] = set()
    last_event: float | None = None
    for m, arrived in received:
        if m["type"] == "event":
            last_event = published.get(m["seq"], last_event)
            continue
        if m["type"] != "insight" or not m.get("timing", {}).get("processed_at"):
            continue
        insight = m["insight"]
        known = insight["insight_id"] in seen
        seen.add(insight["insight_id"])
        sent = last_event if known else published.get(insight["shown_seq"])
        if sent is None:
            continue
        latency = arrived - sent
        (later if known else first).append(latency)
        if sent - started_at < 10_000:
            early.append(latency)
    print(summary("template overlay, publish to receipt: new cards", first))
    print(summary("  changes to cards (VAR, corrections)", later))
    print(summary("  in the first 10 s, while the backfill is processed", early))


def report_latency(received: list[tuple[dict, float]], started_at: float) -> None:
    """Publish to receipt, and each stage of it, from the timestamps every event push carries."""
    stages: dict[str, list[float]] = {"publish to enqueue": [], "enqueue to push": [], "push to receipt": []}
    early: list[float] = []
    later: list[float] = []
    for message, arrived in received:
        timing = message.get("timing", {})
        if message["type"] != "event" or not timing.get("published_at"):
            continue
        published, enqueued, pushed = timing["published_at"], timing.get("enqueued_at"), timing.get("processed_at")
        (early if published - started_at < 10_000 else later).append(arrived - published)
        if enqueued and pushed:
            stages["publish to enqueue"].append(enqueued - published)
            stages["enqueue to push"].append(pushed - enqueued)
            stages["push to receipt"].append(arrived - pushed)
    print(summary("publish to receipt, all events", early + later))
    print(summary("  in the first 10 s, while the backfill is processed", early))
    print(summary("  after that", later))
    for label, values in stages.items():
        print(summary(f"  stage: {label}", values))


async def main(base: str, minute: int, speed: int, timeout: float, settle: float) -> int:
    async with aiohttp.ClientSession() as session:
        offset = await clock_offset(session, base)
        async with session.post(f"{base}/api/runs", json={"start_minute": minute, "speed": speed}) as response:
            if response.status != 201:
                print(f"starting a run failed: HTTP {response.status} {await response.text()}")
                return 1
            run = await response.json()
        run_id = run["run_id"]
        print(
            f"run {run_id}: from {minute}' at {speed}x, backfill to seq {run['backfill_seq']}, last seq {run['last_seq']}"
        )
        # Like the browser: the web app issues a client URL once the processor has recorded the run.
        await snapshot(session, base, run_id)
        async with session.get(f"{base}/api/runs/{run_id}/negotiate") as response:
            if response.status != 200:
                print(f"negotiate failed: HTTP {response.status} {await response.text()}")
                return 1
            url = (await response.json())["url"]

        async with session.ws_connect(url, protocols=("json.webpubsub.azure.v1",)) as ws:
            sizes: list[int] = []
            listening = asyncio.create_task(listen(ws, offset, sizes))
            joined = await snapshot(session, base, run_id)
            # The pitch view's tracking: there at the start of the replay, nothing a minute beyond it.
            layout = joined.get("tracking")
            gate = None
            if layout:
                period, t = moment(run["start_replay"], run["timeline"])
                gate = (
                    await tracking_frames(session, base, run_id, layout, period, t),
                    await tracking_frames(session, base, run_id, layout, period, t + 60),
                )
            try:
                timed = await asyncio.wait_for(listening, timeout)
            except TimeoutError:
                print(f"gave up waiting for the run to end after {timeout:.0f} s")
                return 1
        await asyncio.sleep(settle)
        final = await snapshot(session, base, run_id)
        kept = await stored_pushes(session, base, run_id)

    received = [m for m, _ in timed]
    # Like the browser: the state to build on is the newer of the fetched snapshot (empty until the
    # backfill is stored) and any snapshot pushed after the backfill.
    pushed_snapshots = [m["seq"] for m in received if m["type"] == "snapshot"]
    base_seq = max([(joined.get("view") or {}).get("seq", 0), *pushed_snapshots])
    failures = []
    events = [m for m in received if m["type"] == "event"]
    seqs = [m["seq"] for m in events]
    # Delivery is at least once: a processor restart can push a batch twice. Like the browser, keep
    # the first arrival of each seq and drop repeats.
    first_arrivals = list(dict.fromkeys(s for s in seqs if s > base_seq))
    repeats = len(seqs) - len(set(seqs))
    expected = list(range(base_seq + 1, run["last_seq"] + 1))
    if first_arrivals != expected:
        missing = sorted(set(expected) - set(first_arrivals))
        failures.append(
            f"events after the snapshot out of order or missing: missing {missing[:10]}, {len(first_arrivals)} of {len(expected)}"
        )
    end = next((m for m in received if m["type"] == "run_end"), None)
    if end is None or end["reason"] != "finished":
        failures.append(f"the run did not finish: {end}")
    view = final.get("view") or {}
    last = max(events, key=lambda m: m["seq"], default=None)
    if last and (view.get("seq") != last["seq"] or view.get("score") != last["score"]):
        failures.append("the stored state disagrees with the last push")
    # Like the browser: extend the starting snapshot's state timeline with each push's state.
    start = max(
        [joined.get("view") or {}] + [m for m in received if m["type"] == "snapshot"], key=lambda v: v.get("seq", 0)
    )
    if "state_timeline" in view:
        timeline = list(start.get("state_timeline") or [])
        applied = start.get("seq", 0)
        for m in sorted(events, key=lambda m: m["seq"]):
            if m["seq"] == applied + 1:
                timeline = timeline_after(timeline, m.get("match_state"))
                applied = m["seq"]
        if timeline != view["state_timeline"]:
            failures.append("the state timeline built from the pushes disagrees with the stored one")
    else:
        print("the stored state has no match-state timeline: is the processor running without its models?")

    # What the store serves a viewer whose stream runs behind is what was pushed, timing aside.
    sent = {
        m["seq"]: {k: v for k, v in m.items() if k != "timing"} for m in received if m["type"] in ("event", "snapshot")
    }
    by_seq = {m["seq"]: m for m in kept}
    differ = [seq for seq, m in sent.items() if seq in by_seq and by_seq[seq] != m]
    if differ:
        failures.append(f"stored pushes differ from the ones pushed at seq {differ[:6]}")
    kept_events = [m["seq"] for m in kept if m["type"] == "event"]
    if kept_events != list(range(run["backfill_seq"] + 1, run["last_seq"] + 1)):
        failures.append(f"the stored pushes don't cover every event after the backfill ({len(kept_events)} kept)")
    if run["backfill_seq"] and (not kept or kept[0]["type"] != "snapshot" or kept[0]["seq"] != run["backfill_seq"]):
        failures.append("the stored pushes don't start with the backfill's snapshot")
    if gate is None:
        failures.append("the snapshot carries no tracking layout for the pitch view")
    elif gate[0] <= 0 or gate[1] != 0:
        failures.append(f"tracking frames served at the start and a minute beyond it: {gate}; expected some, then none")

    kinds = [m["type"] for m in received]
    print(
        f"joined at seq {base_seq}; received {len(events)} events ({repeats} repeated, dropped as the browser does), "
        f"{kinds.count('snapshot')} snapshot, {kinds.count('run_end')} run_end"
    )
    print(f"final: {view.get('phase')}, score {view.get('score')}, run status {final.get('status')}")
    print(f"largest push {max(sizes, default=0)} bytes; {sum(n > BILLING_UNIT for n in sizes)} over {BILLING_UNIT}")
    print(f"state timeline: {len(view.get('state_timeline') or [])} spells")
    print(f"stored pushes: {len(kept)}; tracking frames at the start and a minute beyond: {gate}")
    report_latency(timed, run["started_at"])
    report_overlay_latency(timed, run["started_at"])
    report_insights(joined, final, timed, failures)
    for failure in failures:
        print(f"FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="the web app's base URL")
    parser.add_argument("--minute", type=int, default=81)
    parser.add_argument("--speed", type=int, default=4, choices=(1, 2, 4))
    parser.add_argument("--timeout", type=float, default=1800.0, help="seconds to wait for the run to end")
    # The replayer already waits after the last message before ending the run (FINISH_LINGER).
    parser.add_argument("--settle", type=float, default=15.0, help="seconds to wait after the end for agent drafts")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.url.rstrip("/"), args.minute, args.speed, args.timeout, args.settle)))
