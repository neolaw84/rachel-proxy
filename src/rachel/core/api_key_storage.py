"""Client Proxy Key Storage Engine — SOLID, file-backed and Relational implementations.

Provides:
- BaseApiKeyStorage abstract interface.
- FileApiKeyStorage for local JSON storage (data/tenant_api_keys.json).
- RelationalApiKeyStorage for SQL database storage (SQLite + PostgreSQL).
- get_api_key_storage factory function based on STORAGE_ENGINE config.
"""

from __future__ import annotations

import abc
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any

from rachel.config import KEY_FILE
from rachel.core.crypto import hash_key

logger = logging.getLogger(__name__)



class BaseApiKeyStorage(abc.ABC):
    """Abstract Base Class for Client Proxy Key Storage."""

    def __init__(self, tenant_id: str = "local") -> None:
        self.tenant_id = tenant_id

    @abc.abstractmethod
    def create_key(
        self,
        name: str,
        prefix: str,
        raw_key: str,
        expires_at: datetime.datetime | None = None,
    ) -> dict[str, Any]:
        """Create and persist a new tenant API key."""
        pass

    @abc.abstractmethod
    def get_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        """Find an active API key by SHA-256 key hash."""
        pass

    @abc.abstractmethod
    def list_keys(self) -> list[dict[str, Any]]:
        """List active proxy keys for this tenant."""
        pass

    @abc.abstractmethod
    def revoke_key(self, key_id: str) -> bool:
        """Revoke (deactivate) a proxy key by ID."""
        pass

    @abc.abstractmethod
    def seed_bootstrap_key(self) -> None:
        """Auto-seed default tenant bootstrap client API key if missing."""
        pass


class FileApiKeyStorage(BaseApiKeyStorage):
    """JSON file-backed client proxy key storage engine."""

    def __init__(self, tenant_id: str = "local", storage_dir: Any = None) -> None:
        super().__init__(tenant_id)
        from rachel.config import STATE_STORAGE_DIR
        base_dir = Path(storage_dir) if storage_dir is not None else Path(STATE_STORAGE_DIR).parent
        self._path = base_dir / "tenant_api_keys.json"
        self._data: list[dict[str, Any]] = self._load()
        self.seed_bootstrap_key()

    def _load(self) -> list[dict[str, Any]]:
        if self._path.exists():
            try:
                text = self._path.read_text(encoding="utf-8")
                return json.loads(text)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load proxy keys file %s: %s", self._path, exc)
        return []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def create_key(
        self,
        name: str,
        prefix: str,
        raw_key: str,
        expires_at: datetime.datetime | None = None,
    ) -> dict[str, Any]:
        import secrets
        key_id = f"key_{secrets.token_hex(8)}"
        kh = hash_key(raw_key)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        expires_str = expires_at.isoformat() if expires_at else None

        record = {
            "id": key_id,
            "tenant_id": self.tenant_id,
            "key_hash": kh,
            "prefix": prefix,
            "name": name,
            "created_at": now_str,
            "expires_at": expires_str,
            "is_active": True,
        }
        self._data.append(record)
        self._save()
        return record

    def get_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        for rec in self._data:
            if rec.get("key_hash") == key_hash and rec.get("is_active", True):
                return rec
        return None

    def list_keys(self) -> list[dict[str, Any]]:
        return [
            rec for rec in self._data
            if rec.get("tenant_id") == self.tenant_id and rec.get("is_active", True)
        ]

    def revoke_key(self, key_id: str) -> bool:
        found = False
        for rec in self._data:
            if rec.get("id") == key_id and rec.get("tenant_id") == self.tenant_id:
                rec["is_active"] = False
                found = True
                break
        if found:
            self._save()
        return found

    def seed_bootstrap_key(self) -> None:
        existing = [rec for rec in self._data if rec.get("tenant_id") == self.tenant_id]
        if existing:
            return

        raw_key = None
        if KEY_FILE.exists():
            try:
                raw_key = KEY_FILE.read_text(encoding="utf-8").strip()
            except OSError:
                pass
        if not raw_key:
            raw_key = os.environ.get("RACHEL_PROXY_KEY", "rachel-local-default-key")

        kh = hash_key(raw_key)
        prefix = "sk-local-" if self.tenant_id == "local" else "sk-tenant-"
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        bootstrap_key = {
            "id": f"key_{self.tenant_id}_default",
            "tenant_id": self.tenant_id,
            "key_hash": kh,
            "prefix": prefix,
            "name": "Bootstrap Proxy Key",
            "created_at": now_str,
            "expires_at": None,
            "is_active": True,
        }
        self._data.append(bootstrap_key)
        self._save()
        logger.info("Auto-seeded bootstrap proxy key for tenant '%s' in file", self.tenant_id)


class RelationalApiKeyStorage(BaseApiKeyStorage):
    """Relational SQL implementation for client proxy key storage (SQLite + PostgreSQL)."""

    def __init__(
        self,
        tenant_id: str = "local",
        engine: Any = None,
        db_url: str | None = None,
    ) -> None:
        super().__init__(tenant_id)
        from rachel.core.db import get_engine, get_sessionmaker, init_db, seed_bootstrap_key
        self.engine = engine or get_engine(db_url)
        init_db(engine=self.engine)
        self.SessionMaker = get_sessionmaker(self.engine)
        with self.SessionMaker() as session:
            seed_bootstrap_key(session, tenant_id=self.tenant_id)


    def create_key(
        self,
        name: str,
        prefix: str,
        raw_key: str,
        expires_at: datetime.datetime | None = None,
    ) -> dict[str, Any]:
        import secrets
        from rachel.core.db import TenantApiKey
        key_id = f"key_{secrets.token_hex(8)}"
        kh = hash_key(raw_key)

        with self.SessionMaker() as session:
            record = TenantApiKey(
                id=key_id,
                tenant_id=self.tenant_id,
                key_hash=kh,
                prefix=prefix,
                name=name,
                expires_at=expires_at,
                is_active=True,
            )
            session.add(record)
            session.commit()

            return {
                "id": record.id,
                "tenant_id": record.tenant_id,
                "key_hash": record.key_hash,
                "prefix": record.prefix,
                "name": record.name,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                "is_active": record.is_active,
            }

    def get_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        from rachel.core.db import TenantApiKey
        with self.SessionMaker() as session:
            record = session.query(TenantApiKey).filter_by(key_hash=key_hash, is_active=True).first()
            if not record:
                return None
            return {
                "id": record.id,
                "tenant_id": record.tenant_id,
                "key_hash": record.key_hash,
                "prefix": record.prefix,
                "name": record.name,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                "is_active": record.is_active,
            }

    def list_keys(self) -> list[dict[str, Any]]:
        from rachel.core.db import TenantApiKey
        with self.SessionMaker() as session:
            records = (
                session.query(TenantApiKey)
                .filter_by(tenant_id=self.tenant_id, is_active=True)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "tenant_id": r.tenant_id,
                    "key_hash": r.key_hash,
                    "prefix": r.prefix,
                    "name": r.name,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                    "is_active": r.is_active,
                }
                for r in records
            ]

    def revoke_key(self, key_id: str) -> bool:
        from rachel.core.db import TenantApiKey
        with self.SessionMaker() as session:
            record = (
                session.query(TenantApiKey)
                .filter_by(id=key_id, tenant_id=self.tenant_id)
                .first()
            )
            if not record:
                return False
            record.is_active = False
            session.commit()
            return True

    def seed_bootstrap_key(self) -> None:
        from rachel.core.db import seed_bootstrap_key
        with self.SessionMaker() as session:
            seed_bootstrap_key(session, tenant_id=self.tenant_id)


def get_api_key_storage(
    tenant_id: str = "local",
    storage_dir: Any = None,
    engine: Any = None,
    db_url: str | None = None,
) -> BaseApiKeyStorage:
    """Factory function to get API Key storage engine based on STORAGE_ENGINE config."""
    from rachel.config import STORAGE_ENGINE
    if STORAGE_ENGINE.lower() in ("sqlite", "postgres", "sql", "relational"):
        return RelationalApiKeyStorage(tenant_id=tenant_id, engine=engine, db_url=db_url)
    return FileApiKeyStorage(tenant_id=tenant_id, storage_dir=storage_dir)
