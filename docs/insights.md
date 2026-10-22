# Insights

How a moment in the match becomes a card a producer can put on air: what is found and how it
ranks, how figures stay code's own, the checks every card passes, the agents that word them, what
the producer decides, and what happens when VAR or the data provider changes something a card
cited. The principles behind it (P1–P8) are in [audience.md](audience.md); the services it runs on
are in [architecture.md](architecture.md); what viewers get for each card, and when, is the overlay
contract in [overlay.md](overlay.md).

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
5. **Approved, or not.** A card airs once it is approved, by the producer or automatically, and
   reaches each fan when their stream shows the moment.

## Moments

The showcase match produces 36 insights over the whole match, 14 of which an agent drafts. A replay
that starts mid-match adds one more, the catch-up, which an agent drafts too.

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
| Half-time, full time | recap | the whistle | 0.90 | yes |
| Catch-up | recap | a replay that starts mid-match reaches its starting point | 0.85 | yes |
| Correction | correction | the provider amends an event | 0.95 | no: the template says what changed |

Moments found in a run's backfill (before the point the replay jumped to) are kept as history:
they appear in the run's snapshot for catch-up, but no agent drafts them and they never reach the
shortlist. The catch-up sums them up for the replay's viewers ("What you missed", docs/audience.md,
P7): it is found at the backfill's last message, it is live, and it tells what happened, leaving the
score line to the scoreboard beside it. A recap's facts give the goals as they stand, with VAR's and
the provider's changes applied; a recap's writer reads the rest of the story through `get_story`
(below).

## Ranking

A rank is the topic's base, raised by what the match-state model and the numbers say about the
moment. The producer's shortlist shows the three strongest insights still current (each has a
shelf life after its moment, from two minutes for a sprint to ten for a correction), each with
its reason. The half-time recap stays until two minutes into the second half: a replay's break
lasts half a minute, too short for a producer approving by hand while an agent's draft is on its
way.

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

A fact also lists the events it rests on, so a card links to them through the facts it uses: a
goal's scorer to the goal, a spell's share of a state to the spell's shots and changes of
possession, its longest move to that move's passes. Sprint and distance tags come from the tracking
and rest on no event; the shortlist says so where other cards offer their evidence.

## Checks

Every draft, template or agent, passes `check` in `draft.py` before anyone sees it:

- every placeholder names a fact the writer was given, and the writer typed no figure: no digits,
  no numbers or ordinals spelled out ("one", "nil", "first goal", "twentieth minute"), no shares in
  words ("half the ball", "per cent"), no "brace" or "hat-trick". Phrases that use those words
  without stating a figure, such as "first half", "one of" and "final third", are allowed;
- each entry of a draft is one sentence, so the limits on sentences hold;
- capitals are for names. Every capitalised word other than a sentence's first is a name from the
  facts, and names written side by side must be one name as a fact gives it ("Femi Adeyani", or
  "Adeyani" alone), so words from two names can't make a third. A sentence's first word is held to
  this only when it is part of a name: an ordinary word in capitals can't be told from an unknown
  name without a dictionary. Filled in, the headline and every sentence start with a capital or a
  figure, so "{moment.overturned} on-field decision" ("stands on-field decision") is refused, and VAR
  is in capitals ("Var: No penalty" is refused);
- every sentence cites an event the writer was shown or uses a fact, and when the facts rest on
  events the card links to at least one (the card's evidence is the cited events plus those behind
  each fact used);
- the headline fits in 60 characters, the casual line in two sentences and 240, the analyst line
  in three and 360, filled in; a recap, which tells the story of a half, gets three sentences and
  400 characters for its casual line; no betting language, exclamation marks, links or emoji;
- a count shows its noun once: a fact's display carries it ("44 passes", "2 shots on target"), so
  "{key} passes", "{key} shots", "{key} on target" or "{key} completed passes" is refused, and so is
  a word for one thing before it ("74% of a 5 minutes"); a minute after a verb such as "began" needs
  "at", a count of times follows what happened ("there were 7 times" is refused), and a score line,
  which names both clubs, doesn't follow a verb ("Kingsferry lead Saltmarsh 1–2 Kingsferry") or "to"
  ("turns the game to Saltmarsh 1–2 Kingsferry", which the Translator gave as "in favour of" it);
- the ball changing hands counts both sides losing it, so a card can't say one side forced it;
- wording a writer would only have copied from the tools is refused: "shown as" from a fact's
  description, the model's name ("state model"), a count of times followed by a noun ("7 times
  changes of possession"), a spell's length before the word for it ("a 5 minutes spell"), a heading
  such as "No penalty", or the template's list of goals, in the middle of a sentence, and in a recap
  "the last 5 minutes" from a spell's own wording, which meant the minutes before that spell;
- filled in, "a" doesn't go before a vowel or a figure said with one ("a own goal", "a 80% chance"),
  and no word comes twice in a row ("finished a {story.4.play_pattern} counter" read "a counter
  counter");
- a long text fact, such as the provider's reason, goes in one line, not both;
- a sentence saying a goal was ruled out uses the facts of the VAR decision that ruled it out, its
  player or its minute: a recap's goals are the ones that stand, so the decision can't be pinned on
  one of them;
- a card that says who a goal is credited to also says who it was credited to before, when its
  facts include a correction: "later credited to Femi Adeyani" alone reads as if it always had been.
  The earlier credit doesn't come after "not", "instead of" or "rather than", or in brackets: read
  aloud, "(originally given as Jory Penhallow)" sounds like the scorer's other name;
- a card uses no fact its topic withholds: the catch-up uses no score fact;
- the text is plain: no markup, no characters a reader can't see, no number characters besides the
  digits already refused, and no letters from outside the Latin alphabet, so a figure or a name
  can't pass the checks above in disguise (a circled digit, a fraction sign, a zero-width space
  inside "two", a look-alike letter from another alphabet, a name in small capitals).

The checks catch figures and names a writer made up, and a goal ruled out pinned on one that stands.
Any other name from the match given to the wrong player, or a sentence that describes the facts
unfairly, passes them. The evaluations of the agents' output catch some of that
([evaluations.md](evaluations.md)), and reading the cards catches the rest.

## The agents

The agents service (`src/footnote/agents`) runs one Agent Framework workflow per card:

```text
Job -> writer --Attempt--> checker --(passes)----------> accepted: the agent's version airs
         ^                    |
         +------Revise--------+   (fails, with a try left)
                              +--(fails twice)----------> rejected: the template stays
```

The writer is an Agent Framework `Agent` on the Foundry deployment of gpt-5-mini, with two sets of
instructions (`prompts.py`): the moment writer, and the recap writer, which tells the story of the
match so far at half-time and full time and writes the catch-up. (A correction's notice keeps its
template, which says what changed plainly: in five of seven recordings an agent's notice added
nothing to it, and the others slipped, as in "It is not Jory Penhallow's own goal".) The writer's
only tools are the match tools, an MCP server (`src/footnote/tools`) the same process serves on
localhost:

| Tool | Returns |
| --- | --- |
| `get_moment` | what happened, why it was picked, its facts and the template's wording |
| `get_story` | the match's moments so far in order (goals, VAR decisions, red cards, spells, corrections), each with its facts under keys of its own, `story.<n>.<fact>`: what a recap is written from |
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
checker lets the draft use, and the log is kept with the run. Besides `check`, the checker sends
back a draft whose casual line is the template's word for word: it would add nothing, and the
template's wording stands anyway. A recap keeps its template's heading ("Final score: Saltmarsh 1–2
Kingsferry", "What you missed, up to 59'"), the graphic's fixed one, whatever the writer put there.

**Limits and fallbacks.** The template stays, and the insight's `agent_note` says why, when:

- no draft arrives within 45 seconds of the job being claimed, enough for one revision;
- the draft fails the checks twice;
- the model or the tools fail;
- the job waited more than 90 seconds for a worker, counted from when it joined the queue (a
  restated insight joins it afresh), or the replay ended first;
- today's 150 agent runs (UTC) are used up, a ceiling on what the model can cost.

**Reuse.** Every replay is the same match, so the same moment makes the same job. A job's key is
the match, the insight, its facts, the model and its reasoning effort, and the prompt, tools and
writer versions, each with a fingerprint of the code behind it (`src/footnote/agents/versions.py`),
so a change to what the writers are told or shown can't reuse drafts written before it. An accepted
draft is stored under its key and reused by later replays, after today's checks run again on the
facts its writer was shown; its provenance says it was reused and names the agent run that wrote
it. A kept draft that fails today's checks is drafted again, and the fresh draft replaces it, as a
producer's redraft does.

**What each run records** (`agent_runs`, kept after its replay ends): outcome, attempts, input,
output and reasoning tokens, latency, the problems a rejected draft had and the tool calls made.
Each agent version's provenance names the model, prompt version, tools used and that the checks
passed. The console's Agent runs lists a card's runs in its replay and, for a reused draft, the run
in an earlier replay that wrote it.

**Evaluations.** `python -m footnote.evals` drafts every card the showcase asks of the agents, 19
in all, against the deployed model, and evaluates them in code and with Azure AI Evaluation's
groundedness evaluator; CI replays the recorded run on every push. The recorded run, each card in
it, its timings, tokens and cost at list prices (US$0.25 a million input tokens, US$2.00 a million
output) are in [evaluations.md](evaluations.md).

## The producer's desk

The producer console shows the shortlist with each card's status and lets the producer approve,
edit, kill or withdraw it, or ask an agent for a fresh draft. The console's requests go through the
web app to the producer's desk in the agents service (`src/footnote/agents/desk.py`), which applies
each one to the insight, bumps the run's insight revision and pushes the changed card, as the
processor and the agents do. The desk is reachable only inside the Container Apps environment.

- **Who may produce.** The viewer who started the replay: the browser's anonymous ID travels with
  the start request to the run's record, where no API serves it, and the desk compares it with the
  ID each action carries. Anyone else with the link sees the console as it stands. Stopping the
  replay is the starter's alone too: the replayer compares the ID the stop request carries.
- **Approval.** A replay approves each card automatically as it is found, or leaves every card to
  the producer; it starts the second way when it is started from the producer's profile. The
  producer can switch, from the cards found next on. What the producer approves is the wording they
  saw: approval waits while an agent is drafting the card, since the draft would replace the
  wording. The status lifecycle is in [overlay.md](overlay.md#who-decides-what-airs).
- **Edit.** The producer edits the wording as a draft, with placeholders where the figures go, and
  the desk runs `check` on it as on an agent's draft: against the moment's own facts, and the events
  the card already links to. An edit that fails comes back with the problems; one that passes is a
  version of its own (`source: producer`), and is never cached for later replays. An agent's draft
  that used figures from beyond the moment's facts is edited from the template's wording.
- **Redraft.** The insight joins the agents' queue afresh, with no claims against it and past the
  cache of earlier replays; an accepted redraft replaces the draft later replays reuse, so a
  producer can mend a cached card that reads wrong. A card on air with wording the producer
  approved is withdrawn first.
  Each card gets at most five agent runs and each replay thirty, its first drafts and corrections'
  included, so one producer can't spend the agents' daily runs; past that, the producer edits.

## Translation

The agents and the templates write English; Azure AI Translator renders each card in Spanish and
French (`src/footnote/agents/translator.py`). The agents service translates the version of each
card viewers see, the live cards first and then the history a catch-up lists, every few seconds and
whenever the processor finds new cards, one request for a batch of them. The English is prepared for
the Translator first
(`src/footnote/insights/translation.py`):

- Every name in the match (players' full names and surnames, clubs' names) goes as a dictionary
  entry that translates as itself, so the name comes back unchanged and the Translator still builds
  the sentence around it. A name marked to be left alone comes back too, but the verbs around it
  stay in the infinitive ("Saltmarsh igualar la partida").
- Minutes are written out: "6'" goes as "minute 6", since the Translator reads "6'" as six feet.
- A headline goes with a full stop, taken off again after: without one, "Femi Adeyani scores" comes
  back as "Femi Adeyani puntuaciones".
- English it got wrong, or gave word for word, is said another way: "spell" as "period" (it came
  back as a magic spell), "the provider" as "the data provider", "made the last pass" as "played the
  final pass" ("hizo el último adelantamiento", an overtaking), "neither side" as "neither team",
  "left the boot" as "left the foot", "a run from 2' with 44 passes" as "a sequence" ("una carrera",
  a run on foot), "late on" as "late in the match" ("en los minutos de la tarde"), and a few more.

What comes back has the Translator's known slips put right: a word that is never the football one
("penalización" for a penalty, "balonmano" and, in French, "handball" for a handball, "pasada" and
"passage" for a pass), its article and adjective changed with it, a word put inside a score line
("Saltmarsh 1–1 en Kingsferry"), and "in favour of" before one ("a favor de Saltmarsh 1–2
Kingsferry", for a goal that "turns the game to" that score). Code then checks each translation against its English: the same figures, a decimal
comma read as a point, every name, each score line whole (a name either side of the score, so "1–1
pour Saltmarsh Kingsferry" fails), no part empty. A small number may come back as a word ("1 shot"
as "un tiro", "minute 2" as "el segundo minuto"); a figure in digits that changed, or one the
English doesn't have, fails. Apart from score lines, the check counts the figures and names rather
than placing them, so names swapped between roles, a number word the English doesn't have, or "un"
standing in for a dropped 1 would get through. A translation that passes joins the card and the card
is pushed again; one that fails is kept with its problems and never shown, and the viewer reads the
English. When a card is reworded, by an agent's draft or a producer's edit, a page keeps showing the
earlier wording's translation until the new one's arrives; a card a correction restated shows the
English, marked, until its own translation does. Translated wording carries its language for screen
readers. Translations are kept under a hash of the English and reused, so a replay after the first
calls the Translator only for wording it hasn't met, such as a producer's edit. The producer sees
which languages each card is ready in.

The words around the figures and names are the Translator's. The templates are worded so it gets
them right, each rewording noted beside it in the code with the slip it avoids: the full-time recap
is headed "Final score" because "Full time" came back as "Tiempo completo". An agent's wording can
still meet a slip no rule above knows.

## VAR and corrections

- **A check completes.** The card saying VAR is checking leaves the shortlist when the decision
  arrives, whatever the decision. It isn't flagged: it was true while the check lasted.
- **VAR rules a goal out.** Every insight citing the goal is flagged and leaves the shortlist at the
  decision: the goal's own card ("Ruled out by VAR") and the card on the pass that set it up. The
  decision's own card explains it, citing the goal and the pass the offside was judged on.
- **The provider amends an event.** Every insight citing it is flagged. An insight whose facts came
  from it is restated: a new template version with the corrected facts, which the agents draft
  again. A correction insight tells viewers what changed and names the insight it corrects. In the
  showcase match, the 81st-minute goal first recorded as a Penhallow own goal is restated at 84' as
  Adeyani's, and its correction notice ranks 0.95. The notice gives the new credit first and the
  old one in a sentence of its own ("It was originally recorded as Jory Penhallow's own goal"):
  after "not", or in a bracket, the old credit read aloud, and in translation, as if it were the new
  scorer's. The provider's reason is given once, in the analyst line. A restated card the producer
  had approved by hand waits for their approval again; the console lists it under corrections, with
  the wording they are approving and its evidence, beside the notice.

A restated insight is a fresh job: its wait for a worker and its claims count from the
restatement. A draft still being written from the old facts is cancelled when a worker claims the
fresh job, and one that finishes first is dropped, because the facts it was written from are no
longer the insight's.

## Delivery

Each change to an insight bumps the run's insight revision in the same transaction, and its push
carries the revision it made. The processor, the agents service and the producer's desk all push; a
browser applies revisions in order and fetches the snapshot after a gap
(`frontend/src/lib/live/run-reducer.ts`). The snapshot carries every insight with the revision they
are as of. Every push is stored too (`insight_pushes`), and a page fetches the ones after the last
revision it has, so one that loads late, or misses pushes, still has each card's earlier states.
Insights the backfill passed reach viewers through the snapshot, and are pushed only when their
translations arrive.

Each change also names the feed message behind it (`shown_seq`), and a fan's browser shows a
card's state only once their stream reaches that message: a goal VAR ruled out stays a goal on a
delayed screen until the screen reaches the decision ([overlay.md](overlay.md#when-an-item-shows)).
