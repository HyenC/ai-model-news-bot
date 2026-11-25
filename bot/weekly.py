"""주간 정리: 지난주(KST 월~일) 주요 생성 모델 소식을 Confluence 에 자세히 쓰고, 슬랙에는 짧게 링크와 함께 보낸다.
절차는 bot/WEEKLY.md, 판단·작성 기준은 bot/weekly_rules.md.

python weekly.py prepare : 지난주 데일리 기록을 out/weekly_candidates.json 으로, 플랫폼 목록을 out/weekly_catalog.tsv 로 정리
python weekly.py send    : out/weekly_digest.json 을 검사해 슬랙으로 전송

환경 변수
- WEEKLY_SLACK_WEBHOOK_URL : 주간 정리를 보낼 채널의 Incoming Webhook
- DRY_RUN=1                : 슬랙에 보내지 않고 화면에만 출력, 기록도 바꾸지 않음
- WEEKLY_TEST=1            : 테스트 실행. 메시지 앞에 [테스트] 를 붙이고, 팀 태그를 빼고, 보낸 주로 기록하지 않음
- WEEKLY_SLACK_MENTION     : 메시지 맨 위에 태그할 슬랙 사용자 그룹 ID (예: S0123ABCD). 없으면 태그 없음
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

import requests

from common import KST, OUT_DIR, ROOT, WEEKLY_DIR, week_start, write_json
from sources import PLATFORMS, SOURCES

CANDIDATES_PATH = OUT_DIR / "weekly_candidates.json"
CATALOG_PATH = OUT_DIR / "weekly_catalog.tsv"
DIGEST_PATH = OUT_DIR / "weekly_digest.json"
SENT_PATH = ROOT / "state" / "weekly_sent.json"
MAX_ITEMS = 5
MODALITIES = {"이미지", "영상", "오디오", "멀티모달"}
DRY_RUN = os.environ.get("DRY_RUN") == "1"
TEST = os.environ.get("WEEKLY_TEST") == "1"
# 메시지 맨 위에 태그할 슬랙 사용자 그룹 ID (S 로 시작). 비어 있으면 태그하지 않는다
MENTION = os.environ.get("WEEKLY_SLACK_MENTION", "").strip().removeprefix("<!subteam^").rstrip(">").split("|")[0]
WEEKDAYS = "월화수목금토일"


def weeks() -> tuple[str, str, str]:
    """(지난주 월요일, 지난주 일요일, 이번 주 월요일=발행일) KST 날짜 문자열."""
    this_mon = week_start(datetime.now(timezone.utc))
    mon = this_mon - timedelta(weeks=1)
    return mon.isoformat(), (mon + timedelta(days=6)).isoformat(), this_mon.isoformat()


def build_catalog() -> None:
    """Replicate·Runware·BytePlus·Google·fal.ai 의 지금 모델 목록. 데일리 기록(state)은 건드리지 않는다."""
    rows, ok = [], {}
    for name in PLATFORMS:
        try:
            items = SOURCES[name]()
        except Exception:
            print(f"[경고] {name} 목록 읽기 실패", file=sys.stderr)
            traceback.print_exc()
            ok[name] = False
            continue
        ok[name] = True
        for _, iid, p in items:
            title = str(p.get("title") or "").replace("\t", " ")
            rows.append(f"{name}\t{iid}\t{title}\t{p['url']}")
    CATALOG_PATH.write_text("platform\tid\ttitle\turl\n" + "\n".join(rows) + "\n")
    print("CATALOG_OK=" + ",".join(f"{k}:{'ok' if v else 'fail'}" for k, v in ok.items()))


def prepare() -> None:
    mon, sun, pub = weeks()
    path = WEEKLY_DIR / f"{mon}.json"
    records = json.loads(path.read_text()) if path.exists() else []
    # 같은 모델의 후속(공급처 등록)은 원래 소식의 플랫폼 정보에 합친다
    items: dict[str, dict] = {}
    for r in records:
        if r.get("kind") == "new" and r["model_key"] not in items:
            items[r["model_key"]] = {k: v for k, v in r.items() if k not in ("kind", "at")}
    for r in records:
        if r.get("kind") == "followup":
            it = items.get(r["model_key"])
            if it is None:  # 원래 소식은 그 전 주에 나갔고, 지난주엔 공급처 등록만 있었던 경우
                items[r["model_key"]] = it = {"model_key": r["model_key"], "model_name": r["model_name"],
                                              "followup_only": True, "platforms": {p: "" for p in PLATFORMS}}
            it["platforms"].update(r["platforms"])
    write_json(CANDIDATES_PATH, {"week": [mon, sun], "publish_date": pub, "items": list(items.values())})
    build_catalog()
    print(f"WEEK={mon}~{sun}")
    stamp = datetime.now(KST).strftime("%m%d-%H%M")
    print(f"TITLE=Weekly AI News {pub}" + (f" (테스트 {stamp})" if TEST else ""))
    print(f"DAILY_RECORDS={len(items)}")


def load_digest() -> dict:
    data = json.loads(DIGEST_PATH.read_text()) if DIGEST_PATH.exists() else {}
    errors = []
    url = str(data.get("page_url", "")).strip()
    if not (url.startswith("https://") and ".atlassian.net/wiki/" in url):
        errors.append(f"page_url 이 Confluence 주소가 아님: {url or '(비어 있음)'}")
    items = data.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        errors.append(f"items 는 1~{MAX_ITEMS}개 목록이어야 함")
        items = []
    for i, it in enumerate(items, 1):
        for f in ("model_name", "maker", "summary"):
            if not str(it.get(f, "")).strip():
                errors.append(f"{i}번 항목의 {f} 가 비어 있음")
        if it.get("modality") not in MODALITIES:
            errors.append(f"{i}번 항목의 modality 는 {sorted(MODALITIES)} 중 하나여야 함: {it.get('modality')}")
        src = str(it.get("source_url", "")).strip()
        if not src.startswith("https://"):
            errors.append(f"{i}번 항목의 source_url 이 https 주소가 아님: {src or '(비어 있음)'}")
        feats = it.get("features")
        if not isinstance(feats, list) or not 2 <= len(feats) <= 4 or not all(str(x).strip() for x in feats):
            errors.append(f"{i}번 항목의 features 는 2~4개의 문장 목록이어야 함")
    if errors:
        print("weekly_digest.json 형식 오류, 전송하지 않음:\n- " + "\n- ".join(errors), file=sys.stderr)
        sys.exit(1)
    return {"page_url": url, "items": items}


def _md(d: str) -> str:
    dt = datetime.strptime(d, "%Y-%m-%d")
    return f"{dt.month}/{dt.day}({WEEKDAYS[dt.weekday()]})"


def format_digest(week: list[str], digest: dict) -> str:
    head = [("[테스트] " if TEST else "") + f":announcement: *<{digest['page_url']}|Weekly AI News 요약 ({_md(week[0])}~{_md(week[1])})>*",
            "*(링크로 들어가시면 조금 더 자세한 설명이 있습니다.)*"]
    if MENTION and not TEST:  # 테스트 실행에서는 팀 전체에 알림이 가지 않게 태그하지 않는다
        head.insert(0, f"<!subteam^{MENTION}>")
    blocks = ["\n".join(head) + "\n"]  # 첫 소식 앞에 빈 줄을 하나 더 둔다
    for i, it in enumerate(digest["items"], 1):
        # 모델 이름에 출처 링크를 건다 (슬랙 링크 글자에 쓸 수 없는 < > | 는 뺀다)
        name = "".join(c for c in it["model_name"] if c not in "<>|")
        lines = [f"*{i}. [{it['modality']}] <{it['source_url'].strip()}|{name}>* · {it['maker']}", it["summary"].strip()]
        lines += [f"• {x}" for x in it["features"]]
        if str(it.get("available", "")).strip():
            # 슬랙이 "fal.ai" 같은 글자를 자동 링크로 만들지 않게 점 앞에 폭 없는 공백을 넣는다
            lines.append("제공: " + it["available"].strip().replace(".", "\u200b."))
        blocks.append("\n".join(lines))
    return "\n\n\n".join(blocks)  # 덩어리 사이 빈 줄 2개 (제목 뒤는 3개)


def post_slack(text: str) -> None:
    if DRY_RUN:
        print("----- [DRY_RUN] 슬랙 메시지 -----\n" + text + "\n")
        return
    url = os.environ.get("WEEKLY_SLACK_WEBHOOK_URL", "").strip()
    if not url.startswith("https://hooks.slack.com/"):
        # 웹훅 주소는 비밀값이라 로그에 남기지 않는다
        sys.exit("WEEKLY_SLACK_WEBHOOK_URL 이 없거나 https://hooks.slack.com/ 으로 시작하지 않음")
    try:
        r = requests.post(url, json={"text": text, "unfurl_links": False, "unfurl_media": False}, timeout=30)
    except requests.RequestException as e:
        sys.exit(f"슬랙 전송 실패: {type(e).__name__}")
    if r.status_code != 200:
        sys.exit(f"슬랙 전송 실패: HTTP {r.status_code} {r.text[:100]}")


def send() -> None:
    week = json.loads(CANDIDATES_PATH.read_text())["week"]
    sent = json.loads(SENT_PATH.read_text()) if SENT_PATH.exists() else []
    if week[0] in sent and not TEST:
        print(f"이미 보낸 주라 건너뜀: {week[0]}")
        return
    digest = load_digest()
    post_slack(format_digest(week, digest))
    print(f"주간 정리 전송: {len(digest['items'])}건")
    if DRY_RUN or TEST:
        print("[DRY_RUN/테스트] 보낸 주로 기록하지 않음")
        return
    write_json(SENT_PATH, (sent + [week[0]])[-20:])


if __name__ == "__main__":
    {"prepare": prepare, "send": send}[sys.argv[1]]()
