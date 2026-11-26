-- Only runs when PostgreSQL initializes a fresh data directory.
\getenv app_password GARDEN_DB_PASSWORD
CREATE ROLE garden_app LOGIN PASSWORD :'app_password';
REVOKE ALL ON DATABASE little_garden FROM PUBLIC;
GRANT CONNECT ON DATABASE little_garden TO garden_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO garden_app;
