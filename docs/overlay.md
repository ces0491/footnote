# Overlay contract

What a viewer's client or a graphics system gets for each moment worth a graphic: one item per
insight, as it now stands. The items are rows of the `insight_cards` view, served with a run's
snapshot. A live item is also pushed through Web PubSub whenever it changes; an item from before the
replay's start reaches clients through the snapshot only ([architecture.md](architecture.md#contracts)).
The JSON Schema is [overlay.schema.json](overlay.schema.json), printed from the pydantic model in
`src/footnote/live/overlay.py` by `uv run python -m footnote.live.overlay > docs/overlay.schema.json`;
`tests/test_store.py` checks every item a replay pushes against it, and `tests/test_live.py` that the
committed schema is current. How moments are found, ranked and worded is in
[insights.md](insights.md); the needs the fields answer are in
[experience.md](experience.md#what-the-overlay-data-has-to-carry).

The reference renderer is the web app's fan view and producer console (`frontend/`): the timing
rules below are `frontend/src/lib/live/playback.ts`, the graphics are drawn over our own 2D render
of the match in `frontend/src/components/pitch/`, and the side panel carries every graphic's text.

## An item

| Need | Fields |
| --- | --- |
| Identity and lineage | `match_id`, `insight_id` (stable: a later state of an item replaces the earlier), `evidence` (the event IDs the moment rests on), `corrects` (the item a correction notice is about), `flag` |
| Timing | `at` (when it happened), `shown_seq` and `shown_at` (the feed message behind its current state, and its match time), `ts` (that message's provider timestamp), `hold`, `duration`, `until` (when it leaves the producer's shortlist), `seq` (the message its facts are as of), `created_at` and `updated_at` (when the item was first stored and last changed) |
| Ranking | `rank` (0 to 1) and `reason` |
| Kind | `kind`: moment, rule_call, segment, stat, player_tag, recap or correction; `topic`, which also names the graphics template |
| Content | `card`: `headline`, `casual`, `analyst`, `plain` (one text for screen readers), the `evidence` its wording rests on and the `facts` it used; `translations`, the wording in Spanish (`es`) and French (`fr`) once translated and checked; `fields`, each fact's text by key, for a graphics system filling its own template; `version` |
| Provenance | `source` (template, agent or producer), `provenance` (template, agent run, model, prompt version, tools called, attempts, time taken, checks passed, cached; for an edit, the version edited), `agent_state`, `agent_note` |
| Status | `status`, `status_by`, `status_at` |
| Presentation | `placement` (lower_third, side_panel or full_card), `motion` (animated or still), `live` (false for a moment before the replay's start: history, for catch-up only) |

Match times are a period and `t`, seconds since the period kicked off, with the minute a broadcast
shows ([data.md](data.md#the-feed)).

## When an item shows

A viewer's stream can run well behind live: Stats Perform says it measured delays of up to 62
seconds across streaming providers at the 2026 Super Bowl
([audience.md](audience.md#fans-who-arent-watching-live)). A client holds every item until its
viewer's playback reaches `shown_at`, so nothing reaches a viewer before their screen shows the
moment (P4).

- **The state current at playback.** `shown_seq` moves when the feed changes an item: when it is
  found, when a correction restates it, when VAR or a correction flags it. A client keeps each
  state it receives and shows the latest one playback has reached. Every state pushed is also
  stored with the run (`/api/runs/[runId]/insights`), so a client that loads after an item changed
  still has the state before. A goal VAR rules out stays a goal on a delayed screen until that
  screen reaches the decision.
- **Held for a stoppage.** A segment or a stat (`hold: "stoppage"`) waits for the first stoppage
  after `shown_at`, so live play stays uncluttered (P5). The event pushes say which events stop play.
- **On screen.** A lower third or a full card stays on screen for `duration` seconds of match time.
  A side-panel card has no duration: it stays in the panel.
- **The producer's decisions** don't move `shown_at`. An approval given after the moment shows the
  item at once to a viewer already past it: in the panel, and a lower third goes on screen from the
  approval, taking its turn as any graphic does (Placement and motion, below). A full card keeps its
  time from the moment, so a recap approved late stays in the panel rather than covering play. A
  kill or a withdrawal applies at once too: a viewer past the moment loses the item, and one not
  there yet never gets it.
- A correction issued during a break carries the clock of the whistle before it, so an item it
  changes has the whistle as its `shown_at`. The reference renderer times each state from the
  replay second its `shown_seq` message was published, so a delayed viewer gets that state when
  their playback reaches that point in the break.
- The catch-up of a replay that starts mid-match (`topic: "catch_up"`) names the backfill's last
  message as its `shown_seq`, so a client shows it from the replay's start. It sums up the history
  items and is live itself.

The web app also holds the match itself to each viewer's playback: it serves the event pushes it
stored, each with the replay second it was published at, and the tracking for the pitch view only up
to the run's live point (lib/live/playback.ts, `/api/runs/[runId]/pushes` and `/tracking`). The
events behind a card are served as they stood at the card's `shown_seq` (`/events?upto=`), so a
viewer whose stream hasn't reached a correction isn't shown the corrected event either. A run's end
is announced to a fan once their stream reaches it.

## Who decides what airs

Only an item with `status: "approved"` airs, and only a live one (P3).

```text
drafted ──approve──▶ approved ──withdraw──▶ withdrawn
   │                    ▲                       │
   └──kill──▶ killed ───┴──── approve again ────┘
```

`status_by` says who: `auto` when the run approves each item as it is found, `producer` for the
producer's own decisions, and `correction` when a correction restated an item the producer had
approved by hand: the producer approved what it said before, so the corrected item waits for them
again. Whether a restated item waits depends on who approved it, whichever way the run is approving
when the correction arrives. A run starts approving automatically, or by hand when it is started
from the producer's profile; the producer can switch either way, and the switch applies to the items
found from then on.

What the producer approves is the wording they saw. Approval waits while an agent is drafting the
item, and the desk refuses to redraft an item on air with wording the producer approved until the
producer withdraws it. The producer's desk ([insights.md](insights.md#the-producers-desk)) records
each decision.

## Corrections and flags

`flag` is set when VAR or the provider's correction undid what an item cites, with the reason and
the feed message that did it. Two cases differ:

- **Restated.** The goal's own card, when the provider amended the goal: the correction gave it new
  facts, so its wording is already the corrected one. Its `seq` equals `flag.seq`.
- **Undone.** Anything else flagged: a goal VAR ruled out, the card on the pass that set it up, any
  other card that cited an amended event. Its wording no longer stands.

A correction notice is an item of its own (`kind: "correction"`); `corrects` names the goal's card
when the correction restated one. The reference renderer airs the notice, never a flagged item, and
marks flagged cards in the panel: corrected, or struck through with the reason. The catch-up isn't
marked: one that lists a goal whose credit changed later in the replay keeps the old credit.

## Languages

Cards are written in English. The agents service has Azure AI Translator render the version of each
card in Spanish and French, the live ones first and then those from before the replay's start, with
the names given as dictionary entries so they come back as they are, and code checks that every
figure, name and score line came through ([insights.md](insights.md#translation)). A translation that
passes joins the item's `translations` with a new `updated_at`. A live item is pushed again, so a
client keeps it as a new state of the card; an item from before the replay's start reaches a client
with its translations through the snapshot only, when the client next fetches one. A client shows a
language's wording once it is there and the English until then. When a card is reworded with the
same facts (an agent's draft, a producer's edit), the reference renderer keeps showing the earlier
wording's translation until the new one's arrives; a card a correction restated shows the English
until its own translation does. A translation that failed the check never reaches the item, so its
readers get the English. The reference renderer marks in the panel a card it shows in English to a
viewer who chose another language, and marks translated wording with its language for screen
readers.

## Placement and motion

- **Lower third**: moments, rule calls and corrections. **Full card**: half-time and full-time
  recaps. **Side panel**: segments, stats, player tags and the catch-up, which is for a fan's own
  screen rather than the world feed.
- The reference renderer runs one graphic in each place at a time, in the order they may show (a
  lower third the producer approved late, from its approval), the stronger first when two show
  together. One that would wait more than twice its own time on screen is stale by then and is
  dropped. It keeps each graphic up for at least four seconds of wall time, so a graphic stays
  readable in a replay at 2× or 4×.
- `motion: "animated"` (moments) may animate on and off. Calm mode keeps every graphic still, as
  does a device set to reduce motion, and stills the rest of the page too, dialogs included; nothing
  flashes. A fan can hide the pitch view itself and follow from the panel.
- Every graphic's text is in the side panel too (P8), and `plain` is the one text a screen reader
  needs.
