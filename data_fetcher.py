import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

CACHE_FILE = os.path.join(os.path.dirname(__file__), "cache", "data.json")
CACHE_MAX_AGE_HOURS = 24

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=Hakshan+Malaysia+restaurant&hl=en-MY&gl=MY&ceid=MY:en",
    "https://news.google.com/rss/search?q=Hakka+restaurant+Malaysia&hl=en-MY&gl=MY&ceid=MY:en",
    "https://news.google.com/rss/search?q=Malaysia+Chinese+restaurant+food+2026&hl=en-MY&gl=MY&ceid=MY:en",
]

STATIC_DATA = {
    "brand": {
        "name": "客善 Hakshan",
        "tagline_zh": "让平凡的一餐，有着非凡的意义",
        "tagline_en": "Making an ordinary meal, extraordinarily meaningful",
        "website": "hakshan.com",
        "instagram_handle": "@hakshan_",
        "facebook_page": "客善 Hakshan",
        "founded": "~2022–2023",
        "cuisine": "Authentic Hakka (客家) Chinese",
        "country": "Malaysia",
        "market": "Klang Valley (KL & Selangor)",
        "usp": "Malaysia's first restaurant to structurally embed charitable giving into its dining model",
    },
    "social_media": {
        "instagram": {
            "handle": "@hakshan_",
            "followers": 2771,
            "posts": 348,
            "status": "active_undergrown",
            "label": "Under-grown",
            "note": "5-branch chain should have 8K–15K followers",
        },
        "facebook": {
            "page": "客善 Hakshan",
            "likes": 6257,
            "status": "moderate",
            "label": "Moderate",
            "note": "Stronger than IG; skews older Chinese demographic",
        },
        "tiktok": {
            "followers": 0,
            "status": "absent",
            "label": "ABSENT",
            "note": "Critical gap — #1 F&B discovery platform in Malaysia for under-35s",
        },
        "xiaohongshu": {
            "followers": 0,
            "status": "absent",
            "label": "ABSENT",
            "note": "Major missed channel for Mandarin-speaking audience",
        },
        "social_health_score": 4.3,
        "social_health_max": 10,
        "previous_growth": "Achieved 400% follower & engagement increase with right strategy",
    },
    "reviews": {
        "total_google_reviews": "3,000+",
        "overall_rating_range": "4.4–4.7",
        "overall_rating_numeric": 4.5,
        "recommendation_rate": "~100%",
        "implied_nps_range": "60–75",
        "platforms": ["Google Maps", "Tripadvisor", "Foodpanda", "UMAI", "Chiefeater.com"],
        "key_insight": "Hakshan has more Google reviews than Instagram followers — customers love the food but aren't converted to digital followers",
    },
    "branches": [
        {
            "name": "Bandar Menjalara, Kepong",
            "role": "Flagship",
            "address": "Unit R1-G-3, R1 Gallery, No 10, Jalan Idaman 1/62A, Bandar Menjalara, Kepong, KL",
            "maps_query": "Hakshan+Bandar+Menjalara+Kepong",
            "status": "established",
            "rating": 4.7,
            "review_volume": "Highest",
            "highlights": ["Authentic flavours", "Fast service during peak hours", "Value lunch sets"],
            "sentiment_themes": ["Tastes like grandma's cooking", "Clean and comfortable", "Family-friendly"],
            "watch_areas": ["Weekend queues", "Parking challenges"],
        },
        {
            "name": "USJ Taipan, Subang Jaya",
            "role": "Active",
            "address": "33, Jalan USJ 10/1G, USJ Taipan, Subang Jaya, Selangor",
            "maps_query": "Hakshan+USJ+Taipan+Subang+Jaya",
            "status": "established",
            "rating": 4.5,
            "review_volume": "High",
            "highlights": ["Consistent quality", "High footfall commercial hub", "Lunch crowd regulars"],
            "sentiment_themes": ["Pork belly praised", "Good accessibility", "Busy commercial area"],
            "watch_areas": ["Parking availability"],
        },
        {
            "name": "Bandar Puteri Puchong",
            "role": "Active",
            "address": "53G, Jalan Puteri 1/4, Bandar Puteri Puchong, Selangor",
            "maps_query": "Hakshan+Bandar+Puteri+Puchong",
            "status": "growing",
            "rating": 4.4,
            "review_volume": "Growing",
            "highlights": ["Pork patty specifically highlighted", "Recognised as best Hakka in Puchong"],
            "sentiment_themes": ["Moist and gently seasoned pork patty", "Fresh market entry", "Strong community reception"],
            "watch_areas": ["Branch consistency as it matures"],
        },
        {
            "name": "Cheras Traders Square",
            "role": "Active",
            "address": "Cheras Traders Square, Cheras Selatan, KL",
            "maps_query": "Hakshan+Cheras+Traders+Square",
            "status": "active",
            "rating": 4.5,
            "review_volume": "Moderate",
            "highlights": ["Hot-stone noodle sets", "Silky chicken wonton", "Ideal for groups"],
            "sentiment_themes": ["Satisfied and the price is just right", "Great for group dinners"],
            "watch_areas": [],
        },
        {
            "name": "Sri Petaling",
            "role": "Newest",
            "address": "Sri Petaling, KL (next to Bank area)",
            "maps_query": "Hakshan+Sri+Petaling+KL",
            "status": "new",
            "rating": None,
            "review_volume": "Building",
            "highlights": ["Community buzz building", "Dense Chinese residential area", "High growth potential"],
            "sentiment_themes": ["Too early for meaningful review data"],
            "watch_areas": [],
        },
    ],
    "signature_dishes": [
        "Ginger-Sprout Braised Duck Rice",
        "Hakka Trio-Sauce Chicken",
        "Hakka-Style Braised Pork Belly",
        "Wild Boar Curry",
        "Steamed Minced Pork Patty",
        "Silky Chicken Wonton",
        "Hot-Stone Noodle Sets",
    ],
    "competitors": [
        {
            "name": "Hakka Restaurant KL",
            "name_zh": "客家饭店",
            "type": "direct",
            "est": "1956",
            "location": "Jalan Raja Chulan, KLCC",
            "instagram_followers": 500,
            "facebook_likes": 3500,
            "tiktok": False,
            "tripadvisor_rating": 3.9,
            "tripadvisor_reviews": 961,
            "threat_level": "medium",
            "threat_label": "Medium",
            "strengths": ["70-year heritage legacy", "Prime KLCC location", "Large ~300 seat capacity"],
            "weaknesses": ["Extremely weak digital presence", "Aging customer base", "No CSR/charity angle", "Potential redevelopment risk"],
        },
        {
            "name": "Hakka Passion",
            "type": "direct",
            "est": "N/A",
            "location": "Pusat Bandar Puchong",
            "instagram_followers": 500,
            "facebook_likes": None,
            "tiktok": False,
            "tripadvisor_rating": None,
            "tripadvisor_reviews": None,
            "threat_level": "high_puchong",
            "threat_label": "High (Puchong)",
            "strengths": ["Established Puchong community relationships", "Home-style cooking positioning", "Air-conditioned with Wi-Fi"],
            "weaknesses": ["Single location only", "No brand story beyond food", "No charity/CSR differentiator", "Minimal social media"],
        },
    ],
    "recommendations": {
        "h1_quick_wins": [
            "Add Linktree to Instagram bio → link all 5 branches, menu, UMAI reservations",
            "Create Instagram Story Highlights: Menu | Branches | Charity | Reviews | Kitchen",
            "Claim & optimise all 5 Google Business profiles — add 20+ photos each",
            "Start replying to every Google and Facebook review (positive and negative)",
            "Post first monthly charity impact update across all platforms",
            "Launch weekly content calendar: 4–5 posts/week with themed days",
        ],
        "h2_growth": [
            "Launch TikTok @hakshan_ — start with duck braising timelapse ('6 hours for your 10-minute meal')",
            "Partner with 2–4 micro-KOLs (10K–50K followers) monthly — brief must include charity angle",
            "Launch campaign hashtags: #客善家人 (customer UGC) and #每一口的善 (charity content)",
            "Set up Xiaohongshu (小红书) brand account — seed with 15 posts in first month",
            "Upgrade loyalty: digital stamp card via WhatsApp (10 visits = free meal), birthday privilege, referral rewards",
            "Optimise Foodpanda/GrabFood listings — bundle deals, keyword-rich titles, off-peak promos",
        ],
        "h3_brand_building": [
            "Launch year-long campaign '一碗有意义的饭 (A Bowl With Meaning)' across all channels",
            "Create seasonal LTO menus: CNY Reunion Set, Ching Ming Heritage Set, Mooncake Festival specials",
            "Pitch earned media to Sin Chew Daily (星洲日报), Says.com, The Edge Malaysia — 'Malaysia's first charity restaurant'",
            "Host annual charity dinner (ticketed) and bi-annual Hakka Heritage Night events",
            "Develop vegetarian/vegan Hakka menu (yong tau foo, abacus seeds, braised tofu) to broaden audience",
        ],
    },
    "kpi_targets": {
        "instagram_followers": {"current": 2771, "target_3m": 6000, "target_12m": 15000},
        "facebook_likes": {"current": 6257, "target_3m": 10000, "target_12m": 20000},
        "tiktok_followers": {"current": 0, "target_3m": 2000, "target_12m": 10000},
        "xhs_followers": {"current": 0, "target_3m": 500, "target_12m": 2000},
        "google_response_rate": {"current_pct": 20, "target_pct": 90},
        "avg_google_rating": {"current": 4.5, "target": 4.5},
        "monthly_ugc_posts": {"current": 0, "target": 50},
    },
}


def _parse_rss_date(pub_date_str: str) -> datetime:
    try:
        return parsedate_to_datetime(pub_date_str)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def fetch_rss_feed(url: str) -> list:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        if channel is None:
            return []
        items = []
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            if source_el is not None:
                source = (source_el.text or source_el.get("url") or "").strip()
            else:
                source = ""
            raw_desc = (item.findtext("description") or "").strip()
            description = re.sub(r"<[^>]+>", "", raw_desc)[:220]
            if not title or not link:
                continue
            items.append({
                "title": title,
                "link": link,
                "pub_date": pub_date,
                "source": source,
                "description": description,
            })
        return items[:20]
    except Exception as exc:
        print(f"[data_fetcher] RSS fetch failed for {url}: {exc}")
        return []


def fetch_all_news() -> list:
    all_articles = []
    seen_links: set = set()
    for url in RSS_FEEDS:
        for article in fetch_rss_feed(url):
            norm_link = article["link"].split("?")[0]
            if norm_link not in seen_links:
                seen_links.add(norm_link)
                all_articles.append(article)
    all_articles.sort(key=lambda a: _parse_rss_date(a["pub_date"]), reverse=True)
    return all_articles[:30]


def is_cache_stale(data: dict) -> bool:
    fetched_at_str = data.get("fetched_at", "")
    if not fetched_at_str:
        return True
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - fetched_at
        return age.total_seconds() > (CACHE_MAX_AGE_HOURS * 3600)
    except Exception:
        return True


def load_cache() -> dict | None:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[data_fetcher] Cache load failed: {exc}")
        return None


def save_cache(data: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    tmp_path = CACHE_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CACHE_FILE)
    except Exception as exc:
        print(f"[data_fetcher] Cache save failed: {exc}")


def get_data(force: bool = False) -> dict:
    if not force:
        cached = load_cache()
        if cached and not is_cache_stale(cached):
            return cached
    print("[data_fetcher] Fetching fresh news data...")
    news = fetch_all_news()
    payload = {
        **STATIC_DATA,
        "news": news,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "news_fetch_status": "ok" if news else "unavailable",
        "news_count": len(news),
    }
    save_cache(payload)
    print(f"[data_fetcher] Cached {len(news)} news articles.")
    return payload
