import json
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
    "GOOGLE_PLACES_KEY": "Review snapshots — daily rating/count polling per branch via Google Places API",
    "ANTHROPIC_API_KEY": "Weekly AI digest generation — Intelligence section disabled without it",
    "TENANT_SECRET_KEY": "Fernet key for encrypting OAuth tokens in DB — generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"",
    "INSTAGRAM_ACCESS_TOKEN": "Instagram Graph API long-lived token — follower count via official API instead of Playwright",
    "FACEBOOK_PAGE_ACCESS_TOKEN": "Facebook Graph API page token — page like count via official API instead of Playwright",
    "FACEBOOK_PAGE_ID": "Numeric Facebook page ID (e.g. 123456789) — required with FACEBOOK_PAGE_ACCESS_TOKEN",
    "FACEBOOK_APP_ID": "Facebook App ID — required for Phase 2 multi-tenant OAuth connect flow",
    "FACEBOOK_APP_SECRET": "Facebook App Secret — required for Phase 2 OAuth token exchange (keep secret, never log)",
    "APP_BASE_URL": "Public base URL for OAuth callbacks (e.g. https://hakshan-brand-analysis-production.up.railway.app)",
}

# Future-required vars (add to _REQUIRED_ENV_VARS when each phase ships):
#   FLASK_SECRET_KEY        — Phase 1A: session signing
#   TENANT_SECRET_KEY       — Phase 1A: Fernet token encryption
#   GOOGLE_PLACES_KEY       — Phase 1B: review snapshot service (Google Places API)
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

    @app.route("/t/<slug>/social/run", methods=["POST"])
    def tenant_social_run(slug):
        if not SLUG_RE.match(slug):
            return jsonify({"error": "Invalid slug"}), 400
        if not session.get("user_id"):
            return jsonify({"error": "Unauthorized"}), 401
        if session.get("tenant_slug") != slug:
            return jsonify({"error": "Forbidden"}), 403
        tenant = lookup_tenant(slug)
        if tenant is None:
            return jsonify({"error": "Tenant not found"}), 404
        try:
            from social_scraper import get_tenant_api_tokens, get_tenant_social_handles, run_scrape, store_social_snapshot
            handles = get_tenant_social_handles(tenant["id"])
            api_tokens = get_tenant_api_tokens(tenant["id"])
            results = run_scrape(handles, api_tokens=api_tokens)
            for platform, data in results.items():
                store_social_snapshot(tenant["id"], platform, data)
            return jsonify({"ok": list(results.keys()), "results": {
                p: {"followers": d.get("followers")} if d else {"error": "scrape_failed"}
                for p, d in results.items()
            }})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/t/<slug>/snapshot/run", methods=["POST"])
    def tenant_snapshot_run(slug):
        from auth import require_auth, require_tenant
        if not SLUG_RE.match(slug):
            return jsonify({"error": "Invalid slug"}), 400
        if not session.get("user_id"):
            return jsonify({"error": "Unauthorized"}), 401
        if session.get("tenant_slug") != slug:
            return jsonify({"error": "Forbidden"}), 403
        tenant = lookup_tenant(slug)
        if tenant is None:
            return jsonify({"error": "Tenant not found"}), 404
        try:
            from snapshot_service import run_daily_snapshot
            data = get_data(force=False)
            branches = data.get("branches", [])
            result = run_daily_snapshot(tenant["id"], branches)
            return jsonify(result)
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
            from snapshot_service import run_daily_snapshot
            data = get_data(force=False)
            branches = data.get("branches", [])
            result = run_daily_snapshot(tenant["id"], branches)
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Social account settings + OAuth ───────────────────────────────────────

    @app.route("/t/<slug>/settings/social")
    def tenant_settings_social(slug):
        if not SLUG_RE.match(slug):
            return jsonify({"error": "Invalid slug"}), 400
        if not session.get("user_id"):
            return redirect(f"/login?next=/t/{slug}/settings/social")
        if session.get("tenant_slug") != slug:
            return jsonify({"error": "Forbidden"}), 403
        tenant = lookup_tenant(slug)
        if tenant is None:
            return render_template("404.html"), 404

        # Check which platforms are connected
        has_instagram = False
        has_facebook = False
        if os.environ.get("SUPABASE_URL"):
            try:
                from auth import get_supabase_admin_client
                client = get_supabase_admin_client()
                if client:
                    r = (
                        client.table("tenant_config")
                        .select("instagram_token_enc,facebook_token_enc")
                        .eq("tenant_id", tenant["id"])
                        .single()
                        .execute()
                    )
                    row = r.data or {}
                    has_instagram = bool(row.get("instagram_token_enc"))
                    has_facebook = bool(row.get("facebook_token_enc"))
            except Exception:
                pass
        else:
            # Dev: if env vars are set, show as connected
            has_instagram = bool(os.environ.get("INSTAGRAM_ACCESS_TOKEN"))
            has_facebook = bool(os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN"))

        connected = request.args.get("connected") == "true"
        disconnected = request.args.get("disconnected") == "true"
        fb_app_id = os.environ.get("FACEBOOK_APP_ID", "")

        return render_template(
            "tenant/settings_social.html",
            slug=slug,
            brand_name=tenant.get("name", slug.title()),
            has_instagram=has_instagram,
            has_facebook=has_facebook,
            connected=connected,
            disconnected=disconnected,
            fb_app_id=fb_app_id,
        )

    @app.route("/t/<slug>/settings/social/connect")
    def tenant_social_connect(slug):
        """Initiate Facebook OAuth flow."""
        import hashlib
        import hmac as hmac_mod
        import time
        import urllib.parse

        if not SLUG_RE.match(slug):
            return jsonify({"error": "Invalid slug"}), 400
        if not session.get("user_id"):
            return redirect(f"/login?next=/t/{slug}/settings/social")
        if session.get("tenant_slug") != slug:
            return jsonify({"error": "Forbidden"}), 403

        fb_app_id = os.environ.get("FACEBOOK_APP_ID", "")
        app_base_url = os.environ.get("APP_BASE_URL", request.host_url.rstrip("/"))
        if not fb_app_id:
            flash("Facebook App not configured — set FACEBOOK_APP_ID.")
            return redirect(f"/t/{slug}/settings/social")

        # CSRF state: hmac(user_id + tenant_slug + timestamp) using Flask secret
        ts = str(int(time.time()))
        raw = f"{session['user_id']}:{slug}:{ts}"
        state = hmac_mod.new(
            app.secret_key.encode(),
            raw.encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
        session["oauth_state"] = state
        session["oauth_ts"] = ts
        session["oauth_slug"] = slug

        redirect_uri = f"{app_base_url}/auth/facebook/callback"
        params = urllib.parse.urlencode({
            "client_id": fb_app_id,
            "redirect_uri": redirect_uri,
            "scope": "pages_show_list,pages_read_engagement,instagram_basic,instagram_manage_insights",
            "state": state,
            "response_type": "code",
        })
        return redirect(f"https://www.facebook.com/v19.0/dialog/oauth?{params}")

    @app.route("/auth/facebook/callback")
    def facebook_oauth_callback():
        """Handle Facebook OAuth callback — exchange code for long-lived token."""
        import hashlib
        import hmac as hmac_mod
        import urllib.parse
        import urllib.request as urllib_req

        code = request.args.get("code", "")
        state = request.args.get("state", "")
        error = request.args.get("error", "")

        slug = session.pop("oauth_slug", None)
        expected_state = session.pop("oauth_state", None)
        session.pop("oauth_ts", None)

        if not slug or not SLUG_RE.match(slug):
            flash("OAuth session expired. Please try again.")
            return redirect("/")

        settings_url = f"/t/{slug}/settings/social"

        if error:
            flash("Facebook authorization was cancelled or denied.")
            return redirect(settings_url)

        # Validate CSRF state (constant-time compare)
        if not expected_state or not hmac_mod.compare_digest(state, expected_state):
            flash("Invalid OAuth state — possible CSRF. Please try again.")
            return redirect(settings_url)

        tenant = lookup_tenant(slug)
        if not tenant:
            return render_template("404.html"), 404

        fb_app_id = os.environ.get("FACEBOOK_APP_ID", "")
        fb_app_secret = os.environ.get("FACEBOOK_APP_SECRET", "")
        app_base_url = os.environ.get("APP_BASE_URL", request.host_url.rstrip("/"))

        if not fb_app_id or not fb_app_secret:
            flash("Facebook App not configured on server.")
            return redirect(settings_url)

        redirect_uri = f"{app_base_url}/auth/facebook/callback"

        try:
            def _get_json(url: str) -> dict:
                req = urllib_req.Request(url, headers={"User-Agent": "BrandPulse/1.0"})
                with urllib_req.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read())

            # 1. Exchange code for short-lived token
            params = urllib.parse.urlencode({
                "client_id": fb_app_id,
                "redirect_uri": redirect_uri,
                "client_secret": fb_app_secret,
                "code": code,
            })
            token_data = _get_json(f"https://graph.facebook.com/v19.0/oauth/access_token?{params}")
            if "error" in token_data:
                flash("Failed to connect Facebook account. Please try again.")
                return redirect(settings_url)
            short_token = token_data.get("access_token", "")

            # 2. Exchange for 60-day long-lived token
            ll_params = urllib.parse.urlencode({
                "grant_type": "fb_exchange_token",
                "client_id": fb_app_id,
                "client_secret": fb_app_secret,
                "fb_exchange_token": short_token,
            })
            ll_data = _get_json(f"https://graph.facebook.com/v19.0/oauth/access_token?{ll_params}")
            if "error" in ll_data:
                flash("Failed to get long-lived token. Please try again.")
                return redirect(settings_url)
            long_token = ll_data.get("access_token", "")

            # 3. List pages the user manages
            pages_data = _get_json(
                f"https://graph.facebook.com/v19.0/me/accounts"
                f"?access_token={urllib.parse.quote(long_token)}"
            )
            pages = pages_data.get("data", [])
            page_token = ""
            page_id = ""
            if pages:
                # Use first page (most tenants have one page)
                page_token = pages[0].get("access_token", "")
                page_id = pages[0].get("id", "")

            # 4. Encrypt and store
            from auth import encrypt_token, get_supabase_admin_client
            enc_ig = encrypt_token(long_token)
            enc_fb = encrypt_token(page_token) if page_token else None

            client = get_supabase_admin_client()
            if client:
                update = {
                    "instagram_token_enc": enc_ig,
                    "facebook_page_id": page_id,
                }
                if enc_fb:
                    update["facebook_token_enc"] = enc_fb
                client.table("tenant_config").upsert(
                    {"tenant_id": tenant["id"], **update}
                ).execute()

            return redirect(f"{settings_url}?connected=true")

        except Exception:
            flash("An error occurred connecting your account. Please try again.")
            return redirect(settings_url)

    @app.route("/t/<slug>/settings/social/disconnect", methods=["POST"])
    def tenant_social_disconnect(slug):
        """Remove stored social tokens for this tenant."""
        if not SLUG_RE.match(slug):
            return jsonify({"error": "Invalid slug"}), 400
        if not session.get("user_id"):
            return jsonify({"error": "Unauthorized"}), 401
        if session.get("tenant_slug") != slug:
            return jsonify({"error": "Forbidden"}), 403
        tenant = lookup_tenant(slug)
        if tenant is None:
            return jsonify({"error": "Tenant not found"}), 404
        try:
            from auth import get_supabase_admin_client
            client = get_supabase_admin_client()
            if client:
                client.table("tenant_config").update({
                    "instagram_token_enc": None,
                    "facebook_token_enc": None,
                    "facebook_page_id": None,
                }).eq("tenant_id", tenant["id"]).execute()
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        return redirect(f"/t/{slug}/settings/social?disconnected=true")

    # ── Dashboard ──────────────────────────────────────────────────────────────

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
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        next_url = request.args.get("next", "")

        if not email or not password:
            flash("Email and password are required.")
            return redirect(url_for("login_page"))

        try:
            from auth import get_supabase_client
            client = get_supabase_client()
            if not client:
                flash("Auth not configured — SUPABASE_URL missing.")
                return redirect(url_for("login_page"))

            result = client.auth.sign_in_with_password({"email": email, "password": password})
            user = result.user
            if not user:
                flash("Invalid email or password.")
                return redirect(url_for("login_page"))

            # Look up which tenant this user belongs to
            tu = (
                client.table("tenant_users")
                .select("tenant_id")
                .eq("id", user.id)
                .single()
                .execute()
            )
            if not tu.data:
                flash("No tenant linked to this account — contact your administrator.")
                return redirect(url_for("login_page"))

            tenant_id = tu.data["tenant_id"]
            tenant_row = (
                client.table("tenants")
                .select("slug")
                .eq("id", tenant_id)
                .single()
                .execute()
            )
            tenant_slug = tenant_row.data["slug"] if tenant_row.data else ""

            session["user_id"] = user.id
            session["tenant_id"] = tenant_id
            session["tenant_slug"] = tenant_slug
            session.permanent = True

            dest = next_url if next_url and next_url.startswith("/") else f"/t/{tenant_slug}/dashboard"
            return redirect(dest)

        except Exception as exc:
            print(f"[login] Auth error: {exc}")
            flash("Incorrect email or password.")
            return redirect(url_for("login_page") + (f"?next={next_url}" if next_url else ""))

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
                    get_tenant_api_tokens,
                    get_tenant_social_handles,
                    run_scrape,
                    store_social_snapshot,
                )
                for slug, tenant in _DEV_TENANTS.items():
                    handles = get_tenant_social_handles(tenant["id"])
                    if not any(handles.values()):
                        print(f"[scheduler] {slug}: no social handles configured, skipping")
                        continue
                    api_tokens = get_tenant_api_tokens(tenant["id"])
                    results = run_scrape(handles, api_tokens=api_tokens)
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

        def monthly_token_refresh():
            """Refresh Instagram long-lived tokens before 60-day expiry — 1st of month 06:00 UTC."""
            print("[scheduler] Running monthly Instagram token refresh...")
            try:
                import urllib.parse
                import urllib.request as urllib_req
                from auth import _DEV_TENANTS, decrypt_token, encrypt_token, get_supabase_admin_client, get_tenant_social_tokens
                client = get_supabase_admin_client()
                if not client:
                    return
                # Find all tenants with instagram_token_enc set
                rows = client.table("tenant_config").select("tenant_id,instagram_token_enc").execute()
                for row in (rows.data or []):
                    tid = row.get("tenant_id", "")
                    enc = row.get("instagram_token_enc")
                    if not enc:
                        continue
                    try:
                        token = decrypt_token(enc)
                        params = urllib.parse.urlencode({
                            "grant_type": "ig_refresh_token",
                            "access_token": token,
                        })
                        req = urllib_req.Request(
                            f"https://graph.instagram.com/refresh_access_token?{params}",
                            headers={"User-Agent": "BrandPulse/1.0"},
                        )
                        with urllib_req.urlopen(req, timeout=10) as resp:
                            data = json.loads(resp.read())
                        new_token = data.get("access_token", "")
                        if new_token:
                            client.table("tenant_config").update({
                                "instagram_token_enc": encrypt_token(new_token)
                            }).eq("tenant_id", tid).execute()
                            print(f"[scheduler] Token refreshed for tenant {tid}")
                        else:
                            print(f"[scheduler] Token refresh returned no token for tenant {tid}")
                    except Exception as exc:
                        print(f"[scheduler] Token refresh error for tenant {tid}: {type(exc).__name__}")
            except Exception as exc:
                print(f"[scheduler] Monthly token refresh error: {exc}")

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
        # 06:00 UTC on 1st of month — refresh Instagram long-lived tokens (expire after 60 days)
        scheduler.add_job(monthly_token_refresh, "cron", id="monthly_token_refresh",
                          day=1, hour=6, minute=0, **kw)

        scheduler.start()
        print(
            "[scheduler] Started — "
            "daily_refresh 03:00 UTC | daily_snapshot 20:00 UTC | "
            "social_scrape Sun 21:00 UTC | digest Sun 21:30 UTC | "
            "token_refresh 1st-of-month 06:00 UTC"
        )
    except ImportError as exc:
        print(f"[scheduler] APScheduler not available — scheduled jobs disabled: {exc}")


startup_checks()
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)
