from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "dev-secret-change-in-production"
    database_url: str = "sqlite:///./campus_lostfound.db"
    upload_dir: str = "backend/uploads"
    clip_threshold: float = 0.70
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # ── Email / SMTP ──────────────────────────────────────────────────────────
    # Leave blank to disable email notifications entirely (app works fine without them).
    # Recommended sender: Brevo free tier (brevo.com) — 300 emails/day, no 2FA needed.
    smtp_host: str = ""         # e.g. "smtp-relay.brevo.com"
    smtp_port: int = 587        # 587 = STARTTLS (standard for most providers)
    smtp_user: str = ""         # your Brevo signup email
    smtp_password: str = ""     # the SMTP key Brevo gives you (NOT your Brevo password)
    smtp_from: str = ""         # From: address shown in the email, e.g. noreply@lumslostfound.com

    class Config:
        env_file = ".env"


settings = Settings()
