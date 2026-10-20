# Architecture

How the live pipeline runs on Azure: what each service does, how a replay flows through them, what
the services promise each other, and what it costs. The synthetic data it carries is described in
[data.md](data.md).

## The pipeline

```text
replayer ──AMQP──▶ Event Hubs (feed) ──▶ processor ──▶ Postgres
   ▲                                         │
   │ start / stop                            └──▶ Web PubSub (group per run) ──▶ browser
   │                                                                                │
web app (Next.js) ◀───────── snapshot, match metadata, client token ────────────────┘
```

| Service | Runs as | Does |
| --- | --- | --- |
| replayer (`src/footnote/replayer`) | Container App, internal ingress, one replica | Stands in for the data provider: plays the committed showcase feed into Event Hubs, one run per replay |
| processor (`src/footnote/processor`) | Container App, no ingress, one replica | Folds the feed into each run's match state, stores the feed and the state in Postgres, pushes every event with the state after it to the run's viewers |
| web (`frontend/`) | Container App, public ingress | Starts and stops replays, serves snapshots and match metadata from Postgres, issues Web PubSub client tokens, renders the live page |

All three run in one Container Apps environment on the Consumption profile. Images are built in the
container registry by `azd deploy` (remote build), so deploying needs no local Docker.

## A replay

A judge picks a jump point (kick-off, 23', 31', 60' or 81') and a speed (1×, 2× or 4×). The web app
asks the replayer for a run and gets back the run descriptor: its ID, start point, speed, the wall
time at which the start point is live, and the timeline parameters.

**Replay time.** The feed's timestamps follow the wall clock, including a fifteen-minute half-time
break. A replay keeps that pacing but shortens the break to 30 seconds. Replay seconds count from
kick-off along the shortened timeline (`src/footnote/live/timeline.py`). The browser has the same
mapping (`frontend/src/lib/live/timeline.ts`) and uses it to run the match clock between events.

**Backfill, then live.** The replayer first publishes a `run_start` control message, then every feed
message before the start point at once, marked as backfill, then the rest at the pace their
timestamps set, scaled by the speed. A jump starts 30 seconds before its minute. The processor folds
the backfill in without pushing it, then pushes one snapshot; from there it pushes each event. It
stores the run's state view only once the backfill is in, so a snapshot fetched while the backfill
is still being written has no view yet, where it would otherwise show the score from minutes before
the jump. At the end the replayer publishes `run_end` with the reason: finished, stopped, expired
(two hours), evicted (a seventh concurrent run replaces the oldest) or failed.

**Joining.** The browser fetches the run's snapshot from the web app's API first, and for a run that
has ended it stops there. For a run in progress it then joins the run's Web PubSub group, and fetches
the snapshot again each time a connection opens, because pushes sent while it had none are lost.
Pushes that arrive while a snapshot is on its way are held and applied on top of it. Each push
carries the score, phase, clock and stats after its event, so applying one is a replacement. A gap in
`seq` means a push was missed: the browser holds what follows and fetches the snapshot again.

## Contracts

The messages each boundary carries are documented once, in `src/footnote/live/contract.py`, with
the browser's types in `frontend/src/lib/live/contract.ts`.

- **Event Hubs.** The body is the feed message exactly as the provider published it, or a control
  message. Application properties carry `run_id`, `kind`, `published_at` and `backfill`. The
  partition key is the run ID, so a run's messages arrive in order.
- **Web PubSub.** `snapshot`, `event` and `run_end`, JSON. Events drop provider boilerplate and
  freeze frames, and carry timing (`published_at`, `enqueued_at`, `processed_at`) for latency
  measurement. Every event push fits one 2 KB billing unit: `tests/test_live.py` checks the largest
  in the showcase match.
- **Postgres.** `matches` (metadata), `runs` (descriptor and status), `feed_events` (every message
  each run processed) and `run_state` (the latest view). Migrations live in
  `src/footnote/db/migrations` and the processor applies them at start-up.

## Delivery and failure

Delivery from Event Hubs is at least once. The processor stores a batch's feed rows and the run's
state view in one transaction before pushing anything, then checkpoints in Blob Storage.

- A redelivered message is skipped: each run's state ignores a `seq` it has already applied, and
  feed rows are keyed on run and `seq`.
- If the store can't be written after three attempts, the processor drops the run from memory and
  lets the error propagate. Event Hubs redelivers from the last checkpoint and the run is rebuilt
  from its stored feed.
- A restarted processor rebuilds any run it meets from the stored feed, including a run whose
  `run_start` it reads again.
- A partition with no checkpoint yet is read from five minutes before the processor started, so a
  replay that began while a new revision was starting isn't lost.
- A failed push is logged and skipped; the browser's gap check recovers it.
- The replayer holds runs in memory, so a replayer restart ends the runs in progress. A clean
  shutdown publishes their `run_end`; a crash can't. Once a minute the processor ends, as failed, any
  run still marked running whose next message is more than five minutes past its schedule, and tells
  its viewers. The first check waits five minutes after the processor starts, so that a restarted
  processor has caught up on the hub before it judges any run.

Viewers can therefore receive a push twice, for example when a processor restart re-reads a batch
the old replica had already pushed. Every push carries its `seq`, and the browser drops one it has
already applied.

The processor and replayer each run exactly one replica. Scaling the processor out would work with
the checkpoint store's partition ownership, but each run's state would then move between replicas on
rebalancing; one replica keeps that out of scope.

## Latency

`scripts/smoke_live.py` follows a replay from outside the way a browser does and reports the time
from the replayer publishing each event to the client receiving it, using the timestamps every push
carries. Measured on 19 October 2026 from a client in South Africa, so the times include the network
path from westus3:

| Replay | Events | Median | p95 | Max |
| --- | --- | --- | --- | --- |
| from 23' at 4×, through half-time to full time | 1,458 | 227 ms | 303 ms | 1,345 ms |
| from 81' at 4× | 256 | 236 ms | 299 ms | 354 ms |
| from 81' at 4×, started as the processor restarted | 258 | 244 ms | 314 ms | 1,308 ms |

By stage, medians across those runs: publish to Event Hubs enqueue about 50 ms, enqueue to the
processor's push about 55 ms, and push to receipt 115–125 ms, most of it the network. The slowest
events came early in a replay: in the replay from 23', the 12 events in its first 10 seconds had a
maximum of 1,345 ms, and the 1,446 after them a maximum of 669 ms.

## Identity and access

No service uses a key, connection string or password. Local authentication is off on Event Hubs,
Web PubSub and the storage account, and Postgres accepts Microsoft Entra tokens only. Each container
app runs as its own user-assigned managed identity with these roles:

| Identity | Role | On |
| --- | --- | --- |
| replayer | Azure Event Hubs Data Sender | the `feed` event hub |
| processor | Azure Event Hubs Data Receiver | the `feed` event hub |
| processor | Storage Blob Data Contributor | the `checkpoints` container |
| processor | Web PubSub Service Owner | the Web PubSub resource |
| processor | Postgres Entra administrator | the server; owns the schema |
| web | Web PubSub Service Owner | the Web PubSub resource, to issue client tokens |
| web | `select` on `matches`, `runs`, `feed_events`, `run_state` | granted by the processor at start-up |
| all three | AcrPull | the container registry |

The browser's Web PubSub token joins one run's group and carries no roles, so a viewer can't
publish or join another group, and the web app issues one only for a run the processor has recorded.
The deploying user gets data-plane roles on Event Hubs, the checkpoint container and Web PubSub for
local development, and becomes a Postgres administrator when `AZURE_PRINCIPAL_NAME` is set.

Postgres admits Azure services through its firewall because Consumption-profile Container Apps have
no fixed outbound address; sign-in still needs a token for a role the server knows.

## Cost

Everything runs in **westus3**. List prices from the Azure Retail Prices API on 2026-10-19, in US
dollars, for 20 October to 10 November (22 days):

| Resource | Tier | Price | Estimate |
| --- | --- | --- | --- |
| Postgres flexible server | Burstable B1ms, 32 GB | $0.017/hour + $0.115/GB-month | $11.70 |
| Container Apps, three replicas always on | 0.25 vCPU, 0.5 GiB each | idle $0.000003/vCPU-s and /GiB-s; active $0.000024/vCPU-s; a monthly free grant | $10–14 |
| Event Hubs | Basic, 1 throughput unit | $0.015/hour + $0.028 per million events | $7.90 |
| Container registry | Basic | $0.1666/day | $3.70 |
| Log Analytics | pay as you go, capped at 0.2 GB/day | first 5 GB/month free, then $2.30/GB | $0–4 |
| Storage | Standard LRS, checkpoints only | | under $0.10 |
| Web PubSub | Free | $0 | $0 |
| **Total** | | | **$33–41** |

Web PubSub's Free tier allows 20 concurrent connections and 20,000 outbound messages a day. A viewer
watching a whole match at any speed receives about 1,830 messages (one per event plus the snapshot),
so the free tier covers about ten full-match viewers a day. Standard costs $1.61 a day; moving to it
for judging (27 October to 10 November) would add $24. A tier change between Free and Standard
takes the service offline for 30–60 minutes while its address changes, so it has to happen before
submission.

An Azure budget of US$100 covers 1 October to 31 December and emails at 50%, 80% and 100% of
actual spend and when the forecast passes 100%. It doesn't stop spending, so the design keeps fixed
costs low and the resource group is deleted after judging.
