import os
from datetime import datetime, timezone

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from data_fetcher import (
    get_data,
    get_live_social_data,
    load_competitor_social,
    read_analysis_section,
    save_competitor_social,
)


def build_tenant_summary(data: dict, tenant_id: str | None = None) -> dict:
    """Transform raw data into CEO dashboard summary.

    When tenant_id is provided, overlays live snapshot data (ratings, counts,
    health scores, social metrics, and AI digest) from the database.
    """
    branches = data.get("branches", [])
    sm = data.get("social_media", {})
    reviews_meta = data.get("reviews", {})

    def classify(rating):
        if rating is None:
            return "new"
        if rating >= 4.5:
            return "excellent"
        if rating >= 4.2:
            return "good"
        if rating >= 4.0:
            return "watch"
        return "alert"

    status_rank = {"alert": 0, "watch": 1, "good": 2, "excellent": 3, "new": 4}

    snapshot_fn = None
    history_fn = None
    if tenant_id:
        try:
            from snapshot_service import (
                get_latest_snapshot,
                get_snapshot_history,
                compute_all_health_scores,
            )
            snapshot_fn = get_latest_snapshot
            history_fn = get_snapshot_history
        except ImportError:
            pass

    # Build branch list with live data
    branch_summaries = []
    for b in branches:
        branch_id = b.get("id", "")
        rating = b.get("rating")
        review_count_raw = b.get("review_count")
        review_count = "{:,}".format(review_count_raw) if isinstance(review_count_raw, int) else "—"
        review_delta = None

        if tenant_id and snapshot_fn:
            snap = snapshot_fn(tenant_id, branch_id)
            if snap:
                if snap.get("rating") is not None:
                    rating = snap["rating"]
                if snap.get("review_count") is not None:
                    prev_count = snap.get("review_count")
                    review_count = "{:,}".format(prev_count)

        branch_summaries.append({
            "id": branch_id,
            "name": b.get("name", ""),
            "role": b.get("role", ""),
            "rating": rating,
            "review_count": review_count,
            "review_count_raw": review_count_raw,
            "review_delta": review_delta,
            "status": classify(rating),
            "watch_areas": b.get("watch_areas") or [],
            "highlights": (b.get("highlights") or [])[:2],
            "maps_query": b.get("maps_query", ""),
            "health_score": None,
            "sparkline": [],
        })

    # Batch compute health scores (avoids N+1 queries)
    if tenant_id and snapshot_fn:
        try:
            from snapshot_service import compute_all_health_scores, compute_review_velocities
            health_scores = compute_all_health_scores(tenant_id, branch_summaries)
            velocities = compute_review_velocities(tenant_id, branch_summaries)
            for b in branch_summaries:
                bid = b["id"]
                b["health_score"] = health_scores.get(bid)
                b["review_delta"] = velocities.get(bid)
        except Exception:
            pass

    # Attach sparkline history per branch
    if tenant_id and history_fn:
        for b in branch_summaries:
            try:
                rows = history_fn(tenant_id, b["id"], limit=10)
                b["sparkline"] = [
                    {"date": r["snapshot_date"], "count": r.get("review_count")}
                    for r in rows
                ]
            except Exception:
                b["sparkline"] = []

    branch_summaries.sort(key=lambda b: status_rank.get(b["status"], 5))

    alerts = []
    for b in branch_summaries:
        if b["status"] == "alert":
            alerts.append({
                "level": "critical",
                "message": f"{b['name']}: Google rating below 4.0 ★ — immediate attention needed",
            })
        elif b["status"] == "watch":
            alerts.append({
                "level": "warning",
                "message": f"{b['name']}: Rating {b['rating']} ★ — monitoring recommended",
            })

    rated = [b for b in branch_summaries if b["rating"] is not None]
    avg_rating = round(sum(b["rating"] for b in rated) / len(rated), 2) if rated else None

    # Social media: pull from scraper snapshots, fall back to static data
    social_counts = {"instagram": None, "facebook": None, "tiktok": None, "xhs": None}
    if tenant_id:
        try:
            from social_scraper import get_latest_social
            live = get_latest_social(tenant_id)
            social_counts.update({k: v for k, v in live.items() if v is not None})
        except Exception:
            pass

    # Fill static fallbacks for IG/FB when scraper hasn't run yet
    ig = sm.get("instagram", {})
    fb = sm.get("facebook", {})
    if social_counts["instagram"] is None:
        social_counts["instagram"] = ig.get("followers", 0)
    if social_counts["facebook"] is None:
        social_counts["facebook"] = fb.get("likes", 0)

    # AI digest
    digest = None
    if tenant_id:
        try:
            from digest_service import get_latest_digest
            digest = get_latest_digest(tenant_id)
        except Exception:
            pass

    return {
        "alerts": alerts,
        "stats": {
            "avg_rating": avg_rating,
            "total_reviews": reviews_meta.get("total_google_reviews", "—"),
            "branch_count": len(branches),
            "branch_alert": len([b for b in branch_summaries if b["status"] == "alert"]),
            "branch_watch": len([b for b in branch_summaries if b["status"] == "watch"]),
            "branch_healthy": len([b for b in branch_summaries if b["status"] in ("excellent", "good")]),
        },
        "branches": branch_summaries,
        "social": social_counts,
        "digest": digest,
    }

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

_REQUIRED_ENV_VARS = {
    "FLASK_SECRET_KEY": "Signs session cookies — required for auth to work",
}

_OPTIONAL_ENV_VARS = {
    "ADMIN_TOKEN": "Bearer token for POST /api/competitors/social and /api/snapshot/run — admin endpoints disabled without it",
    "SERPAPI_KEY": "Review snapshots — daily rating/count polling per branch",
    "ANTHROPIC_API_KEY": "Weekly AI digest generation — Intelligence section disabled without it",
}

# Future-required vars (add to _REQUIRED_ENV_VARS when each phase ships):
#   FLASK_SECRET_KEY        — Phase 1A: session signing
#   TENANT_SECRET_KEY       — Phase 1A: Fernet token encryption
#   SERPAPI_KEY             — Phase 1B: review snapshot service
#   SUPABASE_URL            — Phase 1A: database
#   SUPABASE_KEY            — Phase 1A: database
#   BILLPLZ_WEBHOOK_SECRET  — Phase 2A: billing
#   TWILIO_AUTH_TOKEN       — Phase 2B: WhatsApp report delivery


def startup_checks() -> None:
    missing = [var for var in _REQUIRED_ENV_VARS if not os.getenv(var)]
    for var in missing:
        print(f"[startup] MISSING required env var: {var} — {_REQUIRED_ENV_VARS[var]}")
    if missing:
        raise RuntimeError(
            f"Cannot start: missing required env vars: {', '.join(missing)}"
        )
    for var, description in _OPTIONAL_ENV_VARS.items():
        if not os.getenv(var):
            print(f"[startup] Optional env var not set: {var} — {description}")


def create_app() -> Flask:
    from auth import SLUG_RE, lookup_tenant

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=2592000,  # 30 days
    )
    os.makedirs(os.path.join(os.path.dirname(__file__), "cache"), exist_ok=True)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/news")
    def news_page():
        return render_template("news.html")

    @app.route("/api/data")
    def api_data():
        try:
            data = get_data(force=False)
            return jsonify(data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/refresh", methods=["POST"])
    def api_refresh():
        try:
            data = get_data(force=True)
            return jsonify(data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/analysis/<section>")
    def api_analysis(section):
        content = read_analysis_section(section)
        if not content:
            return jsonify({"error": "Section not found"}), 404
        return jsonify({"section": section, "content": content})

    @app.route("/api/social/live")
    def api_social_live():
        try:
            data = get_live_social_data(force=False)
            if not data:
                return jsonify({"error": "Social API not configured — set INSTAGRAM_ACCESS_TOKEN"}), 503
            return jsonify(data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/social/refresh", methods=["POST"])
    def api_social_refresh():
        try:
            data = get_live_social_data(force=True)
            if not data:
                return jsonify({"error": "Social API not configured — set INSTAGRAM_ACCESS_TOKEN"}), 503
            return jsonify(data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/competitors/social", methods=["POST"])
    def api_competitors_social():
        auth = request.headers.get("Authorization", "")
        if not ADMIN_TOKEN or auth != f"Bearer {ADMIN_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401
        try:
            updates = request.get_json(force=True)
            if not isinstance(updates, dict):
                return jsonify({"error": "Invalid JSON body"}), 400
            today = datetime.now(timezone.utc).date().isoformat()
            current = load_competitor_social()
            for cid, vals in updates.items():
                if not isinstance(vals, dict):
                    continue
                if cid not in current:
                    current[cid] = {}
                if "ig" in vals:
                    current[cid]["ig"] = int(vals["ig"])
                if "fb" in vals:
                    current[cid]["fb"] = int(vals["fb"])
                current[cid]["updated_at"] = today
            save_competitor_social(current)
            return jsonify({"ok": True, "updated": current})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/snapshot/run", methods=["POST"])
    def api_snapshot_run():
        auth = request.headers.get("Authorization", "")
        if not ADMIN_TOKEN or auth != f"Bearer {ADMIN_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401
        slug = request.args.get("tenant", "hakshan")
        if not SLUG_RE.match(slug):
            return jsonify({"error": "Invalid slug"}), 400
        tenant = lookup_tenant(slug)
        if tenant is None:
            return jsonify({"error": "Tenant not found"}), 404
        try:
            from snapshot_service import run_weekly_snapshot
            data = get_data(force=False)
            branches = data.get("branches", [])
            result = run_weekly_snapshot(tenant["id"], branches)
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/t/<slug>/dashboard")
    def tenant_dashboard(slug):
        if not SLUG_RE.match(slug):
            return jsonify({"error": "Invalid tenant slug"}), 400

        dev_mode = not os.environ.get("SUPABASE_URL")

        if dev_mode:
            # Dev fallback: serve Hakshan data without auth when Supabase not configured
            tenant = {"id": f"dev-{slug}", "name": slug.title(), "slug": slug}
        else:
            tenant = lookup_tenant(slug)
            if tenant is None:
                return render_template("404.html"), 404
            if not session.get("user_id"):
                return redirect(f"/login?next=/t/{slug}/dashboard")
            if session.get("tenant_id") != tenant["id"]:
                return jsonify({"error": "Forbidden"}), 403

        data = get_data(force=False)
        summary = build_tenant_summary(data, tenant_id=tenant["id"])
        brand_name = data.get("brand", {}).get("name", tenant["name"])

        # Social history for sparkline charts (last 8 weeks per platform)
        social_history: dict = {}
        try:
            from social_scraper import get_social_history
            for platform in ("instagram", "facebook", "tiktok", "xhs"):
                rows = get_social_history(tenant["id"], platform, limit=8)
                if rows:
                    social_history[platform] = rows
        except Exception:
            pass

        return render_template(
            "tenant/dashboard.html",
            brand_name=brand_name,
            slug=slug,
            summary=summary,
            social_history=social_history,
            dev_mode=dev_mode,
            now=datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
        )

    @app.route("/login", methods=["GET"])
    def login_page():
        return render_template("login.html")

    @app.route("/login", methods=["POST"])
    def login_submit():
        flash("Magic link sent — check your email.")
        return redirect(url_for("login_page"))

    @app.route("/auth/magic")
    def auth_magic():
        # Stub: token validation not yet implemented
        flash("Invalid or expired link.")
        return redirect(url_for("login_page"))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect("/")

    _setup_scheduler(app)
    return app


def _setup_scheduler(flask_app: Flask) -> None:
    """Start APScheduler with a SQLite persistent jobstore.

    Called inside create_app() so it runs under both Gunicorn and direct
    execution. SQLite jobstore survives process crashes within a deployment;
    replace_existing=True handles disk wipe on Railway redeploy.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        # Memory jobstore: closures can't be pickled for SQLAlchemy jobstore.
        # Jobs are re-registered on every startup (inside create_app), so
        # replace_existing=True handles duplicate IDs across Gunicorn worker restarts.
        scheduler = BackgroundScheduler(daemon=True)

        # ── job definitions ────────────────────────────────────────────────

        def daily_refresh():
            with flask_app.app_context():
                print("[scheduler] Running daily data refresh...")
                get_data(force=True)
                print("[scheduler] Daily refresh complete.")

        def daily_snapshot():
            """Daily review snapshot for all active tenants — 04:00 MYT (20:00 UTC)."""
            print("[scheduler] Running daily review snapshot...")
            try:
                from auth import _DEV_TENANTS
                from snapshot_service import run_daily_snapshot
                data = get_data(force=False)
                branches = data.get("branches", [])
                for slug, tenant in _DEV_TENANTS.items():
                    result = run_daily_snapshot(tenant["id"], branches)
                    print(f"[scheduler] Snapshot {slug}: {result}")
            except Exception as exc:
                print(f"[scheduler] Snapshot error: {exc}")

        def weekly_social_scrape():
            """Weekly social media follower scrape — Monday 05:00 MYT (21:00 UTC Sunday)."""
            print("[scheduler] Running weekly social media scrape...")
            try:
                from auth import _DEV_TENANTS
                from social_scraper import (
                    get_tenant_social_handles,
                    run_scrape,
                    store_social_snapshot,
                )
                for slug, tenant in _DEV_TENANTS.items():
                    handles = get_tenant_social_handles(tenant["id"])
                    if not any(handles.values()):
                        print(f"[scheduler] {slug}: no social handles configured, skipping")
                        continue
                    results = run_scrape(handles)
                    for platform, data in results.items():
                        store_social_snapshot(tenant["id"], platform, data)
                        status = "ok" if data else "failed"
                        print(f"[scheduler] {slug} {platform}: {status}")
            except Exception as exc:
                print(f"[scheduler] Social scrape error: {exc}")

        def weekly_digest():
            """Weekly AI digest — Monday 05:30 MYT (21:30 UTC Sunday)."""
            print("[scheduler] Running weekly digest generation...")
            try:
                from auth import _DEV_TENANTS
                from digest_service import build_intelligence_digest
                from social_scraper import get_latest_social
                data = get_data(force=False)
                branches_raw = data.get("branches", [])
                brand_name = data.get("brand", {}).get("name", "Brand")
                for slug, tenant in _DEV_TENANTS.items():
                    tid = tenant["id"]
                    social = get_latest_social(tid)
                    # Build branches_data for the prompt
                    from snapshot_service import compute_all_health_scores, compute_review_velocities
                    health = compute_all_health_scores(tid, branches_raw)
                    vel = compute_review_velocities(tid, branches_raw)
                    branches_data = [
                        {
                            "branch_name": b.get("name", ""),
                            "rating": b.get("rating"),
                            "review_count": b.get("review_count"),
                            "review_delta": vel.get(b.get("id", "")),
                            "health_score": health.get(b.get("id", "")),
                        }
                        for b in branches_raw
                    ]
                    text = build_intelligence_digest(tid, brand_name, branches_data, social)
                    if text:
                        print(f"[scheduler] Digest {slug}: generated ({len(text)} chars)")
                    else:
                        print(f"[scheduler] Digest {slug}: skipped (no API key or error)")
            except Exception as exc:
                print(f"[scheduler] Digest error: {exc}")

        # ── schedule ───────────────────────────────────────────────────────
        kw = {"replace_existing": True, "misfire_grace_time": 3600}

        # 03:00 UTC daily — general data cache refresh
        scheduler.add_job(daily_refresh, "cron", id="daily_refresh", hour=3, minute=0, **kw)
        # 20:00 UTC daily (04:00 MYT) — review snapshots
        scheduler.add_job(daily_snapshot, "cron", id="daily_snapshot", hour=20, minute=0, **kw)
        # 21:00 UTC Sunday (05:00 MYT Monday) — social scrape
        scheduler.add_job(weekly_social_scrape, "cron", id="weekly_social_scrape",
                          day_of_week="sun", hour=21, minute=0, **kw)
        # 21:30 UTC Sunday (05:30 MYT Monday) — digest (after social data is fresh)
        scheduler.add_job(weekly_digest, "cron", id="weekly_digest",
                          day_of_week="sun", hour=21, minute=30, **kw)

        scheduler.start()
        print(
            "[scheduler] Started — "
            "daily_refresh 03:00 UTC | daily_snapshot 20:00 UTC | "
            "social_scrape Sun 21:00 UTC | digest Sun 21:30 UTC"
        )
    except ImportError as exc:
        print(f"[scheduler] APScheduler not available — scheduled jobs disabled: {exc}")


startup_checks()
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)
