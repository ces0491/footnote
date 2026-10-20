"""End-to-end check of the deployed pipeline, from outside, the way a browser follows a replay.

    uv run python scripts/smoke_live.py https://<web app> [--minute 81] [--speed 4]

Starts a run through the web app's API, waits until the processor has recorded it, joins the run's
Web PubSub group with the URL the API issues, fetches the snapshot, and listens until the run ends. It then checks that every event after
the snapshot arrived, in order (repeats from at-least-once delivery are counted and dropped, as the
browser drops them), that the run finished, and that the stored state agrees with the last push,
and reports the time from the replayer publishing each event to this machine receiving it. Latency is measured against the web app's clock (offset from the quickest of a few
round trips), so it includes the network path to wherever this runs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time

import aiohttp


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


async def listen(ws: aiohttp.ClientWebSocketResponse, offset: float) -> list[tuple[dict, float]]:
    """Every message with when it arrived, on the web app's clock (epoch ms)."""
    received: list[tuple[dict, float]] = []
    async for frame in ws:
        if frame.type != aiohttp.WSMsgType.TEXT:
            continue
        envelope = json.loads(frame.data)
        if envelope.get("type") != "message":
            continue
        message = envelope["data"]
        received.append((message, time.time() * 1000 + offset))
        if message["type"] == "run_end":
            break
    return received


def summary(label: str, values: list[float]) -> str:
    if not values:
        return f"{label}: no samples"
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    return f"{label}: median {statistics.median(ordered):.0f} ms, p95 {p95:.0f} ms, max {ordered[-1]:.0f} ms ({len(ordered)})"


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


async def main(base: str, minute: int, speed: int, timeout: float) -> int:
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
            listening = asyncio.create_task(listen(ws, offset))
            joined = await snapshot(session, base, run_id)
            try:
                timed = await asyncio.wait_for(listening, timeout)
            except TimeoutError:
                print(f"gave up waiting for the run to end after {timeout:.0f} s")
                return 1
        final = await snapshot(session, base, run_id)

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

    kinds = [m["type"] for m in received]
    print(
        f"joined at seq {base_seq}; received {len(events)} events ({repeats} repeated, dropped as the browser does), "
        f"{kinds.count('snapshot')} snapshot, {kinds.count('run_end')} run_end"
    )
    print(f"final: {view.get('phase')}, score {view.get('score')}, run status {final.get('status')}")
    report_latency(timed, run["started_at"])
    for failure in failures:
        print(f"FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="the web app's base URL")
    parser.add_argument("--minute", type=int, default=81)
    parser.add_argument("--speed", type=int, default=4, choices=(1, 2, 4))
    parser.add_argument("--timeout", type=float, default=1800.0, help="seconds to wait for the run to end")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.url.rstrip("/"), args.minute, args.speed, args.timeout)))
