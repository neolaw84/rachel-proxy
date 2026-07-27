# Database Technology Review: Managed NoSQL (GCP Firebase) vs. Relational SQL (SQLite/PostgreSQL) for RACHEL

**Date**: 2026-07-27  
**Author**: GitHub Copilot (Expert AI Architect)  
**Scope**: Evaluation of managed NoSQL offerings (specifically Google Cloud Platform's Firebase Firestore) against the current unified relational database design (SQLite/PostgreSQL) for the RACHEL (RPG Agent Chat Evaluation Loop) proxy.

---

## 1. Executive Summary

RACHEL is a stateful chat completions proxy designed to run a stateful LangGraph RPG agent loop. It supports two operational modes:
1. **Standalone Single-Tenant Mode**: Runs locally on a user's PC using **SQLite**.
2. **Multi-Tenant Cloud Mode**: Runs on GCP Cloud Run using **Neon PostgreSQL** (serverless Postgres).

Currently, RACHEL's database schema is **intentionally denormalized by design**. The core entity—`sessions`—stores RPG session metadata and turn history as a single denormalized JSON blob (`turns_data` dictionary mapping 24-character turn keys to `before` and `after` state snapshots). This design eliminates complex SQL joins, subquery deletions, and multi-table sorting, allowing all LRU (Least Recently Used) eviction and state trimming to occur in-memory in Python before a single-query SQL `UPSERT`.

Given this highly denormalized, document-like data access pattern, this review evaluates whether a **managed NoSQL offering**, specifically **GCP Firebase Firestore**, is more suitable for RACHEL's cloud multi-tenant use cases than the current relational SQL setup.

### Key Recommendation:
* **Maintain the Unified Relational SQL Strategy (SQLite + PostgreSQL)**.
* While Firestore/NoSQL aligns perfectly with RACHEL's denormalized document structure, introducing it breaks the **1-to-1 operational parity** between local standalone execution (SQLite) and cloud multi-tenant execution (PostgreSQL). 
* SQLite is irreplaceable for zero-dependency, local, offline-first desktop packaging. Emulating Firestore locally (via Firestore Emulators) introduces massive dependency bloat and setup friction for non-technical users, violating RACHEL's core desktop-friendly philosophy.
* PostgreSQL (via Neon) handles JSON blobs natively with `JSONB` indexing and query capabilities, providing NoSQL-like document flexibility with the robust transactional guarantees, connection pooling, and universal SQL tooling required for multi-tenant cloud operations.

---

## 2. RACHEL's Data Access Patterns & Schema Analysis

To evaluate database suitability, we must first analyze RACHEL's core data entities and how they are accessed during a chat completion request.

### 2.1 Core Data Entities
RACHEL manages five primary tables/collections:
1. **`tenants`**: Maps a tenant ID to an external SSO user ID (e.g., Clerk, Auth0, Firebase Auth).
2. **`tenant_api_keys`**: Stores hashed proxy keys (`sk-tenant-...` or `sk-local-...`) used by chat clients (JanitorAI, SillyTavern) to authenticate.
3. **`tenant_credentials`**: Stores envelope-encrypted API keys for LLM providers (OpenRouter, OpenAI, Gemini, DeepSeek).
4. **`tenant_settings`**: Stores active provider selection, default models, and reasoning formats.
5. **`sessions`**: Stores the RPG session state and turn history.

### 2.2 The `sessions` Table: A Natural Document
The `sessions` table is the most write-heavy and read-heavy component of the system. Its schema is defined as:
* `tenant_id` (String, Primary Key)
* `session_id` (String, Primary Key)
* `turns_data` (Text/JSON, stores a dictionary of turn keys)
* `updated_at` (DateTime)

The `turns_data` JSON blob has the following structure:
```json
{
  "a1b2c3d4e5f6g7h8i9j0k1l2": {
    "before": {
      "state": {"gold": 100, "hp": 10},
      "plan": ["Defeat the goblin"],
      "summary": "The player entered the cave.",
      "hidden_state": {"goblin_trust": 0}
    },
    "after": {
      "state": {"gold": 120, "hp": 8},
      "plan": ["Defeat the goblin"],
      "summary": "The player fought the goblin and won 20 gold.",
      "hidden_state": {"goblin_trust": -10}
    }
  }
}
```

### 2.3 Read/Write Workloads during `/v1/chat/completions`
For every incoming chat completion request, RACHEL performs:
1. **Read (Auth)**: Fetch and verify the hashed proxy key from `tenant_api_keys` to resolve `tenant_id`.
2. **Read (Config)**: Fetch `tenant_settings` and `tenant_credentials` to resolve the active LLM provider and decrypt the API key.
3. **Read (State)**: Fetch the `sessions` record for `(tenant_id, session_id)` to retrieve the previous turn's state.
4. **Execution**: Run the LangGraph agent loop (including sandbox code execution).
5. **Write (State)**: Perform an `UPSERT` on the `sessions` table with the updated `turns_data` (after in-memory LRU trimming).

This workload is **highly transactional, key-value based, and scoped strictly by `tenant_id`**. There are no complex relational joins, aggregations, or cross-tenant queries.

---

## 3. Managed NoSQL (GCP Firebase Firestore) Evaluation

Google Cloud Firestore is a serverless, fully managed NoSQL document database designed for automatic scaling, high availability, and real-time synchronization.

### 3.1 Advantages of Firebase Firestore for RACHEL
1. **Perfect Document Alignment**: RACHEL's `turns_data` and tenant settings are naturally document-oriented. Firestore stores data as hierarchical documents and collections, eliminating the need to serialize/deserialize JSON strings (which is currently done manually in `RelationalSessionStorage`).
2. **Serverless Scaling & Zero Maintenance**: Firestore scales automatically to millions of users without requiring connection pools (like PgBouncer for PostgreSQL) or manual provisioning. This is highly beneficial for GCP Cloud Run deployments.
3. **Sub-document Mutations**: Firestore allows updating specific fields within a document (e.g., updating a single turn inside `turns_data` using dot notation) without rewriting the entire session document. This reduces network payload sizes for large sessions.
4. **Built-in TTL (Time-To-Live)**: Firestore supports automatic document deletion based on a timestamp field. This can be used to automatically clean up expired sessions or temporary states, offloading maintenance tasks from the application layer.
5. **Seamless Firebase Auth Integration**: If RACHEL uses Firebase Auth for multi-tenant SSO, Firestore integrates natively, allowing secure client-side queries via Firestore Security Rules (though RACHEL's proxy architecture mostly routes queries through the FastAPI backend).

### 3.2 Disadvantages & Blockers of Firebase Firestore for RACHEL
1. **The Local Standalone Dilemma (Critical Blocker)**:
   * RACHEL's primary design requirement is **dual-mode operation**. Standalone mode must run locally on a user's PC with zero external cloud dependencies.
   * Firestore is a proprietary GCP cloud service. To run Firestore locally, users must install the **Java-based Firebase Local Emulator Suite**. This requires installing a Java Runtime Environment (JRE), Node.js, and the Firebase CLI.
   * For non-technical desktop users, this is an absolute dealbreaker. SQLite, by contrast, is built directly into Python's standard library (`sqlite3`) and requires **zero installation or configuration**.
2. **Loss of 1-to-1 Code Parity**:
   * If RACHEL uses Firestore in the cloud and SQLite locally, the storage engine implementations will diverge significantly.
   * Firestore uses a completely different query API (document references, collections, snapshot listeners) compared to SQL (SQLAlchemy Core/ORM).
   * Maintaining two entirely different database paradigms (SQLAlchemy for SQLite vs. Google Cloud Firestore SDK for Cloud) doubles the maintenance overhead, increases the surface area for bugs, and complicates integration testing.
3. **Vendor Lock-in**:
   * Adopting Firestore locks RACHEL's cloud deployment strictly into Google Cloud Platform (GCP).
   * The current relational SQL strategy allows RACHEL to run on *any* cloud provider hosting PostgreSQL (AWS RDS, Azure Database, Neon, Supabase, Render, or self-hosted Dockerized Postgres).
4. **No Native SQL Joins for Admin Reporting**:
   * While RACHEL's core completion path does not use joins, administrative tasks (e.g., listing all active sessions for a tenant, calculating total API keys issued, or auditing credentials) are trivial in SQL but require multiple round-trips or denormalized index collections in Firestore.

---

## 4. Relational SQL (SQLite + PostgreSQL) Evaluation

RACHEL currently utilizes a **Unified Relational SQL Strategy** using SQLAlchemy Core/ORM. It connects to local SQLite in standalone mode and Neon PostgreSQL in cloud mode.

### 4.1 Advantages of the Relational SQL Strategy
1. **Flawless 1-to-1 Parity**:
   * SQLite and PostgreSQL share the exact same SQL schema, SQLAlchemy models, and Python code.
   * The only difference is the connection string (`sqlite:///...` vs. `postgresql+psycopg2://...`).
   * This allows developers to write and test database logic locally on SQLite with 100% confidence that it will behave identically on PostgreSQL in production.
2. **Zero-Dependency Desktop Packaging**:
   * SQLite is serverless, file-backed, and embedded. It compiles into the desktop package with zero external dependencies, keeping the installation footprint tiny and offline-capable.
3. **NoSQL Capabilities via PostgreSQL `JSONB`**:
   * Modern PostgreSQL is an excellent document store. By using the `JSONB` data type (or standard `Text` with JSON serialization), PostgreSQL can index, query, and mutate nested JSON keys inside `turns_data` with high performance.
   * SQLAlchemy supports native JSON operators, allowing RACHEL to query nested session states if needed in the future.
4. **Serverless-Friendly Postgres (Neon)**:
   * Neon PostgreSQL provides serverless, auto-scaling Postgres with instant branching and cold-starts. It mitigates traditional Postgres scaling issues while preserving standard SQL compatibility.
5. **Universal Tooling & Portability**:
   * SQL is the industry standard. RACHEL can be deployed on any cloud infrastructure, and developers can use standard GUI clients (DBeaver, pgAdmin, TablePlus) to inspect and manage data across both local and cloud environments.

### 4.2 Disadvantages of the Relational SQL Strategy
1. **Connection Pooling Overhead**:
   * In serverless environments like GCP Cloud Run, containers scale up and down rapidly. Each container instance opening direct connections to PostgreSQL can quickly exhaust the database's connection limit.
   * *Mitigation*: This is solved by using connection poolers like **PgBouncer** or serverless-native pooling provided by Neon (via their connection string transaction pooling endpoints).
2. **Manual Schema Migrations**:
   * Schema changes (e.g., adding a column to `tenant_settings`) must be applied to both SQLite and PostgreSQL.
   * *Mitigation*: Since RACHEL's schema is highly denormalized and stable, schema changes are rare. Simple manual migration scripts (like `scripts/schema_v1.sql`) or Alembic can easily manage this.

---

## 5. Comparative Matrix

The following matrix compares Firebase Firestore, PostgreSQL (Neon), and SQLite across RACHEL's core architectural requirements:

| Evaluation Dimension | GCP Firebase Firestore | PostgreSQL (Neon Cloud) | SQLite (Local Desktop) |
| :--- | :--- | :--- | :--- |
| **Data Model** | Document / NoSQL | Relational + Document (`JSONB`) | Relational + Document (`Text` JSON) |
| **Local Desktop Suitability** | ❌ **Poor** (Requires JRE, Node, Firebase Emulator) | ❌ **N/A** (Cloud only) | 🏆 **Excellent** (Zero-dependency, embedded in Python) |
| **Cloud Multi-Tenant Suitability** | 🏆 **Excellent** (Serverless, auto-scaling) | 🏆 **Excellent** (Serverless Postgres, pooled) | ❌ **Poor** (No concurrent multi-instance writes) |
| **1-to-1 Code Parity** | ❌ **None** (Requires separate Firestore SDK codebase) | 🏆 **High** (Shares SQLAlchemy models with SQLite) | 🏆 **High** (Shares SQLAlchemy models with Postgres) |
| **Vendor Lock-in** | ❌ **High** (Locked to GCP) | 🏆 **None** (Standard SQL, runs anywhere) | 🏆 **None** (Standard SQL, runs anywhere) |
| **Connection Management** | 🏆 **Seamless** (HTTP-based SDK, no pool limits) | ⚠️ **Requires Pooling** (PgBouncer / Neon Pooler) | 🏆 **Seamless** (Single-file, thread-safe locks) |
| **Query Flexibility** | ⚠️ **Limited** (No joins, complex indexing rules) | 🏆 **High** (Full SQL + JSON indexing) | 🏆 **High** (Full SQL + JSON parsing) |

---

## 6. Architectural Recommendation & Conclusion

### 6.1 The Verdict: Retain the Unified Relational SQL Strategy
Introducing a managed NoSQL database like GCP Firebase Firestore would solve the cloud-mode scaling and document-mapping concerns, but it would **fatally compromise RACHEL's dual-mode operational parity**. 

The necessity of supporting a zero-dependency, offline-first local desktop application makes **SQLite irreplaceable**. Because SQLite is a relational database, the cleanest, most maintainable, and most robust architecture is to pair it with **PostgreSQL** in the cloud. This preserves a single, unified codebase using SQLAlchemy, allowing 100% test coverage parity and seamless data migration between local files and cloud databases.

### 6.2 Recommended Optimization Path for PostgreSQL
To achieve NoSQL-like performance and flexibility within the relational SQL framework, RACHEL should adopt the following practices:

1. **Leverage PostgreSQL `JSONB` for `turns_data`**:
   * In PostgreSQL, define the `turns_data` column as `JSONB` instead of `Text`. `JSONB` stores decomposed binary JSON, allowing fast lookups and partial updates.
   * SQLAlchemy supports `sqlalchemy.dialects.postgresql.JSONB`. We can define the column dynamically based on the active engine:
     ```python
     from sqlalchemy.dialects.postgresql import JSONB
     from sqlalchemy import Text

     # Fallback to Text (serialized JSON) for SQLite, use JSONB for Postgres
     turns_data = Column(JSONB if is_postgres else Text, nullable=False, default="{}")
     ```
2. **Implement Partial Sub-document Updates**:
   * Instead of pulling the entire `turns_data` blob, modifying it in Python, and writing the entire blob back (which can become slow for very long RPG sessions), use PostgreSQL's `jsonb_set` or SQLAlchemy's JSON mutation tracking to update only the specific turn key being added or evicted.
3. **Enforce Connection Pooling in Cloud Run**:
   * Ensure that the production `DATABASE_URL` injected into GCP Cloud Run points to Neon's pooled connection endpoint (usually port `5432` with `-pooler` in the hostname) to prevent container scaling from overwhelming the database.
4. **Keep the LRU Eviction in Python**:
   * Retain the current strategy of performing LRU trimming in-memory in Python. This keeps the database operations simple, fast, and uniform across both SQLite and PostgreSQL.

By maintaining the unified relational SQL strategy and optimizing it with PostgreSQL's native document capabilities, RACHEL achieves the best of both worlds: **the simplicity and scalability of NoSQL in the cloud, and the zero-dependency portability of SQL on the desktop.**
