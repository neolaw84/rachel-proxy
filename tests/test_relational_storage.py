"""Unit tests for Unified Relational Database Storage Engine (SQLite + PostgreSQL)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rachel.core.db import (
    Base,
    Tenant,
    TenantApiKey,
    init_db,
)
from rachel.core.state import RelationalSessionStorage
from rachel.core.settings_storage import RelationalSettingsStorage


@pytest.fixture
def sqlite_engine():
    """In-memory SQLite engine fixture with StaticPool."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine=engine)
    return engine


def test_sqlite_db_init_and_bootstrap_seeding(sqlite_engine):
    """Verify tables are created and bootstrap proxy key is seeded."""
    SessionMaker = sessionmaker(bind=sqlite_engine)
    with SessionMaker() as session:
        tenants = session.query(Tenant).all()
        assert len(tenants) == 1
        assert tenants[0].tenant_id == "local"

        keys = session.query(TenantApiKey).filter_by(tenant_id="local").all()
        assert len(keys) == 1
        assert keys[0].prefix == "sk-local-"
        assert keys[0].is_active is True


def test_relational_session_storage_crud(sqlite_engine):
    """Verify session save, retrieve, list, reset, and delete."""
    storage = RelationalSessionStorage("test_session_1", max_size=5, engine=sqlite_engine)

    # Initial get_before_state for first turn should return empty migrated state
    state_0 = storage.get_before_state(None)
    assert state_0 == {"state": {}, "plan": [], "summary": "", "hidden_state": {}}

    # Save turn 1
    tk1 = "a" * 24
    storage.save_turn(tk1, {"state": {"gold": 10}}, {"state": {"gold": 20}})

    # Get before state for turn 2 referencing turn 1
    state_1 = storage.get_before_state(tk1)
    assert state_1["state"] == {"gold": 20}

    # Save turn 2
    tk2 = "b" * 24
    storage.save_turn(tk2, {"state": {"gold": 20}}, {"state": {"gold": 30}})

    # All turns check
    all_turns = storage.get_all_turns()
    assert len(all_turns) == 2
    assert tk1 in all_turns
    assert tk2 in all_turns

    # List sessions
    sessions = RelationalSessionStorage.list_sessions(engine=sqlite_engine)
    assert "test_session_1" in sessions

    # Reset
    storage.reset()
    assert len(storage.get_all_turns()) == 0

    # Delete
    storage.delete()
    assert "test_session_1" not in RelationalSessionStorage.list_sessions(engine=sqlite_engine)


def test_in_memory_lru_eviction(sqlite_engine):
    """Verify Python in-memory LRU eviction on turns_data when len > max_size."""
    storage = RelationalSessionStorage("lru_session", max_size=3, engine=sqlite_engine)

    keys = [f"{chr(97 + i)}" * 24 for i in range(5)]
    for idx, tk in enumerate(keys):
        storage.save_turn(tk, {"idx": idx}, {"idx": idx + 1})

    turns = storage.get_all_turns()
    assert len(turns) == 3
    # First two keys (0, 1) should have been evicted
    assert keys[0] not in turns
    assert keys[1] not in turns
    # Last three keys (2, 3, 4) should remain
    assert keys[2] in turns
    assert keys[3] in turns
    assert keys[4] in turns


def test_multi_tenant_session_isolation(sqlite_engine):
    """Verify sessions are isolated across different tenant_ids."""
    storage_a = RelationalSessionStorage("session_x", tenant_id="tenant_a", engine=sqlite_engine)
    storage_b = RelationalSessionStorage("session_x", tenant_id="tenant_b", engine=sqlite_engine)

    tk = "c" * 24
    storage_a.save_turn(tk, {"gold": 100}, {"gold": 200})
    storage_b.save_turn(tk, {"gold": 500}, {"gold": 600})

    turns_a = storage_a.get_all_turns()
    turns_b = storage_b.get_all_turns()

    assert turns_a[tk]["after"]["state"] == {"gold": 200}
    assert turns_b[tk]["after"]["state"] == {"gold": 600}

    sessions_a = RelationalSessionStorage.list_sessions(tenant_id="tenant_a", engine=sqlite_engine)
    sessions_b = RelationalSessionStorage.list_sessions(tenant_id="tenant_b", engine=sqlite_engine)

    assert sessions_a == ["session_x"]
    assert sessions_b == ["session_x"]


def test_import_export_session_data(sqlite_engine):
    """Verify session import and export functionality."""
    storage = RelationalSessionStorage("import_session", engine=sqlite_engine)
    tk = "d" * 24

    import_payload = {
        tk: {
            "meta-data": {"session_id": "import_session", "turn_number": 1},
            "before": {"state": {"level": 1}},
            "after": {"state": {"level": 2}},
        }
    }

    storage.import_data(import_payload)
    turns = storage.get_all_turns()
    assert len(turns) == 1
    assert turns[tk]["before"]["state"] == {"level": 1}
    assert turns[tk]["after"]["state"] == {"level": 2}


def test_relational_settings_storage(sqlite_engine):
    """Verify RelationalSettingsStorage active provider and credentials operations."""
    settings = RelationalSettingsStorage(tenant_id="tenant_1", engine=sqlite_engine)

    assert settings.get_active_provider() == "openrouter_byok"

    settings.set_active_provider("openai_byok")
    assert settings.get_active_provider() == "openai_byok"

    settings.set_credential("openai_byok", "sk-proj-test12345")
    creds = settings.get_credentials()
    assert creds.get("openai_byok") == "sk-proj-test12345"

    details = settings.get_active_provider_details()
    assert details[0] == "openai_byok"
    assert details[1] == "https://api.openai.com/v1/chat/completions"
    assert details[2] == "sk-proj-test12345"
    assert details[3] == "gpt-4o-mini"

    # Test localhost_byok with key_not_needed toggle
    assert settings.get_localhost_key_not_needed() is True
    settings.set_active_provider("localhost_byok")
    local_details = settings.get_active_provider_details()
    assert local_details[0] == "localhost_byok"
    assert "localhost:11434" in local_details[1]
    assert local_details[2] == "not-needed"
    assert local_details[3] == "llama3.2"

    # Toggle to False
    settings.set_localhost_key_not_needed(False)
    assert settings.get_localhost_key_not_needed() is False
    local_details_nokey = settings.get_active_provider_details()
    assert local_details_nokey[2] is None

    # Set explicit key while toggle is False
    settings.set_credential("localhost_byok", "sk-local-secret")
    local_details_explicit = settings.get_active_provider_details()
    assert local_details_explicit[2] == "sk-local-secret"

    # Custom localhost base URL in relational storage
    assert settings.get_localhost_base_url() is None
    settings.set_localhost_base_url("http://localhost:8080/v1/chat/completions")
    assert settings.get_localhost_base_url() == "http://localhost:8080/v1/chat/completions"
    details_custom = settings.get_active_provider_details()
    assert details_custom[1] == "http://localhost:8080/v1/chat/completions"
