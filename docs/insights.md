# Insights

How a moment in the match becomes a card a producer can put on air: what is found and how it
ranks, how figures stay code's own, the checks every card passes, the agents that word them, and
what happens when VAR or the data provider changes something a card cited. The principles behind
it (P1–P8) are in [audience.md](audience.md); the services it runs on are in
[architecture.md](architecture.md).

## From an event to a card

1. **Found.** The processor folds each feed message into the run's state, and the moment finder
   (`src/footnote/insights/moments.py`) looks at it there. A goal, a VAR check, a spell of the
   match state, a hard pass or a sprint becomes an insight, with its facts, a rank, the reason for
   the rank and the events it rests on.
2. **Worded by its template.** Every insight starts with the code's own wording
   (`templates.py`), so the producer has a card the moment the event arrives.
3. **Stored and pushed.** The insight is stored in the same transaction as the feed rows that
   caused it, and pushed to the run's viewers.
4. **Drafted by an agent.** Insights where wording adds something are left pending for the agents
   service. Its writer reads the moment through the match tools, drafts a card, and code checks
   it. A draft that passes becomes the version viewers see; otherwise the template stays, and the
   insight says why.

## Moments

The showcase match produces 36 insights over the whole match, 13 of which an agent drafts.

| Topic | Kind | Found when | Base rank | Agent drafts it |
| --- | --- | --- | --- | --- |
| Goal, own goal | moment | a goal | 0.80 | yes |
| Penalty | moment | a foul given as a penalty | 0.80 | yes |
| Red card | moment | a red or second yellow | 0.70 | yes |
| VAR check started | rule call | a check begins | 0.70 | no: the status goes out at once |
| VAR decision | rule call | a check completes | 0.78 | yes |
| Pressure, chaos, control | segment | the shown match state holds for long enough (below) | 0.55, 0.50, 0.45 | pressure and chaos |
| Key pass | stat | a goal with a completed last pass to the scorer | 0.40 | no |
| Hardest pass yet | stat | a completed pass rated at least 0.80, harder than any before | 0.40 | no |
| Fastest shot yet | stat | a shot other than a goal, of 100 km/h or more and faster than any before | 0.35 | no |
| Sprint, distance | player tag | a record sprint; a player passing 10 km | 0.35, 0.25 | no |
| Half-time, full time | recap | the whistle | 0.90 | no |
| Correction | correction | the provider amends an event | 0.95 | yes |

Moments found in a run's backfill (before the point the replay jumped to) are kept as history:
they appear in the run's snapshot for catch-up, but no agent drafts them and they never reach the
shortlist.

## Ranking

A rank is the topic's base, raised by what the match-state model and the numbers say about the
moment. The producer's shortlist shows the three strongest insights still current (each has a
shelf life after its moment, from two minutes for a sprint to ten for a correction), each with
its reason.

- **Goals.** +0.10 against the run of play, +0.05 if it equalises or takes the lead, +0.03 from
  the 80th minute. Against the run of play means that, over the ten minutes before the move (the
  last half-minute left out), the state the model showed each second was the scorers' own for at
  most a quarter of the time and the other side's for at least 45%. The showcase's 23rd-minute
  goal ranks 0.95: Saltmarsh were on top for 66% of the ten minutes before Kingsferry scored.
- **VAR decisions.** +0.10 when the on-field decision is overturned.
- **Segments.** From the state shown each second: one side pinning the other back for 60% of the
  last three minutes, chaos for half of them, or one side in control for 70% of the last five.
  Chaos needs a smaller share because the model names it less readily (it catches 42% of chaos
  seconds, [models.md](models.md)). Each topic and club gets at most one segment card per five
  minutes of a half. The rank rises with the share held, and for pressure with each shot in the
  spell. Segments and stats are marked to wait for the next stoppage before a fan sees them (P5).
- **Stats and tags.** A key pass ranks higher the harder it was; a sprint, the faster.

The thresholds were set by hand. The showcase match's beats (docs/experience.md) were the sense
check: the 23rd-minute goal comes out against the run of play, Saltmarsh's 38–45' spell and the
63–68' chaos are found. The best three-minute chaos share in the whole match is 58%, at 67–69'.

## Facts and placeholders

A card never carries a figure code didn't compute (P2). Each figure and name a card may use is a
fact (`facts.py`): a key such as `teams.SAL.possession`, its value, the text a card shows for it
("71%") and what it is. Wording, a template's or an agent's, puts the key in braces where the
figure goes, `{teams.SAL.possession}`, and code fills it in. Counts carry their noun ("3 shots",
"no shots"), so wording needn't agree with the number.

## Checks

Every draft, template or agent, passes `check` in `draft.py` before anyone sees it:

- every placeholder names a fact the writer was given, and the writer typed no figure: no digits,
  no numbers spelled out, no "per cent";
- every capitalised word inside a sentence is a name from the facts, so no player, club or place
  outside the match appears. A capitalised word that starts a sentence can't be told from an
  ordinary word without a dictionary, so that one place is not checked;
- every sentence cites an event the writer was shown or uses a fact, so each claim links to the
  events behind it (the card's evidence is the cited events plus those behind each fact used);
- the headline fits in 60 characters, the casual line in two sentences and 240, the analyst line
  in three and 360, filled in; no betting language, exclamation marks, links or emoji.

The checks catch invented figures and names. Whether a sentence describes the facts fairly (that a
goal really was against the run of play) is left to the facts themselves and to evaluations of the
agents' output (Day 6).

## The agents

The agents service (`src/footnote/agents`) runs one Agent Framework workflow per card:

```text
Job -> writer --Attempt--> checker --(passes)----------> accepted: the agent's version airs
         ^                    |
         +------Revise--------+   (fails, with a try left)
                              +--(fails twice)----------> rejected: the template stays
```

The writer is an Agent Framework `Agent` on the Foundry deployment of gpt-5-mini, with two sets of
instructions: one for moments and one for correction notices (`prompts.py`). Its only tools are
the match tools, an MCP server (`src/footnote/tools`) the same process serves on localhost:

| Tool | Returns |
| --- | --- |
| `get_moment` | what happened, why it was picked, its facts and the template's wording |
| `get_match_stats` | the score and each club's counts, shares and model figures |
| `get_match_state` | the state shown now and each club's share of recent minutes in each state |
| `get_player` | one player's passing, difficulty, distance, top speed, shots and goals |
| `get_events` | particular events as they stand at the moment, corrections applied |
| `get_recent_events` | the key events of the last few minutes before the moment |
| `get_lineups` | both squads, and who is on the pitch |

Every call is scoped by headers the service sets and the model never sees: the run and the
insight. The tools rebuild the run's state from its stored feed up to the insight's seq with the
processor's own code, so the writer sees the match as viewers had it at that moment and nothing
later. A function middleware logs each call; the facts and events the calls returned are all the
checker lets the draft use, and the log is kept with the run.

**Limits and fallbacks.** The template stays, and the insight's `agent_note` says why, when:

- no draft arrives within 45 seconds of the job being claimed, enough for one revision;
- the draft fails the checks twice;
- the model or the tools fail;
- the job waited more than 90 seconds for a worker, or the replay ended first;
- today's 150 agent runs (UTC) are used up, a ceiling on what the model can cost.

**Reuse.** Every replay is the same match, so the same moment makes the same job. A job's key is
the match, the insight, its facts, the model, and the prompt, tools and writer versions. An
accepted draft is stored under its key and reused by later replays, after the same checks run
again on the facts its writer was shown; its provenance says it was reused and names the agent
run that wrote it.

**What each run records** (`agent_runs`): outcome, attempts, input, output and reasoning tokens,
latency, the problems a rejected draft had and the tool calls made. Each agent version's
provenance names the model, prompt version, tools used and that the checks passed.

Eight cards drafted locally against the deployed model on 20 October 2026 (reasoning effort low;
goals, VAR decisions, pressure and chaos spells and the correction) were all accepted at the first
attempt, in 6–17 seconds, using 2,200–5,600 input and 280–960 output tokens each. At the list
prices (US$0.25 a million input tokens, US$2.00 a million output) that is under US$0.004 a card.

## VAR and corrections

- **VAR rules a goal out.** The goal's insight is flagged ("Ruled out by VAR") and leaves the
  shortlist at the decision; the decision's own card explains it, citing the goal and the pass the
  offside was judged on.
- **The provider amends an event.** Every insight citing it is flagged. An insight whose facts came
  from it is restated: a new template version with the corrected facts, which the agents draft
  again. A correction insight tells viewers what changed and names the insight it corrects. In the
  showcase match, the 81st-minute goal first recorded as a Penhallow own goal is restated at 84' as
  Adeyani's, and its correction notice ranks 0.95.

A draft still being written when a correction restates its insight is cancelled, and one that
finishes in the moment between is dropped, because the facts it was written from are no longer the
insight's.

## Delivery

Each change to an insight bumps the run's insight revision in the same transaction, and its push
carries the revision it made. The processor and the agents service both push; a browser applies
revisions in order and fetches the snapshot after a gap (`frontend/src/lib/live/run-reducer.ts`).
The snapshot carries every insight with the revision they are as of. Insights the backfill passed
reach viewers through the snapshot only.
