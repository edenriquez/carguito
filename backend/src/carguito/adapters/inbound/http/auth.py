from __future__ import annotations

from uuid import UUID

import jwt
from flask import current_app, g, request

from ....config.container import Container


class AuthError(Exception):
    status_code = 401


def get_container() -> Container:
    return current_app.extensions["container"]


def current_user_id() -> UUID:
    """Resolve the authenticated user from the request.

    In dev (``AUTH_DISABLED=true``) returns the configured dev user. Otherwise
    verifies the Supabase JWT from the ``Authorization: Bearer`` header.
    """
    if "user_id" in g:
        return g.user_id

    settings = get_container().settings
    if settings.auth_disabled:
        g.user_id = UUID(settings.dev_user_id)
        return g.user_id

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthError("Missing bearer token")
    token = header[len("Bearer ") :].strip()

    if not settings.supabase_jwt_secret:
        raise AuthError("Server is missing SUPABASE_JWT_SECRET")
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise AuthError("Token missing subject")
    g.user_id = UUID(sub)
    return g.user_id
