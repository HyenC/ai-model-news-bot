"""새 소식 후보를 모으는 소스들.

각 함수는 (source, item_id, payload) 목록을 돌려준다.
item_id 는 소스 안에서 고유한 값이고, 이미 본 항목인지 판단할 때 쓴다.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

UA = {"User-Agent": "model-news-bot/1.0"}

# 이미지·영상·오디오 생성 분야만 본다.
FAL_CATEGORIES = {
    "text-to-image", "image-to-image", "text-to-video", "image-to-video",
    "video-to-video", "text-to-audio", "text-to-speech", "audio-to-audio",
}
HF_TAGS = [
    "text-to-image", "image-to-image", "text-to-video", "image-to-video",
    "text-to-speech", "text-to-audio", "any-to-any",
]
# Hugging Face 에 새로 올라오는 모델은 대부분 개인 파인튜닝·경량화 버전이라,
# 주요 기관이 올린 것만 바로 후보로 삼는다. (그 외는 급상승 목록에서 잡는다)
HF_ORGS = {o.lower() for o in [
    "google", "black-forest-labs", "stabilityai", "Wan-AI", "Qwen", "tencent",
    "Tencent-Hunyuan", "ByteDance", "ByteDance-Seed", "bytedance-research",
    "MiniMaxAI", "Lightricks", "genmo", "THUDM", "zai-org", "hpcai-tech",
    "meituan-longcat", "stepfun-ai", "nvidia", "microsoft", "facebook",
    "openai", "HiDream-ai", "ResembleAI", "hexgrad", "sesame", "canopylabs",
    "fishaudio", "SWivid", "nari-labs", "boson-ai", "kyutai", "ACE-Step",
    "Kwai-Kolors", "KwaiVGI", "baidu", "xai-org", "apple", "Skywork",
    "inclusionAI", "deepseek-ai", "moonshotai", "IndexTeam", "FunAudioLLM",
    "MeiGen-AI", "decart-ai", "lodestones", "OpenGVLab", "rhymes-ai",
    "Alibaba-NLP", "alibaba-pai", "Shitao", "VectorSpaceLab", "AIDC-AI",
]}
HF_TRENDING_MIN_LIKES = 30
HF_TRENDING_MAX_AGE_DAYS = 21

RSS_FEEDS = {
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "OpenAI": "https://openai.com/news/rss.xml",
    "Hugging Face 블로그": "https://huggingface.co/blog/feed.xml",
    "Replicate 블로그": "https://replicate.com/blog/rss",
    "fal.ai 블로그": "https://blog.fal.ai/rss/",
    "ElevenLabs": "https://elevenlabs.io/blog/rss.xml",
}


def _get_json(url: str, params: dict | None = None, tries: int = 6) -> dict | list:
    """429(요청 제한)이면 retry-after 만큼 기다렸다가 다시 시도한다."""
    for attempt in range(tries):
        r = requests.get(url, params=params, headers=UA, timeout=30)
        if r.status_code == 429:
            wait = int(r.headers.get("retry-after") or 10 * (attempt + 1))
            time.sleep(min(wait, 70) + 1)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"요청 제한이 풀리지 않음: {url}")


def fetch_fal() -> list[tuple[str, str, dict]]:
    """fal.ai 전체 모델 목록. 날짜순 정렬이 안 돼서 전부 넘겨 보고 새 ID 를 찾는다."""
    out, cursor = [], None
    while True:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        d = _get_json("https://api.fal.ai/v1/models", params)
        for m in d["models"]:
            md = m.get("metadata") or {}
            if md.get("category") not in FAL_CATEGORIES:
                continue
            out.append(("fal", m["endpoint_id"], {
                "source_label": "fal.ai",
                "title": md.get("display_name"),
                "category": md.get("category"),
                "description": md.get("description"),
                "date": md.get("date"),
                "url": f"https://fal.ai/models/{m['endpoint_id']}",
            }))
        if not d.get("has_more"):
            return out
        cursor = d["next_cursor"]
        time.sleep(6)  # 익명 요청은 분당 약 10회로 제한된다


def _hf_payload(m: dict, how: str) -> dict:
    return {
        "source_label": f"Hugging Face ({how})",
        "title": m["id"],
        "category": m.get("pipeline_tag"),
        "likes": m.get("likes"),
        "date": m.get("createdAt"),
        "tags": [t for t in m.get("tags", []) if not t.startswith(("region:", "arxiv:"))][:15],
        "url": f"https://huggingface.co/{m['id']}",
    }


def fetch_hf() -> list[tuple[str, str, dict]]:
    out: dict[str, dict] = {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=HF_TRENDING_MAX_AGE_DAYS)
    for tag in HF_TAGS:
        newest = _get_json("https://huggingface.co/api/models", {
            "pipeline_tag": tag, "sort": "createdAt", "direction": -1, "limit": 100,
        })
        for m in newest:
            if m["id"].split("/")[0].lower() in HF_ORGS:
                out[m["id"]] = _hf_payload(m, "주요 기관 신규")
        trending = _get_json("https://huggingface.co/api/models", {
            "pipeline_tag": tag, "sort": "trendingScore", "limit": 30,
        })
        for m in trending:
            created = m.get("createdAt")
            if (m.get("likes") or 0) < HF_TRENDING_MIN_LIKES or not created:
                continue
            if datetime.fromisoformat(created.replace("Z", "+00:00")) < cutoff:
                continue
            out.setdefault(m["id"], _hf_payload(m, "급상승"))
    return [("hf", k, v) for k, v in out.items()]


def fetch_rss() -> list[tuple[str, str, dict]]:
    out = []
    for label, url in RSS_FEEDS.items():
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        for e in feedparser.parse(r.content).entries[:30]:
            link = e.get("link")
            if not link:
                continue
            out.append(("rss", link, {
                "source_label": label,
                "title": e.get("title"),
                "description": (e.get("summary") or "")[:600],
                "date": e.get("published") or e.get("updated"),
                "url": link,
            }))
    return out


SOURCES = {"fal": fetch_fal, "hf": fetch_hf, "rss": fetch_rss}
