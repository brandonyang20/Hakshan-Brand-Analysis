import os
import re
from functools import wraps

from flask import redirect, request, session


# ── Fernet token encryption ────────────────────────────────────────────────────

def _get_fernet():
    key = os.environ.get("TENANT_SECRET_KEY", "")
    if not key:
        raise RuntimeError("TENANT_SECRET_KEY not set — cannot encrypt/decrypt tokens")
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def encrypt_token(plaintext: str) -> str:
    """Fernet-encrypt a token. Returns base64 string safe for DB storage."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted token. Raises InvalidToken on tamper/wrong key."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def get_tenant_social_tokens(tenant_id: str) -> dict:
    """
    Load + decrypt social tokens from tenant_config.
    Returns {"instagram": token, "facebook_token": token, "facebook_page_id": id}
    Returns {} on any error — never raises, never logs token values.
    """
    try:
        client = get_supabase_admin_client()
        if not client:
            return {}
        r = (
            client.table("tenant_config")
            .select("instagram_token_enc,facebook_token_enc,facebook_page_id")
            .eq("tenant_id", tenant_id)
            .single()
            .execute()
        )
        row = r.data or {}
        result = {}
        if row.get("instagram_token_enc"):
            try:
                result["instagram"] = decrypt_token(row["instagram_token_enc"])
            except Exception:
                print(f"[auth] Failed to decrypt instagram token for tenant {tenant_id}")
        if row.get("facebook_token_enc"):
            try:
                result["facebook_token"] = decrypt_token(row["facebook_token_enc"])
                result["facebook_page_id"] = row.get("facebook_page_id", "")
            except Exception:
                print(f"[auth] Failed to decrypt facebook token for tenant {tenant_id}")
        return result
    except Exception:
        return {}

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
