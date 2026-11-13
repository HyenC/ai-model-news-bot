"""새 소식 후보를 모으는 소스들.

각 함수는 (source, item_id, payload) 목록을 돌려준다.
item_id 는 소스 안에서 고유한 값이고, 이미 본 항목인지 판단할 때 쓴다.
"""

from __future__ import annotations

import html as html_lib
import re
import time
from datetime import datetime, timedelta, timezone

from urllib.parse import urljoin, urlparse

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
    "Google AI 블로그": "https://blog.google/technology/ai/rss/",
    "Qwen 블로그": "https://qwenlm.github.io/blog/index.xml",
}

# RSS 가 없는 모델 회사는 뉴스·블로그 페이지에 새 글 링크가 생기는지 본다.
# (이름: (페이지 주소, 글 주소에 들어가는 경로))
BLOG_PAGES = {
    "Black Forest Labs (FLUX)": ("https://bfl.ai/blog", "/blog/"),
    "Runway": ("https://runwayml.com/news", "/news/"),
    "Luma AI": ("https://lumalabs.ai/news", "/news/"),
    "MiniMax": ("https://www.minimax.io/news", "/news/"),
    "Meta AI": ("https://ai.meta.com/blog/", "/blog/"),
    "Recraft": ("https://www.recraft.ai/blog", "/blog/"),
    "Lightricks (LTX)": ("https://ltx.io/blog", "/blog/"),
    "Suno": ("https://suno.com/blog", "/blog/"),
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


def fetch_runware() -> list[tuple[str, str, dict]]:
    """Runware 공개 모델 페이지에 들어 있는 모델 정보(이름, ID, 기능, 시작 가격)를 읽는다."""
    r = requests.get("https://runware.ai/models", headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    html = r.text.replace('\\"', '"')
    out = {}
    for rec in re.findall(r'\{"caps":\[.*?"startingPrice":[^}]*\}', html):
        outputs = re.search(r'"outputs":\[(.*?)\]', rec)
        if not outputs or not any(o in outputs.group(1) for o in ('"image"', '"video"', '"audio"')):
            continue
        text = re.search(r'"searchText":"(.*?)"', rec).group(1).split()
        creator = re.search(r'"creatorId":"(.*?)"', rec).group(1)
        slug_i = next((i for i, t in enumerate(text) if t.startswith(creator + "-")), None)
        if slug_i is None:
            continue
        slug, air = text[slug_i], text[slug_i + 1] if slug_i + 1 < len(text) else ""
        price = re.search(r'"startingPrice":([0-9.]+|null)', rec).group(1)
        out[slug] = {
            "source_label": "Runware",
            "title": " ".join(text[:slug_i]),
            "maker": creator,
            "category": " ".join(t for t in text[slug_i + 2:] if "-to-" in t or t == "edit"),
            "air_id": air,
            "starting_price_usd": None if price == "null" else float(price),
            "url": f"https://runware.ai/models/{slug}",
        }
    if len(out) < 50:
        raise RuntimeError(f"Runware 모델이 {len(out)}개만 읽힘. 페이지 구조가 바뀐 것 같음")
    return [("runware", k, v) for k, v in out.items()]


REPLICATE_NOT_MODELS = {
    "collections", "docs", "blog", "pricing", "about", "explore", "account",
    "signin", "_next", "changelog", "terms", "privacy", "home", "deployments",
}


def fetch_replicate() -> list[tuple[str, str, dict]]:
    """Replicate 가 직접 관리하는 공식 모델 목록. (전체 API 목록은 토큰이 필요해서 이 목록만 본다)"""
    r = requests.get("https://replicate.com/collections/official",
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    slugs = set(re.findall(r'href="/([a-z0-9_-]+/[a-z0-9._-]+)"', r.text))
    slugs = {s for s in slugs if s.split("/")[0] not in REPLICATE_NOT_MODELS}
    if len(slugs) < 50:
        raise RuntimeError(f"Replicate 모델이 {len(slugs)}개만 읽힘. 페이지 구조가 바뀐 것 같음")
    return [("replicate", s, {
        "source_label": "Replicate 공식 모델",
        "title": s,
        "url": f"https://replicate.com/{s}",
    }) for s in slugs]


def _feed_date(e) -> str | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc).isoformat() if t else None


def fetch_rss() -> list[tuple[str, str, dict]]:
    out = []
    for label, url in RSS_FEEDS.items():
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[경고] RSS 실패: {label} ({type(e).__name__})")
            continue
        for e in feedparser.parse(r.content).entries[:30]:
            link = e.get("link")
            if not link:
                continue
            out.append(("rss", link, {
                "source_label": label,
                "title": e.get("title"),
                "description": (e.get("summary") or "")[:600],
                "date": _feed_date(e),
                "url": link,
            }))
    return out


def page_info(url: str) -> dict:
    """모델·글 페이지의 소개 문구(meta description)와 게시일. 새 항목에만 쓴다."""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
    except requests.RequestException:
        return {}
    info = {}
    m = (re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', r.text)
         or re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', r.text))
    if m:
        info["description"] = html_lib.unescape(m.group(1)).strip()[:600]
    text = r.text.replace('\\"', '"')
    d = (re.search(r'article:published_time"[^>]*content="([^"]+)"', text)
         or re.search(r'"datePublished"\s*:\s*"([^"]+)"', text)
         or re.search(r'"releasedAt"\s*:\s*"([^"]+)"', text))  # Runware 모델 페이지
    if d:
        info["date"] = d.group(1)
    elif "replicate.com/" in url:
        # Replicate 모델 페이지: 모델·버전 생성 시각 중 가장 이른 것 = 처음 올라온 시각
        created = re.findall(r'"created_at"\s*:\s*"([^"]+)"', text)
        if created:
            info["date"] = min(created)
    return info


def fetch_blogs() -> list[tuple[str, str, dict]]:
    out = []
    for label, (page, prefix) in BLOG_PAGES.items():
        try:
            r = requests.get(page, headers={"User-Agent": "Mozilla/5.0 (Macintosh)"}, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[경고] 블로그 페이지 실패: {label} ({type(e).__name__})")
            continue
        host = urlparse(page).netloc.removeprefix("www.")
        page_path = urlparse(page).path.rstrip("/")
        links = set()
        for href in re.findall(r'href="([^"#?]+)"', r.text):
            u = urlparse(urljoin(page, href))
            if not u.netloc.removeprefix("www.").endswith(host) or prefix not in u.path:
                continue
            if u.path.rstrip("/") == page_path or len(u.path.split(prefix, 1)[1].strip("/")) <= 3:
                continue
            links.add(f"https://{u.netloc}{u.path.rstrip('/')}")
        for link in links:
            out.append(("blog", link, {
                "source_label": label,
                "title": link.rsplit("/", 1)[-1].replace("-", " "),
                "url": link,
            }))
    return out


# 목록에 설명이 없는 소스는 새 항목에 한해 모델 페이지 설명을 붙인다
NEEDS_DESCRIPTION = {"replicate", "runware", "blog"}

SOURCES = {
    "fal": fetch_fal, "replicate": fetch_replicate, "runware": fetch_runware,
    "hf": fetch_hf, "rss": fetch_rss, "blog": fetch_blogs,
}
# 알림마다 '여기서 쓸 수 있는지'를 표시할 플랫폼
PLATFORMS = {"replicate": "Replicate", "runware": "Runware", "fal": "fal.ai"}
