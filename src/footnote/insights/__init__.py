"""Insights: the moments worth putting on screen, ranked, worded and checked.

`moments` finds candidate moments as a run's feed is folded and ranks them with the match-state
model. `facts` holds the figures and names a card may state, all computed by code. `draft` is a
card's wording, with placeholders where the figures go, and the checks every draft passes before
anyone sees it. `templates` writes the code's own draft of each moment, which viewers see first and
which stays on screen whenever an agent's draft doesn't arrive in time or fails a check. `book`
keeps a run's insights and what later happens to them: VAR decisions, corrections from the provider
and the restated versions they lead to.
"""
