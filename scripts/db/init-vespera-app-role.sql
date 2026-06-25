-- Spec 12: create the least-privilege runtime role used by the API + ARQ worker.
-- Idempotent. Runs at DB bootstrap (docker-entrypoint-initdb.d on a fresh volume) and as an
-- explicit CI step before `alembic upgrade`. NOT part of any Alembic migration. The password
-- MUST match app_database_url in Vault (vespera_app / vespera_app for local + CI).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vespera_app') THEN
        CREATE ROLE vespera_app LOGIN PASSWORD 'vespera_app'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE vespera TO vespera_app;
