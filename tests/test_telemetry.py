"""Tracing to Application Insights (footnote.telemetry): traces only, every span of them, and nothing
without a connection string. The distro itself is replaced, so nothing is sent."""

from __future__ import annotations

import os
from unittest import mock

import agent_framework.observability
import azure.monitor.opentelemetry
import pytest

from footnote import telemetry

CONNECTION = "InstrumentationKey=00000000-0000-0000-0000-000000000000"


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(azure.monitor.opentelemetry, "configure_azure_monitor", lambda **kw: calls.append(kw))
    monkeypatch.setattr(agent_framework.observability, "enable_instrumentation", lambda **kw: None)
    return calls


def test_nothing_is_set_up_without_a_connection_string(configured: list[dict]) -> None:
    with mock.patch.dict(os.environ, clear=True):
        assert telemetry.configure("footnote-agents") is False
    assert configured == []


def test_only_traces_are_sent(configured: list[dict]) -> None:
    env = {"APPLICATIONINSIGHTS_CONNECTION_STRING": CONNECTION, "AZURE_CLIENT_ID": "agents-identity"}
    with mock.patch.dict(os.environ, env, clear=True):
        assert telemetry.configure("footnote-agents") is True
        assert os.environ["OTEL_LOGS_EXPORTER"] == os.environ["OTEL_METRICS_EXPORTER"] == "none"
        assert os.environ["APPLICATIONINSIGHTS_OPENTELEMETRY_RESOURCE_METRIC_DISABLED"] == "true"
        # The exporter's own statistics, to the resource and to Microsoft, are metrics too.
        assert os.environ["APPLICATIONINSIGHTS_SDKSTATS_DISABLED"] == "true"
        assert os.environ["APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL"] == "true"
        # Every span kept: the distro's default samples at five spans a second.
        assert os.environ["OTEL_TRACES_SAMPLER"] == "always_on"
    [kwargs] = configured
    assert kwargs["connection_string"] == CONNECTION
    assert kwargs["enable_live_metrics"] is False
    assert kwargs["enable_performance_counters"] is False
    assert kwargs["resource"].attributes["service.name"] == "footnote-agents"
