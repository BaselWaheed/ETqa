-- Re-run after every migration, as etqa_migrate:  psql -U etqa_migrate -d etqa -f scripts/sql/02_app_grants.sql
-- Idempotent. Gives the runtime role data access but no DDL, and makes the audit table append-only.
GRANT USAGE ON SCHEMA public TO etqa_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO etqa_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO etqa_app;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_auditevent FROM etqa_app;
