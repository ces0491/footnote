# What each person sees

This document follows the showcase match through five viewers: the screens they
use, what the overlay data has to carry for them, and the two-minute video. The
people and their needs come from [audience.md](audience.md); numbers in
principle references (P1–P8) point to its design principles.

Figures and card wording in the sketches show format only. The showcase match's
own figures come from the generator, and its cards' wording from the templates
and the agents ([evaluations.md](evaluations.md) has the agents' recorded
cards).

## The showcase match

**Saltmarsh Rovers v Kingsferry Athletic.** Saltmarsh keep the ball and press
high. Kingsferry sit deep and break quickly. A search reruns the generator from
saved points with new seeds until each moment below happens. Two things are set
by hand: the provider's first call on the 81st-minute goal, a Penhallow own goal
amended at 84', and the named cast, who are never substituted
([data.md](data.md#the-showcase-match)).

| Cast | Club | Role |
| --- | --- | --- |
| Teo Varlan (10) | Saltmarsh | Playmaker; the player-focus subject |
| Marco Dellow (9) | Saltmarsh | Striker |
| Jory Penhallow (4) | Saltmarsh | Centre-back |
| Femi Adeyani (7) | Kingsferry | Winger |
| Isaac Brennholt (1) | Kingsferry | Goalkeeper |

| Minute | What happens | Match state | Exercises |
| --- | --- | --- | --- |
| 0–22 | Saltmarsh dominate the ball | Control (Saltmarsh) | State timeline |
| 23 | Kingsferry score from their first counter | Transition | P1, P4 |
| 31 | Dellow scores; VAR rules it out for offside | Stoppage | P5 |
| 38–45 | Saltmarsh pin Kingsferry back | Sustained pressure | P1, P6 |
| HT | Half-time recap | | P7 |
| 52 | Varlan equalises from distance | Control | Player focus, shot speed |
| 60 | A viewer joins late | | P7 |
| 63–68 | Possession changes hands repeatedly | Chaos | Rhythm explanation |
| 74 | Handball penalty claim; VAR says no | Stoppage | P5 |
| 81 | Goal credited as a Penhallow own goal | Transition | |
| 84 | Credit amended to Adeyani | | P2, P3 |
| FT | Full-time recap | | P7 |

## The people

| Person | Situation | Settings |
| --- | --- | --- |
| **Nadia**, producer | Runs the world feed's graphics for this match | Producer console |
| **Sam**, casual fan | Follows Saltmarsh because family does; streams on a service about 40 s behind live | Casual, club Saltmarsh, delay 40 s |
| **Priya**, fantasy manager | Owns Varlan; wants to know if he's worth keeping | Analyst, focus Varlan, metric pass difficulty |
| **Lucía**, late joiner | In Madrid; joins at minute 60 after work | Casual, Spanish |
| **Tom**, blind fan | Follows on a phone with a screen reader | Described feed, standard detail |

## Screens

The fan app is one web app. On a desktop it shows the match (our own 2D pitch
render standing in for the video) with overlays, plus a side panel. On a phone
it leaves out the pitch view: the scoreboard, the described feed when it's on,
the panel, the match state and the key moments stack in one column, as a second
screen next to the TV.

### Producer console

```text
PRODUCER                                 Saltmarsh 0–1 Kingsferry   23:41
State  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒        control → transition
───────────────────────────┬──────────────────────────────────────────────
 Feed preview              │ Shortlist
                           │ 1  Against the run of play          rank 0.91
   [ pitch + overlay ]     │    Kingsferry scored with their first
                           │    counter. Saltmarsh had 71% of the ball.
                           │    Evidence e1043 e1044 e1047 e1049
                           │    [Approve] [Edit] [Kill]   template · agent drafting
                           │ 2  Adeyani sprint 33.8 km/h         rank 0.74
                           │ 3  Key pass difficulty 0.82         rank 0.66
───────────────────────────┴──────────────────────────────────────────────
 On air: —       Queue: 1       Corrections: 0
```

Each card shows its reason and its evidence, and opening the evidence lists the
events; **Agent runs** shows the agents' work on it. A card starts as the
template version and swaps to the agent's version when it arrives, marked either
way. In a replay started as Nadia, nothing airs until she approves it (P3), and
Approve waits for an agent's draft that is on its way, so what airs is the
wording Nadia saw. A lower third approved after its moment goes on air from the
approval. Beside each card, **Edit** and **Kill** act before it airs, and
**Withdraw** takes it off air, after which **Approve again** puts it back;
**Redraft** asks the agents for fresh wording. The **Approve automatically**
switch lets cards through as they're found, from then on.

### Fan view, casual

```text
CASUAL · Saltmarsh                              Your stream: 40 s behind live
┌──────────────────────────────────────────────┐
│                                              │
│          [ match / 2D pitch ]                │
│                                              │
│   ┌──────────────────────────────────────┐   │
│   │ 0–1  Kingsferry score on the break   │   │
│   └──────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
Who's on top   Saltmarsh ▓▓▓▓▓▓▓▓▓▓▓▓░░░░ Kingsferry
Why it matters Saltmarsh have had most of the ball, but Kingsferry
               only needed one quick break.                 [events ▸]
```

Rule calls get a card during the stoppage (P5):

```text
VAR CHECK · Offside
Dellow was beyond the last defender when Varlan passed.
[ freeze-frame at the pass, offside line drawn ]
Offside is judged at the moment of the pass.                [events ▸]
```

### Fan view, analyst with player focus

```text
ANALYST · Focus Varlan (10) · Metric pass difficulty
State   0' ▓▓▓▓▓▓▓▓▓▓▓▒▒░░░▓▓▓▓▓▓▓▓ 45'
           control     trans  pressure
38'–45' Sustained pressure, Saltmarsh
        Final-third entries 14 · Shots 5 · Possession 78%
Varlan  Passes 41/46 · Avg difficulty 0.48 · Hardest 0.86 (31')
        Distance 6.2 km · Top speed 31.4 km/h
23'     Against the run of play
        Key pass completion chance 18% → difficulty 0.82   [events ▸]
```

Player focus keeps the club context on screen and adds the player's line to
every moment the player is involved in (P6). The chosen metric is pinned at the top.

### Described feed

```text
DESCRIBED FEED     Detail: Standard ▾   Pace: Normal ▾   [Pause]
30:36  Saltmarsh win the ball in a duel, in the opposition half.
30:47  Varlan, in the centre circle, plays a pass forward to Dellow,
       in the final third.
30:51  Dellow shoots with the right foot from 19 metres: goal.
30:51  Goal for Saltmarsh, scored by Dellow. Saltmarsh 1, Kingsferry 1.
30:51  VAR is checking the goal for offside.
32:11  VAR decision: no goal. The decision on the field is overturned.
       Saltmarsh 0, Kingsferry 1.
       On screen: VAR: No goal. Marco Dellow was offside when Teo Varlan
       played the pass, so the goal is ruled out. ...
```

Lines come from templates over the event data, so they say only what the events
contain. Each graphic is read out once, as it airs, in the viewer's language and
marked as such for the screen reader. The device's screen reader speaks the feed
through a live region at the pace the listener picks. The detail levels:

- **Key moments:** goals and shots, VAR, cards and penalties, substitutions,
  corrections and the clock (kick-off, added time, half-time, full time).
- **Standard** adds the build-up: changes of possession in open play, passes
  and runs that take the ball forward, crosses, through balls, fouls, offsides,
  injuries and set pieces other than throw-ins.
- **Full** adds every pass and run, throw-ins, tackles, interceptions,
  clearances, blocks and the keeper's claims.

When lines back up (P8):

- up to three waiting lines are said together, so a pass and the shot it sets
  up are heard as one;
- with more than three, in a fast replay, it says the key moments among them,
  each with the line that led up to it, then the latest line;
- after a pause it says every key moment that waited, then the latest line.

### Catch-up

```text
WHAT YOU MISSED, UP TO 59'
Saltmarsh had long spells of possession and pinned Kingsferry back
before the opener. Adeyani scored on the break at 23', then VAR ruled
out a Saltmarsh goal for offside. Varlan levelled at 52' and Saltmarsh
have controlled the game since.
Before you joined   23'      Femi Adeyani scores
                    33'      VAR: No goal
                    44'      Saltmarsh pinning Kingsferry back
                    52'      Teo Varlan scores
[Back to the match]
```

The recap agent writes it from the match's moments when the replay reaches its starting point. It
tells what happened, goals included, and leaves the score line to the scoreboard beside it. A fan
reading in Spanish or French gets it, and the moments under it, in their language once translated.

### Settings

Mode, club, player in focus, pinned metric, language, stream delay, calm mode,
the pitch view and its graphics, and the described feed with its detail and
pace. They're kept in the browser and restored on the next visit.

## Minute by minute

**23', Kingsferry score.** The goal ranks first on Nadia's shortlist, raised by
the match-state model because Saltmarsh were on top for most of the ten minutes
before it. Nadia gets the card at once with the template wording, the agent
version replaces it once drafted (8 to 24 seconds in the recorded evaluation
run) or at once when an earlier replay's draft is reused, and Nadia approves it
for air. Sam's stream is 40 s behind, so the overlay and the "why it matters"
card wait until the goal appears on Sam's screen, or until Nadia approves the
card if that comes later, and carry the wording she approved. Priya sees the
same moment with the key pass's difficulty. Tom hears the build-up as it happens
on the event feed and the goal line straight after.

**31', offside.** Every viewer gets the VAR status as soon as the check starts,
timed to their own playback. When the decision lands, Sam's card shows the
freeze-frame and the one-line rule. Tom hears the decision ("VAR decision: no
goal") and the card read out. Priya's view shows the pass that set it up,
Varlan's hardest completed pass so far.

**38'–45', pressure.** The state model marks a sustained pressure spell. Nadia's
shortlist offers it as a segment graphic. Priya's timeline shades the spell, and
the segment card gives its figures. Sam sees the card ("Saltmarsh pinning
Kingsferry back") at the next stoppage.

**Half-time.** Recaps in each mode. Tom's feed reads the score, the two key
moments and who has had the ball.

**52', Varlan equalises.** The goal card gives the shot's distance and speed
for analysts. Priya's player line updates. Sam's "who's on top" bar moves with
the shift in control.

**60', Lucía joins.** Lucía opens the app in Spanish, reads "what you missed"
in Spanish, goes back to the match, and from then on gets each card in Spanish
once its translation passes the check against the English source (figures,
minutes, names and score lines); a card that fails stays in English, marked as
such.

**63'–68', chaos.** The state model finds neither side in control: rapid
changes of possession, few completed sequences. Nadia gets a rhythm card on how
often the ball changed hands in the last three minutes and the longest run of
passes either side strung together. Priya sees the chaos segment on the
timeline.

**74', handball check.** Same pattern as the offside: status first, decision and
rule explanation in the stoppage.

**81' and 84', the amended goal.** The 81st-minute goal is first recorded as a
Penhallow own goal, and an "own goal" card airs. At 84' the feed amends the
credit to Adeyani. Every insight citing the original event is flagged, and the
goal's card is restated with the corrected facts. Nadia approved the old wording,
so the corrected card comes off air and waits for her again, listed under
corrections beside the correction notice. Nadia approves the corrected card and
the notice. Fans' cards update when their streams reach 84', and say the provider
corrected them. Tom's feed reads the correction.

**Full time.** Recaps in each mode and language.

## What the overlay data has to carry

From the walkthrough, each item in the overlay feed needs:

- **Identity and lineage:** item ID, match ID, the event IDs it cites, and the ID
  of any item it corrects or replaces
- **Timing:** match clock (period, minute, second), feed timestamp, the match
  time it may show from (`shown_at`, so each client can hold it against its own
  playback), duration
- **Ranking:** rank score and the reason it was ranked
- **Kind:** moment, stat, player tag, rule call, segment, recap, correction
- **Content:** template ID and field values for graphics systems; text per mode
  and language; a plain-text equivalent for screen readers
- **Provenance:** template or agent, the agent run ID, and which checks passed
- **Status:** drafted, approved, withdrawn or killed, with who changed it and
  when
- **Presentation hints:** placement (lower third, side panel, full card), motion
  level for calm mode

The contract that carries them, and the rules for timing, approval and corrections,
is [overlay.md](overlay.md).

## The video

[On YouTube](https://youtu.be/rT6zPgLGF38), 1:55 long, its footage filmed from the deployed app.

| Time | Beat | Shows |
| --- | --- | --- |
| 0:00–0:10 | What Footnote does, in one line | Pitch with an overlay landing |
| 0:10–0:35 | 23' goal: ranked shortlist, reason, evidence, the agents' run (MCP tool calls, checks, time and tokens), approve | Nadia's console, Agent runs |
| 0:35–0:57 | The same goal for Priya (player focus), Lucía (Spanish) and Sam (held for the stream delay) | Each fan's pitch in turn, then the three side by side |
| 0:57–1:20 | 31' offside: the announcements Tom's described feed gave the screen reader, read by text-to-speech | Described feed with audio and captions |
| 1:20–1:35 | 84' correction reaches the console, and the corrected graphic goes on air | Corrections, the restated card back for approval |
| 1:35–1:50 | How it runs: architecture, state model scored against the answer key, measured latency | Diagram and figures |
| 1:50–1:55 | Close and synthetic-data disclaimer | End card |

The music was synthesised in code for the video, and the voice is a Windows text-to-speech voice
reading the feed's own words, trimmed to fit.

## The judges' path

The judges' path is in the [README](../README.md#try-it).
