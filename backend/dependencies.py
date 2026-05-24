# backend/dependencies.py
# ─────────────────────────────────────────────────────────────────────────────
# FastAPI "dependency" functions — reusable building blocks that get injected
# into route handlers via `Depends(...)`.
#
# FastAPI calls these functions automatically before running a route handler.
# If a dependency raises an HTTPException, the route handler never runs at all —
# FastAPI sends the error response immediately.
#
# This file provides three things:
#   1. get_db()              — yields a database session for one request
#   2. get_current_user()    — strict auth: raises 401 if token is missing/bad
#   3. get_optional_user()   — soft auth: returns None instead of raising 401
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import SessionLocal
from backend.models import User


# ── 1. Database session dependency ───────────────────────────────────────────

def get_db():
    """
    Opens a SQLAlchemy database session and yields it to the route handler.

    The `yield` turns this into a generator — FastAPI runs the code BEFORE
    the yield to set up, and the code AFTER the yield to tear down.

    The `finally` block guarantees the session is always closed, even if
    an exception is raised during the request. Unclosed sessions hold
    database connections open, which wastes resources.

    Usage in a route:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            items = db.query(Item).all()
    """
    db = SessionLocal()  # open a new session from the connection pool
    try:
        yield db          # hand the session to the route handler
    finally:
        db.close()        # always close it after the response is sent


# ── 2. Bearer token extractor ─────────────────────────────────────────────────

# HTTPBearer reads the "Authorization: Bearer <token>" header and exposes
# the token string. In the Swagger /docs UI it shows a simple "Value" field
# where you paste your JWT — much friendlier than the OAuth2 username/password form.
#
# auto_error=True  → raises 401 automatically when header is missing (strict auth)
# auto_error=False → returns None when header is missing (optional auth for guests)
bearer_scheme = HTTPBearer(auto_error=True)
bearer_scheme_optional = HTTPBearer(auto_error=False)


# ── Internal helper: decode a JWT and return the user_id ─────────────────────

def _decode_token(token: str) -> int:
    """
    Validates and decodes a JWT, returning the user's ID from the `sub` claim.

    A JWT has three parts separated by dots: header.payload.signature
    - Header: algorithm info (e.g. HS256)
    - Payload: claims (sub, exp, etc.) — NOT secret, just base64
    - Signature: HMAC of header+payload using our SECRET_KEY

    `jwt.decode` verifies the signature AND checks expiry automatically.
    If either check fails, it raises a JWTError, which we catch below.
    """
    try:
        # Decode the token using our secret key and expected algorithm.
        # If the signature is wrong or the token is expired, JWTError is raised.
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],  # only HS256 is accepted
        )

        # `sub` (subject) is the standard JWT claim for "who this token belongs to".
        # We store the user's id as a string inside `sub` when creating the token.
        user_id_str: str | None = payload.get("sub")

        if user_id_str is None:
            # A valid JWT but with no `sub` claim — shouldn't happen in practice,
            # but we handle it defensively.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject claim.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return int(user_id_str)  # convert "42" → 42

    except JWTError:
        # JWTError covers: expired tokens, bad signatures, malformed tokens.
        # We give one generic error message so attackers get no hints.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials — please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── 3. Strict auth dependency ─────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Strict authentication dependency. Use this on routes that REQUIRE login.

    Examples of protected routes:
        - POST /items        (only logged-in users can post items)
        - DELETE /items/{id} (only the owner can delete their item)
        - GET /dashboard     (registered-user feature only)

    Flow:
        1. HTTPBearer reads the "Authorization: Bearer <token>" header.
           If missing → raises 401 before we even run.
        2. We extract the raw token string from credentials.credentials.
        3. We decode the JWT to get the user_id.
        4. We fetch the user from the DB and return them to the route handler.

    Usage in a route:
        @router.get("/dashboard")
        def dashboard(user: User = Depends(get_current_user)):
            return user.items
    """
    # credentials.credentials holds just the raw token string
    # (HTTPBearer strips the "Bearer " prefix automatically)
    token = credentials.credentials

    # Decode the JWT and extract user_id
    user_id = _decode_token(token)

    # Look up the user in the database
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        # Token was valid, but the user account was deleted after the token was issued.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user  # FastAPI injects this User object into the route handler


# ── 4. Optional auth dependency ───────────────────────────────────────────────

def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """
    Soft authentication dependency. Use this on PUBLIC routes that work for
    both guests and logged-in users.

    Examples:
        - GET /items          (guests can browse, logged-in users see extra info)
        - GET /items/{id}     (anyone can view an item)
        - POST /items/{id}/messages (anyone can message, but we track who)

    Returns the User if a valid token is present, or None for guests.
    NEVER raises 401 — guest access is a first-class feature in this app.

    Usage in a route:
        @router.get("/items")
        def browse(user: User | None = Depends(get_optional_user)):
            if user:
                # personalize response for logged-in user
            else:
                # standard guest response
    """
    if credentials is None:
        # No Authorization header at all — this is a guest request, which is fine
        return None

    try:
        # Extract the raw token and try to decode it
        token = credentials.credentials
        user_id = _decode_token(token)
        return db.query(User).filter(User.id == user_id).first()
    except HTTPException:
        # A token was sent but it's invalid (expired, tampered with, etc.).
        # We treat this as a guest rather than erroring, because:
        #   - Old tokens linger in browsers after logout
        #   - This prevents a bad UX where the page breaks entirely
        return None
