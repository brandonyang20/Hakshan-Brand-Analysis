import os
import re
from functools import wraps

from flask import redirect, request, session

SLUG_RE = re.compile(r"^[a-z0-9-]{3,50}$")


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(f"/login?next={request.path}")
        return f(*args, **kwargs)

    return decorated


def require_tenant(slug):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not SLUG_RE.match(slug):
                from flask import abort

                abort(400)
            if session.get("tenant_slug") != slug:
                from flask import abort

                abort(403)
            return f(*args, **kwargs)

        return decorated

    return decorator


def get_supabase_client():
    try:
        from supabase import create_client
    except ImportError:
        return None

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None

    return create_client(url, key)


def get_supabase_admin_client():
    """Service role client — bypasses RLS. Use for all server-side queries."""
    try:
        from supabase import create_client
    except ImportError:
        return None

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None

    return create_client(url, key)


_DEV_TENANTS = {
    "hakshan": {"id": "dev-hakshan", "slug": "hakshan", "name": "客善 Hakshan", "status": "active"},
}


def lookup_tenant(slug):
    # Dev fallback when Supabase not configured
    if not os.environ.get("SUPABASE_URL"):
        return _DEV_TENANTS.get(slug)
    try:
        client = get_supabase_admin_client() or get_supabase_client()
        if client is None:
            return None
        result = client.table("tenants").select("*").eq("slug", slug).single().execute()
        return result.data
    except Exception:
        return None
