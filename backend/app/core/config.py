from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    app_name: str = "Super Shop Management API"
    environment: str = "development"  # development | production | test
    debug: bool = False
    database_url: str = f"sqlite:///{(BASE_DIR / 'shop.db').as_posix()}"
    secret_key: str = "dev-only-secret-change-me-please-0123456789"
    jwt_secret: str = "dev-only-jwt-secret-change-me-0123456789"
    refresh_token_secret: str = "dev-only-refresh-secret-change-me-0123456789"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    cors_origins: str = "http://localhost:3000"
    upload_dir: str = str(BASE_DIR / "uploads")
    backup_dir: str = str(BASE_DIR / "backups")
    max_upload_mb: int = 5
    auto_migrate: bool = True
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    rate_limit_per_minute: int = 600
    login_rate_limit_per_minute: int = 20
    cookie_secure: bool | None = None  # default: secure in production
    cookie_samesite: str = "lax"  # use "none" (with HTTPS) only if the web app and API live on different sites
    cookie_domain: str = ""
    frontend_url: str = "http://localhost:3000"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_security: str = "starttls"  # starttls | ssl | none (none only for a local test sink)
    smtp_from: str = "no-reply@supershop.local"

    @field_validator("database_url")
    @classmethod
    def _db_url(cls, v: str) -> str:
        # Render/Heroku-style URLs use postgres:// or postgresql://; SQLAlchemy needs the driver name.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        return v.lower()

    @property
    def refresh_cookie_secure(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def assert_production_safe(self) -> None:
        if not self.is_production:
            return
        for name in ("secret_key", "jwt_secret", "refresh_token_secret"):
            value = getattr(self, name)
            if value.startswith("dev-only") or len(value) < 32:
                raise RuntimeError(f"{name.upper()} must be set to a strong random value in production")
        if self.debug:
            raise RuntimeError("DEBUG must be false in production")
        if self.cookie_samesite.lower() == "none" and not self.refresh_cookie_secure:
            raise RuntimeError("COOKIE_SAMESITE=none requires secure cookies")
        if "*" in self.cors_origin_list:
            raise RuntimeError("CORS_ORIGINS must not contain '*' in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
