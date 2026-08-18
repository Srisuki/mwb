# MWB Internal Audit Manager

Database-backed migration of the original browser-only audit manager. The unchanged `MWB_Internal_Audit_Manager.html` remains the functional reference; the production application uses React, FastAPI, PostgreSQL and server-side file storage.

## Architecture

- React + TypeScript + Vite frontend served by Nginx
- FastAPI REST API with backend-enforced permissions
- SQLAlchemy relational models and Alembic migrations
- PostgreSQL as the authoritative application datastore
- Host-mounted evidence storage with checksums and secured downloads
- Docker Compose health checks and automated PostgreSQL backups
- Optional Caddy HTTPS deployment through `compose.production.yaml`

No business data is stored in browser `localStorage`. Browser session storage contains only access and refresh tokens.

## Local startup

1. Copy `.env.example` to `.env` and replace all placeholder secrets.
2. Set `DOCUMENT_STORAGE_PATH` and `BACKUP_STORAGE_PATH` to the desired host folders.
3. Start Docker Desktop.
4. Run `docker compose up -d --build`.
5. Configure `ADMIN_EMAIL`, `ADMIN_PASSWORD` and `ADMIN_NAME` in `.env`, then initialize the system:

   ```sh
   docker compose exec backend python -m app.seed --baseline --sample-data
   ```

6. Open <http://localhost:8080>.

The initialization operation is idempotent. `--baseline` loads the preserved legacy entities, audit areas and checklist; `--sample-data` is optional.

## User and role management

Admin / Partner users can open **Users** from the application navigation. User administration provides:

- create and edit users without exposing password hashes;
- stable system role codes and friendly role names;
- future-ready `user_roles` database relationship with one primary role today;
- client/entity scope assignments independent of role;
- role-aware client selection, mandatory for Client Management;
- search, role/client/status filters and pagination;
- user details, effective permissions and recent activity;
- dedicated activate/deactivate operations that preserve historical records;
- distinct immutable audit events for creation, updates, role changes, client-scope changes and account status changes.

System roles are `ADMIN_PARTNER`, `AUDIT_MANAGER`, `AUDIT_STAFF` and `CLIENT_MANAGEMENT`. Permissions are stored relationally and enforced by API dependencies. UI visibility is only a convenience; direct unauthorized API calls receive `401` or `403`.

Temporary passwords are hashed and users must change them after first login. The password-change workflow marks the account verified and revokes existing refresh sessions.

## Data persistence

- PostgreSQL data: Docker volume `audit_manager_postgres_data`
- Uploaded files: `${DOCUMENT_STORAGE_PATH}` (default `./uploads`)
- Backups: `${BACKUP_STORAGE_PATH}` (default `./backups`)

Stopping containers does not remove these data locations. Avoid `docker compose down -v` unless volume deletion is intentional.

## Backups and restore

The `backup` service creates timestamped custom-format PostgreSQL dumps and applies configured retention. Restore is intentionally interactive:

```sh
./scripts/restore-backup.sh /absolute/path/to/mwb_audit_TIMESTAMP.dump
```

## Database migrations

The backend applies `alembic upgrade head` during container startup. User and role management is introduced by migration `0004_user_role_management.py`, which adds user metadata, stable role codes, role metadata, future multi-role support, requested permissions and initial mappings.

## Development checks

The repository includes backend permission/API contract tests, user-management rule tests, frontend component tests and Playwright workflow tests. Per the current project direction, the latest user-management changes have been implemented but the broader test/build/runtime verification cycle has been deferred.

Never reuse credentials or PINs embedded in the legacy HTML. They are not valid production credentials and are intentionally excluded from migration.
