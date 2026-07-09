import bcrypt
from fastapi import Request
from fastapi.responses import RedirectResponse

import config


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def set_session(request: Request, user_id, role: str, display_name: str, class_tag: str = ""):
    request.session["user"] = {
        "user_id": user_id,
        "role": role,
        "display_name": display_name,
        "class_tag": class_tag,
    }


def get_session_user(request: Request) -> dict | None:
    return request.session.get("user")


def clear_session(request: Request):
    request.session.clear()


def redirect_if_not_admin(request: Request):
    """Return a redirect response if the requester is not admin, else None."""
    user = get_session_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse("/login", status_code=302)
    return None


def redirect_if_not_authenticated(request: Request):
    """Return a redirect response if the requester is not logged in, else None."""
    user = get_session_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return None
