"""1단계: 소스를 확인해서 새 후보를 out/candidates.json 에 쓴다.

- 처음 보는 소스는 지금 목록을 기준으로 바로 state 에 저장하고 후보로 내지 않는다.
- 나머지 새 항목은 out/pending_seen.json 에 적어 두고, publish.py 가 전송을 마친 뒤 state 에 반영한다.
마지막 줄에 'CANDIDATES=<개수>' 를 출력한다.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime, timedelta, timezone

from common import (
    CANDIDATES_PATH, CATALOG_PATH, CATALOG_STATUS_PATH, PENDING_PATH,
    load_state, save_state, write_json,
)
from sources import NEEDS_DESCRIPTION, PLATFORMS, SOURCES, page_info

# 한 소스에서 한꺼번에 이만큼 넘게 '새 항목'이 나오면 소스 쪽 변경(ID 체계 변경 등)으로 보고
# 보내지 않고 기준만 다시 잡는다. 채널 도배 방지용.
FLOOD_LIMIT = 80

# 출처 날짜가 처음 발견한 때보다 이만큼 넘게 이르면 지난 소식으로 보고 보내지 않는다.
# (목록에 옛 글이 다시 걸리는 경우 등) 날짜가 없으면 거르지 않는다.
# fal.ai 날짜는 공개 전에 만든 날짜일 때가 있어서 이 기준을 쓰지 않는다.
MAX_AGE = timedelta(days=3)
NO_AGE_CHECK = {"fal"}


def _too_old(source: str, date, now: datetime) -> bool:
    if source in NO_AGE_CHECK or not date:
        return False
    try:
        d = datetime.fromisoformat(str(date).replace("Z", "+00:00"))
    except ValueError:
        return False
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return now - d > MAX_AGE


def main() -> None:
    state = load_state()
    candidates, pending = [], {}
    state_changed = False
    catalog_rows, catalog_ok = [], {p: False for p in PLATFORMS}
    seeded = set(state.get("seeded_labels", []))
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    for name, fetch in SOURCES.items():
        try:
            items = fetch()
        except Exception:
            print(f"[경고] {name} 소스 실패, 이번 회차는 건너뜀", file=sys.stderr)
            traceback.print_exc()
            continue
        if name in PLATFORMS:
            catalog_ok[name] = True
            for _, iid, p in items:
                title = str(p.get("title") or "").replace("\t", " ")
                catalog_rows.append(f"{name}\t{iid}\t{title}\t{p['url']}")
        seen = set(state["seen"].get(name, []))
        # 소스 안의 하위 출처(블로그 하나하나 등)도 처음 보는 곳이면 기준점만 저장한다
        if name in state["seen"]:
            fresh_labels = {p["source_label"] for _, _, p in items} - seeded
            if fresh_labels:
                quiet = [iid for _, iid, p in items if p["source_label"] in fresh_labels and iid not in seen]
                print(f"[{name}] 새로 추가된 출처 {sorted(fresh_labels)}: {len(quiet)}개를 기준으로 저장만 함")
                state["seen"][name].extend(quiet)
                seen.update(quiet)
                state_changed = True
        seeded.update(p["source_label"] for _, _, p in items)
        new = [(iid, p) for _, iid, p in items if iid not in seen]
        if name not in state["seen"] or len(new) > FLOOD_LIMIT:
            why = "첫 실행" if name not in state["seen"] else f"새 항목 {len(new)}개로 비정상"
            print(f"[{name}] {why}: 현재 {len(items)}개를 기준으로 저장만 함")
            state["seen"].setdefault(name, []).extend(iid for iid, _ in new)
            state_changed = True
            continue
        print(f"[{name}] 전체 {len(items)}개 중 새 항목 {len(new)}개")
        pending[name] = [iid for iid, _ in new]
        for iid, p in new:
            if name in NEEDS_DESCRIPTION and not (p.get("description") and p.get("date")):
                for k, val in page_info(p["url"]).items():
                    p[k] = p.get(k) or val
            if _too_old(name, p.get("date"), now_dt):
                print(f"[{name}] 지난 소식이라 제외 ({str(p.get('date'))[:10]}): {p['url']}")
                continue
            candidates.append({"id": f"{name}:{iid}", "source": name, "found_at": now, **p})

    if set(state.get("seeded_labels", [])) != seeded:
        state["seeded_labels"] = sorted(seeded)
        state_changed = True
    if state_changed:
        save_state(state)
    write_json(CANDIDATES_PATH, candidates)
    write_json(PENDING_PATH, pending)
    CATALOG_PATH.write_text("platform\tid\ttitle\turl\n" + "\n".join(catalog_rows) + "\n")
    write_json(CATALOG_STATUS_PATH, catalog_ok)
    print(f"CANDIDATES={len(candidates)}")


if __name__ == "__main__":
    main()
