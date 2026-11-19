"""2단계: out/verdicts.json 을 읽어 슬랙으로 보내고 state 를 갱신한다.

환경 변수
- SLACK_WEBHOOK_URL : 보낼 채널의 Incoming Webhook
- DRY_RUN=1         : 슬랙에 보내지 않고 화면에만 출력, state 도 바꾸지 않음
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from common import (
    CANDIDATES_PATH, CATALOG_PATH, CATALOG_STATUS_PATH, PENDING_PATH, RETIRE_VERDICTS_PATH,
    RETIREMENTS_PATH, SERVED_PATH, VERDICTS_PATH,
    append_weekly, load_state, save_state,
)
from sources import PLATFORMS, RETIRE_SOURCES

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
    "byteplus": "BytePlus에 새로 등록",
    "google": "Google(Gemini API·Vertex AI)에 새로 등록",
    "hf": "Hugging Face에 공개",
}


KST = timezone(timedelta(hours=9))
WEEKDAYS = "월화수목금토일"
DATE_BASIS = {
    "fal": "fal.ai 등록일", "replicate": "Replicate 등록일", "runware": "Runware 출시일", "google": "Google 문서",
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


SUPPLIERS = ("replicate", "runware", "byteplus", "google")  # 우리가 API를 가져오는 곳. 첫 소식 뒤에도 새로 등록되면 한 줄로 알린다


def merged_platforms(group: list[dict]) -> dict[str, str]:
    """같은 묶음 안에서 플랫폼 정보가 있는 쪽을 쓴다. 출처가 그 플랫폼이면 출처 주소도 등록 근거로 본다."""
    plats = {p: "" for p in PLATFORMS}
    for c in group:
        for p, url in c["verdict"]["platforms"].items():
            plats[p] = plats[p] or url
    for c in group:
        if c["source"] in plats:
            plats[c["source"]] = plats[c["source"]] or c["url"]
    return plats


def event_line(group: list[dict]) -> str:
    upcoming = any(c["verdict"].get("upcoming") is True for c in group)
    labels = []
    for c in group:
        if c["source"] in ("rss", "blog"):
            label = f"{c['source_label']} {'출시 예정 발표' if upcoming else '발표'}"
        else:
            label = EVENT_LABEL.get(c["source"], f"{c['source_label']} 발표")
            if upcoming:
                label += " (출시 예정)"
        if label not in labels:
            labels.append(label)
    return " / ".join(labels)


def format_followup(v: dict, new_plats: dict[str, str]) -> str:
    lines = [f"{no_autolink(PLATFORMS[p])}에 새로 등록됨 (<{url}|바로가기>)" for p, url in new_plats.items()]
    return f"*[후속] {v['model_name']}* · {v['maker']}\n앞서 보낸 모델이 우리 공급처에 올라왔습니다.\n" + "\n".join(lines)


def weekly_entry(mk: str, group: list[dict], plats: dict[str, str]) -> dict:
    """주간 정리에서 다시 쓸 수 있게, 실시간으로 보낸 소식의 내용을 그대로 남긴다."""
    v = group[0]["verdict"]
    return {
        "kind": "new", "model_key": mk,
        **{f: v.get(f, "") for f in ("model_name", "maker", "modality", "one_liner", "features",
                                     "vs_previous", "upcoming", "other_availability")},
        "event": event_line(group), "date": date_line(group), "platforms": plats,
        "sources": [{"url": c["url"], "title": c["title"]} for c in group[:5]],
    }


def no_autolink(label: str) -> str:
    """슬랙은 "fal.ai" 같은 도메인 모양 글자를 자동으로 링크로 만든다. 점 앞에 폭 없는 공백을 넣어 막는다."""
    return label.replace(".", "\u200b.")


def format_message(group: list[dict], catalog_ok: dict[str, bool]) -> str:
    v = group[0]["verdict"]
    event = event_line(group)
    plats = merged_platforms(group)
    plat_lines = []
    for p, label in PLATFORMS.items():
        if plats[p]:
            plat_lines.append(f"{no_autolink(label)}: 등록됨 (<{plats[p]}|바로가기>)")
        elif catalog_ok.get(p):
            plat_lines.append(f"{no_autolink(label)}: 아직 없음")
        else:
            plat_lines.append(f"{no_autolink(label)}: 이번에 확인 실패")

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


def load_served() -> set[str] | None:
    """우리 서비스 모델의 표시 이름 목록. 없으면 None (커넥터를 못 읽은 회차)."""
    if not SERVED_PATH.exists():
        return None
    try:
        data = json.loads(SERVED_PATH.read_text())
    except ValueError:
        return None
    names = {str(m.get("displayName", "")).strip() for m in data if isinstance(m, dict)}
    names.discard("")
    return names or None


def load_retire_verdicts(ids: set[str], served: set[str]) -> list[dict]:
    data = json.loads(RETIRE_VERDICTS_PATH.read_text()) if RETIRE_VERDICTS_PATH.exists() else {"items": []}
    items, errors, got = data.get("items", []), [], set()
    for v in items:
        vid = v.get("id")
        got.add(vid)
        if vid not in ids:
            errors.append(f"종료 공지 후보에 없는 id: {vid}")
        if not isinstance(v.get("relevant"), bool):
            errors.append(f"relevant 가 true/false 가 아님: {vid}")
        if v.get("relevant"):
            for f in ("model_name", "maker", "where", "summary"):
                if not str(v.get(f, "")).strip():
                    errors.append(f"{f} 가 비어 있음: {vid}")
            sm = v.get("served_models")
            if not isinstance(sm, list) or not sm:
                errors.append(f"served_models 는 1개 이상인 목록이어야 함: {vid}")
            else:
                for name in sm:
                    if name not in served:
                        errors.append(f"served_models 의 '{name}' 이 out/served_models.json 의 displayName 에 없음: {vid}")
            sd = str(v.get("shutdown_date", "")).strip()
            if sd:
                try:
                    datetime.strptime(sd, "%Y-%m-%d")
                except ValueError:
                    errors.append(f"shutdown_date 는 YYYY-MM-DD 이거나 빈 문자열: {vid} -> {sd}")
    missing = ids - got
    if missing:
        errors.append(f"판단이 빠진 종료 공지 후보 {len(missing)}개: {sorted(missing)[:5]}")
    if errors:
        print("retire_verdicts.json 형식 오류, 전송하지 않음:\n- " + "\n- ".join(errors), file=sys.stderr)
        sys.exit(1)
    return items


def format_retirement(v: dict, c: dict) -> str:
    sd = str(v.get("shutdown_date", "")).strip()
    head = f"*[제공 종료 예정] {v['model_name']}* · {v['maker']}\n{v['where']}"
    if sd:
        d = datetime.strptime(sd, "%Y-%m-%d").date()
        left = (d - datetime.now(KST).date()).days
        when = f"{left}일 남음" if left > 0 else ("오늘" if left == 0 else "이미 지남")
        head += f"\n종료일: {d:%Y-%m-%d}({WEEKDAYS[d.weekday()]}) · {when}"
    blocks = [head, v["summary"]]
    if str(v.get("replacement", "")).strip():
        blocks.append(f"*대체 모델*\n{v['replacement']}")
    blocks.append("*우리 서비스 모델*\n" + "\n".join(f"• {x}" for x in v["served_models"]))
    blocks.append(f"*출처*\n<{c['url']}|{c['source_label']}>")
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
        # 같은 모델은 출처(fal.ai, Runware 등)가 달라도 한 묶음으로 보낸다
        groups: dict[str, list[dict]] = {}
        for v in verdicts:
            if not v["relevant"]:
                continue
            c = by_id[v["id"]]
            c["verdict"] = v
            groups.setdefault(v["model_key"].strip().lower(), []).append(c)

        posted: dict[str, set[str]] = {}
        for p in state["posted"]:
            if p["source"] != "retire":
                posted.setdefault(p["model_key"], set()).add(p["source"])
        now = datetime.now(timezone.utc).isoformat()
        for mk, group in groups.items():
            plats = merged_platforms(group)
            if mk in posted:
                # 이미 소식을 보낸 모델: 우리 공급처에 새로 올라온 경우만 한 줄로 알린다
                new = {p: plats[p] for p in SUPPLIERS if plats[p] and p not in posted[mk]}
                if not new:
                    print(f"이미 보낸 모델이라 건너뜀: {mk}")
                    continue
                post_slack(format_followup(group[0]["verdict"], new))
                done = set(new)
                if not DRY_RUN:
                    append_weekly({"kind": "followup", "model_key": mk,
                                   "model_name": group[0]["verdict"]["model_name"], "platforms": new})
            else:
                post_slack(format_message(group, catalog_ok))
                if not DRY_RUN:
                    append_weekly(weekly_entry(mk, group, plats))
                # 출처와, 이 메시지에 '등록됨'으로 나간 플랫폼을 함께 기록해 같은 내용의 후속 알림을 막는다
                done = {c["source"] for c in group} | {p for p, url in plats.items() if url}
            state["posted"].extend({"model_key": mk, "source": s, "at": now} for s in sorted(done))
            posted.setdefault(mk, set()).update(done)
            sent += 1
            if not DRY_RUN:
                save_state(state)  # 중간에 실패해도 이미 보낸 건 다시 보내지 않도록
    print(f"후보 {len(candidates)}개 중 {sent}건 전송")

    # 제공 종료 공지: 우리 서비스 모델 목록이 있어야 판단할 수 있다.
    retirements = json.loads(RETIREMENTS_PATH.read_text()) if RETIREMENTS_PATH.exists() else []
    served = load_served()
    if retirements and served is None:
        print(f"[경고] out/served_models.json 이 없어 종료 공지 {len(retirements)}개를 다음 회차로 미룸")
        for name in RETIRE_SOURCES:
            pending.pop(name, None)  # 본 것으로 기록하지 않아서 다음 회차에 다시 판단한다
    elif retirements:
        r_by_id = {c["id"]: c for c in retirements}
        r_sent = 0
        posted_keys = {(p["model_key"], p["source"]) for p in state["posted"]}
        now = datetime.now(timezone.utc).isoformat()
        for v in load_retire_verdicts(set(r_by_id), served):
            if not v["relevant"]:
                continue
            # state 는 공개 저장소에 올라가므로 우리 서비스 모델을 알 수 있는 이름 대신 해시로 기록한다
            raw = f"{v['model_name'].strip().lower()}|{v.get('shutdown_date', '')}|{v['where']}"
            key = (hashlib.sha256(raw.encode()).hexdigest()[:16], "retire")
            if key in posted_keys:
                print("이미 보낸 종료 공지라 건너뜀")
                continue
            post_slack(format_retirement(v, r_by_id[v["id"]]))
            state["posted"].append({"model_key": key[0], "source": key[1], "at": now})
            posted_keys.add(key)
            r_sent += 1
            if not DRY_RUN:
                save_state(state)
        print(f"종료 공지 후보 {len(retirements)}개 중 {r_sent}건 전송")

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
