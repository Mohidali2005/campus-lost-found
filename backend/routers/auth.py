# backend/routers/auth.py
# ─────────────────────────────────────────────────────────────────────────────
# Authentication router for the LUMS Campus Lost & Found app.
#
# This file handles three things:
#   POST /auth/register  — create a new LUMS student account
#   POST /auth/login     — verify credentials, issue a JWT token
#   GET  /auth/me        — return the currently logged-in user's profile
#
# LUMS-specific rule:
#   Only emails ending in @lums.edu.pk are allowed to register.
#   This keeps the app exclusive to the LUMS community.
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from backend.config import settings
from backend.dependencies import get_db, get_current_user
from backend.models import User
from backend.schemas import UserRegister, UserLogin, TokenResponse, UserOut


# ── Router setup ──────────────────────────────────────────────────────────────

# APIRouter is like a mini FastAPI app — it groups related endpoints.
# The `prefix="/auth"` means every route in this file is accessible at /auth/...
# The `tags=["auth"]` groups them together in the /docs swagger UI.
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Password hashing ──────────────────────────────────────────────────────────

# CryptContext manages password hashing using bcrypt.
# bcrypt is the industry standard for password storage because:
#   1. It's intentionally slow (work factor) — brute force takes way longer
#   2. It automatically generates and stores a unique salt per password
#      (so two users with the same password get different hashes)
#   3. It's resistant to rainbow table attacks because of the salt
#
# `deprecated="auto"` means if we ever switch hashing schemes, old passwords
# are automatically re-hashed on next login.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Converts a plain-text password into a bcrypt hash.
    The hash is what gets stored in the database — NEVER the plain password.

    Example output: "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """
    Checks if a plain-text password matches a stored bcrypt hash.
    Returns True if they match, False otherwise.

    passlib handles the comparison safely — it extracts the salt from the
    stored hash, re-hashes the plain password with the SAME salt, and compares.
    This is why we don't need to store the salt separately.
    """
    return pwd_context.verify(plain_password, stored_hash)


# ── JWT token creation ────────────────────────────────────────────────────────

def create_access_token(user_id: int) -> str:
    """
    Creates a signed JWT (JSON Web Token) for the given user.

    What is a JWT?
        A JWT is a self-contained token with three parts: header.payload.signature
        - Header: {"alg": "HS256", "typ": "JWT"}
        - Payload: {"sub": "42", "exp": 1234567890}  ← our claims
        - Signature: HMAC_SHA256(header + payload, SECRET_KEY)

    The signature is what makes JWTs secure — without the SECRET_KEY,
    no one can forge or modify a token. On every request, we verify the
    signature before trusting anything in the payload.

    Claims we include:
        `sub` (subject) — the user's id. Standard JWT convention.
        `exp` (expiry)  — when the token becomes invalid. Auto-checked by jose.

    The token expires after `access_token_expire_minutes` (7 days from config).
    """
    # Calculate the exact moment this token should stop being valid
    expiry_time = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)

    # Build the payload (the data encoded inside the token)
    payload = {
        "sub": str(user_id),  # must be a string — JWT spec requirement
        "exp": expiry_time,   # python-jose converts datetime → Unix timestamp automatically
    }

    # Sign and encode the token using our secret key
    # Anyone who has the token can READ the payload (it's base64, not encrypted),
    # but they CANNOT modify it without invalidating the signature.
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token


# ── LUMS email validator ──────────────────────────────────────────────────────

def _require_lums_email(email: str) -> None:
    """
    Raises HTTP 400 if the email address is not from LUMS (@lums.edu.pk).

    This is the gatekeeping function that restricts registration to the
    LUMS community (students and faculty). Without this check, anyone on
    the internet could create an account.

    We use `.lower()` so uppercase variants like "Name@LUMS.EDU.PK" still pass.
    """
    if not email.lower().endswith("@lums.edu.pk"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only LUMS email addresses (@lums.edu.pk) can register. "
                "If you are a LUMS student, please use your official university email."
            ),
        )


# ── Endpoint 1: Register ──────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserOut,          # what shape of data to return
    status_code=status.HTTP_201_CREATED,  # 201 = "resource was created" (not 200 "ok")
    summary="Register a new LUMS student account",
)
def register(
    body: UserRegister,          # FastAPI parses and validates the JSON request body
    db: Session = Depends(get_db),  # inject a database session
):
    """
    Creates a new user account for a LUMS student.

    Request body (UserRegister schema):
        name        — full name, e.g. "Ali Hassan"
        email       — must end in @lums.edu.pk
        password    — plain text (we hash it before storing)
        student_id  — optional, e.g. "24100123"

    Steps:
        1. Reject non-LUMS emails immediately
        2. Check for duplicate email (each email = one account)
        3. Hash the password with bcrypt
        4. Save the new user to the DB
        5. Return the user profile (no password hash exposed)

    Why 201 instead of 200?
        HTTP 201 Created specifically means "a new resource was created as a
        result of this request" — semantically more precise for registration.
    """

    # ── Step 1: LUMS email gate ───────────────────────────────────────────────
    # Raises 400 immediately if not @lums.edu.pk. No DB queries wasted.
    _require_lums_email(body.email)

    # ── Step 2: Duplicate email check ─────────────────────────────────────────
    # Query the users table for any row with this exact email.
    # `.first()` returns the first matching row, or None if no match.
    existing_user = db.query(User).filter(User.email == body.email).first()

    if existing_user:
        # 409 Conflict = the request conflicts with current state of the server
        # (i.e., this email is already taken)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Try logging in instead.",
        )

    # ── Step 3: Hash the password ─────────────────────────────────────────────
    # NEVER store the password in plain text. If the database is ever breached,
    # bcrypt hashes give attackers essentially no useful information.
    hashed_password = hash_password(body.password)

    # ── Step 4: Create and save the user ──────────────────────────────────────
    # Create a User ORM object (this does NOT hit the database yet)
    new_user = User(
        name=body.name,
        email=body.email,
        student_id=body.student_id,   # None is fine — student_id is optional
        password_hash=hashed_password,  # store the bcrypt hash, not the plain password
        is_admin=False,               # all new accounts are regular users
                                      # admins are promoted manually via the DB
    )

    db.add(new_user)    # stage the INSERT — tells SQLAlchemy "add this row"
    db.commit()         # actually execute the SQL INSERT and commit the transaction
    db.refresh(new_user)  # re-read the row from DB so new_user.id and
                           # new_user.created_at are populated (set by the DB)

    # ── Step 5: Return the user profile ───────────────────────────────────────
    # Pydantic automatically converts the User ORM object to the UserOut schema,
    # which excludes sensitive fields like password_hash.
    return new_user


# ── Endpoint 2: Login ─────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,  # returns {"access_token": "...", "token_type": "bearer"}
    summary="Log in with LUMS email and password",
)
def login(
    body: UserLogin,             # expects {"email": "...", "password": "..."}
    db: Session = Depends(get_db),
):
    """
    Authenticates a user and returns a JWT access token.

    The client should store this token (e.g. in localStorage) and send it
    on every subsequent request as:
        Authorization: Bearer <token>

    Security note on error messages:
        We return the SAME error whether the email doesn't exist OR the password
        is wrong. This prevents "user enumeration" — where an attacker sends
        many emails to discover which accounts exist based on different errors.
    """

    # ── Step 1: Find the user by email ────────────────────────────────────────
    user = db.query(User).filter(User.email == body.email).first()
    # `user` is either a User ORM object or None (if no account with that email)

    # ── Step 2: Verify the password ───────────────────────────────────────────
    # We check BOTH conditions in one `if` to ensure the same error response
    # regardless of whether the email was wrong or the password was wrong.
    #
    # `not verify_password(...)` is short-circuit evaluated — if user is None,
    # Python skips the verify_password call entirely (which avoids a crash).
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},  # standard HTTP auth header
        )

    # ── Step 3: Issue a JWT token ─────────────────────────────────────────────
    # At this point we know the credentials are correct — mint a fresh token.
    token = create_access_token(user.id)

    # Return the token wrapped in the TokenResponse schema
    return TokenResponse(access_token=token, token_type="bearer")


# ── Endpoint 3: Get current user profile ─────────────────────────────────────

@router.get(
    "/me",
    response_model=UserOut,
    summary="Get the currently logged-in user's profile",
)
def get_me(
    current_user: User = Depends(get_current_user),
    # `get_current_user` (from dependencies.py) handles everything:
    #   - Reading the Authorization header
    #   - Decoding and validating the JWT
    #   - Fetching the User from the DB
    # If anything fails, it raises 401 BEFORE this function runs.
):
    """
    Returns the profile of the currently authenticated LUMS student.

    This endpoint is useful for the frontend to:
        - Check if the user is still logged in on page load
        - Show the user's name and student ID in the nav bar
        - Know if the user is an admin (to show admin controls)

    Requires: Authorization: Bearer <token> header.
    Returns: UserOut (id, name, email, student_id, is_admin, created_at)
    """
    # `current_user` is already a fully loaded User ORM object injected by
    # the dependency — nothing more to do, just return it.
    return current_user
