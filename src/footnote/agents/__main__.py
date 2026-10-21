"""Run the agents service: python -m footnote.agents.

One process serves the match tools over MCP on localhost (footnote.tools) and runs the worker that
drafts cards with them (worker.py). It wakes on the processor's notifications on the
`footnote_agents` channel and also looks for jobs every few seconds, in case one was missed. It
also serves the producer's desk (desk.py) to the web app, inside the Container Apps environment,
and, given a Translator, translates the cards viewers see into Spanish and French (translator.py).

Settings come from the environment (set by infra/agents.bicep in Azure):

    FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL   the Foundry project and the model deployment
    WEBPUBSUB_ENDPOINT, WEBPUBSUB_HUB
    POSTGRES_HOST, POSTGRES_DATABASE, POSTGRES_USER
    AZURE_CLIENT_ID                           the service's managed identity
    AGENT_DEADLINE_SECONDS, AGENT_DAILY_RUNS, AGENT_CONCURRENCY, AGENT_REASONING_EFFORT   optional
    MCP_PORT                                  the match tools' local port, 8100 unless set
    DESK_PORT                                 the producer's desk, 8080 unless set
    TRANSLATOR_ENDPOINT                       Azure AI Translator; cards stay in English without it
    APPLICATIONINSIGHTS_CONNECTION_STRING     traces to Application Insights (footnote.telemetry)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys

import aiohttp
import psycopg
import uvicorn
from agent_framework_foundry import FoundryChatClient
from azure.core.credentials_async import AsyncTokenCredential
from azure.messaging.webpubsubservice.aio import WebPubSubServiceClient

from footnote import cloud, telemetry
from footnote.agents.desk import Desk, create_app
from footnote.agents.store import AgentStore, PostgresSource
from footnote.agents.translator import AzureTranslator, TranslationStore, TranslationWorker
from footnote.agents.worker import Settings, Worker
from footnote.db.connect import TOKEN_SCOPE, conninfo, entra_pool
from footnote.db.insights import AGENT_CHANNEL
from footnote.insights.translation import names_of
from footnote.live.analysis import Analysis
from footnote.live.match import SHOWCASE_MATCH_ID, load_match
from footnote.processor.push import WebPubSubPush
from footnote.tools.scope import Scopes
from footnote.tools.server import build_server

log = logging.getLogger("footnote.agents")


def settings() -> Settings:
    env = os.environ
    return Settings(
        model=cloud.require("FOUNDRY_MODEL"),
        deadline_seconds=float(env.get("AGENT_DEADLINE_SECONDS", "45")),
        daily_runs=int(env.get("AGENT_DAILY_RUNS", "150")),
        concurrency=int(env.get("AGENT_CONCURRENCY", "3")),
        reasoning_effort=env.get("AGENT_REASONING_EFFORT", "low"),
    )


async def listen(credential: AsyncTokenCredential, *wakes: asyncio.Event) -> None:
    """Wake the workers on each notification, reconnecting if the connection drops."""
    while True:
        try:
            token = await credential.get_token(TOKEN_SCOPE)
            async with await psycopg.AsyncConnection.connect(conninfo(), password=token.token, autocommit=True) as conn:
                await conn.execute(f"listen {AGENT_CHANNEL}")
                log.info("listening on %s", AGENT_CHANNEL)
                async for _ in conn.notifies():
                    for wake in wakes:
                        wake.set()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("listening for jobs failed; retrying in 5 s")
            await asyncio.sleep(5)


async def main() -> None:
    telemetry.configure("footnote-agents")
    match = load_match(os.environ.get("FOOTNOTE_MATCH_ID", SHOWCASE_MATCH_ID))
    analysis = Analysis.load(match)
    credential = cloud.credential()
    pool = entra_pool(credential, max_size=6)
    await pool.open(wait=True, timeout=120)

    port = int(os.environ.get("MCP_PORT", "8100"))
    tools = build_server(Scopes(PostgresSource(pool), match, analysis))
    mcp = uvicorn.Server(uvicorn.Config(tools.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning"))

    client = FoundryChatClient(
        project_endpoint=cloud.require("FOUNDRY_PROJECT_ENDPOINT"),
        model=cloud.require("FOUNDRY_MODEL"),
        credential=credential,
    )
    webpubsub = WebPubSubServiceClient(
        endpoint=cloud.require("WEBPUBSUB_ENDPOINT"), hub=cloud.require("WEBPUBSUB_HUB"), credential=credential
    )
    push = WebPubSubPush(webpubsub)
    worker = Worker(AgentStore(pool), push, client, f"http://127.0.0.1:{port}/mcp", settings())
    wake, wake_translator = asyncio.Event(), asyncio.Event()
    desk_port = int(os.environ.get("DESK_PORT", "8080"))
    desk = uvicorn.Server(
        uvicorn.Config(create_app(Desk(pool, push)), host="0.0.0.0", port=desk_port, log_level="warning")
    )
    translator_endpoint = os.environ.get("TRANSLATOR_ENDPOINT", "")
    http = aiohttp.ClientSession()
    translations = (
        TranslationWorker(
            TranslationStore(pool), push, AzureTranslator(translator_endpoint, credential, http), names_of(match.meta)
        )
        if translator_endpoint
        else None
    )

    stop = asyncio.Event()
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)

    log.info("drafting with %s; match tools on port %d, the desk on %d", worker.settings.model, port, desk_port)
    log.info("translating cards: %s", "yes" if translations else "no Translator configured")
    async with webpubsub, http:
        tasks = [
            asyncio.create_task(mcp.serve(), name="mcp"),
            asyncio.create_task(desk.serve(), name="desk"),
            asyncio.create_task(listen(credential, wake, wake_translator), name="listen"),
            asyncio.create_task(worker.run(wake), name="worker"),
            asyncio.create_task(stop.wait(), name="stop"),
        ]
        if translations is not None:
            tasks.append(asyncio.create_task(translations.run(wake_translator), name="translator"))
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                failure = None if task.get_name() == "stop" else task.exception()
                if failure is not None:
                    raise failure
        finally:
            mcp.should_exit = True
            desk.should_exit = True
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            await pool.close()
            await credential.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for noisy in ("azure", "httpx", "httpx2", "mcp", "agent_framework"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if sys.platform == "win32":
        # For local runs: psycopg's async mode can't use Windows' default (proactor) loop.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
