"""Environment-driven configuration for the PathSnap backend."""
from __future__ import annotations

import os


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Resolved from environment variables; see backend/.env.example."""

    def __init__(self) -> None:
        self.mode: str = os.environ.get("PATHSNAP_MODE", "mock").strip().lower()
        if self.mode not in {"mock", "real"}:
            raise ValueError(
                f"PATHSNAP_MODE must be 'mock' or 'real', got {self.mode!r}"
            )
        self.teammates_module: str = os.environ.get("PATHSNAP_TEAMMATES_MODULE", "").strip()
        self.data_dir: str = os.environ.get("PATHSNAP_DATA_DIR", "./data")
        origins = os.environ.get("PATHSNAP_CORS_ORIGINS", "*")
        self.cors_origins: list[str] = [o.strip() for o in origins.split(",") if o.strip()]
        self.return_reference_geometry: bool = _bool("PATHSNAP_RETURN_REFERENCE_GEOMETRY", True)
        self.host: str = os.environ.get("PATHSNAP_HOST", "0.0.0.0")
        self.port: int = int(os.environ.get("PATHSNAP_PORT", "8000"))


settings = Settings()
