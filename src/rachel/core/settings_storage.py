"""User Settings & LLM Credentials Storage Engine.

Adheres to SOLID principles:
- BaseSettingsStorage defining abstract operations.
- FileSettingsStorage for local JSON storage (data/settings.json).
- RelationalSettingsStorage for SQL database storage (SQLite + PostgreSQL).
"""

from __future__ import annotations

import abc
import datetime
import json
import logging
from pathlib import Path
from typing import Any

from rachel.core.crypto import decrypt_api_key, derive_kek, encrypt_api_key

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_BASE_URLS = {
    "openrouter_byok": "https://openrouter.ai/api/v1/chat/completions",
    "openrouter_pkce": "https://openrouter.ai/api/v1/chat/completions",
    "openai_byok": "https://api.openai.com/v1/chat/completions",
    "gemini_byok": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "deepseek_byok": "https://api.deepseek.com/chat/completions",
}

DEFAULT_PROVIDER_MODELS = {
    "openrouter_byok": "google/gemini-3.5-flash",
    "openrouter_pkce": "google/gemini-3.5-flash",
    "openai_byok": "gpt-4o-mini",
    "gemini_byok": "gemini-2.5-flash",
    "deepseek_byok": "deepseek-chat",
}


class BaseSettingsStorage(abc.ABC):
    """Abstract Base Class for User Settings and Credentials Storage."""

    def __init__(self, tenant_id: str = "local", sso_sub: str | None = None) -> None:
        self.tenant_id = tenant_id
        self.sso_sub = sso_sub

    @abc.abstractmethod
    def get_active_provider(self) -> str:
        """Return active provider string name (e.g. 'openrouter_byok')."""
        pass

    @abc.abstractmethod
    def set_active_provider(self, provider: str) -> None:
        """Set active provider string name."""
        pass

    def get_default_model(self) -> str | None:
        """Return tenant-configured default model override, if any."""
        return None

    def set_default_model(self, model: str | None) -> None:
        """Set tenant-configured default model override."""
        pass

    def get_reasoning_format(self) -> str | None:
        """Return tenant-configured reasoning format override, if any."""
        return None

    def set_reasoning_format(self, reasoning_format: str | None) -> None:
        """Set tenant-configured reasoning format override."""
        pass

    @abc.abstractmethod
    def get_credentials(self) -> dict[str, str]:
        """Return map of provider_key -> secret_api_key."""
        pass

    @abc.abstractmethod
    def set_credential(self, provider: str, api_key: str) -> None:
        """Save secret API key for specified provider."""
        pass

    def get_active_provider_details(self) -> tuple[str, str, str | None, str]:
        """Return (active_provider, base_url, api_key, default_model)."""
        active = self.get_active_provider()
        creds = self.get_credentials()
        api_key = creds.get(active)
        base_url = DEFAULT_PROVIDER_BASE_URLS.get(active, DEFAULT_PROVIDER_BASE_URLS["openrouter_byok"])
        custom_default = self.get_default_model()
        default_model = custom_default or DEFAULT_PROVIDER_MODELS.get(active, "google/gemini-3.5-flash")
        return active, base_url, api_key, default_model

    def get_settings(self) -> dict[str, Any]:
        """Return tenant settings dictionary representation."""
        return {
            "tenant_id": self.tenant_id,
            "active_provider": self.get_active_provider(),
            "default_model": self.get_default_model(),
            "reasoning_format": self.get_reasoning_format(),
        }


class FileSettingsStorage(BaseSettingsStorage):
    """Local JSON file storage implementation for settings & credentials."""

    def __init__(
        self,
        tenant_id: str = "local",
        sso_sub: str | None = None,
        storage_dir: Any = None,
    ) -> None:
        super().__init__(tenant_id, sso_sub)
        from rachel.config import STATE_STORAGE_DIR
        base_dir = Path(storage_dir) if storage_dir is not None else Path(STATE_STORAGE_DIR).parent
        self._path = base_dir / "settings.json"
        self.kek = derive_kek(tenant_id=self.tenant_id, sso_sub=self.sso_sub)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                text = self._path.read_text(encoding="utf-8")
                raw = json.loads(text)
                if isinstance(raw, dict):
                    # Migrate legacy flat settings format to tenant-indexed structure
                    if "tenants" not in raw:
                        legacy_active = raw.get("active_provider", "openrouter_byok")
                        legacy_creds = raw.get("credentials", {})
                        raw = {
                            "tenants": {
                                "local": {
                                    "active_provider": legacy_active,
                                    "default_model": None,
                                    "reasoning_format": None,
                                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                    "credentials": legacy_creds,
                                }
                            }
                        }
                    return raw
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load settings file %s: %s", self._path, exc)

        return {"tenants": {}}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _get_tenant_bucket(self) -> dict[str, Any]:
        tenants = self._data.setdefault("tenants", {})
        if self.tenant_id not in tenants:
            tenants[self.tenant_id] = {
                "active_provider": "openrouter_byok",
                "default_model": None,
                "reasoning_format": None,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "credentials": {},
            }
        return tenants[self.tenant_id]

    def get_active_provider(self) -> str:
        bucket = self._get_tenant_bucket()
        return bucket.get("active_provider") or "openrouter_byok"

    def set_active_provider(self, provider: str) -> None:
        if provider not in DEFAULT_PROVIDER_BASE_URLS:
            raise ValueError(f"Invalid provider: '{provider}'")
        bucket = self._get_tenant_bucket()
        bucket["active_provider"] = provider
        bucket["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._save()

    def get_default_model(self) -> str | None:
        if not hasattr(self, "_data"):
            return None
        bucket = self._get_tenant_bucket()
        return bucket.get("default_model")

    def set_default_model(self, model: str | None) -> None:
        bucket = self._get_tenant_bucket()
        bucket["default_model"] = model
        bucket["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._save()

    def get_reasoning_format(self) -> str | None:
        if not hasattr(self, "_data"):
            return None
        bucket = self._get_tenant_bucket()
        return bucket.get("reasoning_format")

    def set_reasoning_format(self, reasoning_format: str | None) -> None:
        bucket = self._get_tenant_bucket()
        bucket["reasoning_format"] = reasoning_format
        bucket["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._save()

    def get_credentials(self) -> dict[str, str]:
        bucket = self._get_tenant_bucket()
        raw_creds = bucket.get("credentials", {})
        res = {}
        for p_key, enc_val in raw_creds.items():
            if not enc_val:
                continue
            try:
                res[p_key] = decrypt_api_key(str(enc_val), self.kek)
            except Exception as exc:
                logger.warning("Could not decrypt credential for provider %s: %s", p_key, exc)
                res[p_key] = str(enc_val)
        return res

    def set_credential(self, provider: str, api_key: str) -> None:
        if provider not in DEFAULT_PROVIDER_BASE_URLS:
            raise ValueError(f"Invalid provider: '{provider}'")
        bucket = self._get_tenant_bucket()
        if "credentials" not in bucket:
            bucket["credentials"] = {}
        encrypted_val = encrypt_api_key(api_key.strip(), self.kek)
        bucket["credentials"][provider] = encrypted_val
        bucket["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._save()


class RelationalSettingsStorage(BaseSettingsStorage):
    """Relational SQL storage implementation for tenant settings & credentials (SQLite + PostgreSQL)."""

    def __init__(
        self,
        tenant_id: str = "local",
        sso_sub: str | None = None,
        engine: Any = None,
        db_url: str | None = None,
    ) -> None:
        super().__init__(tenant_id, sso_sub)
        from rachel.core.db import get_engine, get_sessionmaker, init_db
        self.kek = derive_kek(tenant_id=tenant_id, sso_sub=sso_sub)
        self.engine = engine or get_engine(db_url)
        init_db(engine=self.engine)
        self.SessionMaker = get_sessionmaker(self.engine)

    def get_active_provider(self) -> str:
        from rachel.core.db import TenantSetting
        with self.SessionMaker() as session:
            setting = session.query(TenantSetting).filter_by(tenant_id=self.tenant_id).first()
            return setting.active_provider if setting else "openrouter_byok"

    def set_active_provider(self, provider: str) -> None:
        if provider not in DEFAULT_PROVIDER_BASE_URLS:
            raise ValueError(f"Invalid provider: '{provider}'")
        from rachel.core.db import TenantSetting
        with self.SessionMaker() as session:
            setting = session.query(TenantSetting).filter_by(tenant_id=self.tenant_id).first()
            if not setting:
                setting = TenantSetting(tenant_id=self.tenant_id, active_provider=provider)
                session.add(setting)
            else:
                setting.active_provider = provider
            session.commit()

    def get_default_model(self) -> str | None:
        from rachel.core.db import TenantSetting
        with self.SessionMaker() as session:
            setting = session.query(TenantSetting).filter_by(tenant_id=self.tenant_id).first()
            return setting.default_model if setting else None

    def set_default_model(self, model: str | None) -> None:
        from rachel.core.db import TenantSetting
        with self.SessionMaker() as session:
            setting = session.query(TenantSetting).filter_by(tenant_id=self.tenant_id).first()
            if not setting:
                setting = TenantSetting(tenant_id=self.tenant_id, default_model=model)
                session.add(setting)
            else:
                setting.default_model = model
            session.commit()

    def get_reasoning_format(self) -> str | None:
        from rachel.core.db import TenantSetting
        with self.SessionMaker() as session:
            setting = session.query(TenantSetting).filter_by(tenant_id=self.tenant_id).first()
            return setting.reasoning_format if setting else None

    def set_reasoning_format(self, reasoning_format: str | None) -> None:
        from rachel.core.db import TenantSetting
        with self.SessionMaker() as session:
            setting = session.query(TenantSetting).filter_by(tenant_id=self.tenant_id).first()
            if not setting:
                setting = TenantSetting(tenant_id=self.tenant_id, reasoning_format=reasoning_format)
                session.add(setting)
            else:
                setting.reasoning_format = reasoning_format
            session.commit()

    def get_credentials(self) -> dict[str, str]:
        from rachel.core.db import TenantCredential
        with self.SessionMaker() as session:
            rows = session.query(TenantCredential).filter_by(tenant_id=self.tenant_id).all()
            res = {}
            for r in rows:
                try:
                    res[r.provider] = decrypt_api_key(r.api_key, self.kek)
                except Exception as exc:
                    logger.warning("Could not decrypt credential for provider %s: %s", r.provider, exc)
            return res

    def set_credential(self, provider: str, api_key: str) -> None:
        if provider not in DEFAULT_PROVIDER_BASE_URLS:
            raise ValueError(f"Invalid provider: '{provider}'")
        from rachel.core.db import TenantCredential
        encrypted_val = encrypt_api_key(api_key.strip(), self.kek)
        with self.SessionMaker() as session:
            cred = session.query(TenantCredential).filter_by(tenant_id=self.tenant_id, provider=provider).first()
            if not cred:
                cred = TenantCredential(tenant_id=self.tenant_id, provider=provider, api_key=encrypted_val)
                session.add(cred)
            else:
                cred.api_key = encrypted_val
            session.commit()


class PostgresSettingsStorage(RelationalSettingsStorage):
    """PostgreSQL storage implementation for tenant settings & credentials (alias to RelationalSettingsStorage)."""
    pass


def get_settings_storage(
    tenant_id: str = "local",
    sso_sub: str | None = None,
    storage_dir: Any = None,
) -> BaseSettingsStorage:
    """Factory function to get settings storage engine based on STORAGE_ENGINE config."""
    from rachel.config import STORAGE_ENGINE
    if STORAGE_ENGINE.lower() in ("sqlite", "postgres", "sql", "relational"):
        return RelationalSettingsStorage(tenant_id=tenant_id, sso_sub=sso_sub)
    return FileSettingsStorage(tenant_id=tenant_id, sso_sub=sso_sub, storage_dir=storage_dir)
