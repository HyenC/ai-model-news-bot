from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state" / "seen.json"
OUT_DIR = ROOT / "out"
CANDIDATES_PATH = OUT_DIR / "candidates.json"
PENDING_PATH = OUT_DIR / "pending_seen.json"
VERDICTS_PATH = OUT_DIR / "verdicts.json"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"seen": {}, "posted": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    for k in state["seen"]:
        state["seen"][k] = sorted(set(state["seen"][k]))[-20000:]
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
