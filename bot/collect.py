"""1단계: 소스를 확인해서 새 후보를 out/candidates.json 에 쓴다.

- 처음 보는 소스는 지금 목록을 기준으로 바로 state 에 저장하고 후보로 내지 않는다.
- 나머지 새 항목은 out/pending_seen.json 에 적어 두고, publish.py 가 전송을 마친 뒤 state 에 반영한다.
마지막 줄에 'CANDIDATES=<개수>' 를 출력한다.
"""

from __future__ import annotations

import sys
import traceback

from common import CANDIDATES_PATH, PENDING_PATH, load_state, save_state, write_json
from sources import SOURCES

# 한 소스에서 한꺼번에 이만큼 넘게 '새 항목'이 나오면 소스 쪽 변경(ID 체계 변경 등)으로 보고
# 보내지 않고 기준만 다시 잡는다. 채널 도배 방지용.
FLOOD_LIMIT = 80


def main() -> None:
    state = load_state()
    candidates, pending = [], {}
    state_changed = False
    for name, fetch in SOURCES.items():
        try:
            items = fetch()
        except Exception:
            print(f"[경고] {name} 소스 실패, 이번 회차는 건너뜀", file=sys.stderr)
            traceback.print_exc()
            continue
        seen = set(state["seen"].get(name, []))
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
            candidates.append({"id": f"{name}:{iid}", "source": name, **p})

    if state_changed:
        save_state(state)
    write_json(CANDIDATES_PATH, candidates)
    write_json(PENDING_PATH, pending)
    print(f"CANDIDATES={len(candidates)}")


if __name__ == "__main__":
    main()
