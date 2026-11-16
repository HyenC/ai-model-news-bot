from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state" / "seen.json"
OUT_DIR = ROOT / "out"
CANDIDATES_PATH = OUT_DIR / "candidates.json"
PENDING_PATH = OUT_DIR / "pending_seen.json"
VERDICTS_PATH = OUT_DIR / "verdicts.json"
CATALOG_PATH = OUT_DIR / "catalog.tsv"          # 플랫폼별 전체 모델 목록 (사용 가능 여부 확인용)
CATALOG_STATUS_PATH = OUT_DIR / "catalog_status.json"  # 플랫폼별 목록을 읽었는지
RETIREMENTS_PATH = OUT_DIR / "retirements.json"          # 제공 종료 공지 후보
RETIRE_VERDICTS_PATH = OUT_DIR / "retire_verdicts.json"  # 제공 종료 공지 판단 결과
SERVED_PATH = OUT_DIR / "served_models.json"             # 우리가 서비스하는 모델 목록 (드롭샷 커넥터에서)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"seen": {}, "posted": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    for k in state["seen"]:
        state["seen"][k] = sorted(set(state["seen"][k]))[-20000:]
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n")


WEEKLY_DIR = ROOT / "state" / "weekly"                   # 주간 정리용 기록 (주 시작 월요일 KST 날짜별 파일)
WEEKLY_KEEP = 8                                          # 최근 몇 주치 기록을 남길지
KST = timezone(timedelta(hours=9))


def week_start(dt: datetime) -> date:
    """dt 가 속한 주(KST 월~일)의 월요일."""
    d = dt.astimezone(KST).date()
    return d - timedelta(days=d.weekday())


def append_weekly(entry: dict) -> None:
    """보낸 새 모델 소식을 이번 주 파일에 덧붙이고, 오래된 주 파일은 지운다.
    공개 저장소에 올라가므로 공개된 모델 소식만 넣는다(제공 종료 공지는 넣지 않는다)."""
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = WEEKLY_DIR / f"{week_start(now).isoformat()}.json"
    items = json.loads(path.read_text()) if path.exists() else []
    items.append({**entry, "at": now.isoformat()})
    write_json(path, items)
    cutoff = (week_start(now) - timedelta(weeks=WEEKLY_KEEP)).isoformat()
    for f in WEEKLY_DIR.glob("*.json"):
        if f.stem < cutoff:
            f.unlink()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
