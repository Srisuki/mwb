MWB Internal Audit Manager — Local Docker Application

The production application is not opened by double-clicking the legacy HTML file.
The legacy file remains only as the original functional reference.

START

1. Start Docker Desktop.
2. Open Terminal in:
   /Users/shrini/Documents/Audit_manager
3. Run:
   docker compose up -d --build
4. Open:
   http://localhost:8080

INITIAL ADMINISTRATOR

Configure ADMIN_EMAIL, ADMIN_PASSWORD and ADMIN_NAME in .env, then run:

docker compose exec backend python -m app.seed --baseline --sample-data

The administrator must change the temporary password after first login.
Never use the PINs embedded in MWB_Internal_Audit_Manager.html.

DATA LOCATIONS

PostgreSQL application data:
  Docker volume audit_manager_postgres_data

Uploaded evidence files:
  /Users/shrini/Documents/Audit_manager/uploads

Database backups:
  /Users/shrini/Documents/Audit_manager/backups

Data remains available when containers are stopped. Do not delete Docker volumes or
the uploads/backups folders unless you intentionally want to remove that data.

USER ADMINISTRATION

Sign in as Admin / Partner and open Users in the left navigation.
The module supports user creation, roles, client access, search/filtering, details,
effective permissions, role changes, activation/deactivation and audit history.

STOP

docker compose stop

START AGAIN

docker compose start

Do not use docker compose down -v because -v removes the PostgreSQL volume.
