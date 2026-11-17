-- Run once as a PostgreSQL superuser (or a role with CREATEROLE) when setting up a database.
-- psql -U postgres -v migrate_password='...' -v app_password='...' -f scripts/sql/01_roles.sql
-- etqa_migrate owns the schema and runs migrations; etqa_app is what Django uses at runtime.
CREATE ROLE etqa_migrate LOGIN PASSWORD :'migrate_password';
CREATE ROLE etqa_app LOGIN PASSWORD :'app_password';
CREATE DATABASE etqa OWNER etqa_migrate;
\connect etqa
GRANT CONNECT ON DATABASE etqa TO etqa_app;
GRANT USAGE ON SCHEMA public TO etqa_app;
