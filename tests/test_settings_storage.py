"""Unit tests for SettingsStorage (FileSettingsStorage)."""

import tempfile
from pathlib import Path
from rachel.core.settings_storage import FileSettingsStorage

def test_file_settings_storage_defaults():
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = FileSettingsStorage(tenant_id="local", storage_dir=tmp_dir)
        assert storage.get_active_provider() == "openrouter_byok"
        assert storage.get_credentials() == {}

        active, base_url, api_key, default_model = storage.get_active_provider_details()
        assert active == "openrouter_byok"
        assert "openrouter.ai" in base_url
        assert api_key is None
        assert default_model == "google/gemini-3.5-flash"


def test_file_settings_storage_save_and_update():
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = FileSettingsStorage(tenant_id="local", storage_dir=tmp_dir)
        storage.set_credential("openai_byok", "sk-test12345")
        storage.set_active_provider("openai_byok")

        assert storage.get_active_provider() == "openai_byok"
        assert storage.get_credentials() == {"openai_byok": "sk-test12345"}

        active, base_url, api_key, default_model = storage.get_active_provider_details()
        assert active == "openai_byok"
        assert "api.openai.com" in base_url
        assert api_key == "sk-test12345"
        assert default_model == "gpt-4o-mini"

        # Reload from disk
        storage2 = FileSettingsStorage(tenant_id="local", storage_dir=tmp_dir)
        assert storage2.get_active_provider() == "openai_byok"
        assert storage2.get_credentials().get("openai_byok") == "sk-test12345"


def test_file_settings_storage_localhost_byok():
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = FileSettingsStorage(tenant_id="local", storage_dir=tmp_dir)
        assert storage.get_localhost_key_not_needed() is True

        storage.set_active_provider("localhost_byok")
        active, base_url, api_key, default_model = storage.get_active_provider_details()
        assert active == "localhost_byok"
        assert "localhost:11434" in base_url
        assert api_key == "not-needed"
        assert default_model == "llama3.2"

        # Explicit key overrides dummy key even when toggle is True
        storage.set_credential("localhost_byok", "sk-custom-local")
        _, _, api_key, _ = storage.get_active_provider_details()
        assert api_key == "sk-custom-local"

        # Toggle OFF: when toggle is False and no key set, returns None
        storage_no_key = FileSettingsStorage(tenant_id="local_nokey", storage_dir=tmp_dir)
        storage_no_key.set_active_provider("localhost_byok")
        storage_no_key.set_localhost_key_not_needed(False)
        assert storage_no_key.get_localhost_key_not_needed() is False
        _, _, api_key_off, _ = storage_no_key.get_active_provider_details()
        assert api_key_off is None

        # Toggle OFF but key is provided (even if "not-needed" string)
        storage_no_key.set_credential("localhost_byok", "not-needed")
        _, _, api_key_explicit_not_needed, _ = storage_no_key.get_active_provider_details()
        assert api_key_explicit_not_needed == "not-needed"

        # Custom localhost base URL
        assert storage.get_localhost_base_url() is None
        storage.set_localhost_base_url("http://localhost:1234/v1/chat/completions")
        assert storage.get_localhost_base_url() == "http://localhost:1234/v1/chat/completions"
        _, custom_base_url, _, _ = storage.get_active_provider_details()
        assert custom_base_url == "http://localhost:1234/v1/chat/completions"

        # Reset to None
        storage.set_localhost_base_url(None)
        assert storage.get_localhost_base_url() is None
        _, default_base_url, _, _ = storage.get_active_provider_details()
        assert "localhost:11434" in default_base_url
