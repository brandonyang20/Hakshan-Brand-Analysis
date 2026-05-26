"""
Social media profile scraper using Playwright headless browser.

Scrapes public-facing metrics (followers, posts, likes) for Instagram,
TikTok, Facebook, and XHS (Xiaohongshu) without requiring OAuth tokens.

Tenant onboarding: store handles in tenant_config.social_handles JSONB:
  {"instagram": "hakshan_", "facebook": "hakshan", "tiktok": "hakshan", "xhs": "5f1234..."}

XHS note: most profile data requires a logged-in session. Pass xhs_cookies
(list of Playwright cookie dicts) from a stored browser session to enable it.
"""

import asyncio
import json
import os
import random
import re
from datetime import date, datetime, timezone

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache", "social")


# ── number parsing ─────────────────────────────────────────────────────────────

def _parse_count(text: str | None) -> int | None:
    """Parse '2,771', '2.7K', '1.2M' to int. Returns None on failure."""
    if not text:
        return None
    text = text.strip().replace(",", "")
    m = re.match(r"^([\d.]+)([KkMm]?)$", text)
    if not m:
        return None
    num = float(m.group(1))
    suffix = m.group(2).upper()
    if suffix == "K":
        return int(num * 1_000)
    if suffix == "M":
        return int(num * 1_000_000)
    return int(num)


def _find_count(pattern: str, text: str, group: int = 1) -> int | None:
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        raw = m.group(group).replace(",", "")
        try:
            return int(raw)
        except ValueError:
            return _parse_count(raw)
    return None


# ── per-platform scrapers ──────────────────────────────────────────────────────

async def _scrape_instagram(handle: str, browser) -> dict | None:
    ctx = await browser.new_context(
        user_agent=random.choice(_USER_AGENTS),
        viewport={"width": 1280, "height": 800},
    )
    page = await ctx.new_page()
    try:
        await page.goto(
            f"https://www.instagram.com/{handle}/",
            wait_until="domcontentloaded",
            timeout=25_000,
        )
        await page.wait_for_timeout(2_000)

        # Primary: og:description contains "2,771 Followers, 456 Following, 127 Posts"
        og_desc = await page.get_attribute('meta[property="og:description"]', "content") or ""
        followers = _find_count(r"([\d,]+)\s+[Ff]ollowers", og_desc)
        posts = _find_count(r"([\d,]+)\s+[Pp]osts", og_desc)
        following = _find_count(r"([\d,]+)\s+[Ff]ollowing", og_desc)

        if followers is not None:
            return {
                "followers": followers,
                "following": following,
                "posts": posts,
                "source": "instagram_scrape",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

        # Fallback: look for followerCount in embedded JSON
        content = await page.content()
        followers = _find_count(r'"followerCount"\s*:\s*(\d+)', content)
        if followers is not None:
            return {
                "followers": followers,
                "source": "instagram_scrape_json",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

        print(f"[social_scraper] Instagram @{handle}: no follower data found (login wall?)")
        return None
    except Exception as exc:
        print(f"[social_scraper] Instagram @{handle} error: {exc}")
        return None
    finally:
        await ctx.close()


async def _scrape_tiktok(handle: str, browser) -> dict | None:
    ctx = await browser.new_context(
        user_agent=random.choice(_USER_AGENTS),
        viewport={"width": 1280, "height": 800},
    )
    page = await ctx.new_page()
    try:
        await page.goto(
            f"https://www.tiktok.com/@{handle}",
            wait_until="domcontentloaded",
            timeout=25_000,
        )
        await page.wait_for_timeout(2_500)

        content = await page.content()

        # TikTok embeds profile stats in __UNIVERSAL_DATA_FOR_REHYDRATION__
        for pattern in [
            r'window\["__UNIVERSAL_DATA_FOR_REHYDRATION__"\]\s*=\s*(\{.+?\})\s*;',
            r'__UNIVERSAL_DATA_FOR_REHYDRATION__\s*=\s*(\{.+?\})\s*;',
        ]:
            m = re.search(pattern, content, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    scope = data.get("__DEFAULT_SCOPE__", {})
                    stats = (
                        scope.get("webapp.user-detail", {})
                        .get("userInfo", {})
                        .get("stats", {})
                    )
                    if stats:
                        return {
                            "followers": stats.get("followerCount"),
                            "following": stats.get("followingCount"),
                            "total_likes": stats.get("heartCount"),
                            "posts": stats.get("videoCount"),
                            "source": "tiktok_scrape",
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                        }
                except (json.JSONDecodeError, KeyError):
                    pass

        # Fallback: og:description
        og_desc = await page.get_attribute('meta[property="og:description"]', "content") or ""
        followers = _find_count(r"([\d,.]+[KkMm]?)\s+[Ff]ollowers", og_desc)
        if followers is not None:
            return {
                "followers": followers,
                "source": "tiktok_scrape_meta",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

        print(f"[social_scraper] TikTok @{handle}: no stats found")
        return None
    except Exception as exc:
        print(f"[social_scraper] TikTok @{handle} error: {exc}")
        return None
    finally:
        await ctx.close()


async def _scrape_facebook(page_identifier: str, browser) -> dict | None:
    ctx = await browser.new_context(
        user_agent=random.choice(_USER_AGENTS),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    page = await ctx.new_page()
    try:
        url = (
            page_identifier
            if page_identifier.startswith("http")
            else f"https://www.facebook.com/{page_identifier}"
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3_000)

        content = await page.content()

        # Facebook embeds counts in JSON or readable text
        for pattern in [
            r'"followerCount"\s*:\s*(\d+)',
            r'"fan_count"\s*:\s*(\d+)',
            r'"page_likers"\s*:\s*\{"count"\s*:\s*(\d+)',
            r'([\d,]+)\s+people follow this',
            r'([\d,]+)\s+followers',
        ]:
            followers = _find_count(pattern, content)
            if followers is not None:
                return {
                    "followers": followers,
                    "source": "facebook_scrape",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }

        print(f"[social_scraper] Facebook {page_identifier}: no follower count found")
        return None
    except Exception as exc:
        print(f"[social_scraper] Facebook {page_identifier} error: {exc}")
        return None
    finally:
        await ctx.close()


async def _scrape_xhs(handle: str, browser, cookies: list | None = None) -> dict | None:
    ctx = await browser.new_context(
        user_agent=random.choice(_USER_AGENTS),
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    page = await ctx.new_page()
    try:
        if cookies:
            await ctx.add_cookies(cookies)

        # If handle looks like a 24-hex user ID, go direct; otherwise search
        if re.match(r"^[0-9a-f]{24}$", handle):
            url = f"https://www.xiaohongshu.com/user/profile/{handle}"
        else:
            url = f"https://www.xiaohongshu.com/search_result?keyword={handle}&type=user"

        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(4_000)

        content = await page.content()

        for pattern in [
            r'"fans"\s*:\s*(\d+)',
            r'"fansCount"\s*:\s*(\d+)',
            r'"followerCount"\s*:\s*(\d+)',
        ]:
            followers = _find_count(pattern, content)
            if followers is not None:
                return {
                    "followers": followers,
                    "source": "xhs_scrape",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }

        if not cookies:
            print(f"[social_scraper] XHS {handle}: login session required — store xhs_cookies in tenant_config")
        else:
            print(f"[social_scraper] XHS {handle}: no follower count found even with cookies")
        return None
    except Exception as exc:
        print(f"[social_scraper] XHS {handle} error: {exc}")
        return None
    finally:
        await ctx.close()


# ── orchestrator ───────────────────────────────────────────────────────────────

async def scrape_all_platforms(
    social_handles: dict,
    xhs_cookies: list | None = None,
) -> dict:
    """
    Scrape all configured platforms for one tenant.

    Args:
        social_handles: {"instagram": "handle", "tiktok": "handle", ...}
        xhs_cookies:    Optional Playwright cookie list for XHS authentication.

    Returns:
        {"instagram": {...metrics or None}, "tiktok": {...}, ...}
    """
    from playwright.async_api import async_playwright

    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            for platform, handle in social_handles.items():
                if not handle:
                    continue

                if results:
                    await asyncio.sleep(random.uniform(4, 8))

                print(f"[social_scraper] Scraping {platform}: {handle}")
                if platform == "instagram":
                    results["instagram"] = await _scrape_instagram(handle, browser)
                elif platform == "tiktok":
                    results["tiktok"] = await _scrape_tiktok(handle, browser)
                elif platform == "facebook":
                    results["facebook"] = await _scrape_facebook(handle, browser)
                elif platform == "xhs":
                    results["xhs"] = await _scrape_xhs(handle, browser, xhs_cookies)
        finally:
            await browser.close()

    return results


def run_scrape(social_handles: dict, xhs_cookies: list | None = None) -> dict:
    """Synchronous wrapper — use this from APScheduler and Flask routes."""
    return asyncio.run(scrape_all_platforms(social_handles, xhs_cookies))


# ── storage ────────────────────────────────────────────────────────────────────

def store_social_snapshot(tenant_id: str, platform: str, data: dict | None) -> None:
    """Upsert scraped metrics to Supabase or local JSON cache."""
    today = date.today().isoformat()
    row = {
        "tenant_id": tenant_id,
        "platform": platform,
        "snapshot_date": today,
        "followers": data.get("followers") if data else None,
        "following": data.get("following") if data else None,
        "posts": data.get("posts") if data else None,
        "total_likes": data.get("total_likes") if data else None,
        "error": None if data else "scrape_failed",
    }

    if os.environ.get("SUPABASE_URL"):
        try:
            from auth import get_supabase_admin_client
            client = get_supabase_admin_client()
            if client:
                client.table("social_snapshots").upsert(row).execute()
                return
        except Exception as exc:
            print(f"[social_scraper] Supabase store failed ({platform}): {exc}")

    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, f"{tenant_id}_{platform}.json")
    try:
        rows: list = []
        if os.path.exists(path):
            with open(path) as f:
                rows = json.load(f)
        rows = [r for r in rows if r.get("snapshot_date") != today]
        rows.append(row)
        rows = sorted(rows, key=lambda r: r["snapshot_date"])[-16:]
        with open(path, "w") as f:
            json.dump(rows, f)
    except Exception as exc:
        print(f"[social_scraper] Cache write failed ({platform}): {exc}")


def get_social_history(tenant_id: str, platform: str, limit: int = 12) -> list:
    """Return recent snapshots for this platform, oldest first, for trend charts."""
    if os.environ.get("SUPABASE_URL"):
        try:
            from auth import get_supabase_admin_client
            client = get_supabase_admin_client()
            if client:
                r = (
                    client.table("social_snapshots")
                    .select("snapshot_date,followers,posts,total_likes,error")
                    .eq("tenant_id", tenant_id)
                    .eq("platform", platform)
                    .order("snapshot_date", desc=True)
                    .limit(limit)
                    .execute()
                )
                return list(reversed(r.data or []))
        except Exception:
            return []

    path = os.path.join(_CACHE_DIR, f"{tenant_id}_{platform}.json")
    try:
        if os.path.exists(path):
            with open(path) as f:
                rows = json.load(f)
            return rows[-limit:]
    except Exception:
        pass
    return []


def get_latest_social(tenant_id: str) -> dict:
    """
    Return most recent follower count per platform as a flat dict.
    {"instagram": 2771, "tiktok": 0, "facebook": 6257, "xhs": None}
    """
    platforms = ("instagram", "facebook", "tiktok", "xhs")
    result = {}
    for platform in platforms:
        rows = get_social_history(tenant_id, platform, limit=1)
        if rows and rows[-1].get("followers") is not None:
            result[platform] = rows[-1]["followers"]
        else:
            result[platform] = None
    return result


def get_tenant_social_handles(tenant_id: str) -> dict:
    """Load social handles from tenant_config. Falls back to dev config."""
    if os.environ.get("SUPABASE_URL"):
        try:
            from auth import get_supabase_admin_client
            client = get_supabase_admin_client()
            if client:
                r = (
                    client.table("tenant_config")
                    .select("social_handles")
                    .eq("tenant_id", tenant_id)
                    .single()
                    .execute()
                )
                return (r.data or {}).get("social_handles", {})
        except Exception:
            pass

    # Dev fallback for Hakshan
    return {
        "instagram": "hakshan_",
        "facebook": "hakshan",
        "tiktok": "",
        "xhs": "",
    }
