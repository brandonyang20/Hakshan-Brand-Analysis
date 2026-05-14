import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

CACHE_FILE = os.path.join(os.path.dirname(__file__), "cache", "data.json")
CACHE_MAX_AGE_HOURS = 24

# Categorised RSS feeds — category tag is attached to each fetched article
RSS_FEEDS = [
    {
        "url": "https://news.google.com/rss/search?q=Hakshan+Malaysia+restaurant&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "hakshan",
    },
    {
        "url": "https://news.google.com/rss/search?q=Hakka+restaurant+Malaysia+2026&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "competitor",
    },
    {
        "url": "https://news.google.com/rss/search?q=Malaysia+Chinese+restaurant+food+industry&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "industry",
    },
]

ANALYSIS_FILES = {
    "brand":        "01-brand-overview.md",
    "social":       "02-social-media-analysis.md",
    "reviews":      "03-reviews-sentiment.md",
    "competitors":  "04-competitor-analysis.md",
    "strategy":     "05-recommendations.md",
}

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
            "best_content": "Branch opening announcements; food photography",
            "missing": "No Reels strategy, no CSR storytelling, no Stories Highlights",
            "optimal_post_times": ["Tue 12pm", "Thu 7pm", "Sat 11am"],
        },
        "facebook": {
            "page": "客善 Hakshan",
            "likes": 6257,
            "status": "moderate",
            "label": "Moderate",
            "note": "Stronger than IG; skews older Chinese demographic (30–55)",
            "best_content": "Branch updates, community news",
            "missing": "No Facebook Events, no Groups participation",
            "optimal_post_times": ["Mon 8am", "Wed 12pm", "Sun 6pm"],
        },
        "tiktok": {
            "followers": 0,
            "status": "absent",
            "label": "ABSENT",
            "note": "#1 F&B discovery platform for under-35s in Malaysia — zero presence",
        },
        "xiaohongshu": {
            "followers": 0,
            "status": "absent",
            "label": "ABSENT",
            "note": "Top platform for Mandarin-speaking Chinese-Malaysian audience",
        },
        "social_health_score": 4.3,
        "social_health_max": 10,
        "health_dimensions": {
            "Platform Presence":    4,
            "Content Quality":      6,
            "Posting Consistency":  5,
            "Engagement Rate":      6,
            "Community Mgmt":       4,
            "Charity Activation":   2,
            "Influencer Collab":    3,
        },
        "previous_growth": "Achieved 400% follower & engagement increase with the right strategy",
    },
    "reviews": {
        "total_google_reviews": "3,000+",
        "overall_rating_range": "4.4–4.7",
        "overall_rating_numeric": 4.5,
        "recommendation_rate": "~100%",
        "implied_nps_range": "60–75",
        "platforms": ["Google Maps", "Tripadvisor", "Foodpanda", "UMAI", "Chiefeater.com"],
        "key_insight": "Hakshan has more Google reviews than Instagram followers — customers love the food but aren't converted to digital followers",
        "review_response_rate_pct": 20,
        "top_positive_themes": [
            "Authentic Hakka flavours",
            "Value for money",
            "Fast & friendly service",
            "Clean ambiance",
            "Generous portions",
        ],
        "top_negative_themes": [
            "Weekend wait times / queues",
            "Parking challenges",
            "Limited vegetarian options",
            "Slight branch inconsistency",
            "Low charity awareness",
        ],
    },
    "branches": [
        {
            "id": "kepong",
            "name": "Bandar Menjalara, Kepong",
            "role": "Flagship",
            "address": "Unit R1-G-3, R1 Gallery, No 10, Jalan Idaman 1/62A, Bandar Menjalara, Kepong, KL",
            "maps_query": "Hakshan+Bandar+Menjalara+Kepong",
            "status": "established",
            "rating": 4.7,
            "review_count": "1,200+",
            "review_volume": "Highest",
            "highlights": ["Authentic flavours", "Fast service during peak hours", "Value lunch sets", "Family-friendly"],
            "sentiment_themes": ["Tastes like grandma's cooking", "Clean and comfortable", "Fast turnover praised"],
            "watch_areas": ["Weekend queues", "Parking challenges"],
            "best_dishes": ["Ginger-Sprout Braised Duck Rice", "Hakka Pork Belly"],
        },
        {
            "id": "subang",
            "name": "USJ Taipan, Subang Jaya",
            "role": "Active",
            "address": "33, Jalan USJ 10/1G, USJ Taipan, Subang Jaya, Selangor",
            "maps_query": "Hakshan+USJ+Taipan+Subang+Jaya",
            "status": "established",
            "rating": 4.5,
            "review_count": "850+",
            "review_volume": "High",
            "highlights": ["Consistent quality", "High footfall commercial hub", "Lunch crowd regulars"],
            "sentiment_themes": ["Pork belly praised", "Good accessibility", "Repeat diners"],
            "watch_areas": ["Parking availability"],
            "best_dishes": ["Hakka Trio-Sauce Chicken", "Braised Pork Belly"],
        },
        {
            "id": "puchong",
            "name": "Bandar Puteri Puchong",
            "role": "Active",
            "address": "53G, Jalan Puteri 1/4, Bandar Puteri Puchong, Selangor",
            "maps_query": "Hakshan+Bandar+Puteri+Puchong",
            "status": "growing",
            "rating": 4.4,
            "review_count": "550+",
            "review_volume": "Growing",
            "highlights": ["Pork patty specifically highlighted", "Recognised as best Hakka in Puchong"],
            "sentiment_themes": ["Moist and gently seasoned pork patty", "Strong community reception"],
            "watch_areas": ["Branch consistency as it matures"],
            "best_dishes": ["Steamed Minced Pork Patty", "Duck Rice"],
        },
        {
            "id": "cheras",
            "name": "Cheras Traders Square",
            "role": "Active",
            "address": "Cheras Traders Square, Cheras Selatan, KL",
            "maps_query": "Hakshan+Cheras+Traders+Square",
            "status": "active",
            "rating": 4.5,
            "review_count": "400+",
            "review_volume": "Moderate",
            "highlights": ["Hot-stone noodle sets", "Silky chicken wonton", "Ideal for groups"],
            "sentiment_themes": ["Price is just right", "Great for group dinners"],
            "watch_areas": [],
            "best_dishes": ["Silky Chicken Wonton", "Hot-Stone Noodle Sets"],
        },
        {
            "id": "sri_petaling",
            "name": "Sri Petaling",
            "role": "Newest",
            "address": "Sri Petaling, KL (next to Bank area)",
            "maps_query": "Hakshan+Sri+Petaling+KL",
            "status": "new",
            "rating": None,
            "review_count": "Building",
            "review_volume": "Building",
            "highlights": ["Community buzz building", "Dense Chinese residential area", "High growth potential"],
            "sentiment_themes": ["Too early for meaningful review data"],
            "watch_areas": [],
            "best_dishes": [],
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
            "posts_per_month": 2,
            "content_mix": {"Food": 80, "Heritage/Events": 10, "Promotions": 10},
            "avg_engagement": "Very Low (<20 likes/post)",
            "last_active": "Irregular",
            "strengths": ["70-year heritage legacy", "Prime KLCC location", "Large ~300 seat capacity"],
            "weaknesses": ["Extremely weak digital", "Aging customer base", "No CSR angle", "Potential redevelopment risk"],
            "content_strategy_note": "Infrequent posting, no video content, no community engagement. Legacy brand coasting.",
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
            "posts_per_month": 1,
            "content_mix": {"Food": 90, "Promotions": 10},
            "avg_engagement": "Very Low",
            "last_active": "Rare",
            "strengths": ["Established Puchong community", "Home-style positioning", "Air-conditioned + Wi-Fi"],
            "weaknesses": ["Single location", "No brand story", "No CSR", "Minimal social media"],
            "content_strategy_note": "Almost no social presence. Relies entirely on existing community word-of-mouth.",
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
            "Upgrade loyalty: digital stamp card via WhatsApp, birthday privilege, referral rewards",
            "Optimise Foodpanda/GrabFood listings — bundle deals, keyword-rich titles, off-peak promos",
        ],
        "h3_brand_building": [
            "Launch year-long campaign '一碗有意义的饭 (A Bowl With Meaning)' across all channels",
            "Create seasonal LTO menus: CNY Reunion Set, Ching Ming Heritage Set, Mooncake specials",
            "Pitch earned media to Sin Chew Daily (星洲日报), Says.com, The Edge Malaysia",
            "Host annual charity dinner (ticketed) and bi-annual Hakka Heritage Night events",
            "Develop vegetarian/vegan Hakka menu to broaden audience",
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
    "chart_data": {
        "review_trend": {
            "labels": ["Dec '25", "Jan '26", "Feb '26", "Mar '26", "Apr '26", "May '26"],
            "kepong":       [130, 155, 175, 165, 195, 215],
            "subang":       [95,  115,  135, 125, 145, 165],
            "puchong":      [55,   75,  100,  95, 115, 125],
            "cheras":       [48,   68,   82,  77,  87,  97],
            "sri_petaling": [0,     0,    0,  22,  32,  38],
            "all_branches": [328,  413,  492, 484, 574, 640],
        },
        "social_growth": {
            "labels": ["Jan '26", "Feb '26", "Mar '26", "Apr '26", "May '26"],
            "instagram": [2100, 2310, 2510, 2660, 2771],
            "facebook":  [5190, 5470, 5790, 6090, 6257],
        },
        "brand_health_radar": {
            "dimensions": ["Social Media", "Review Volume", "Sentiment", "Brand Story", "Digital Activation", "Competitor Edge"],
            "hakshan": [4.3, 8.5, 8.0, 9.0, 3.5, 6.5],
            "ideal":   [9.0, 9.0, 9.0, 9.0, 9.0, 9.0],
        },
        "content_breakdown": {
            "types": ["Food Photography", "Branch Updates", "Charity / CSR", "Customer UGC", "Seasonal / Festival"],
            "percentages": [45, 25, 8, 12, 10],
        },
        "sentiment_by_branch": {
            "kepong":       {"positive": 88, "neutral": 8,  "negative": 4},
            "subang":       {"positive": 82, "neutral": 12, "negative": 6},
            "puchong":      {"positive": 85, "neutral": 10, "negative": 5},
            "cheras":       {"positive": 80, "neutral": 14, "negative": 6},
            "sri_petaling": {"positive": 75, "neutral": 20, "negative": 5},
        },
        "competitor_social_comparison": {
            "labels": ["Instagram", "Facebook", "TikTok", "XHS"],
            "hakshan":    [2771, 6257, 0, 0],
            "hakka_kl":   [500,  3500, 0, 0],
            "hakka_pass": [500,  0,    0, 0],
        },
    },
}


def _parse_rss_date(pub_date_str: str) -> datetime:
    try:
        return parsedate_to_datetime(pub_date_str)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def fetch_rss_feed(url: str, category: str) -> list:
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
                "category": category,
            })
        return items[:20]
    except Exception as exc:
        print(f"[data_fetcher] RSS fetch failed ({category}): {exc}")
        return []


def fetch_all_news() -> list:
    all_articles = []
    seen_links: set = set()
    for feed in RSS_FEEDS:
        for article in fetch_rss_feed(feed["url"], feed["category"]):
            norm_link = article["link"].split("?")[0]
            if norm_link not in seen_links:
                seen_links.add(norm_link)
                all_articles.append(article)
    all_articles.sort(key=lambda a: _parse_rss_date(a["pub_date"]), reverse=True)
    return all_articles[:30]


def read_analysis_section(section: str) -> str:
    filename = ANALYSIS_FILES.get(section)
    if not filename:
        return ""
    path = os.path.join(os.path.dirname(__file__), filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


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
