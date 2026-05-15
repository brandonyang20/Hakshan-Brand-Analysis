import os
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

from data_fetcher import (
    get_data,
    get_live_social_data,
    load_competitor_social,
    read_analysis_section,
    save_competitor_social,
)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

_REQUIRED_ENV_VARS = {
    "ADMIN_TOKEN": "Bearer token for POST /api/competitors/social — admin endpoint silently disabled without it",
}

_OPTIONAL_ENV_VARS = {
    "INSTAGRAM_ACCESS_TOKEN": "Live Instagram data — dashboard falls back to static counts without it",
    "FACEBOOK_PAGE_ACCESS_TOKEN": "Live Facebook data — requires FACEBOOK_PAGE_ID too",
    "FACEBOOK_PAGE_ID": "Live Facebook data — requires FACEBOOK_PAGE_ACCESS_TOKEN too",
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
    app = Flask(__name__)
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

        scheduler.add_job(daily_refresh, trigger="cron", hour=3, minute=0)
        scheduler.add_job(social_refresh, trigger="cron", hour=3, minute=30)
        scheduler.add_job(social_refresh, trigger="cron", hour=9, minute=0)
        scheduler.add_job(social_refresh, trigger="cron", hour=15, minute=0)
        scheduler.add_job(social_refresh, trigger="cron", hour=21, minute=0)
        scheduler.start()
        print("[scheduler] Daily refresh at 03:00, social refresh every 6h.")
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
