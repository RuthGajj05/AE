"""Sign-in for business owners (Supabase Auth, email + password).

The frontend signs in with Supabase and sends the access token as `Authorization: Bearer <token>`. This module
asks Supabase who the token belongs to (GET /auth/v1/user), so it works with any of the project's key formats
without holding a JWT secret. Answers are cached for a minute.

Auth is on whenever Supabase is configured (SUPABASE_URL plus a key) and AUTH_DISABLED isn't 1. With it off
(local tests, offline demos) every request is anonymous and nothing is gated. Browsing (spots, cuisines, the
consumer feed) never needs a sign-in; business endpoints do, and only the business's owner gets its data.
"""

import os
import threading
import time

import httpx
from fastapi import Header, HTTPException

import config

CACHE_SECS = 60
_cache: dict[str, tuple[float, dict | None]] = {}
_lock = threading.Lock()


def _key() -> str | None:
    # Any project key can authorize the lookup; the user's own token decides who they are.
    for name in ("SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        if config.has_key(name):
            return os.environ[name].strip()
    return None


def enabled() -> bool:
    return os.getenv("AUTH_DISABLED") != "1" and config.has_key("SUPABASE_URL") and _key() is not None


def user_from_token(token: str) -> dict | None:
    """{"id", "email"} for a valid access token, None for an invalid or expired one."""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(token)
        if hit and hit[0] > now:
            return hit[1]
    try:
        resp = httpx.get(
            f"{os.environ['SUPABASE_URL'].rstrip('/')}/auth/v1/user",
            headers={"apikey": _key(), "Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "We couldn't check your sign-in right now. Please try again in a minute.")
    if resp.status_code in (401, 403):
        user = None
    elif resp.is_success:
        data = resp.json()
        user = {"id": data["id"], "email": data.get("email")}
    else:
        raise HTTPException(503, "We couldn't check your sign-in right now. Please try again in a minute.")
    with _lock:
        _cache[token] = (now + CACHE_SECS, user)
        if len(_cache) > 5000:  # keep the cache small; entries refill on demand
            _cache.clear()
    return user


def current_user(authorization: str | None = Header(None)) -> dict | None:
    """FastAPI dependency: the signed-in user, or None (signed out, or auth off)."""
    if not enabled() or not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    return user_from_token(token) if token else None


def require_user(user: dict | None) -> dict | None:
    """Raise 401 when auth is on and nobody is signed in. With auth off, returns None and lets the request through."""
    if enabled() and user is None:
        raise HTTPException(401, "Please sign in to manage your spot.")
    return user


def check_owner(business: dict | None, user: dict | None) -> dict:
    """The business, if this user may see it. Demo businesses are open to everyone; with auth off, so is everything.
    Someone else's business answers 404, the same as a missing one, so ids can't be probed."""
    missing = HTTPException(404, "We couldn't find that business. Try onboarding it again.")
    if business is None:
        raise missing
    if business["demo"] or not enabled():
        return business
    require_user(user)
    if business.get("owner_user_id") != user["id"]:
        raise missing
    if not business.get("owner_email") and user.get("email"):
        # Spots set up before owner emails were recorded get the owner's sign-in email the next time they use it.
        import store
        store.update_business(business["id"], owner_email=user["email"])
        business = {**business, "owner_email": user["email"]}
    return business
