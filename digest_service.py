"""
Weekly AI intelligence digest generator.

Calls Claude claude-sonnet-4-6 to produce a concise brand health summary
paragraph for the CEO dashboard Intelligence section.

Digests are upserted to the intelligence_digests Supabase table (one per
tenant per week) and cached locally for dev/offline mode.
"""

import json
import os
from datetime import date, timedelta

_DIGEST_MODEL = "claude-sonnet-4-6"
_DIGEST_MAX_TOKENS = 300
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache", "digests")


def _week_start(d: date | None = None) -> date:
    """Return the Monday of the week containing d (defaults to today)."""
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def build_intelligence_digest(
    tenant_id: str,
    brand_name: str,
    branches_data: list,
    social_counts: dict | None = None,
) -> str | None:
    """
    Generate a weekly digest paragraph via Claude.

    branches_data items must have keys:
        branch_name, rating, review_count, review_delta, health_score (int|None)

    social_counts: {"instagram": 2771, "tiktok": 0, ...} or None

    Returns the digest string, or None when ANTHROPIC_API_KEY is not set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[digest_service] ANTHROPIC_API_KEY not set — digest skipped")
        return None

    try:
        import anthropic
    except ImportError:
        print("[digest_service] anthropic package not installed")
        return None

    client = anthropic.Anthropic(api_key=api_key)

    branch_lines = []
    for b in branches_data:
        delta = b.get("review_delta")
        delta_str = (
            f" (+{delta} new reviews)" if delta and delta > 0
            else f" ({delta} reviews)" if delta and delta < 0
            else ""
        )
        health = b.get("health_score")
        health_str = f", health score {health}/100" if health is not None else ""
        branch_lines.append(
            f"  - {b['branch_name']}: {b.get('rating', '—')}/5.0 stars, "
            f"{b.get('review_count', '—')} total reviews{delta_str}{health_str}"
        )

    social_lines = []
    if social_counts:
        platform_labels = {"instagram": "Instagram", "facebook": "Facebook", "tiktok": "TikTok", "xhs": "XHS"}
        for platform, count in social_counts.items():
            if count:
                social_lines.append(
                    f"  - {platform_labels.get(platform, platform)}: {count:,} followers"
                )

    week = _week_start()
    prompt = f"""You are a brand intelligence analyst for {brand_name}, a restaurant chain in Malaysia.

Weekly brand data for the week of {week.strftime('%d %b %Y')}:

Branch performance:
{chr(10).join(branch_lines)}
{"" if not social_lines else chr(10) + "Social media:" + chr(10) + chr(10).join(social_lines)}

Write a concise 2-3 sentence intelligence summary for the CEO. Be specific:
1. What is the overall brand health trend (improving / stable / declining)?
2. Call out the best and worst performing branch by name.
3. Give one concrete action the CEO should take this week.

Plain English, no bullet points, no headers. Direct and specific."""

    try:
        response = client.messages.create(
            model=_DIGEST_MODEL,
            max_tokens=_DIGEST_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        store_digest(tenant_id, text)
        return text
    except Exception as exc:
        print(f"[digest_service] Claude API error: {exc}")
        return None


def store_digest(tenant_id: str, digest_text: str) -> None:
    """Upsert the digest to Supabase or local JSON cache."""
    week = _week_start().isoformat()

    if os.environ.get("SUPABASE_URL"):
        try:
            from auth import get_supabase_admin_client
            client = get_supabase_admin_client()
            if client:
                client.table("intelligence_digests").upsert({
                    "tenant_id": tenant_id,
                    "week_start": week,
                    "digest_text": digest_text,
                    "model": _DIGEST_MODEL,
                }).execute()
                return
        except Exception as exc:
            print(f"[digest_service] Supabase store failed: {exc}")

    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, f"{tenant_id}.json")
    try:
        rows: list = []
        if os.path.exists(path):
            with open(path) as f:
                rows = json.load(f)
        rows = [r for r in rows if r.get("week_start") != week]
        rows.append({"week_start": week, "digest_text": digest_text})
        rows = sorted(rows, key=lambda r: r["week_start"])[-8:]
        with open(path, "w") as f:
            json.dump(rows, f)
    except Exception as exc:
        print(f"[digest_service] Cache write failed: {exc}")


def get_latest_digest(tenant_id: str) -> dict | None:
    """
    Return the most recent digest as {"week_start": "...", "digest_text": "..."}, or None.
    """
    if os.environ.get("SUPABASE_URL"):
        try:
            from auth import get_supabase_admin_client
            client = get_supabase_admin_client()
            if client:
                r = (
                    client.table("intelligence_digests")
                    .select("digest_text,week_start")
                    .eq("tenant_id", tenant_id)
                    .order("week_start", desc=True)
                    .limit(1)
                    .execute()
                )
                return r.data[0] if r.data else None
        except Exception:
            return None

    path = os.path.join(_CACHE_DIR, f"{tenant_id}.json")
    try:
        if os.path.exists(path):
            with open(path) as f:
                rows = json.load(f)
            return rows[-1] if rows else None
    except Exception:
        pass
    return None
