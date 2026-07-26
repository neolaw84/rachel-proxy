-- Initial PostgreSQL Schema for RACHEL Multi-Tenant Cloud Mode (Neon PostgreSQL)
-- Version: 1.0.0

-- 1. Tenants Table
CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(64) PRIMARY KEY,
    external_user_id VARCHAR(255) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tenants_external_user_id ON tenants(external_user_id);

-- 2. Tenant Settings Table
CREATE TABLE IF NOT EXISTS tenant_settings (
    tenant_id VARCHAR(64) PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    active_provider VARCHAR(64) DEFAULT 'openrouter_byok',
    default_model VARCHAR(128) DEFAULT 'google/gemini-3.5-flash',
    include_reasoning BOOLEAN DEFAULT TRUE,
    reasoning_format VARCHAR(64) DEFAULT 'Open-Router',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tenant Credentials Table (AES-256-GCM encrypted payload)
CREATE TABLE IF NOT EXISTS tenant_credentials (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(64) NOT NULL,
    encrypted_payload TEXT NOT NULL,
    nonce TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_credentials_tenant_provider ON tenant_credentials(tenant_id, provider);

-- 4. Tenant API Keys Table (Proxy client keys sk-tenant-...)
CREATE TABLE IF NOT EXISTS tenant_api_keys (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash VARCHAR(128) NOT NULL UNIQUE,
    key_prefix VARCHAR(16) NOT NULL,
    label VARCHAR(128) DEFAULT 'Client Key',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON tenant_api_keys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON tenant_api_keys(key_hash);

-- 5. Sessions Table (Denormalized LRU turn state JSON blob)
CREATE TABLE IF NOT EXISTS sessions (
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id VARCHAR(128) NOT NULL,
    turns_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_tenant_updated ON sessions(tenant_id, updated_at DESC);
