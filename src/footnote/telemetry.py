"""Tracing to Application Insights, for the agents service.

Given APPLICATIONINSIGHTS_CONNECTION_STRING (infra/agents.bicep sets it in Azure), traces go to
Application Insights through the Azure Monitor OpenTelemetry distro, signed in with the service's
managed identity: the resource takes no keys. A trace covers each card an agent drafts (the job,
then Agent Framework's own spans for the agent's run, its model calls and its tool calls), each batch
of translations, the producer's desk requests and the Azure SDK's calls, such as the pushes to Web
PubSub. Every span is kept: the distro would otherwise sample at five spans a second, which drops
model and tool calls from a card's trace when a replay's first cards come together. Prompts and
replies are left out of the spans. Traces are all this sends, into the Log Analytics workspace and
under its daily cap: logs stay in the container logs, and no metrics go, the exporter's own
statistics included.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import trace

log = logging.getLogger(__name__)

tracer = trace.get_tracer("footnote")


def configure(service_name: str) -> bool:
    """Send this process's traces to Application Insights; returns False when none is configured."""
    connection = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not connection:
        return False
    from agent_framework.observability import enable_instrumentation
    from azure.identity import AzureCliCredential, ManagedIdentityCredential
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry.sdk.resources import Resource

    client_id = os.environ.get("AZURE_CLIENT_ID")
    credential = ManagedIdentityCredential(client_id=client_id) if client_id else AzureCliCredential()
    # The distro exports logs and metrics as well unless these say "none"; it has no argument that
    # turns them off (1.8.11 overwrites a disable_logging or disable_metrics with what these say).
    # The trace exporter also sends a metric of the service's resource attributes with each batch,
    # its own statistics to the resource every 15 minutes and Statsbeat to Microsoft, and it samples
    # at five spans a second unless told a sampler.
    os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
    os.environ.setdefault("APPLICATIONINSIGHTS_OPENTELEMETRY_RESOURCE_METRIC_DISABLED", "true")
    os.environ.setdefault("APPLICATIONINSIGHTS_SDKSTATS_DISABLED", "true")
    os.environ.setdefault("APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL", "true")
    os.environ.setdefault("OTEL_TRACES_SAMPLER", "always_on")
    configure_azure_monitor(
        connection_string=connection,
        credential=credential,
        resource=Resource.create({"service.name": service_name}),
        enable_live_metrics=False,
        enable_performance_counters=False,
    )
    enable_instrumentation(enable_sensitive_data=False)
    log.info("tracing to Application Insights as %s", service_name)
    return True
