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
    """Transform raw STATIC_DATA into CEO dashboard summary.

    When tenant_id is provided, live snapshot data (rating, review count, deltas)
    from the Phase 1B snapshot service overlays the static fallback values.
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
    delta_fn = None
    if tenant_id:
        try:
            from snapshot_service import get_latest_snapshot, get_review_delta
            snapshot_fn = get_latest_snapshot
            delta_fn = get_review_delta
        except ImportError:
            pass

    branch_summaries = []
    for b in branches:
        branch_id = b.get("id", "")
        rating = b.get("rating")
        review_count = b.get("review_count", "—")
        review_delta = None

        if tenant_id and snapshot_fn:
            snap = snapshot_fn(tenant_id, branch_id)
            if snap:
                if snap.get("rating") is not None:
                    rating = snap["rating"]
                if snap.get("review_count") is not None:
                    review_count = "{:,}".format(snap["review_count"])
            if delta_fn:
                review_delta = delta_fn(tenant_id, branch_id)

        branch_summaries.append({
            "id": branch_id,
            "name": b.get("name", ""),
            "role": b.get("role", ""),
            "rating": rating,
            "review_count": review_count,
            "review_delta": review_delta,
            "status": classify(rating),
            "watch_areas": b.get("watch_areas") or [],
            "highlights": (b.get("highlights") or [])[:2],
            "maps_query": b.get("maps_query", ""),
        })

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

    ig = sm.get("instagram", {})
    fb = sm.get("facebook", {})

    return {
        "alerts": alerts,
        "stats": {
            "avg_rating": avg_rating,
            "total_reviews": reviews_meta.get("total_google_reviews", "—"),
            "ig_followers": ig.get("followers", 0),
            "fb_likes": fb.get("likes", 0),
            "branch_count": len(branches),
            "branch_alert": len([b for b in branch_summaries if b["status"] == "alert"]),
            "branch_watch": len([b for b in branch_summaries if b["status"] == "watch"]),
            "branch_healthy": len([b for b in branch_summaries if b["status"] in ("excellent", "good")]),
        },
        "branches": branch_summaries,
        "social": {
            "ig_followers": ig.get("followers", 0),
            "ig_handle": ig.get("handle", ""),
            "fb_likes": fb.get("likes", 0),
        },
    }

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

_REQUIRED_ENV_VARS = {
    "FLASK_SECRET_KEY": "Signs session cookies — required for auth to work",
}

_OPTIONAL_ENV_VARS = {
    "ADMIN_TOKEN": "Bearer token for POST /api/competitors/social and /api/snapshot/run — admin endpoints disabled without it",
    "INSTAGRAM_ACCESS_TOKEN": "Live Instagram data — dashboard falls back to static counts without it",
    "FACEBOOK_PAGE_ACCESS_TOKEN": "Live Facebook data — requires FACEBOOK_PAGE_ID too",
    "FACEBOOK_PAGE_ID": "Live Facebook data — requires FACEBOOK_PAGE_ACCESS_TOKEN too",
    "SERPAPI_KEY": "Phase 1B review snapshots — weekly rating/count polling per branch; deltas unavailable without it",
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

        # Merge live social if available
        try:
            live = get_live_social_data(force=False)
            if live and live.get("instagram"):
                data["social_media"]["instagram"]["followers"] = (
                    live["instagram"].get("followers")
                    or data["social_media"]["instagram"]["followers"]
                )
            if live and live.get("facebook"):
                data["social_media"]["facebook"]["likes"] = (
                    live["facebook"].get("likes")
                    or data["social_media"]["facebook"]["likes"]
                )
        except Exception:
            pass

        summary = build_tenant_summary(data, tenant_id=tenant["id"])
        brand_name = data.get("brand", {}).get("name", tenant["name"])

        return render_template(
            "tenant/dashboard.html",
            brand_name=brand_name,
            slug=slug,
            summary=summary,
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

    return app


startup_checks()
app = create_app()


def setup_scheduler(flask_app: Flask):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(daemon=True)

        def daily_refresh():
            with flask_app.app_context():
                print("[scheduler] Running daily data refresh...")
                get_data(force=True)
                print("[scheduler] Daily refresh complete.")

        def social_refresh():
            print("[scheduler] Running social media refresh...")
            get_live_social_data(force=True)
            print("[scheduler] Social refresh complete.")

        def weekly_snapshot():
            print("[scheduler] Running weekly review snapshot...")
            try:
                from auth import _DEV_TENANTS
                from snapshot_service import run_weekly_snapshot
                data = get_data(force=False)
                branches = data.get("branches", [])
                for slug, tenant in _DEV_TENANTS.items():
                    result = run_weekly_snapshot(tenant["id"], branches)
                    print(f"[scheduler] Snapshot {slug}: {result}")
            except Exception as exc:
                print(f"[scheduler] Snapshot error: {exc}")

        scheduler.add_job(daily_refresh, trigger="cron", hour=3, minute=0)
        scheduler.add_job(social_refresh, trigger="cron", hour=3, minute=30)
        scheduler.add_job(social_refresh, trigger="cron", hour=9, minute=0)
        scheduler.add_job(social_refresh, trigger="cron", hour=15, minute=0)
        scheduler.add_job(social_refresh, trigger="cron", hour=21, minute=0)
        # Weekly Sunday 03:15 MYT (= 19:15 UTC Saturday) — after daily_refresh
        scheduler.add_job(weekly_snapshot, trigger="cron", day_of_week="sun", hour=19, minute=15)
        scheduler.start()
        print("[scheduler] Daily refresh at 03:00, social refresh every 6h, review snapshot Sunday 03:15 MYT.")
        return scheduler
    except ImportError:
        print("[scheduler] APScheduler not installed — scheduled refresh disabled.")
        return None


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    scheduler = setup_scheduler(app)
    try:
        app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)
    finally:
        if scheduler:
            scheduler.shutdown()
