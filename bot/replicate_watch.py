"""Replicate 가격·옵션 변경 감시: 하루 한 번(09시 KST 이후 첫 실행) Replicate 공식 모델의 가격표와 입력 옵션을 저장하고,
전날과 달라진 모델 중 우리 서비스 모델(out/served_models.json 의 name)만 슬랙으로 알린다.

공개 저장소라서 우리 모델만 따로 저장하지 않고 공식 모델 전체를 저장한다. 어떤 모델이 우리 것인지는 실행할 때만 본다.

python replicate_watch.py

환경 변수
- SLACK_WEBHOOK_URL : 데일리 채널 웹훅 (publish.py 와 같음)
- ALERT_SLACK_WEBHOOK_URL : 관리자 개인 DM 웹훅. 확인을 못 했거나 페이지를 못 읽은 날 하루 한 번 알린다 (alert.py)
- DRY_RUN=1         : 슬랙에 보내지 않고 화면에만 출력, 기록도 바꾸지 않음
- FORCE=1           : 시간·날짜 조건 무시하고 지금 확인
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

from common import KST, ROOT, SERVED_PATH, write_json
from alert import send_alert
from publish import DRY_RUN, post_slack
from sources import fetch_replicate

WATCH_PATH = ROOT / "state" / "replicate_watch.json"
CHECK_HOUR_KST = 9
FORCE = os.environ.get("FORCE") == "1"
UA = {"User-Agent": "Mozilla/5.0"}
JSON_SCRIPT = re.compile(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S)
OPTION_FIELDS = ("type", "enum", "default", "minimum", "maximum", "minItems", "maxItems")


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _input_options(schema: dict) -> dict:
    props = schema.get("components", {}).get("schemas", {}).get("Input", {}).get("properties", {})
    out = {}
    for name, p in props.items():
        merged = dict(p)
        for sub in p.get("allOf", []) + p.get("anyOf", []):  # 고를 수 있는 값이 allOf 안에 있을 때가 있다
            if isinstance(sub, dict):
                merged = {**sub, **{k: v for k, v in merged.items() if k not in ("allOf", "anyOf")}}
        out[name] = {f: merged[f] for f in OPTION_FIELDS if f in merged}
    return out


def _tiers(bc: dict) -> dict:
    """{조건: [가격 문구, ...]}"""
    out = {}
    for t in bc.get("current_tiers") or []:
        cond = ", ".join(f"{c.get('title') or ''}={c.get('value')}".lstrip("=") for c in t.get("criteria") or []) or "기본"
        out[cond] = [f"{p.get('price')} {p.get('title') or ''}".strip() for p in t.get("prices") or []]
    return out


def parse_page(html: str) -> dict:
    """페이지 안 JSON 에서 가격표와 최신 버전의 입력 옵션을 뽑는다. 못 찾으면 그 항목은 None."""
    billing, versions = None, []
    for raw in JSON_SCRIPT.findall(html):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        for d in _walk(data):
            if billing is None and isinstance(d.get("billingConfig"), dict):
                billing = d["billingConfig"]
            schema = d.get("openapi_schema") or (d.get("_extras") or {}).get("dereferenced_openapi_schema")
            if isinstance(schema, dict) and d.get("id") and d.get("created_at"):
                versions.append((d["created_at"], d["id"], schema))
    options = None
    if versions:
        _, _, schema = max(versions, key=lambda v: v[0])  # 가장 최근 버전
        options = _input_options(schema)
    return {"price": _tiers(billing) if billing else None, "options": options}


def fetch_one(slug: str) -> tuple[str, dict | None]:
    try:
        r = requests.get(f"https://replicate.com/{slug}", headers=UA, timeout=60)
        r.raise_for_status()
        return slug, parse_page(r.text)
    except Exception as e:  # noqa: BLE001
        print(f"[경고] {slug} 읽기 실패: {type(e).__name__}", file=sys.stderr)
        return slug, None


def _fmt(v) -> str:
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) or "(없음)"
    return "(없음)" if v is None else str(v)


def diff(old: dict, new: dict) -> tuple[list[str], list[str]]:
    price, opt = [], []
    if old.get("price") is not None and new.get("price") is not None and old["price"] != new["price"]:
        for cond in sorted(set(old["price"]) | set(new["price"])):
            a, b = old["price"].get(cond), new["price"].get(cond)
            if a != b:
                price.append(f"• {cond}: {_fmt(a)} → {_fmt(b)}")
    if old.get("options") is not None and new.get("options") is not None and old["options"] != new["options"]:
        o, n = old["options"], new["options"]
        for name in sorted(set(o) | set(n)):
            if name not in o:
                opt.append(f"• 옵션 추가: {name}" + (f" ({_fmt(n[name]['enum'])})" if "enum" in n[name] else ""))
            elif name not in n:
                opt.append(f"• 옵션 삭제: {name}")
            else:
                for f in OPTION_FIELDS:
                    if o[name].get(f) != n[name].get(f):
                        label = {"enum": "", "default": " 기본값", "minimum": " 최소", "maximum": " 최대",
                                 "type": " 형식", "minItems": " 최소 개수", "maxItems": " 최대 개수"}[f]
                        opt.append(f"• {name}{label}: {_fmt(o[name].get(f))} → {_fmt(n[name].get(f))}")
    return price, opt


def load_served() -> dict[str, str] | None:
    """{replicate 주소: 표시 이름}. 커넥터를 못 읽은 회차면 None."""
    if not SERVED_PATH.exists():
        return None
    try:
        data = json.loads(SERVED_PATH.read_text())
    except ValueError:
        return None
    out = {}
    for m in data:
        if isinstance(m, dict) and m.get("name"):
            out[str(m["name"]).split(":")[0].strip().lower()] = str(m.get("displayName") or m["name"])
    return out or None


def main() -> None:
    now = datetime.now(KST)
    today = now.date().isoformat()
    state = json.loads(WATCH_PATH.read_text()) if WATCH_PATH.exists() else {"checked": "", "models": {}}
    if not FORCE and (now.hour < CHECK_HOUR_KST or state.get("checked") == today):
        print("REPLICATE_WATCH=skip (오늘 확인했거나 아직 9시 전)")
        return
    served = load_served()
    if served is None:
        print("REPLICATE_WATCH=skip (out/served_models.json 없음, 다음 회차에 다시 시도)")
        send_alert("list_models", "드롭샷 커넥터 `list_models` 호출이 실패해 오늘 Replicate 가격·옵션 확인을 하지 못했습니다.\n"
                   f"마지막으로 확인한 날: {state.get('checked') or '기록 없음'}\n"
                   "제공 종료 공지 판단도 목록을 받을 때까지 미뤄집니다. 자세한 오류는 예약 실행 기록에서 볼 수 있습니다.")
        return

    try:
        slugs = sorted({s for _, s, _ in fetch_replicate()} | {s for s in served if "/" in s and s in state["models"]})
    except Exception as e:  # noqa: BLE001
        slugs = []
        print(f"[경고] Replicate 공식 모델 목록 읽기 실패: {type(e).__name__}", file=sys.stderr)
    if not slugs:
        send_alert("replicate_list", "Replicate 공식 모델 목록을 읽지 못해 오늘 가격·옵션 확인을 하지 못했습니다. 다음 회차에 다시 시도합니다.")
        print("REPLICATE_WATCH=fail (공식 모델 목록 읽기 실패)")
        return
    with ThreadPoolExecutor(8) as ex:
        results = dict(ex.map(fetch_one, slugs))

    # 우리 모델인데 읽지 못했거나 가격·옵션을 못 찾은 경우 (페이지 구조 변경 등)
    broken = [s for s in served if s in results and not (results.get(s) and results[s]["price"] is not None
                                                                   and results[s]["options"] is not None)]
    first_run = not state["models"]
    sent = 0
    for slug in sorted(results):
        new = results[slug]
        old = state["models"].get(slug)
        if new is None:
            continue
        # 못 읽은 항목은 이전 값을 유지한다 (한 번 못 읽었다고 '바뀜'으로 보지 않도록)
        merged = {k: (new[k] if new[k] is not None else (old or {}).get(k)) for k in ("price", "options")}
        if old and slug in served:
            price, opt = diff(old, merged)
            if price or opt:
                blocks = [f"*[Replicate 변경] {served[slug]}* ({slug})"]
                if price:
                    blocks.append("*가격*\n" + "\n".join(price))
                if opt:
                    blocks.append("*옵션*\n" + "\n".join(opt))
                blocks.append(f"<https://replicate.com/{slug}|바로가기>")
                post_slack("\n\n".join(blocks))
                sent += 1
        state["models"][slug] = merged

    if broken:
        send_alert("replicate_pages", f"Replicate 감시: 우리 서비스 모델 {len(broken)}개의 가격·옵션을 Replicate 페이지에서 읽지 못했습니다. "
                   "페이지 구조가 바뀌었을 수 있어 확인이 필요합니다.")
    state["checked"] = today
    print(f"REPLICATE_WATCH=done 읽은 모델 {sum(1 for v in results.values() if v)}/{len(slugs)}, "
          f"우리 모델 중 Replicate 에 있는 것 {sum(1 for s in served if s in results)}, 변경 알림 {sent}건, "
          f"읽기 실패 {len(broken)}" + (" (첫 실행: 기준만 저장)" if first_run else ""))
    if DRY_RUN:
        print("[DRY_RUN] 기록은 저장하지 않음")
        return
    write_json(WATCH_PATH, state)


if __name__ == "__main__":
    main()
