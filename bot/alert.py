"""관리자 개인 DM 으로 봇 오류를 알린다. 같은 오류(key)는 KST 하루에 한 번만 보낸다.

코드에서: from alert import send_alert, source_result
명령으로: python alert.py <key> "<오류 한 줄 요약>"
  - key 는 오류 종류 (예: list_models, publish, push, weekly_confluence). weekly_ 로 시작하면 주간 정리 오류로 표시한다.

환경 변수
- ALERT_SLACK_WEBHOOK_URL : 관리자 개인 DM 웹훅. 없으면 보내지 않고 로그에만 남긴다
- DRY_RUN=1               : 보내지 않고 화면에만 출력, 기록도 바꾸지 않음

오류 때문에 봇의 다른 단계가 멈추지 않도록, 이 파일의 함수는 실패해도 예외를 내지 않는다.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import requests

from common import KST, ROOT, write_json

ALERTS_PATH = ROOT / "state" / "alerts.json"
SOURCE_FAIL_LIMIT = 3  # 같은 수집 출처가 이만큼 연속 실패하면 알린다 (한두 번은 일시 오류가 흔함)
DRY_RUN = os.environ.get("DRY_RUN") == "1"


def _load() -> dict:
    try:
        data = json.loads(ALERTS_PATH.read_text())
    except (OSError, ValueError):
        data = {}
    data.setdefault("sent", {})
    data.setdefault("source_fails", {})
    return data


def _save(data: dict) -> None:
    if not DRY_RUN:
        write_json(ALERTS_PATH, data)


def _post(text: str) -> bool:
    if DRY_RUN:
        print("----- [DRY_RUN] 관리자 DM -----\n" + text + "\n")
        return True
    url = os.environ.get("ALERT_SLACK_WEBHOOK_URL", "").strip()
    if not url.startswith("https://hooks.slack.com/"):
        # 웹훅 주소는 비밀값이라 로그에 남기지 않는다
        print("[경고] ALERT_SLACK_WEBHOOK_URL 이 없거나 형식이 달라 관리자 알림을 보내지 않음", file=sys.stderr)
        return False
    try:
        r = requests.post(url, json={"text": text, "unfurl_links": False, "unfurl_media": False}, timeout=30)
    except requests.RequestException as e:
        print(f"[경고] 관리자 알림 전송 실패: {type(e).__name__}", file=sys.stderr)
        return False
    if r.status_code != 200:
        print(f"[경고] 관리자 알림 전송 실패: HTTP {r.status_code}", file=sys.stderr)
        return False
    return True


def send_alert(key: str, text: str) -> bool:
    """오늘 같은 key 로 보낸 적이 없으면 보낸다. 보냈으면 True."""
    try:
        today = datetime.now(KST).date().isoformat()
        data = _load()
        if data["sent"].get(key) == today:
            return False
        title = "주간 정리 오류" if key.startswith("weekly_") else "데일리 봇 오류"
        if not _post(f"*[모델 소식 봇] {title}*\n{text.strip()}"):
            return False
        data["sent"][key] = today
        _save(data)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[경고] 관리자 알림 처리 실패: {type(e).__name__}", file=sys.stderr)
        return False


def source_result(name: str, ok: bool) -> None:
    """수집 출처 하나의 성공·실패를 기록하고, 연속 실패가 기준에 닿으면 알린다."""
    try:
        data = _load()
        fails = data["source_fails"]
        if ok:
            if fails.pop(name, None) is not None:
                _save(data)
            return
        fails[name] = fails.get(name, 0) + 1
        _save(data)
        if fails[name] >= SOURCE_FAIL_LIMIT:
            send_alert(f"source:{name}",
                       f"수집 출처 `{name}` 을(를) {fails[name]}회차 연속으로 읽지 못했습니다. "
                       "사이트 구조가 바뀌었거나 접속이 막혔을 수 있습니다. 자세한 오류는 예약 실행 기록에서 볼 수 있습니다.")
    except Exception as e:  # noqa: BLE001
        print(f"[경고] 출처 실패 기록 처리 실패: {type(e).__name__}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3 or not sys.argv[1].strip() or not " ".join(sys.argv[2:]).strip():
        sys.exit('사용법: python alert.py <key> "<오류 한 줄 요약>"')
    sent = send_alert(sys.argv[1].strip(), " ".join(sys.argv[2:]))
    print("ALERT=" + ("sent" if sent else "skip (오늘 이미 보냈거나 보낼 수 없음)"))
