"""Familect dictionary — read/write familect.json."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from src.config import DICT_PATH

# Simple asyncio lock to prevent concurrent writes
_write_lock = asyncio.Lock()


def _load_sync() -> list[dict]:
    try:
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def load() -> list[dict]:
    """Load all entries synchronously (safe to call from anywhere)."""
    return _load_sync()


async def save(args: dict[str, Any], added_by: str) -> dict | None:
    """Save a new word. Returns the saved entry, or None if it already exists."""
    term = args.get("term", args.get("word", "")).strip()
    if not term:
        return None

    async with _write_lock:
        entries = _load_sync()

        # Deduplicate
        if any(e.get("term", e.get("word", "")).lower() == term.lower() for e in entries):
            print(f'[dict] "{term}" already exists, skipping')
            return None

        entry: dict = {
            "term":       term,
            "definition": args.get("definition", "").strip(),
            "added_by":   added_by,
            "saved_at":   datetime.now(timezone.utc).isoformat(),
        }
        if pos := args.get("part_of_speech", "").strip():
            entry["part_of_speech"] = pos
        if pronunciation := args.get("pronunciation", "").strip():
            entry["pronunciation"] = pronunciation
        if example := args.get("example", "").strip():
            entry["example"] = example

        entries.append(entry)

        # Atomic write: write to .tmp then rename
        tmp = DICT_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        os.replace(tmp, DICT_PATH)

        print(f'[dict] saved "{term}"')
        return entry


def build_context() -> str:
    """Build the dictionary context string for the system prompt."""
    entries = load()
    if not entries:
        return "The Familect is currently empty."
    lines = [f"The Familect holds {len(entries)} word(s):"]
    for e in entries:
        term = e.get("term", e.get("word", "?"))
        pos  = e.get("part_of_speech", "")
        pos_str = f" ({pos})" if pos else ""
        pron_str = f" [{e['pronunciation']}]" if e.get("pronunciation") else ""
        line = f"- {term}{pos_str}{pron_str} — {e.get('definition', '')} · added by {e.get('added_by', '?')}"
        if example := e.get("example"):
            line += f' · e.g. "{example}"'
        lines.append(line)
    return "\n".join(lines)


def ensure_file() -> None:
    """Create familect.json if it doesn't exist."""
    if not os.path.exists(DICT_PATH):
        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2, ensure_ascii=False)
        print(f"[dict] created {DICT_PATH}")
