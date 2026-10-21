"""The agents service's translator: each live card's wording in Spanish and French.

The version of a card viewers see is translated with Azure AI Translator, the names given to it as
dictionary entries, and checked by code (footnote.insights.translation); the run's viewers are then
pushed the card again with its translations, which the overlay contract carries by language
(docs/overlay.md).
Only the current version of a live card in a running replay is translated: an agent's draft usually
replaces the template's within seconds, and a viewer whose stream is behind gets the later one.

Every replay is the same match, so the same wording comes round again: translations are kept under
a hash of the English, the names protected and TRANSLATION_VERSION, and reused, so a replay after
the first calls the Translator only for wording it hasn't met (a producer's edit, say). A failed call
is retried with backoff; a translation that fails the check is kept with its problems and not shown.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Protocol

import aiohttp
from azure.core.credentials_async import AsyncTokenCredential
from psycopg.types.json import Jsonb

from footnote.db.connect import Pool
from footnote.db.insights import next_rev, push_insights
from footnote.insights.translation import LANGUAGES, PARTS, check, prepare, read_back

log = logging.getLogger(__name__)

# Change it when the preparing or the check changes, so translations kept from before aren't reused.
TRANSLATION_VERSION = "2026-10-21.4"
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"
TRANSLATE_PATH = "translator/text/v3.0/translate"


class Translator(Protocol):
    async def translate(self, texts: list[str], languages: tuple[str, ...]) -> list[dict[str, str]]:
        """Each text (HTML, from `prepare`) in each language: one dict per text, by language."""
        ...


class AzureTranslator:
    """Azure AI Translator's v3 API on the resource's own subdomain, with a Microsoft Entra token."""

    def __init__(self, endpoint: str, credential: AsyncTokenCredential, session: aiohttp.ClientSession) -> None:
        self.url = f"{endpoint.rstrip('/')}/{TRANSLATE_PATH}"
        self.credential = credential
        self.session = session

    async def translate(self, texts: list[str], languages: tuple[str, ...]) -> list[dict[str, str]]:
        token = await self.credential.get_token(TOKEN_SCOPE)
        params = [("api-version", "3.0"), ("from", "en"), ("textType", "html"), *(("to", lang) for lang in languages)]
        async with self.session.post(
            self.url,
            params=params,
            json=[{"Text": text} for text in texts],
            headers={"Authorization": f"Bearer {token.token}"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            response.raise_for_status()
            body = await response.json()
        return [{t["to"]: t["text"] for t in item["translations"]} for item in body]


@dataclass(frozen=True)
class Pending:
    run_id: str
    insight_id: str
    version: int
    card: dict  # the English wording: headline, casual, analyst and the rest

    @property
    def ref(self) -> tuple[str, str, int]:
        return (self.run_id, self.insight_id, self.version)


Results = dict[str, dict]  # by language: {"card": {...} or None, "problems": [...] or None}

_PENDING = """
select v.run_id, v.insight_id, v.version, v.card
  from insights i
  join runs r on r.run_id = i.run_id
  join insight_versions v on v.run_id = i.run_id and v.insight_id = i.insight_id and v.version = i.version
 where r.status = 'running' and i.live and i.status <> 'killed'
   and not exists (select 1 from card_translations t
                    where t.run_id = v.run_id and t.insight_id = v.insight_id and t.version = v.version)
 order by v.created_at
 limit %s
"""


class TranslationStore:
    def __init__(self, pool: Pool) -> None:
        self.pool = pool

    async def pending(self, limit: int) -> list[Pending]:
        async with self.pool.connection() as conn:
            rows = await (await conn.execute(_PENDING, (limit,))).fetchall()
        return [Pending(r["run_id"], r["insight_id"], r["version"], r["card"]) for r in rows]

    async def cached(self, key: str) -> Results | None:
        async with self.pool.connection() as conn:
            rows = await (
                await conn.execute("select lang, card, problems from translation_cache where cache_key = %s", (key,))
            ).fetchall()
        found = {r["lang"]: {"card": r["card"], "problems": r["problems"]} for r in rows}
        return found if set(found) >= set(LANGUAGES) else None

    async def cache(self, key: str, results: Results) -> None:
        async with self.pool.connection() as conn, conn.cursor() as cur:
            await cur.executemany(
                "insert into translation_cache (cache_key, lang, card, problems) values (%s, %s, %s, %s)"
                " on conflict do nothing",
                [(key, lang, _json(r["card"]), _json(r["problems"])) for lang, r in results.items()],
            )

    async def store(self, pending: Pending, results: Results) -> dict | None:
        """Keep the translations; if the version is still the one viewers see, push the card again with
        them. Returns the push, or None when a later version has replaced it."""
        async with self.pool.connection() as conn, conn.transaction():
            async with conn.cursor() as cur:
                await cur.executemany(
                    "insert into card_translations (run_id, insight_id, version, lang, card, problems)"
                    " values (%s, %s, %s, %s, %s, %s) on conflict do nothing",
                    [
                        (
                            pending.run_id,
                            pending.insight_id,
                            pending.version,
                            lang,
                            _json(r["card"]),
                            _json(r["problems"]),
                        )
                        for lang, r in results.items()
                    ],
                )
            row = await (
                await conn.execute(
                    "select version from insights where run_id = %s and insight_id = %s for update",
                    (pending.run_id, pending.insight_id),
                )
            ).fetchone()
            if row is None or row["version"] != pending.version or not any(r["card"] for r in results.values()):
                return None
            # A new state of the card for the pages that keep each one: its translations changed.
            await conn.execute(
                "update insights set updated_at = now() where run_id = %s and insight_id = %s",
                (pending.run_id, pending.insight_id),
            )
            rev = await next_rev(conn, pending.run_id)
            pushes = await push_insights(conn, pending.run_id, {pending.insight_id: rev})
            return pushes[0] if pushes else None


def _json(value: object) -> Jsonb | None:
    return None if value is None else Jsonb(value)


class Push(Protocol):
    async def send(self, run_id: str, message: dict) -> None: ...


class TranslationWorker:
    def __init__(
        self,
        store: TranslationStore,
        push: Push,
        translator: Translator,
        names: list[str],
        languages: tuple[str, ...] = LANGUAGES,
        batch: int = 10,
    ) -> None:
        self.store = store
        self.push = push
        self.translator = translator
        self.names = names
        self.languages = languages
        self.batch = batch
        self.failures = 0

    def key(self, card: dict) -> str:
        payload = {
            "parts": [card.get(part, "") for part in PARTS],
            "names": self.names,
            "languages": list(self.languages),
            "version": TRANSLATION_VERSION,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    async def run(self, wake: asyncio.Event, poll_seconds: float = 2.0) -> None:
        """Translate what viewers see until cancelled, looking again when woken and every few seconds,
        and backing off while the Translator fails."""
        while True:
            try:
                await self.drain()
                self.failures = 0
            except Exception:
                self.failures += 1
                log.exception("translating cards failed (%d in a row)", self.failures)
            wait = poll_seconds if self.failures == 0 else min(60.0, poll_seconds * 2**self.failures)
            try:
                await asyncio.wait_for(wake.wait(), timeout=wait)
            except TimeoutError:
                pass
            wake.clear()

    async def drain(self) -> int:
        """Translate a batch of the cards waiting; returns how many."""
        pending = await self.store.pending(self.batch)
        if not pending:
            return 0
        results: dict[tuple[str, str, int], Results] = {}
        fresh: list[Pending] = []
        for p in pending:
            hit = await self.store.cached(self.key(p.card))
            if hit is not None:
                results[p.ref] = hit
            else:
                fresh.append(p)
        if fresh:
            translated = await self._translate(fresh)
            for p, r in zip(fresh, translated, strict=True):
                await self.store.cache(self.key(p.card), r)
                results[p.ref] = r
        for p in pending:
            message = await self.store.store(p, results[p.ref])
            if message is not None:
                try:
                    await self.push.send(p.run_id, message)
                except Exception:
                    log.exception("push failed for %s/%s", p.run_id, p.insight_id)
        return len(pending)

    async def _translate(self, cards: list[Pending]) -> list[Results]:
        """Every part of every card in one request, checked card by card."""
        english = [{part: str(p.card.get(part) or "") for part in PARTS} for p in cards]
        texts = [text for card in english for text in prepare(card, self.names)]
        out = await self.translator.translate(texts, self.languages)
        results = []
        for i, p in enumerate(cards):
            mine = out[i * len(PARTS) : (i + 1) * len(PARTS)]
            per: Results = {}
            for lang in self.languages:
                translated = read_back(english[i], [text.get(lang, "") for text in mine])
                problems = check(english[i], translated, self.names, lang)
                per[lang] = {"card": None if problems else translated, "problems": problems or None}
                if problems:
                    log.info(
                        "%s/%s v%d: the %s translation failed the check: %s",
                        p.run_id,
                        p.insight_id,
                        p.version,
                        lang,
                        problems,
                    )
            results.append(per)
        return results
