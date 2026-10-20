"""Match tools: what an agent may read about a moment, served over MCP.

Every call is scoped to one insight of one run by headers the agents service sets and the model
never sees (`scope.py`). The tools read the run's stored feed up to the insight's seq, folded with
the code the processor runs, so an agent sees the match as viewers had it at that moment: nothing
later, and nothing from another run. Each figure a tool returns is a fact (footnote.insights.facts)
with its key, value, the text a card shows and what it is; agents write cards with the keys and
code fills in the figures (`server.py`).
"""
