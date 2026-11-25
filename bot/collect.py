"""1단계: 소스를 확인해서 새 후보를 out/candidates.json 에 쓴다.

- 처음 보는 소스는 지금 목록을 기준으로 바로 state 에 저장하고 후보로 내지 않는다.
- 나머지 새 항목은 out/pending_seen.json 에 적어 두고, publish.py 가 전송을 마친 뒤 state 에 반영한다.
제공 종료 공지 후보는 out/retirements.json 에 따로 쓴다.
마지막 두 줄에 'CANDIDATES=<개수>', 'RETIREMENTS=<개수>' 를 출력한다.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime, timedelta, timezone

from alert import source_result
from common import (
    CANDIDATES_PATH, CATALOG_PATH, CATALOG_STATUS_PATH, PENDING_PATH, RETIREMENTS_PATH,
    load_state, save_state, write_json,
)
from sources import NEEDS_DESCRIPTION, PLATFORMS, RETIRE_SOURCES, SOURCES, byteplus_info, google_info, page_info, vertex_info

# 한 소스에서 한꺼번에 이만큼 넘게 '새 항목'이 나오면 소스 쪽 변경(ID 체계 변경 등)으로 보고
# 보내지 않고 기준만 다시 잡는다. 채널 도배 방지용.
FLOOD_LIMIT = 80

# 출처 날짜가 처음 발견한 때보다 이만큼 넘게 이르면 지난 소식으로 보고 보내지 않는다.
# (목록에 옛 글이 다시 걸리는 경우 등) 날짜가 없으면 거르지 않는다.
# fal.ai 날짜는 공개 전에 만든 날짜일 때가 있어서 이 기준을 쓰지 않는다.
MAX_AGE = timedelta(days=3)

# 처음 보는 소스라도 기준점만 잡지 않고 바로 후보로 내는 소스.
# fal.ai 종료 예정 목록은 지금 종료가 잡혀 있는 모델 중 우리 모델이 있으면 한 번 알려야 해서.
REPORT_ON_FIRST_RUN = {"fal_retire"}
# 종료 공지 페이지 하나에서 새 문단이 이만큼 넘게 나오면 페이지 구조가 바뀐 것으로 보고 기준만 다시 잡는다.
DEPRECATION_PAGE_FLOOD = 20
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
    candidates, retirements, pending = [], [], {}
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
            source_result(name, False)  # 연속으로 실패하면 관리자 DM
            continue
        source_result(name, True)
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
        if name not in state["seen"] and name in REPORT_ON_FIRST_RUN:
            state["seen"][name] = []
        new = [(iid, p) for _, iid, p in items if iid not in seen]
        if name == "deprecation" and name in state["seen"]:
            per_page: dict[str, list[str]] = {}
            for iid, p in new:
                per_page.setdefault(p["source_label"], []).append(iid)
            for label, ids in per_page.items():
                if len(ids) > DEPRECATION_PAGE_FLOOD:
                    print(f"[{name}] {label} 새 문단 {len(ids)}개로 비정상, 기준만 다시 저장함")
                    state["seen"][name].extend(ids)
                    state_changed = True
            reseeded = {iid for ids in per_page.values() if len(ids) > DEPRECATION_PAGE_FLOOD for iid in ids}
            new = [(iid, p) for iid, p in new if iid not in reseeded]
        if name not in state["seen"] or len(new) > FLOOD_LIMIT:
            why = "첫 실행" if name not in state["seen"] else f"새 항목 {len(new)}개로 비정상"
            print(f"[{name}] {why}: 현재 {len(items)}개를 기준으로 저장만 함")
            state["seen"].setdefault(name, []).extend(iid for iid, _ in new)
            state_changed = True
            continue
        print(f"[{name}] 전체 {len(items)}개 중 새 항목 {len(new)}개")
        pending[name] = [iid for iid, _ in new]
        if name in RETIRE_SOURCES:
            retirements.extend({"id": f"{name}:{iid}", "source": name, "found_at": now, **p} for iid, p in new)
            continue
        for iid, p in new:
            if name in NEEDS_DESCRIPTION and not (p.get("description") and p.get("date")):
                for k, val in page_info(p["url"]).items():
                    p[k] = p.get(k) or val
            if name == "byteplus":  # 모델 목록에는 ID 뿐이라, 그 모델의 BytePlus 문서 본문을 붙인다
                p.update(byteplus_info(iid))
            if name == "google":  # 목록은 ID 뿐이라 설명을 붙인다: Vertex 는 모델 문서, Gemini API 는 변경 기록 문단
                p.update(vertex_info(p["url"]) if iid.startswith("vertex/") else google_info(iid))
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
    write_json(RETIREMENTS_PATH, retirements)
    write_json(PENDING_PATH, pending)
    CATALOG_PATH.write_text("platform\tid\ttitle\turl\n" + "\n".join(catalog_rows) + "\n")
    write_json(CATALOG_STATUS_PATH, catalog_ok)
    print(f"CANDIDATES={len(candidates)}")
    print(f"RETIREMENTS={len(retirements)}")


if __name__ == "__main__":
    main()
