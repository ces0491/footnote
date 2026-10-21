# Architecture

How the live pipeline runs on Azure: what each service does, how a replay flows through them, what
the services promise each other, and what it costs. The synthetic data it carries is described in
[data.md](data.md); how moments become cards, the agents that word them and the producer's desk, in
[insights.md](insights.md); what viewers get for each card, and when, in [overlay.md](overlay.md).

## The pipeline

```text
replayer ──AMQP──▶ Event Hubs (feed) ──▶ processor ──▶ Postgres ◀──── jobs, versions ────┐
   ▲                                         │            │ notify                     │
   │ start / stop                            │            ▼                            │
   │                                         │       agents service ── MCP ──▶ match tools
   │                                         │            │  ├──── Responses API ──▶ Foundry (gpt-5-mini)
   │                                         │            │  ├──── cards in English ──▶ Azure AI Translator
   │                                         │            │  └──── traces ──▶ Application Insights
   │                                         ▼            ▼
   │                               Web PubSub (group per run) ──▶ browser
   │                                                                │
web app (Next.js) ◀── snapshot, stored pushes, tracking, evidence, client token ┘
   └──── the producer's actions ──▶ agents service (the producer's desk)
```

| Service | Runs as | Does |
| --- | --- | --- |
| replayer (`src/footnote/replayer`) | Container App, internal ingress, one replica | Stands in for the data provider: plays the committed showcase feed into Event Hubs, one run per replay |
| processor (`src/footnote/processor`) | Container App, no ingress, one replica | Folds the feed into each run's match state, with pass difficulty, the estimated match state and figures from the tracking; finds and ranks the run's insights; stores the feed (each live row with the push viewers were sent), the state and the insights in Postgres, and the match's tracking for the pitch view; pushes every event with the state after it, and every insight change, to the run's viewers |
| agents (`src/footnote/agents`) | Container App, internal ingress, one replica | Serves the match tools over MCP on localhost (`src/footnote/tools`), and drafts the cards insights want with Agent Framework writers on Foundry; code checks each draft; stores and pushes the accepted ones, or says why the template stands. Translates the cards viewers see into Spanish and French with Azure AI Translator, checked by code. Serves the producer's desk to the web app: approves, edits, kills and withdraws cards for the viewer who started the replay. Traces each card it drafts and each batch it translates to Application Insights |
| web (`frontend/`) | Container App, public ingress | Starts replays, and stops one for the browser that started it; serves snapshots (with insights), the event and insight pushes stored for a run, the tracking up to its live point, match metadata and the events behind an insight from Postgres; passes producer actions to the desk; issues Web PubSub client tokens; renders the fan view and the producer console |

All four run in one Container Apps environment on the Consumption profile. The model is a Global
Standard deployment of gpt-5-mini in a Foundry project, created by the same Bicep. Images are built in the
container registry by `azd deploy` (remote build), so deploying needs no local Docker, except on a
subscription running on free credits, where the registry's builds are paused and azd builds locally.
azd deploys the processor before the agents service and the web app (`uses` in `azure.yaml`): the
processor creates their database roles when it starts, and the agents service can't start without its
role.

## A replay

A judge picks a jump point (kick-off, 23', 31', 60' or 81') and a speed (1×, 2× or 4×). The web app
asks the replayer for a run and gets back the run descriptor: its ID, start point, speed, the wall
time at which the start point is live, and the timeline parameters. The request carries the
anonymous ID the browser goes by, and a viewer's new replay replaces their previous one, so trying
the jump points in turn never pushes anyone else's replay out. It also says how the run's graphics
are approved: by the producer when the replay starts from the producer's profile, automatically
otherwise. The replayer passes both to the processor in `run_start`, outside the descriptor every
viewer can read, and the processor records them with the run: only the viewer who started a replay
may produce it ([insights.md](insights.md#the-producers-desk)), and only they may stop it, which the
replayer checks against the ID it keeps with the run.

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
the jump. At the end the replayer publishes `run_end` with the reason: finished, stopped (by the
viewer, or by their next replay), expired (two hours), evicted (a seventh concurrent run replaces
the oldest) or failed. A finished run's `run_end` comes 60 seconds after its last message: the
full-time recap is found at the final whistle, and the agents give up a job once its run has ended,
when the translator and the producer's desk stop too and pages stop listening, so its draft, its
translations and, in a replay the producer approves by hand, its approval need the run still open to
reach them.

**What the processor works out.** Beside the counts, each run's state carries what the models in
`src/footnote/interpret` read from the feed and the tracking ([models.md](models.md)): each pass's
difficulty, every player's passing line, the match state as of five seconds ago with a timeline of
it and each side's share of the last five minutes it held a state of its own (counted each second,
as the insights count it), distance covered and top speeds, and tags for sprints and distance
milestones. The tracking
file ships in the processor's image and stands in for a tracking feed: the processor reads it
against each event's clock, so a run never sees positions from beyond the point its feed has
reached. The fitted parameters ship with the code, and the answer key stays out of the image.

**Insights.** As each message is folded, the moment finder looks at the run's state and starts an
insight for a goal, a VAR check, a spell of the match state, a hard pass or a sprint, ranked and
worded by its template; later messages can flag or restate one (a VAR decision, a correction from
the provider). The processor stores each change with the feed rows that caused it and pushes it.
An insight that wants an agent's draft is left pending, and the processor notifies the agents
service on the `footnote_agents` Postgres channel. [insights.md](insights.md) has the rules.

**Joining.** The browser fetches the run's snapshot from the web app's API (its status, insights,
match metadata and tracking layout) together with the pushes stored after the last event it has
(the first time, the snapshot at the end of the backfill and every event since) and the insight
pushes stored after the last revision it has, which give it each card's earlier states. For a run
that has ended it stops there. For a run in progress it then joins the run's Web PubSub group, and does the
same again each time a connection opens, because pushes sent while it had none are lost. Pushes that
arrive while that is on its way are held and applied on top. Each push carries the score, phase,
clock and stats after its event, so applying one is a replacement. A gap in `seq` means a push was
missed: the browser holds what follows and fetches what it lacks.

**Playback.** From the backfill's snapshot and every event since, a page can show the match as of
any moment of the replay. The producer works live. A fan's stream runs behind live by the delay
they set, so their page shows the match folded up to the last event their playback has reached, and
each card as it stood then ([overlay.md](overlay.md#when-an-item-shows)). The pitch view draws the
tracking at the same moment: it fetches it in five-second chunks around the viewer's playback, and
the web app cuts each chunk at the run's live point, so nobody is sent positions from beyond it. A
chunk live is still inside is fetched again every 750 ms, or every 250 ms when playback is under
1.2 seconds of real time behind live, as a 3-second delay is at 4×. Once a run has ended, live stays
where it ended: a delayed stream plays on to there and asks for nothing beyond it. A phone draws no
pitch view and fetches no tracking.

Once the page shows a run it keeps showing it. A fetch that fails is retried with backoff, and the
page says the connection is in trouble meanwhile. If the push connection can't be opened (the free
tier allows 20) the page fetches what it lacks every few seconds instead and tries the connection
again every half minute; it does the same while the client reconnects. It runs one fetch at a time:
a poll while one is on its way is answered by fetching again when it lands, so a slow fetch is never
cancelled for a newer one. Once the run has ended the page stops connecting and polling, including
an attempt that was on its way when the end arrived.

## Contracts

The messages each boundary carries are documented once, in `src/footnote/live/contract.py`, with
the browser's types in `frontend/src/lib/live/contract.ts`.

- **Event Hubs.** The body is the feed message exactly as the provider published it, or a control
  message. Application properties carry `run_id`, `kind`, `published_at` and `backfill`. The
  partition key is the run ID, so a run's messages arrive in order.
- **Web PubSub.** `snapshot`, `event` and `run_end`, compact JSON sent as text, so the bytes billed
  are the bytes the tests measure (the SDK's own JSON encoding adds a space after every comma and
  colon). Events drop provider boilerplate and freeze frames, and carry timing (`published_at`,
  `enqueued_at`, `processed_at`) for latency measurement. An event push also carries the match state after it, a pass's difficulty, the line
  of the player on the event and any tags that fell due; the snapshot carries the state timeline,
  every player's line and the tags so far. Each event push also says when the provider published
  it, in replay seconds, and whether play is stopped after it. The browser extends the timeline from
  each push by the rule the processor uses, so the two agree (`tests/fixtures/state_timeline.json` is
  checked on both sides). Every event push fits one 2 KB billing unit: `tests/test_live.py` and
  `tests/test_analysis.py` check the largest in the showcase match.
- **Web PubSub, insights.** `insight` carries one changed insight, an item of the overlay contract
  ([overlay.md](overlay.md)), and `rev`, the run's insight revision the change made. The processor,
  the agents service and the producer's desk all push them; the browser applies revisions in order
  and fetches the snapshot after a gap. An item carries every fact's text for graphics systems and,
  once translated, its Spanish and French, so the larger ones take two billing units or three: in a
  replay from 81' on 21 October, 17 of 40 insight pushes took two and the full-time recap with both
  translations (4,306 bytes) three, against 256 events in one unit each.
- **Postgres.** `matches` (metadata and the tracking layout), `tracking_chunks` (the tracking for
  the pitch view, five seconds a row, `src/footnote/live/pitch.py`), `runs` (descriptor, status,
  insight revision, who started it and how its graphics are approved), `feed_events` (every message
  each run processed, and with each live one the push viewers were sent), `run_state` (the latest
  view), `insights` and `insight_versions` (every version of each card: template, agent or
  producer), `insight_pushes` (every insight change pushed, by revision), `agent_runs` (every agent
  run: outcome, tokens, latency, tool calls), `agent_cache` (accepted drafts reused across
  replays), `card_translations` (each card version's Spanish and French, or what failed the check)
  and `translation_cache` (translations reused across replays). Migrations live in
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
- An event that isn't a replayer message (one sent from the portal, say) is logged and skipped. A
  message the processor can't fold fails the same way however often it is read, so it isn't left
  to redelivery, which would hold up its partition, and every run on it, until the hub's one-day
  retention dropped it. Its run keeps what came before, is ended as failed, and its later messages
  are skipped.
- A failed push is logged and skipped; the browser's gap check fetches the missing events from the
  store, and the snapshot for a missing insight. A lost `run_end` isn't recovered: the page shows the
  run as still going until it next fetches the snapshot.
- The replayer holds runs in memory, so a replayer restart ends the runs in progress. A clean
  shutdown publishes their `run_end`; a crash can't. Once a minute the processor ends, as failed, any
  run still marked running whose next message is more than five minutes past its schedule, and tells
  its viewers. The first check waits five minutes after the processor starts, so that a restarted
  processor has caught up on the hub before it judges any run.

Viewers can therefore receive a push twice, for example when a processor restart re-reads a batch
the old replica had already pushed. Every push carries its `seq`, and the browser drops one it has
already applied.

The agents service claims pending insights with `for update skip locked` under a lease, so a
crashed worker's job is claimed again once the lease runs out, and a job that has been claimed
three times falls back to its template. Writing a draft locks the insight and checks its facts are
the ones the job started from: a correction that restated the insight in the meantime has queued a
fresh job, with its own wait and claims, so the stale draft is dropped. Jobs whose replay has ended are given up. A missed
notification costs at most five seconds: the service also looks for jobs on a timer.

The producer's desk refuses an action from anyone but the viewer who started the replay, on a
replay that has ended, or that the card's status doesn't allow; an approval while an agent is
drafting the card; a redraft of a card on air with wording the producer approved, or past the
redraft limits. It sends back an edit that fails the checks with the problems. Each action it takes
is one transaction with its revision, like the other writers', and locks the card on its own, so an
action that waits for another writer's change acts on the card as that change left it. If the desk
can't be reached the console says so and nothing changes.

The processor and replayer each run exactly one replica. Scaling the processor out would work with
the checkpoint store's partition ownership, but each run's state would then move between replicas on
rebalancing; one replica keeps that out of scope.

## Latency

`scripts/smoke_live.py` follows a replay from outside the way a browser does and reports the time
from the replayer publishing each event to the client receiving it, using the timestamps every push
carries. Measured from a client in South Africa, so the times include the network path from westus3.
The first three runs were on 19 October 2026, before the processor ran the models; the next two
were on 20 October, with them and then with the insights; the last on 21 October, with the overlay
contract and the producer's desk:

| Replay | Events | Median | p95 | Max |
| --- | --- | --- | --- | --- |
| from 23' at 4×, through half-time to full time | 1,458 | 227 ms | 303 ms | 1,345 ms |
| from 81' at 4× | 256 | 236 ms | 299 ms | 354 ms |
| from 81' at 4×, started as the processor restarted | 258 | 244 ms | 314 ms | 1,308 ms |
| from 81' at 4×, with the models | 236 | 278 ms | 359 ms | 427 ms |
| from 81' at 4×, with the models and the insights | 256 | 284 ms | 390 ms | 5,704 ms |
| from 23' at 4×, through to full time, with the desk | 1,458 | 238 ms | 318 ms | 537 ms |

**The template overlay.** The processor pushes a card straight after the event that found it, with
the template's wording. In the run of 21 October, from the replayer publishing the feed message
behind each of the 30 cards found to the client receiving the card's push: median 268 ms, p95
461 ms, maximum 475 ms. An agent's wording follows seconds later, by design (insights.md).

By stage, medians across the first three runs: publish to Event Hubs enqueue about 50 ms, enqueue
to the processor's push about 55 ms, and push to receipt 115–125 ms, most of it the network. The
slowest events came early in a replay: in the replay from 23', the 12 events in its first 10 seconds
had a maximum of 1,345 ms, and the 1,446 after them a maximum of 669 ms. In the run with the models,
the processor's stage kept its median (53 ms); push to receipt took longer that run (172 ms median).

The client in that run joined after the first 20 events had gone out; the client in the last run
joined at the end of the backfill and received every event. Its first 23 events, in the first 10
seconds, waited while the processor took in the 1,563-message backfill: p95 4,871 ms, max 5,704 ms.
No store write in that run took over a second, which leaves folding the backfill through the
models, on the processor's quarter of a vCPU, as the likely cost. The 233 events after them had a
p95 of 368 ms and a maximum of 429 ms.

## Tracing

The agents service sends traces to Application Insights through the Azure Monitor OpenTelemetry
distro, signed in with its managed identity (`src/footnote/telemetry.py`). The resource is
workspace-based, so the traces are kept in the Log Analytics workspace, under its daily cap.

- **Each card drafted is a trace.** Its `draft card` span carries the run, the insight, its topic
  and facts version, whether the producer asked for a redraft, and how the job ended: `cached`,
  `accepted` or `rejected` (with the attempts and the `agent_runs` row), `fallback` (with the note
  viewers see) or `superseded`. Agent Framework's spans nest under it: the writer and checker
  workflow, each call to gpt-5-mini with its tokens, each MCP tool call, then the push to Web PubSub.
- **Each batch translated is a trace**, `translate cards`: how many cards were waiting, how many
  went to the Translator rather than coming from the cache, and how many translations failed the
  check.
- Every span is kept. The distro's default samples five spans a second, which drops model and tool
  calls from a card's trace when a replay's first cards come together.
- Prompts and replies stay out of the spans. The service sends traces only: its logs stay in the
  container logs, and it sends no metrics, the exporter's own statistics included.

A replay from 81' to full time at 4× on 21 October, under the default sampler, made five card traces
(four drafts reused, one drafted) and 18 translation batches: 93 spans, 102 KB, and 4 KB of span
events. Keeping every span sends more, against a daily cap of 0.2 GB. In the workspace,
`AppDependencies | where Name == "draft card"` lists the jobs, and a trace's `OperationId` finds the
rest of it.

## Identity and access

No service uses a key or password. Local authentication is off on Event Hubs, Web PubSub, the
storage account and Application Insights, and Postgres accepts Microsoft Entra tokens only; the
connection string the agents service has for Application Insights names the resource and its
endpoint, and sending takes the service's token. Each container app runs as its own user-assigned
managed identity with these roles:

| Identity | Role | On |
| --- | --- | --- |
| replayer | Azure Event Hubs Data Sender | the `feed` event hub |
| processor | Azure Event Hubs Data Receiver | the `feed` event hub |
| processor | Storage Blob Data Contributor | the `checkpoints` container |
| processor | Web PubSub Service Owner | the Web PubSub resource |
| processor | Postgres Entra administrator | the server; owns the schema |
| web | Web PubSub Service Owner | the Web PubSub resource, to issue client tokens |
| web | `select` on `matches`, `runs` (all but who started each), `feed_events`, `run_state`, `insights`, `insight_versions`, `insight_cards`, `insight_pushes`, `agent_runs`, `tracking_chunks` | granted by the processor at start-up |
| agents | Foundry User | the Foundry project, to call the model |
| agents | Cognitive Services User | the Translator, to translate the cards |
| agents | Web PubSub Service Owner | the Web PubSub resource, to push the versions it writes |
| agents | Monitoring Metrics Publisher | Application Insights, to send its traces |
| agents | `select` on the match tables; `insert` on `insight_versions`, `insight_pushes`, `card_translations` and `translation_cache`; `insert` and `update` on `agent_runs` and `agent_cache`; `update` of `insights`' agent and status columns, its version, `redraft`, `queued_at` and `updated_at`, of `runs.insight_rev` and of `runs.producer` | granted by the processor at start-up |
| all four | AcrPull | the container registry |

The processor grants each database role exactly what its list says, revoking whatever an earlier
version granted on those tables first, in one transaction.

The browser's Web PubSub token joins one run's group and carries no roles, so a viewer can't
publish or join another group, and the web app issues one only for a run the processor has recorded.
The deploying user gets data-plane roles on Event Hubs, the checkpoint container, Web PubSub,
Application Insights, the Translator and Foundry for local development (on the account as well as
the project, since the evaluations' judge calls the account's OpenAI endpoint), and becomes a
Postgres administrator when `AZURE_PRINCIPAL_NAME` is set. Deploying needs the right to create the
resources and to assign roles on the subscription (Owner, or Contributor with User Access
Administrator), since the Bicep assigns every one of these roles.

The match tools listen on 127.0.0.1 inside the agents container, so nothing outside it can reach
them. The producer's desk listens on the container's internal ingress, which only apps in the
Container Apps environment reach; the web app passes on the viewer's anonymous ID, and the desk acts
only for the viewer who started the run. The run and insight a call is about travel in request headers the service sets from the job;
the model chooses the tool and its arguments, never the scope.

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
| Log Analytics, with the Application Insights traces | pay as you go, capped at 0.2 GB/day | first 5 GB/month free, then $2.30/GB | $0–4 |
| Storage | Standard LRS, hot: the processor's checkpoints | $0.05 per 10,000 writes or lists | $5–6 |
| Web PubSub | Free | $0 | $0 |
| Container Apps, the agents service from 20 October | 0.5 vCPU, 1 GiB, always on | as above | $8–9 |
| Foundry, gpt-5-mini | Global Standard | $0.25 per million input tokens, $2.00 per million output (prices of 20 October) | $1–14 |
| Azure AI Translator | Free (F0): 2 million characters a month | $0 | $0 |
| **Total** | | | **$47–70** |

Storage is billed by operation, and nearly all of them are the processor's partition ownership:
every 5–6 seconds it lists the ownership blobs and renews its claim on both partitions, three
operations whether or not anything is replaying, or 43,000–52,000 a day. A replay adds about one
checkpoint write per publishing step, 1,364 for a whole match.

The overlay contract, the producer's desk and the fan view add no resource. Translation uses the
Translator's free tier of 2 million characters a month: the showcase's 36 template cards come to
5,335 characters of English and 13,502 as sent for each language, since the Translator bills the
markup that marks the names too ([Translator FAQ](https://learn.microsoft.com/en-us/azure/ai-services/translator/translator-faq)).
Agent drafts add a few hundred characters each, every version is billed once for each of the two
languages, the history a catch-up lists is translated as well, and replays after the first reuse the
translations they have met. The tier also limits the rate, to about 33,300 characters a minute; the
worker sends ten cards a request and backs off when refused, and none of the 18 batches in the replay
from 81' above was refused. A subscription can have only one free Translator: `azd env set
TRANSLATOR_SKU S1` makes it the Standard tier, billed by the character, where one exists already.
Application Insights has no charge of its own: its traces are ingestion into the workspace, 105 KB
for that replay, under the same free 5 GB and daily cap. In Postgres the pushes
kept for delayed viewers take about 1.1 KB an event, around 2 MB for a replay from kick-off; the
insight pushes kept beside them, about fifty a replay, the largest 2,310 bytes; and the tracking
7 MB once. The server's 32 GB holds them all. A viewer's pitch view fetches 960 bytes of
tracking per second of match, about 6 MB for a whole match at any speed.

The model costs nothing until it is called. A card cost $0.004 on average in the recorded
evaluation run, and $0.008 at most, for the full-time recap, which reads the whole story
([evaluations.md](evaluations.md)). A full match has 16 cards to draft (the restated goal twice),
so a replay from kick-off costs about $0.06 the first time and close to nothing after, because later
replays reuse the accepted drafts, catch-ups included. A change to what the agents are told or shown
changes the versions in the cache key, so the next replays draft afresh. The ceiling is the daily cap
on agent runs (`AGENT_DAILY_RUNS`, 150): about $0.65 a day at that average, about $14 over the 21
days if every day reached it. An evaluation run drafts 20 cards outside the cap, about $0.09 at list
prices, plus the judge's calls; it is run by hand after such a change.

Web PubSub's Free tier allows 20 concurrent connections and 20,000 outbound messages a day, counted
in 2 KB units. A viewer watching a whole match at any speed receives about 2,000: one per event, the
insight changes (about a hundred now that translations arrive as pushes of their own, the larger in
two or three units), the snapshot and the end. The free tier covers about ten full-match viewers a
day. Standard costs $1.61 a day; moving to it
for judging (27 October to 10 November) would add $24. A tier change between Free and Standard
takes the service offline for 30–60 minutes while its address changes, so it has to happen before
submission.

An Azure budget of US$100 covers 1 October to 31 December and emails at 50%, 80% and 100% of
actual spend and when the forecast passes 100%. It doesn't stop spending, so the design keeps fixed
costs low and the resource group is deleted after judging.
