"""Unit and Integration Tests for JSON File Storage 1-to-1 Schema Parity.

Verifies that JSON file storage implementations have 1-to-1 operational and schema
parity with Relational SQL (SQLite) storage across:
1. Tenant Entities (tenants)
2. Client Proxy Keys (tenant_api_keys)
3. User Settings & Credentials (tenant_settings & tenant_credentials)
4. Session State Stores (sessions)
5. End-to-end proxy key auth and administration API endpoints in file vs sqlite modes.
"""

import os
import tempfile
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from rachel.auth import PROXY_API_KEY, require_proxy_key
from rachel.core.api_key_storage import (
    FileApiKeyStorage,
    RelationalApiKeyStorage,
    get_api_key_storage,
    hash_key,
)
from rachel.core.tenant_storage import (
    FileTenantStorage,
    RelationalTenantStorage,
    get_tenant_storage,
)
from rachel.core.settings_storage import (
    FileSettingsStorage,
    RelationalSettingsStorage,
    get_settings_storage,
)
from rachel.core.state import (
    FileSessionStorage,
    RelationalSessionStorage,
    get_session_storage,
)
from rachel.proxy import app

client = TestClient(app)


def test_tenant_storage_parity():
    """Verify FileTenantStorage and RelationalTenantStorage 1-to-1 feature parity."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        sqlite_url = f"sqlite:///{tmp_dir}/test.sqlite3"

        file_storage = FileTenantStorage(storage_dir=tmp_dir)
        rel_storage = RelationalTenantStorage(db_url=sqlite_url)

        # 1. Default local tenant present in both engines
        assert file_storage.get_tenant("local") is not None
        assert rel_storage.get_tenant("local") is not None

        # 2. Create custom tenant
        t_file = file_storage.create_tenant("tenant_abc", external_user_id="user_123")
        t_rel = rel_storage.create_tenant("tenant_abc", external_user_id="user_123")

        assert t_file["tenant_id"] == t_rel["tenant_id"] == "tenant_abc"
        assert t_file["external_user_id"] == t_rel["external_user_id"] == "user_123"

        # 3. List tenants
        list_file = file_storage.list_tenants()
        list_rel = rel_storage.list_tenants()

        ids_file = {t["tenant_id"] for t in list_file}
        ids_rel = {t["tenant_id"] for t in list_rel}
        assert "tenant_abc" in ids_file
        assert "tenant_abc" in ids_rel


def test_api_key_storage_parity():
    """Verify FileApiKeyStorage and RelationalApiKeyStorage 1-to-1 feature parity."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        sqlite_url = f"sqlite:///{tmp_dir}/test.sqlite3"

        file_storage = FileApiKeyStorage(tenant_id="local", storage_dir=tmp_dir)
        rel_storage = RelationalApiKeyStorage(tenant_id="local", db_url=sqlite_url)

        # 1. Both auto-seed bootstrap key
        bootstrap_file = file_storage.list_keys()
        bootstrap_rel = rel_storage.list_keys()
        assert len(bootstrap_file) >= 1
        assert len(bootstrap_rel) >= 1

        # 2. Create custom key
        k_file = file_storage.create_key(
            name="My Test Key",
            prefix="sk-local-",
            raw_key="sk-local-1234567890abcdef",
        )
        k_rel = rel_storage.create_key(
            name="My Test Key",
            prefix="sk-local-",
            raw_key="sk-local-1234567890abcdef",
        )

        assert k_file["name"] == k_rel["name"] == "My Test Key"
        assert k_file["prefix"] == k_rel["prefix"] == "sk-local-"
        assert k_file["is_active"] == k_rel["is_active"] is True

        # 3. Lookup by hash
        kh = hash_key("sk-local-1234567890abcdef")
        found_file = file_storage.get_key_by_hash(kh)
        found_rel = rel_storage.get_key_by_hash(kh)

        assert found_file is not None
        assert found_rel is not None
        assert found_file["id"] == k_file["id"]
        assert found_rel["id"] == k_rel["id"]

        # 4. Revoke key
        rev_file = file_storage.revoke_key(k_file["id"])
        rev_rel = rel_storage.revoke_key(k_rel["id"])
        assert rev_file is True
        assert rev_rel is True

        assert file_storage.get_key_by_hash(kh) is None
        assert rel_storage.get_key_by_hash(kh) is None


def test_settings_storage_parity():
    """Verify FileSettingsStorage and RelationalSettingsStorage 1-to-1 feature parity."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        sqlite_url = f"sqlite:///{tmp_dir}/test.sqlite3"

        file_storage = FileSettingsStorage(tenant_id="tenant_1", storage_dir=tmp_dir)
        rel_storage = RelationalSettingsStorage(tenant_id="tenant_1", db_url=sqlite_url)

        # 1. Active provider default
        assert file_storage.get_active_provider() == rel_storage.get_active_provider() == "openrouter_byok"

        # 2. Set active provider & settings
        file_storage.set_active_provider("openai_byok")
        rel_storage.set_active_provider("openai_byok")

        file_storage.set_default_model("gpt-4o")
        rel_storage.set_default_model("gpt-4o")

        file_storage.set_reasoning_format("Raw-Think")
        rel_storage.set_reasoning_format("Raw-Think")

        assert file_storage.get_active_provider() == rel_storage.get_active_provider() == "openai_byok"
        assert file_storage.get_default_model() == rel_storage.get_default_model() == "gpt-4o"
        assert file_storage.get_reasoning_format() == rel_storage.get_reasoning_format() == "Raw-Think"

        # 3. Encrypted Credentials
        file_storage.set_credential("openai_byok", "sk-secret-key-123")
        rel_storage.set_credential("openai_byok", "sk-secret-key-123")

        creds_file = file_storage.get_credentials()
        creds_rel = rel_storage.get_credentials()

        assert creds_file.get("openai_byok") == "sk-secret-key-123"
        assert creds_rel.get("openai_byok") == "sk-secret-key-123"

        # 4. Details resolution
        details_file = file_storage.get_active_provider_details()
        details_rel = rel_storage.get_active_provider_details()

        assert details_file == details_rel == ("openai_byok", "https://api.openai.com/v1/chat/completions", "sk-secret-key-123", "gpt-4o")


def test_session_storage_parity():
    """Verify FileSessionStorage and RelationalSessionStorage 1-to-1 feature parity."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        sqlite_url = f"sqlite:///{tmp_dir}/test.sqlite3"

        file_storage = FileSessionStorage(session_id="sess_123", tenant_id="tenant_x", storage_dir=tmp_dir)
        rel_storage = RelationalSessionStorage(session_id="sess_123", tenant_id="tenant_x", db_url=sqlite_url)

        turn_key = "123456789012345678901234"
        before = {"gold": 10}
        after = {"gold": 20}

        file_storage.save_turn(turn_key, before, after)
        rel_storage.save_turn(turn_key, before, after)

        turns_file = file_storage.get_all_turns()
        turns_rel = rel_storage.get_all_turns()

        assert turn_key in turns_file
        assert turn_key in turns_rel
        assert turns_file[turn_key]["after"]["state"]["gold"] == 20
        assert turns_rel[turn_key]["after"]["state"]["gold"] == 20

        # Reset
        file_storage.reset()
        rel_storage.reset()

        assert file_storage.get_all_turns() == {}
        assert rel_storage.get_all_turns() == {}


def test_plug_and_play_engine_switching_end_to_end():
    """Verify that switching STORAGE_ENGINE between file and sqlite produces 100% working proxy key APIs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        headers = {"Authorization": f"Bearer {PROXY_API_KEY}"}

        # --- Mode 1: JSON File Engine ---
        with patch.dict(os.environ, {"STORAGE_ENGINE": "file"}):
            with patch("rachel.config.STATE_STORAGE_DIR", tmp_dir):
                # 1. Create a client proxy key
                resp = client.post(
                    "/v1/proxy-keys",
                    json={"name": "File Mode Key"},
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                key_id = data["id"]
                raw_proxy_key = data["proxy_key"]
                assert raw_proxy_key.startswith("sk-local-")

                # 2. List keys
                resp_list = client.get("/v1/proxy-keys", headers=headers)
                assert resp_list.status_code == 200
                assert any(k["id"] == key_id for k in resp_list.json()["keys"])

                # 3. Authenticate with newly created proxy key
                auth_resp = client.get("/v1/sessions", headers={"Authorization": f"Bearer {raw_proxy_key}"})
                assert auth_resp.status_code == 200

                # 4. Revoke key
                del_resp = client.delete(f"/v1/proxy-keys/{key_id}", headers=headers)
                assert del_resp.status_code == 200

                # 5. Revoked key fails authentication
                failed_auth = client.get("/v1/sessions", headers={"Authorization": f"Bearer {raw_proxy_key}"})
                assert failed_auth.status_code == 401

        # --- Mode 2: SQLite Engine ---
        sqlite_db = os.path.join(tmp_dir, "test_rachel.sqlite3")
        with patch.dict(os.environ, {"STORAGE_ENGINE": "sqlite", "DATABASE_URL": f"sqlite:///{sqlite_db}"}):
            with patch("rachel.config.STATE_STORAGE_DIR", tmp_dir):
                # 1. Create a client proxy key
                resp = client.post(
                    "/v1/proxy-keys",
                    json={"name": "SQLite Mode Key"},
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                key_id = data["id"]
                raw_proxy_key = data["proxy_key"]
                assert raw_proxy_key.startswith("sk-local-")

                # 2. List keys
                resp_list = client.get("/v1/proxy-keys", headers=headers)
                assert resp_list.status_code == 200
                assert any(k["id"] == key_id for k in resp_list.json()["keys"])

                # 3. Authenticate with newly created proxy key
                auth_resp = client.get("/v1/sessions", headers={"Authorization": f"Bearer {raw_proxy_key}"})
                assert auth_resp.status_code == 200

                # 4. Revoke key
                del_resp = client.delete(f"/v1/proxy-keys/{key_id}", headers=headers)
                assert del_resp.status_code == 200

                # 5. Revoked key fails authentication
                failed_auth = client.get("/v1/sessions", headers={"Authorization": f"Bearer {raw_proxy_key}"})
                assert failed_auth.status_code == 401
