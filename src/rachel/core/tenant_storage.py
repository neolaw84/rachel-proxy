"""Tenant Entity Storage Engine — SOLID, file-backed and Relational implementations.

Provides:
- BaseTenantStorage abstract interface.
- FileTenantStorage for local JSON storage (data/tenants.json).
- RelationalTenantStorage for SQL database storage (SQLite + PostgreSQL).
- get_tenant_storage factory function based on STORAGE_ENGINE config.
"""

from __future__ import annotations

import abc
import datetime
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BaseTenantStorage(abc.ABC):
    """Abstract Base Class for Tenant Entity Storage."""

    @abc.abstractmethod
    def create_tenant(
        self,
        tenant_id: str,
        external_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Create and persist a new tenant record."""
        pass

    @abc.abstractmethod
    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        """Get a tenant record by tenant_id."""
        pass

    @abc.abstractmethod
    def list_tenants(self) -> list[dict[str, Any]]:
        """List all stored tenant records."""
        pass


class FileTenantStorage(BaseTenantStorage):
    """JSON file-backed tenant entity storage engine."""

    def __init__(self, storage_dir: Any = None) -> None:
        from rachel.config import STATE_STORAGE_DIR
        base_dir = Path(storage_dir) if storage_dir is not None else Path(STATE_STORAGE_DIR).parent
        self._path = base_dir / "tenants.json"
        self._data: list[dict[str, Any]] = self._load()
        self._ensure_default_local_tenant()

    def _load(self) -> list[dict[str, Any]]:
        if self._path.exists():
            try:
                text = self._path.read_text(encoding="utf-8")
                return json.loads(text)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load tenants file %s: %s", self._path, exc)
        return []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _ensure_default_local_tenant(self) -> None:
        if not self.get_tenant("local"):
            self.create_tenant(tenant_id="local", external_user_id=None)

    def create_tenant(
        self,
        tenant_id: str,
        external_user_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get_tenant(tenant_id)
        if existing:
            return existing

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        record = {
            "tenant_id": tenant_id,
            "external_user_id": external_user_id,
            "created_at": now_str,
            "updated_at": now_str,
        }
        self._data.append(record)
        self._save()
        return record

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        for rec in self._data:
            if rec.get("tenant_id") == tenant_id:
                return rec
        return None

    def list_tenants(self) -> list[dict[str, Any]]:
        return list(self._data)


class RelationalTenantStorage(BaseTenantStorage):
    """Relational SQL implementation for tenant entity storage (SQLite + PostgreSQL)."""

    def __init__(self, engine: Any = None, db_url: str | None = None) -> None:
        from rachel.core.db import get_engine, get_sessionmaker, init_db
        self.engine = engine or get_engine(db_url)
        init_db(engine=self.engine)
        self.SessionMaker = get_sessionmaker(self.engine)

    def create_tenant(
        self,
        tenant_id: str,
        external_user_id: str | None = None,
    ) -> dict[str, Any]:
        from rachel.core.db import Tenant
        with self.SessionMaker() as session:
            record = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not record:
                record = Tenant(tenant_id=tenant_id, external_user_id=external_user_id)
                session.add(record)
                session.commit()
            return {
                "tenant_id": record.tenant_id,
                "external_user_id": record.external_user_id,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        from rachel.core.db import Tenant
        with self.SessionMaker() as session:
            record = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not record:
                return None
            return {
                "tenant_id": record.tenant_id,
                "external_user_id": record.external_user_id,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }

    def list_tenants(self) -> list[dict[str, Any]]:
        from rachel.core.db import Tenant
        with self.SessionMaker() as session:
            records = session.query(Tenant).all()
            return [
                {
                    "tenant_id": r.tenant_id,
                    "external_user_id": r.external_user_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in records
            ]


def get_tenant_storage(
    storage_dir: Any = None,
    engine: Any = None,
    db_url: str | None = None,
) -> BaseTenantStorage:
    """Factory function to get Tenant storage engine based on STORAGE_ENGINE config."""
    from rachel.config import STORAGE_ENGINE
    if STORAGE_ENGINE.lower() in ("sqlite", "postgres", "sql", "relational"):
        return RelationalTenantStorage(engine=engine, db_url=db_url)
    return FileTenantStorage(storage_dir=storage_dir)
