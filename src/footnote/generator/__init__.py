"""Synthetic football league and match generator.

A seeded agent-based simulation: hidden match states (regimes) shape how two
teams of simulated players pass, carry, press and shoot; officials judge
offside, handball and fouls from the simulated positions; a provider layer turns
what happened into an event feed, and keeps the hidden truth in a separate
answer key.
"""
