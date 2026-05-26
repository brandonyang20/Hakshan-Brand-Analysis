"""Phase 1B: weekly review snapshot service.

Fetches each branch's Google Maps rating and review count via Serpapi,
stores results to Supabase (production) or local JSON files (dev/offline),
and exposes delta helpers used by build_tenant_summary().
"""

import json
import os
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_MYT = ZoneInfo("Asia/Kuala_Lumpur")

_PLACE_IDS_FILE = os.path.join(os.path.dirname(__file__), "cache", "place_ids.json")


def _load_place_ids() -> dict:
    try:
        with open(_PLACE_IDS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_place_ids(ids: dict) -> None:
    os.makedirs(os.path.dirname(_PLACE_IDS_FILE), exist_ok=True)
    with open(_PLACE_IDS_FILE, "w") as f:
        json.dump(ids, f)


# ── Google Places API fetch ────────────────────────────────────────────────────

def fetch_branch_snapshot(maps_query: str, branch_key: str | None = None) -> dict | None:
    """
    Fetch rating + review count from Google Places API.

    First call per branch uses Text Search (discovers place_id).
    Subsequent calls use Place Details with the cached place_id (faster).
    branch_key format: "{tenant_id}:{branch_id}" for place_id caching.
    """
    api_key = os.environ.get("GOOGLE_PLACES_KEY")
    if not api_key:
        return None

    import urllib.parse
    import urllib.request

    place_ids = _load_place_ids()
    cached_id = place_ids.get(branch_key) if branch_key else None

    if cached_id:
        params = urllib.parse.urlencode({
            "place_id": cached_id,
            "fields": "rating,user_ratings_total",
            "key": api_key,
        })
        try:
            req = urllib.request.Request(
                f"https://maps.googleapis.com/maps/api/place/details/json?{params}",
                headers={"User-Agent": "BrandPulse/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            result = data.get("result", {})
            if result.get("rating") is not None:
                return {
                    "rating": result.get("rating"),
                    "review_count": result.get("user_ratings_total"),
                }
        except Exception:
            pass  # fall through to Text Search

    # Text Search — resolves query to place_id on first call
    params = urllib.parse.urlencode({
        "query": maps_query.replace("+", " "),
        "key": api_key,
    })
    try:
        req = urllib.request.Request(
            f"https://maps.googleapis.com/maps/api/place/textsearch/json?{params}",
            headers={"User-Agent": "BrandPulse/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        results = data.get("results") or []
        if not results:
            return None
        top = results[0]
        # Cache place_id so future calls skip Text Search
        if branch_key and top.get("place_id"):
            place_ids[branch_key] = top["place_id"]
            _save_place_ids(place_ids)
        return {
            "rating": top.get("rating"),
            "review_count": top.get("user_ratings_total"),
        }
    except Exception:
        return None


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
    today = datetime.now(_MYT).date().isoformat()

    if os.environ.get("SUPABASE_URL"):
        try:
            from auth import get_supabase_admin_client
            client = get_supabase_admin_client()
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
            from auth import get_supabase_admin_client
            client = get_supabase_admin_client()
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
            from auth import get_supabase_admin_client
            client = get_supabase_admin_client()
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


# ── history + health scores ────────────────────────────────────────────────────

def get_snapshot_history(tenant_id: str, branch_id: str, limit: int = 12) -> list:
    """Return up to `limit` snapshots oldest-first for sparkline rendering."""
    if os.environ.get("SUPABASE_URL"):
        try:
            from auth import get_supabase_admin_client
            client = get_supabase_admin_client()
            if client:
                r = (
                    client.table("review_snapshots")
                    .select("snapshot_date,rating,review_count")
                    .eq("tenant_id", tenant_id)
                    .eq("branch_id", branch_id)
                    .order("snapshot_date", desc=True)
                    .limit(limit)
                    .execute()
                )
                return list(reversed(r.data or []))
        except Exception:
            return []

    rows = _load_file(tenant_id, branch_id)
    return rows[-limit:]


def compute_review_velocities(tenant_id: str, branches: list) -> dict:
    """
    Return review velocity (new reviews per week) per branch.
    Velocity = latest review_count - review_count from the prior snapshot.
    Result: {"branch_id": velocity_int_or_None, ...}
    """
    velocities: dict = {}
    for b in branches:
        bid = b.get("id", "")
        history = get_snapshot_history(tenant_id, bid, limit=2)
        if len(history) >= 2:
            a = history[-1].get("review_count")
            b_prev = history[-2].get("review_count")
            velocities[bid] = (a - b_prev) if (a is not None and b_prev is not None) else None
        else:
            velocities[bid] = None
    return velocities


def compute_all_health_scores(tenant_id: str, branches_data: list) -> dict:
    """
    Batch-compute composite health scores for all branches.

    Formula (no FeedMe sales data yet):
        health = 55% rating_score + 45% velocity_score

    rating_score: (rating - 3.5) / 1.5 * 100, clamped 0-100
        — maps 3.5 stars → 0, 5.0 stars → 100
    velocity_score: min-max normalised across the chain, mapped 0-100
        — the fastest-growing branch scores 100, slowest 0

    Returns: {"branch_id": score_0_to_100_or_None, ...}
    """
    # Collect velocities for all branches in one pass
    velocities = compute_review_velocities(tenant_id, branches_data)

    # Compute rating scores
    rating_scores: dict = {}
    for b in branches_data:
        bid = b.get("id", "")
        rating = b.get("rating")
        if rating is not None:
            raw = (float(rating) - 3.5) / 1.5 * 100
            rating_scores[bid] = max(0.0, min(100.0, raw))
        else:
            rating_scores[bid] = None

    # Normalise velocities chain-wide
    valid_v = [v for v in velocities.values() if v is not None]
    v_min = min(valid_v) if valid_v else 0
    v_max = max(valid_v) if valid_v else 0
    v_range = v_max - v_min

    velocity_scores: dict = {}
    for bid, vel in velocities.items():
        if vel is None:
            velocity_scores[bid] = None
        elif v_range == 0:
            velocity_scores[bid] = 50.0
        else:
            velocity_scores[bid] = (vel - v_min) / v_range * 100.0

    # Combine
    scores: dict = {}
    for b in branches_data:
        bid = b.get("id", "")
        rs = rating_scores.get(bid)
        vs = velocity_scores.get(bid)
        if rs is None and vs is None:
            scores[bid] = None
        elif rs is None:
            scores[bid] = round(vs)
        elif vs is None:
            scores[bid] = round(rs)
        else:
            scores[bid] = round(0.55 * rs + 0.45 * vs)

    return scores


# ── batch runner ───────────────────────────────────────────────────────────────

def run_daily_snapshot(tenant_id: str, branches: list) -> dict:
    """Snapshot all branches for a tenant. Returns {ok, failed, skipped} lists."""
    if not os.environ.get("GOOGLE_PLACES_KEY"):
        return {"error": "GOOGLE_PLACES_KEY not configured"}

    ok, failed, skipped = [], [], []
    for b in branches:
        bid = b.get("id")
        query = b.get("maps_query")
        if not bid or not query:
            skipped.append(bid or "?")
            continue

        branch_key = f"{tenant_id}:{bid}"
        snap = fetch_branch_snapshot(query, branch_key)
        if snap and snap.get("rating") is not None:
            store_snapshot(tenant_id, bid, snap["rating"], snap.get("review_count"))
            ok.append(bid)
        else:
            failed.append(bid)

        time.sleep(1)

    return {"ok": ok, "failed": failed, "skipped": skipped}
