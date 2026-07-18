"""LLM arranger: group a loaded MIDI's tracks across the connected phones.

On song load, the track list (name, instrument, drum flag, note count) and
the roster of phones go to an LLM which answers with a strict JSON mapping
{section_id: [part indices]} — clustering by musical role and register (the
rhythm section together, melody spotlighted, pads spread). Uses Backboard as
the gateway (X-API-Key, same account as the announcer). Defensive on every
axis: 6s timeout, JSON extracted from fences, unknown sections/indices
dropped, unassigned parts round-robined back in — and if anything at all
fails the engine simply keeps its default round-robin. Never load-bearing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.request

import config

log = logging.getLogger("arranger")

PROMPT = (
    "You are the orchestra arranger for a distributed phone orchestra. Group the "
    "MIDI tracks below across the available phones by musical role and frequency "
    "range: rhythm/percussion together, bass low in the room, melody spotlighted "
    "on its own phone when possible, pads/harmony spread. Reply with ONLY a JSON "
    'object mapping phone id to a list of track indices, e.g. {"s1": [0, 3], '
    '"s2": [1]}. Use every track index exactly once. No prose.\n'
)


def configured() -> bool:
    return bool(config.BACKBOARD_KEY)


async def arrange(tracks: list[dict], section_ids: list[str]) -> dict[str, list[int]] | None:
    """section_id -> part indices, or None (keep round-robin)."""
    if not configured() or len(section_ids) < 2 or len(tracks) < 2:
        return None
    digest = [{"i": i, "name": t.get("name", ""), "instrument": t.get("instrument", ""),
               "is_drum": bool(t.get("is_drum")), "notes": t.get("note_count", 0)}
              for i, t in enumerate(tracks)]
    body = json.dumps({
        "content": PROMPT + json.dumps({"tracks": digest, "phones": section_ids}),
        "llm_provider": config.BACKBOARD_PROVIDER,
        "model_name": config.BACKBOARD_MODEL,
        "memory": "off",
        "stream": False,
    }).encode()
    loop = asyncio.get_running_loop()
    try:
        resp = await asyncio.wait_for(loop.run_in_executor(None, _post, body), timeout=6.0)
    except Exception as e:  # noqa: BLE001 - the arranger is a bonus, never a blocker
        log.warning("arranger failed (%s) — round-robin stays", type(e).__name__)
        return None
    mapping = _parse(resp, section_ids, len(tracks))
    if mapping:
        log.info("arrangement: %s", mapping)
    return mapping


def _post(body: bytes) -> dict:
    req = urllib.request.Request(
        config.BACKBOARD_URL.rstrip("/") + "/threads/messages", data=body,
        headers={"Content-Type": "application/json", "X-API-Key": config.BACKBOARD_KEY})
    with urllib.request.urlopen(req, timeout=5.5) as resp:
        return json.loads(resp.read().decode())


def _parse(resp: dict, section_ids: list[str], n_tracks: int) -> dict[str, list[int]] | None:
    text = None
    for probe in (resp.get("content"), resp.get("response"), resp.get("text")):
        if isinstance(probe, str) and probe.strip():
            text = probe.strip()
            break
    if not text:
        return None
    if "{" in text:                              # strip prose / code fences
        text = text[text.index("{"):text.rindex("}") + 1]
    try:
        raw = json.loads(text)
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    mapping: dict[str, list[int]] = {}
    used: set[int] = set()
    for sid, idxs in raw.items():
        if sid not in section_ids or not isinstance(idxs, list):
            continue
        good = []
        for i in idxs:
            if isinstance(i, (int, float)) and 0 <= int(i) < n_tracks and int(i) not in used:
                good.append(int(i))
                used.add(int(i))
        if good:
            mapping[sid] = good
    if not mapping:
        return None
    leftovers = [i for i in range(n_tracks) if i not in used]
    for j, i in enumerate(leftovers):            # every part must sound somewhere
        sid = section_ids[j % len(section_ids)]
        mapping.setdefault(sid, []).append(i)
    return mapping
