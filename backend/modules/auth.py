import os
from typing import Any

from flask import current_app, request, jsonify
import jwt


class AuthError(Exception):
    pass


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET") or current_app.config.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT secret is not configured. Set JWT_SECRET in environment or app config.")
    return secret


def create_jwt(payload: dict[str, Any], exp_seconds: int = 3600) -> str:
    to_encode = {**payload}
    return jwt.encode(to_encode, _jwt_secret(), algorithm="HS256")


def decode_jwt(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except Exception as exc:
        raise AuthError(str(exc)) from exc


def require_auth(role: str | None = None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return jsonify({"error": "Missing or invalid Authorization header"}), 401
            token = auth[len("Bearer "):]
            try:
                payload = decode_jwt(token)
            except AuthError:
                return jsonify({"error": "Invalid token"}), 401
            user_role = payload.get("role")
            if role and user_role != role and not (role == "engineer" and user_role == "admin"):
                return jsonify({"error": "Forbidden"}), 403
            request.environ["auth.user"] = payload.get("email")
            request.environ["auth.role"] = user_role
            return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        return wrapper

    return decorator
