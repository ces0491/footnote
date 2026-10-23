# SCOPE — Footnote

## Purpose

A solo entry to the Microsoft Premier League Hackathon that turns synthetic
football events into explained match intelligence: each moment ranked from a
base for its kind, raised by a match-state model and the moment's figures,
worded for each mode and language, linked to the events behind it, and
delivered when each viewer's stream reaches it. Who it serves and why is in
[docs/audience.md](docs/audience.md).

## Done

Data

- [x] Seeded generator for a fictional league: clubs, players, team styles, and
      matches driven by hidden match states. Events include offside, handball,
      VAR checks and an amended event, plus player and ball positions
- [x] Answer key (hidden states, team strengths) stored apart from the event feed
- [x] Calibration report comparing generated match-level averages with
      published figures, sources cited ([docs/calibration.md](docs/calibration.md))

Pipeline (deployed on Azure)

- [x] Replayer → Event Hubs → processor on Container Apps → Postgres → Web PubSub → browser
- [x] Live stats: pass distance, accuracy and difficulty rating; ball and shot
      speed; player speed and distance tags when thresholds are crossed
- [x] Match-state timeline updated live, and the state model scored against the
      answer key on held-out matches whose team styles it wasn't fitted on
- [x] Template overlay p95 under 1 s from event publish to browser, measured on
      the deployed stack (461 ms on 21 October, [docs/architecture.md](docs/architecture.md#latency))

Explain

- [x] Moments ranked from a base for each kind, raised by the state model and
      the moment's figures; the producer sees a shortlist, each item with its reason
- [x] Agents (Agent Framework, Foundry models) read the numbers through our MCP
      tools; code checks every figure in their output; each sentence cites the
      events it rests on or uses a fact code computed
- [x] A failed or slow agent falls back to the template, and the fallback is visible
- [x] An amended event flags every insight that cited it, and its overlay can be withdrawn
- [x] Half-time and full-time recaps, and a "what did I miss" catch-up

Render and personalise

- [x] Timed overlay data contract documented, with a reference renderer on our
      own 2D pitch view
- [x] Producer console: approve, edit or kill a graphic before it airs
- [x] Spoiler-safe delivery: the viewer sets their stream delay, and nothing
      reaches them before their playback does
- [x] Casual and analyst modes, favourite club, player focus layered on the
      club, one chosen metric
- [x] Casual mode explains offside, handball and VAR calls when they happen,
      using player positions at that moment
- [x] Described feed: text play-by-play of ball position, passes and build-up
      for screen readers, with detail and pace controls
- [x] Calm mode: reduced motion, no flashing, overlays the viewer can hide
- [x] Agents write in English; Azure AI Translator renders Spanish and French;
      code checks that numbers, minutes and names survive translation
- [x] Ready-made fan profiles for judges to switch between, with each viewer's
      settings kept in the browser
- [ ] Viewer profiles stored server-side under an anonymous ID kept in the
      browser

Quality and submission

- [x] No secrets in code; Azure budget alert set
- [ ] `azd up` deploys from scratch, verified on an empty environment. Tried on
      23 October: Azure refused the model deployment and the Postgres server
      (README, Deploying to Azure)
- [x] CI runs lint, type checks, tests and agent-output evaluations
- [x] README: judge quick-start, architecture diagram, synthetic-data disclaimer,
      link to docs/audience.md
- [ ] Video under 2:00 showing the deployed app; public repo; elevator pitch
- [ ] Live demo stays up and free for judges until 2026-11-10
- [ ] Submitted by Tuesday 27 October, evening SAST

## Out of scope

- Real match data, real footage, real clubs, players, crests or league branding
- Generating events from video: a stretch goal, started only after every Done
  item is ticked, and kept out of the video unless it works
- Win probability, and betting or odds features
- Synthetic voice commentary; screen readers handle speech for the described feed
- Testing with blind or partially sighted users. The README names it as the
  first next step
- Our own user accounts and sign-in. A profile store would take an external
  user ID from the host platform's login
- Multi-tenancy, load beyond demo traffic, multi-region, SLAs
- Integration with a real broadcast graphics engine
- Copying SCLA or rugby-tournament-predictor code; methods carry over, code is new

## Bar

Competition entry, judged on a working deployment and a public repo. Production
practice in infrastructure as code, CI, tests on the models and the overlay
contract, managed identity and tracing. Left out: load testing, a formal
security review and on-call docs.

## Decision

Ces, at the Friday 23 October checkpoint: walk the judge quick-start against
the deployed app end to end. Anything still unticked by then is either finished
on Monday 26 October or dropped, with an entry in the revision history below.
If cuts are needed, in this order: the rule explainers; server-side viewer
profiles (the ready-made fan profiles stay, with settings kept in the browser);
the described feed's detail and pace controls (one level and pause stay); and
the amended-event demo last, as the clearest moment for the Enterprise
category.

## Revision history

- 2026-10-19: initial scope
- 2026-10-20: checkpoint moved from Sunday 25 to Friday 23 October
- 2026-10-20: cut order revised: viewer profiles and the described feed's
  controls go before the amended-event demo
