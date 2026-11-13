"""2단계: out/verdicts.json 을 읽어 슬랙으로 보내고 state 를 갱신한다.

환경 변수
- SLACK_WEBHOOK_URL : 보낼 채널의 Incoming Webhook
- DRY_RUN=1         : 슬랙에 보내지 않고 화면에만 출력, state 도 바꾸지 않음
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

from common import (
    CANDIDATES_PATH, PENDING_PATH, VERDICTS_PATH, load_state, save_state,
)

POSTED_KEEP_DAYS = 30
MODALITIES = {"이미지", "영상", "오디오", "멀티모달", "해당 없음"}
DRY_RUN = os.environ.get("DRY_RUN") == "1"


def load_verdicts(candidate_ids: set[str]) -> list[dict]:
    """형식이 어긋나면 아무것도 보내지 않고 멈춘다. (state 도 그대로라 다음 회차에 다시 시도됨)"""
    data = json.loads(VERDICTS_PATH.read_text()) if VERDICTS_PATH.exists() else {"items": []}
    items = data.get("items", [])
    errors = []
    got = set()
    for v in items:
        vid = v.get("id")
        got.add(vid)
        if vid not in candidate_ids:
            errors.append(f"후보에 없는 id: {vid}")
        if not isinstance(v.get("relevant"), bool):
            errors.append(f"relevant 가 true/false 가 아님: {vid}")
        if v.get("modality") not in MODALITIES:
            errors.append(f"modality 값이 잘못됨: {vid} -> {v.get('modality')}")
        if v.get("relevant"):
            for f in ("model_key", "model_name", "maker", "summary_ko", "availability"):
                if not str(v.get(f, "")).strip():
                    errors.append(f"{f} 가 비어 있음: {vid}")
    missing = candidate_ids - got
    if missing:
        errors.append(f"판단이 빠진 후보 {len(missing)}개: {sorted(missing)[:5]}")
    if errors:
        print("verdicts.json 형식 오류, 전송하지 않음:\n- " + "\n- ".join(errors), file=sys.stderr)
        sys.exit(1)
    return items


def format_message(group: list[dict]) -> str:
    v = group[0]["verdict"]
    src = group[0]["source_label"]
    lines = [
        f"*[{v['modality']}] {v['model_name']}* · {v['maker']}",
        v["summary_ko"],
        f"*어디서 쓸 수 있나:* {v['availability']}",
        f"*출처:* {src}" + (f" (관련 항목 {len(group)}개)" if len(group) > 1 else ""),
        "\n".join(f"<{c['url']}|{c['title']}>" for c in group[:5]),
    ]
    return "\n\n".join(lines)


def post_slack(text: str) -> None:
    if DRY_RUN:
        print("----- [DRY_RUN] 슬랙 메시지 -----\n" + text + "\n")
        return
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url.startswith("https://hooks.slack.com/"):
        # 웹훅 주소는 비밀값이라 로그에 남기지 않는다
        sys.exit("SLACK_WEBHOOK_URL 이 없거나 https://hooks.slack.com/ 으로 시작하지 않음")
    try:
        r = requests.post(
            url,
            json={"text": text, "unfurl_links": False, "unfurl_media": False},
            timeout=30,
        )
    except requests.RequestException as e:
        sys.exit(f"슬랙 전송 실패: {type(e).__name__}")
    if r.status_code != 200:
        sys.exit(f"슬랙 전송 실패: HTTP {r.status_code} {r.text[:100]}")


def main() -> None:
    state = load_state()
    candidates = json.loads(CANDIDATES_PATH.read_text()) if CANDIDATES_PATH.exists() else []
    pending = json.loads(PENDING_PATH.read_text()) if PENDING_PATH.exists() else {}
    by_id = {c["id"]: c for c in candidates}

    sent = 0
    if candidates:
        verdicts = load_verdicts(set(by_id))
        groups: dict[tuple[str, str], list[dict]] = {}
        for v in verdicts:
            if not v["relevant"]:
                continue
            c = by_id[v["id"]]
            c["verdict"] = v
            groups.setdefault((v["model_key"].strip().lower(), c["source"]), []).append(c)

        posted_keys = {(p["model_key"], p["source"]) for p in state["posted"]}
        now = datetime.now(timezone.utc).isoformat()
        for key, group in groups.items():
            if key in posted_keys:
                print(f"이미 보낸 모델이라 건너뜀: {key}")
                continue
            post_slack(format_message(group))
            state["posted"].append({"model_key": key[0], "source": key[1], "at": now})
            sent += 1
            if not DRY_RUN:
                save_state(state)  # 중간에 실패해도 이미 보낸 건 다시 보내지 않도록
    print(f"후보 {len(candidates)}개 중 {sent}건 전송")

    # 전송까지 끝난 뒤에만 '본 항목'으로 기록한다. 중간에 실패하면 다음 회차에 다시 시도된다.
    for name, ids in pending.items():
        state["seen"].setdefault(name, []).extend(ids)
    cutoff = datetime.now(timezone.utc) - timedelta(days=POSTED_KEEP_DAYS)
    state["posted"] = [p for p in state["posted"] if datetime.fromisoformat(p["at"]) >= cutoff]

    if DRY_RUN:
        print("[DRY_RUN] state 는 저장하지 않음")
    else:
        save_state(state)


if __name__ == "__main__":
    main()
