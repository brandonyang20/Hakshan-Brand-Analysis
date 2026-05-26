import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

CACHE_FILE = os.path.join(os.path.dirname(__file__), "cache", "data.json")
SOCIAL_LIVE_CACHE_FILE = os.path.join(os.path.dirname(__file__), "cache", "social_live.json")
COMPETITOR_SOCIAL_FILE = os.path.join(os.path.dirname(__file__), "cache", "competitor_social.json")
CACHE_MAX_AGE_HOURS = 24
SOCIAL_LIVE_CACHE_MAX_AGE_HOURS = 6

INSTAGRAM_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
FACEBOOK_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")

# Categorised RSS feeds — category + optional competitor_id tag attached to each article
RSS_FEEDS = [
    {
        "url": "https://news.google.com/rss/search?q=Hakshan+Malaysia+restaurant&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "hakshan",
        "competitor_id": "",
    },
    {
        "url": "https://news.google.com/rss/search?q=Hakka+restaurant+Malaysia+2026&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "competitor",
        "competitor_id": "",
    },
    {
        "url": "https://news.google.com/rss/search?q=Malaysia+Chinese+restaurant+food+industry&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "industry",
        "competitor_id": "",
    },
    # Competitor-specific feeds — news tracked per brand
    {
        "url": "https://news.google.com/rss/search?q=%22Hakka+Restaurant%22+%22Jalan+Raja+Chulan%22+Malaysia&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "competitor",
        "competitor_id": "hakka_kl",
    },
    {
        "url": "https://news.google.com/rss/search?q=%22Hakka+Passion%22+Puchong+restaurant+Malaysia&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "competitor",
        "competitor_id": "hakka_pass",
    },
    {
        "url": "https://news.google.com/rss/search?q=%22%E5%AE%A2%E4%BA%BA%E4%BE%86%22+OR+%22Ke+Ren+Lai%22+Malaysia+restaurant&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "competitor",
        "competitor_id": "ke_ren_lai",
    },
    {
        "url": "https://news.google.com/rss/search?q=%22Hakka+Village%22+restaurant+Malaysia+Puchong&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "competitor",
        "competitor_id": "hakka_village",
    },
    {
        "url": "https://news.google.com/rss/search?q=%22Hakka+Niang%22+OR+%22%E5%AE%A2%E5%AE%B6%E5%A8%98%22+restaurant+Malaysia&hl=en-MY&gl=MY&ceid=MY:en",
        "category": "competitor",
        "competitor_id": "hakka_niang",
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
            "followers": 3100,
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
            "likes": 8000,
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
            "rating": None,
            "review_count": None,
            "highlights": ["Authentic flavours", "Fast service during peak hours"],
            "sentiment_themes": ["Tastes like grandma's cooking", "Clean and comfortable"],
            "watch_areas": ["Weekend queues", "Parking challenges"],
            "best_dishes": ["Ginger-Sprout Braised Duck Rice", "Hakka Pork Belly"],
        },
        {
            "id": "ss2",
            "name": "SS2, Petaling Jaya",
            "role": "Active",
            "address": "SS2, Petaling Jaya, Selangor",
            "maps_query": "Hakshan+SS2",
            "status": "established",
            "rating": None,
            "review_count": None,
            "highlights": ["Dense PJ Chinese residential catchment"],
            "sentiment_themes": [],
            "watch_areas": [],
            "best_dishes": [],
        },
        {
            "id": "ipoh",
            "name": "Ipoh, Perak",
            "role": "Active",
            "address": "Ipoh, Perak",
            "maps_query": "Hakshan+Ipoh+Perak",
            "status": "established",
            "rating": None,
            "review_count": None,
            "highlights": ["Expanding into Perak market"],
            "sentiment_themes": [],
            "watch_areas": [],
            "best_dishes": [],
        },
        {
            "id": "sri_petaling",
            "name": "Sri Petaling",
            "role": "Active",
            "address": "Sri Petaling, KL",
            "maps_query": "Hakshan+Sri+Petaling+KL",
            "status": "established",
            "rating": None,
            "review_count": None,
            "highlights": ["Dense Chinese residential area"],
            "sentiment_themes": [],
            "watch_areas": [],
            "best_dishes": [],
        },
        {
            "id": "cheras",
            "name": "Cheras Traders Square",
            "role": "Active",
            "address": "Cheras Traders Square, Cheras Selatan, KL",
            "maps_query": "Hakshan+Cheras+Traders+Square",
            "status": "established",
            "rating": None,
            "review_count": None,
            "highlights": ["Hot-stone noodle sets", "Silky chicken wonton"],
            "sentiment_themes": ["Price is just right", "Great for group dinners"],
            "watch_areas": [],
            "best_dishes": ["Silky Chicken Wonton", "Hot-Stone Noodle Sets"],
        },
        {
            "id": "kota_damansara",
            "name": "Kota Damansara",
            "role": "Active",
            "address": "Kota Damansara, Selangor",
            "maps_query": "Hakshan+Kota+Damansara+Selangor",
            "status": "established",
            "rating": None,
            "review_count": None,
            "highlights": ["Affluent township catchment"],
            "sentiment_themes": [],
            "watch_areas": [],
            "best_dishes": [],
        },
        {
            "id": "subang",
            "name": "USJ Taipan, Subang Jaya",
            "role": "Active",
            "address": "33, Jalan USJ 10/1G, USJ Taipan, Subang Jaya, Selangor",
            "maps_query": "Hakshan+USJ+Taipan+Subang+Jaya",
            "status": "established",
            "rating": None,
            "review_count": None,
            "highlights": ["Consistent quality", "High footfall commercial hub"],
            "sentiment_themes": ["Good accessibility", "Repeat diners"],
            "watch_areas": ["Parking availability"],
            "best_dishes": ["Hakka Trio-Sauce Chicken", "Braised Pork Belly"],
        },
        {
            "id": "bukit_tinggi",
            "name": "Bukit Tinggi, Klang",
            "role": "Active",
            "address": "Bukit Tinggi, Klang, Selangor",
            "maps_query": "Hakshan+Bukit+Tinggi+Klang",
            "status": "established",
            "rating": None,
            "review_count": None,
            "highlights": ["Klang market expansion"],
            "sentiment_themes": [],
            "watch_areas": [],
            "best_dishes": [],
        },
        {
            "id": "puchong",
            "name": "Bandar Puteri Puchong",
            "role": "Active",
            "address": "53G, Jalan Puteri 1/4, Bandar Puteri Puchong, Selangor",
            "maps_query": "Hakshan+Bandar+Puteri+Puchong",
            "status": "established",
            "rating": None,
            "review_count": None,
            "highlights": ["Pork patty specifically highlighted", "Recognised as best Hakka in Puchong"],
            "sentiment_themes": ["Strong community reception"],
            "watch_areas": [],
            "best_dishes": ["Steamed Minced Pork Patty", "Duck Rice"],
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
            "id": "hakka_kl",
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
            "id": "hakka_pass",
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
        {
            "id": "ke_ren_lai",
            "name": "客人來 Ke Ren Lai",
            "name_zh": "客人來",
            "type": "direct",
            "est": "~2015",
            "location": "PJ / Subang area, multiple outlets",
            "instagram_followers": 1200,
            "facebook_likes": 4200,
            "tiktok": False,
            "tripadvisor_rating": 4.1,
            "tripadvisor_reviews": 320,
            "threat_level": "high_pj",
            "threat_label": "High (PJ/Subang)",
            "posts_per_month": 3,
            "content_mix": {"Food": 75, "Promotions": 15, "Events": 10},
            "avg_engagement": "Low (~30 likes/post)",
            "last_active": "Occasional",
            "strengths": ["Multi-outlet PJ/Subang presence", "Overlaps Hakshan's Subang market", "Active Facebook community"],
            "weaknesses": ["No TikTok presence", "Low IG engagement rate", "No differentiated brand story or CSR angle"],
            "content_strategy_note": "Primarily FB-driven. Occasional food photography posts, no video content or influencer partnerships.",
        },
        {
            "id": "hakka_village",
            "name": "Hakka Village",
            "name_zh": "客家村",
            "type": "direct",
            "est": "~2018",
            "location": "Puchong / Cheras area",
            "instagram_followers": 680,
            "facebook_likes": 2100,
            "tiktok": False,
            "tripadvisor_rating": 4.0,
            "tripadvisor_reviews": 180,
            "threat_level": "medium_puchong",
            "threat_label": "Medium (Puchong)",
            "posts_per_month": 2,
            "content_mix": {"Food": 85, "Promotions": 15},
            "avg_engagement": "Very Low",
            "last_active": "Sporadic",
            "strengths": ["Village-style ambiance differentiator", "Established Puchong locals base", "Affordable family pricing"],
            "weaknesses": ["Very weak digital footprint", "No Google Maps optimisation", "No loyalty programme"],
            "content_strategy_note": "Sporadic food photo posts only. No brand narrative, no video content, no community engagement.",
        },
        {
            "id": "hakka_niang",
            "name": "Hakka Niang",
            "name_zh": "客家娘",
            "type": "direct",
            "est": "~2019",
            "location": "Cheras / Taman Connaught",
            "instagram_followers": 420,
            "facebook_likes": 1500,
            "tiktok": False,
            "tripadvisor_rating": None,
            "tripadvisor_reviews": None,
            "threat_level": "medium_cheras",
            "threat_label": "Medium (Cheras)",
            "posts_per_month": 2,
            "content_mix": {"Food": 90, "Promotions": 10},
            "avg_engagement": "Very Low",
            "last_active": "Rare",
            "strengths": ["Dense Cheras Chinese residential catchment", "Home-style feminine branding appeal", "Long-standing regulars"],
            "weaknesses": ["Near-zero digital strategy", "Single location", "No CSR angle", "No TikTok or XHS"],
            "content_strategy_note": "Almost entirely word-of-mouth. Minimal social posting, no influencer or video strategy.",
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
        "instagram_followers": {"current": 3100, "target_3m": 6000, "target_12m": 15000},
        "facebook_likes": {"current": 8000, "target_3m": 12000, "target_12m": 25000},
        "tiktok_followers": {"current": 0, "target_3m": 2000, "target_12m": 10000},
        "xhs_followers": {"current": 0, "target_3m": 500, "target_12m": 2000},
        "google_response_rate": {"current_pct": 20, "target_pct": 90},
        "avg_google_rating": {"current": 4.5, "target": 4.5},
        "monthly_ugc_posts": {"current": 0, "target": 50},
    },
    "chart_data": {
        "review_trend": {
            "labels": ["Dec '25", "Jan '26", "Feb '26", "Mar '26", "Apr '26", "May '26"],
            "kepong":         [130, 155, 175, 165, 195, 215],
            "ss2":            [0,   0,   0,   0,   0,   0],
            "ipoh":           [0,   0,   0,   0,   0,   0],
            "sri_petaling":   [0,   0,   0,  22,  32,  38],
            "cheras":         [48,  68,  82,  77,  87,  97],
            "kota_damansara": [0,   0,   0,   0,   0,   0],
            "subang":         [95, 115, 135, 125, 145, 165],
            "bukit_tinggi":   [0,   0,   0,   0,   0,   0],
            "puchong":        [55,  75, 100,  95, 115, 125],
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
            "hakshan":    [3100, 8000, 0, 0],
            "hakka_kl":   [500,  3500, 0, 0],
            "hakka_pass": [500,  0,    0, 0],
            "ke_ren_lai": [1200, 4200, 0, 0],
        },
    },
}


def _parse_rss_date(pub_date_str: str) -> datetime:
    try:
        return parsedate_to_datetime(pub_date_str)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def fetch_rss_feed(url: str, category: str, competitor_id: str = "") -> list:
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
                "competitor_id": competitor_id,
            })
        return items[:20]
    except Exception as exc:
        print(f"[data_fetcher] RSS fetch failed ({category}/{competitor_id or 'general'}): {exc}")
        return []


def fetch_all_news() -> list:
    all_articles = []
    seen_links: set = set()
    for feed in RSS_FEEDS:
        for article in fetch_rss_feed(
            feed["url"],
            feed["category"],
            feed.get("competitor_id", ""),
        ):
            norm_link = article["link"].split("?")[0]
            if norm_link not in seen_links:
                seen_links.add(norm_link)
                all_articles.append(article)
    all_articles.sort(key=lambda a: _parse_rss_date(a["pub_date"]), reverse=True)
    return all_articles[:50]


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


def fetch_instagram_data(token: str) -> "dict | None":
    base = "https://graph.instagram.com/v19.0"
    try:
        profile_resp = requests.get(
            f"{base}/me",
            params={"fields": "followers_count,media_count,username", "access_token": token},
            timeout=10,
        )
        profile = profile_resp.json()
        if "error" in profile:
            print(f"[data_fetcher] Instagram API error: {profile['error'].get('message')}")
            return None

        media_resp = requests.get(
            f"{base}/me/media",
            params={
                "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink",
                "limit": 5,
                "access_token": token,
            },
            timeout=10,
        ).json()

        recent_posts = []
        for post in media_resp.get("data", []):
            media_url = post.get("media_url") or post.get("thumbnail_url") or ""
            recent_posts.append({
                "id": post.get("id", ""),
                "caption": (post.get("caption") or "")[:150],
                "media_url": media_url,
                "timestamp": post.get("timestamp", ""),
                "permalink": post.get("permalink", ""),
            })

        return {
            "followers": profile.get("followers_count", 0),
            "posts": profile.get("media_count", 0),
            "username": profile.get("username", ""),
            "recent_posts": recent_posts,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "instagram_api",
        }
    except Exception as exc:
        print(f"[data_fetcher] Instagram fetch failed: {exc}")
        return None


def fetch_facebook_data(token: str, page_id: str) -> "dict | None":
    base = "https://graph.facebook.com/v19.0"
    try:
        resp = requests.get(
            f"{base}/{page_id}",
            params={"fields": "fan_count,name", "access_token": token},
            timeout=10,
        ).json()
        if "error" in resp:
            print(f"[data_fetcher] Facebook API error: {resp['error'].get('message')}")
            return None
        return {
            "likes": resp.get("fan_count", 0),
            "name": resp.get("name", ""),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "facebook_api",
        }
    except Exception as exc:
        print(f"[data_fetcher] Facebook fetch failed: {exc}")
        return None


def get_live_social_data(force: bool = False) -> "dict | None":
    if not INSTAGRAM_TOKEN:
        return None
    if not force and os.path.exists(SOCIAL_LIVE_CACHE_FILE):
        try:
            with open(SOCIAL_LIVE_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            fetched_at_str = cached.get("fetched_at", "")
            if fetched_at_str:
                fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - fetched_at
                if age.total_seconds() < SOCIAL_LIVE_CACHE_MAX_AGE_HOURS * 3600:
                    return cached
        except Exception:
            pass

    print("[data_fetcher] Fetching live social media data...")
    result: dict = {"fetched_at": datetime.now(timezone.utc).isoformat()}

    ig = fetch_instagram_data(INSTAGRAM_TOKEN)
    if ig:
        result["instagram"] = ig

    if FACEBOOK_PAGE_TOKEN and FACEBOOK_PAGE_ID:
        fb = fetch_facebook_data(FACEBOOK_PAGE_TOKEN, FACEBOOK_PAGE_ID)
        if fb:
            result["facebook"] = fb

    os.makedirs(os.path.dirname(SOCIAL_LIVE_CACHE_FILE), exist_ok=True)
    tmp_path = SOCIAL_LIVE_CACHE_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, SOCIAL_LIVE_CACHE_FILE)
    except Exception as exc:
        print(f"[data_fetcher] Social live cache save failed: {exc}")

    return result


def load_competitor_social() -> dict:
    if not os.path.exists(COMPETITOR_SOCIAL_FILE):
        return {}
    try:
        with open(COMPETITOR_SOCIAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_competitor_social(data: dict) -> None:
    os.makedirs(os.path.dirname(COMPETITOR_SOCIAL_FILE), exist_ok=True)
    tmp_path = COMPETITOR_SOCIAL_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, COMPETITOR_SOCIAL_FILE)
    except Exception as exc:
        print(f"[data_fetcher] Competitor social save failed: {exc}")


def _overlay_competitor_social(payload: dict) -> None:
    comp_social = load_competitor_social()
    if not comp_social:
        return
    for comp in payload.get("competitors", []):
        cid = comp.get("id")
        if cid and cid in comp_social:
            override = comp_social[cid]
            if "ig" in override:
                comp["instagram_followers"] = override["ig"]
            if "fb" in override:
                comp["facebook_likes"] = override["fb"]
            if "updated_at" in override:
                comp["social_updated_at"] = override["updated_at"]


def _overlay_live_data(payload: dict) -> None:
    live = get_live_social_data(force=False)
    if not live:
        return
    sm = payload.get("social_media", {})
    if live.get("instagram"):
        ig_live = live["instagram"]
        ig = sm.get("instagram", {})
        ig["followers"] = ig_live.get("followers", ig.get("followers"))
        ig["posts"] = ig_live.get("posts", ig.get("posts"))
        ig["recent_posts"] = ig_live.get("recent_posts", [])
        ig["source"] = "live"
    if live.get("facebook"):
        fb = sm.get("facebook", {})
        fb["likes"] = live["facebook"].get("likes", fb.get("likes"))
        fb["source"] = "live"
    payload["social_live_fetched_at"] = live.get("fetched_at")


def get_data(force: bool = False) -> dict:
    if not force:
        cached = load_cache()
        if cached and not is_cache_stale(cached):
            _overlay_competitor_social(cached)
            _overlay_live_data(cached)
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
    _overlay_competitor_social(payload)
    _overlay_live_data(payload)
    return payload
