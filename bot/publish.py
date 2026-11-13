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
from email.utils import parsedate_to_datetime

import requests

from common import (
    CANDIDATES_PATH, CATALOG_PATH, CATALOG_STATUS_PATH, PENDING_PATH, VERDICTS_PATH,
    load_state, save_state,
)
from sources import PLATFORMS

POSTED_KEEP_DAYS = 30
MODALITIES = {"이미지", "영상", "오디오", "멀티모달", "해당 없음"}
DRY_RUN = os.environ.get("DRY_RUN") == "1"


def load_catalog() -> tuple[dict[str, set[str]], dict[str, bool]]:
    urls: dict[str, set[str]] = {p: set() for p in PLATFORMS}
    if CATALOG_PATH.exists():
        for line in CATALOG_PATH.read_text().splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 4 and parts[0] in urls:
                urls[parts[0]].add(parts[3])
    ok = json.loads(CATALOG_STATUS_PATH.read_text()) if CATALOG_STATUS_PATH.exists() else {}
    return urls, ok


def load_verdicts(candidate_ids: set[str], catalog: dict[str, set[str]]) -> list[dict]:
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
            for f in ("model_key", "model_name", "maker", "one_liner"):
                if not str(v.get(f, "")).strip():
                    errors.append(f"{f} 가 비어 있음: {vid}")
            feats = v.get("features")
            if not isinstance(feats, list) or not 1 <= len(feats) <= 5 or not all(str(x).strip() for x in feats):
                errors.append(f"features 는 1~5개의 문장 목록이어야 함: {vid}")
            plats = v.get("platforms")
            if not isinstance(plats, dict) or set(plats) != set(PLATFORMS):
                errors.append(f"platforms 에는 {sorted(PLATFORMS)} 키가 있어야 함: {vid}")
            else:
                for p, url in plats.items():
                    if url and url not in catalog[p]:
                        errors.append(f"platforms.{p} url 이 catalog 에 없음(지어낸 주소): {vid} -> {url}")
    missing = candidate_ids - got
    if missing:
        errors.append(f"판단이 빠진 후보 {len(missing)}개: {sorted(missing)[:5]}")
    if errors:
        print("verdicts.json 형식 오류, 전송하지 않음:\n- " + "\n- ".join(errors), file=sys.stderr)
        sys.exit(1)
    return items


EVENT_LABEL = {
    "fal": "fal.ai에 새로 등록",
    "replicate": "Replicate에 새로 등록",
    "runware": "Runware에 새로 등록",
    "hf": "Hugging Face에 공개",
}


KST = timezone(timedelta(hours=9))
WEEKDAYS = "월화수목금토일"
DATE_BASIS = {
    "fal": "fal.ai 등록일", "replicate": "Replicate 등록일", "runware": "Runware 출시일",
    "hf": "Hugging Face 공개일", "rss": "공식 글 게시일", "blog": "공식 글 게시일",
}


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(str(value))
        except (TypeError, ValueError):
            return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(KST)


FAL_DATE_MAX_GAP = timedelta(days=7)


def date_line(group: list[dict]) -> str:
    """발표일: 이 소식 출처들의 날짜 중 가장 이른 날짜. 못 찾으면 줄을 뺀다(발견 시각으로 대신하지 않는다).
    fal.ai 날짜는 공개 전에 만든 날짜일 때가 있어서, 처음 발견한 시각보다 7일 넘게 이르면 쓰지 않는다."""
    dates = []
    for c in group:
        d = _parse_date(c.get("date"))
        if not d:
            continue
        found = _parse_date(c.get("found_at"))
        if c["source"] == "fal" and found and found - d > FAL_DATE_MAX_GAP:
            continue
        dates.append((d, DATE_BASIS.get(c["source"], "공식 글 게시일")))
    if not dates:
        return ""
    d, basis = min(dates, key=lambda x: x[0])
    return f"발표일: {d:%Y-%m-%d}({WEEKDAYS[d.weekday()]}) · {basis} 기준"


def format_message(group: list[dict], catalog_ok: dict[str, bool]) -> str:
    v = group[0]["verdict"]
    c0 = group[0]
    event = EVENT_LABEL.get(c0["source"], f"{c0['source_label']} 발표")
    if any(c["verdict"].get("upcoming") is True for c in group):
        event = f"{c0['source_label']} 출시 예정 발표" if c0["source"] in ("rss", "blog") else f"{event} (출시 예정)"

    # 같은 묶음 안에서 플랫폼 정보가 있는 쪽을 쓴다
    plats = {p: "" for p in PLATFORMS}
    for c in group:
        for p, url in c["verdict"]["platforms"].items():
            plats[p] = plats[p] or url
    plat_lines = []
    for p, label in PLATFORMS.items():
        if plats[p]:
            plat_lines.append(f"{label}: 등록됨 (<{plats[p]}|바로가기>)")
        elif catalog_ok.get(p):
            plat_lines.append(f"{label}: 아직 없음")
        else:
            plat_lines.append(f"{label}: 이번에 확인 실패")

    blocks = [
        f"*[{v['modality']}] {v['model_name']}* · {v['maker']}\n{event}"
        + (f"\n{dl}" if (dl := date_line(group)) else ""),
        v["one_liner"],
        "*특징*\n" + "\n".join(f"• {x}" for x in v["features"]),
        "*등록 플랫폼*\n" + "\n".join(plat_lines),
    ]
    vs = str(v.get("vs_previous", "")).strip()
    if vs and vs != "확인 안 됨":
        blocks.insert(3, f"*이전 대비*\n{vs}")
    if str(v.get("other_availability", "")).strip():
        blocks.append(f"*그 외*\n{v['other_availability']}")
    blocks.append("*출처*\n" + "\n".join(f"<{c['url']}|{c['title']}>" for c in group[:5]))
    return "\n\n".join(blocks)


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
        catalog, catalog_ok = load_catalog()
        verdicts = load_verdicts(set(by_id), catalog)
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
            post_slack(format_message(group, catalog_ok))
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
