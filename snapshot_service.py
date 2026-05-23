"""Phase 1B: weekly review snapshot service.

Fetches each branch's Google Maps rating and review count via Serpapi,
stores results to Supabase (production) or local JSON files (dev/offline),
and exposes delta helpers used by build_tenant_summary().
"""

import json
import os
import time
from datetime import date

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache", "snapshots")


# ── file-based storage (dev / Supabase-not-configured) ────────────────────────

def _snap_path(tenant_id: str, branch_id: str) -> str:
    d = os.path.join(_CACHE_DIR, tenant_id)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{branch_id}.json")


def _load_file(tenant_id: str, branch_id: str) -> list:
    try:
        with open(_snap_path(tenant_id, branch_id)) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_file(tenant_id: str, branch_id: str, rows: list) -> None:
    with open(_snap_path(tenant_id, branch_id), "w") as f:
        json.dump(rows, f)


# ── Serpapi fetch ──────────────────────────────────────────────────────────────

def fetch_branch_snapshot(maps_query: str) -> dict | None:
    """Call Serpapi Google Maps engine. Return {rating, review_count} or None."""
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        return None
    import urllib.parse
    import urllib.request

    params = urllib.parse.urlencode({
        "engine": "google_maps",
        "q": maps_query.replace("+", " "),
        "api_key": api_key,
    })
    try:
        req = urllib.request.Request(
            f"https://serpapi.com/search.json?{params}",
            headers={"User-Agent": "BrandPulse/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = data.get("local_results") or []
        if not results:
            return None
        top = results[0]
        return {"rating": top.get("rating"), "review_count": top.get("reviews")}
    except Exception:
        return None


# ── storage ────────────────────────────────────────────────────────────────────

def store_snapshot(tenant_id: str, branch_id: str, rating, review_count) -> None:
    today = date.today().isoformat()

    if os.environ.get("SUPABASE_URL"):
        try:
            from auth import get_supabase_client
            client = get_supabase_client()
            if client:
                client.table("review_snapshots").upsert({
                    "tenant_id": tenant_id,
                    "branch_id": branch_id,
                    "snapshot_date": today,
                    "rating": rating,
                    "review_count": review_count,
                }).execute()
                return
        except Exception:
            pass

    rows = _load_file(tenant_id, branch_id)
    existing = next((r for r in rows if r["date"] == today), None)
    if existing:
        existing["rating"] = rating
        existing["review_count"] = review_count
    else:
        rows.append({"date": today, "rating": rating, "review_count": review_count})
    rows = sorted(rows, key=lambda r: r["date"])[-16:]  # keep ~4 months
    _save_file(tenant_id, branch_id, rows)


# ── read helpers ───────────────────────────────────────────────────────────────

def get_latest_snapshot(tenant_id: str, branch_id: str) -> dict | None:
    """Return the most recent snapshot row, or None."""
    if os.environ.get("SUPABASE_URL"):
        try:
            from auth import get_supabase_client
            client = get_supabase_client()
            if client:
                r = (
                    client.table("review_snapshots")
                    .select("snapshot_date,rating,review_count")
                    .eq("tenant_id", tenant_id)
                    .eq("branch_id", branch_id)
                    .order("snapshot_date", desc=True)
                    .limit(1)
                    .execute()
                )
                rows = r.data or []
                return rows[0] if rows else None
        except Exception:
            return None

    rows = _load_file(tenant_id, branch_id)
    return rows[-1] if rows else None


def get_review_delta(tenant_id: str, branch_id: str):
    """Return this_week_count - last_week_count, or None if < 2 snapshots."""
    if os.environ.get("SUPABASE_URL"):
        try:
            from auth import get_supabase_client
            client = get_supabase_client()
            if client:
                r = (
                    client.table("review_snapshots")
                    .select("review_count")
                    .eq("tenant_id", tenant_id)
                    .eq("branch_id", branch_id)
                    .order("snapshot_date", desc=True)
                    .limit(2)
                    .execute()
                )
                rows = r.data or []
                if len(rows) >= 2:
                    a, b = rows[0].get("review_count"), rows[1].get("review_count")
                    if a is not None and b is not None:
                        return a - b
                return None
        except Exception:
            return None

    rows = _load_file(tenant_id, branch_id)
    if len(rows) >= 2:
        a, b = rows[-1].get("review_count"), rows[-2].get("review_count")
        if a is not None and b is not None:
            return a - b
    return None


# ── batch runner ───────────────────────────────────────────────────────────────

def run_weekly_snapshot(tenant_id: str, branches: list) -> dict:
    """Snapshot all branches for a tenant. Returns {ok, failed, skipped} lists."""
    if not os.environ.get("SERPAPI_KEY"):
        return {"error": "SERPAPI_KEY not configured"}

    ok, failed, skipped = [], [], []
    for b in branches:
        bid = b.get("id")
        query = b.get("maps_query")
        if not bid or not query:
            skipped.append(bid or "?")
            continue

        snap = fetch_branch_snapshot(query)
        if snap and snap.get("rating") is not None:
            store_snapshot(tenant_id, bid, snap["rating"], snap.get("review_count"))
            ok.append(bid)
        else:
            failed.append(bid)

        time.sleep(2)  # polite rate limiting — 1 request per 2 seconds

    return {"ok": ok, "failed": failed, "skipped": skipped}
