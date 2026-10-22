"""Pre-generate the agent's speech so calls play without waiting for text-to-speech.

Text-to-speech is the slow part on a machine without an NVIDIA GPU (10-30 s per sentence on a
laptop CPU). Everything the agent can say is either a fixed sentence or built from the order
(greeting, order details, the promised-date confirmation), so all of it can be made in advance.

    # 1. Fixed sentences (same for every order). Can be made on any machine and copied:
    python -m voice_agent.prepare --static

    # 2. Sentences for specific orders (run on the demo machine, on the demo day - the
    #    greeting uses the order's current balance and "tomorrow" depends on today's date):
    python -m voice_agent.prepare --order ORD-2026-0007 --order ORD-2026-0008

    # Options: --langs en,te (with --static), --all-langs (all 4 languages for orders),
    #          --days 7 (date confirmations)

The audio is stored in CACHE_DIR (voice_agent/cache). Copying that folder to another machine
with the same TTS settings reuses it.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import replace
from datetime import date, timedelta

import httpx

from .brain import Brain
from .config import get_settings
from .models import CallContext, Classification
from .phrases import LANGS, split_sentences, static_sentences
from .tts import ParlerTTS
from .tts_cache import CachedTTS, cache_key

log = logging.getLogger("voice_agent.prepare")


def _never(*_args) -> Classification:  # the classifier is not used when only rendering text
    return Classification()


def order_sentences(ctx: CallContext, days: int = 7) -> list[str]:
    """Every order-specific sentence the agent may say on this call."""
    texts = [Brain(ctx, _never).greeting().text]

    b = Brain(ctx, _never)
    b.greeting()
    texts.append(b._on_main(Classification(intent="ask_details")).text)

    for offset in range(0, days + 1):
        b = Brain(ctx, _never)
        b.greeting()
        texts.append(b._confirm_date(ctx.today + timedelta(days=offset)).text)

    static = set(static_sentences(ctx.language))
    out: list[str] = []
    for text in texts:
        for sentence in split_sentences(text):
            if sentence not in static and sentence not in out:
                out.append(sentence)
    return out


def fetch_context(order: str) -> CallContext:
    s = get_settings()
    r = httpx.get(f"{s.backend_url.rstrip('/')}/api/internal/reminder-context", params={"order": order},
                  headers={"X-Agent-Secret": s.voice_agent_secret}, timeout=15)
    if r.status_code == 401:
        sys.exit("Backend rejected the secret: VOICE_AGENT_SECRET must match backend/.env")
    if r.status_code == 404:
        sys.exit(f"Order {order} not found")
    r.raise_for_status()
    return CallContext.from_dict(r.json()["context"])


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m voice_agent.prepare", description=__doc__.split("\n\n")[0])
    p.add_argument("--static", action="store_true", help="fixed sentences in all 4 languages")
    p.add_argument("--order", action="append", default=[], help="order number or id (repeatable)")
    p.add_argument("--all-langs", action="store_true", help="order sentences in all 4 languages")
    p.add_argument("--langs", help="limit --static to these languages, e.g. en,te (default: all 4)")
    p.add_argument("--days", type=int, default=7, help="promised-date confirmations for the next N days")
    p.add_argument("--today", type=date.fromisoformat, help="pretend today is YYYY-MM-DD (default: backend's date)")
    args = p.parse_args(argv)
    if not args.static and not args.order:
        p.error("give --static and/or --order")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    s = get_settings()
    jobs: list[tuple[str, str]] = []
    if args.static:
        langs = [x.strip() for x in args.langs.split(",")] if args.langs else list(LANGS)
        bad = [x for x in langs if x not in LANGS]
        if bad:
            p.error(f"unknown language(s): {', '.join(bad)} (use {', '.join(LANGS)})")
        jobs += [(t, lang) for lang in langs for t in static_sentences(lang)]
    for order in args.order:
        ctx = fetch_context(order)
        if args.today:
            ctx = replace(ctx, today=args.today)
        for lang in (LANGS if args.all_langs else (ctx.language,)):
            jobs += [(t, lang) for t in order_sentences(replace(ctx, language=lang), args.days)]

    voice = lambda lang: f"{s.tts_model}|{s.voice_description(lang)}"  # noqa: E731 - same key as the server
    tts = CachedTTS(ParlerTTS(s.tts_model, s.voice_description, s.tts_device), s.cache_dir, voice)
    todo = [(t, lang) for t, lang in dict.fromkeys(jobs)
            if not (tts.dir / f"{cache_key(t, lang, voice(lang))}.wav").exists()]
    print(f"{len(jobs)} sentences, {len(jobs) - len(todo)} already prepared, {len(todo)} to generate")
    started = time.monotonic()
    for i, (text, lang) in enumerate(todo, 1):
        t0 = time.monotonic()
        tts.get(text, lang)
        left = (time.monotonic() - started) / i * (len(todo) - i)
        print(f"[{i}/{len(todo)}] {lang} {time.monotonic() - t0:4.1f}s  ~{left / 60:.0f} min left  {text[:60]}")
    print(f"Done. Audio is in {tts.dir}")


if __name__ == "__main__":
    main()
