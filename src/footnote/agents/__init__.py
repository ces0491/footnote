"""The agents: they word the moments the processor finds, and code checks every word they write.

The agents service claims each insight that wants a draft (the processor leaves it pending in
Postgres and notifies the service), runs a writer agent built with Microsoft Agent Framework on a
Foundry model, and has code check the draft before anyone sees it (`writer.py`). The writer reads
the match only through the match tools (footnote.tools), served over MCP by the same process. It
never types a figure: it writes placeholders that code fills from the facts the tools returned.

A draft that fails its checks gets one chance to be revised; one that still fails, or that doesn't
arrive within the deadline, leaves the template's wording on screen, and the insight says why
(`worker.py`). Accepted drafts are cached by the job that made them, so later replays of the same
match reuse them, and a daily cap on agent runs bounds what the service can spend.
"""
