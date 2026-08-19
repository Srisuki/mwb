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

CLOUDFLARE TUNNEL (audit.hombal.co.in)

The tunnel is outbound-only. Do not open router ports 80, 443, 5432 or 8000.
Local access remains available at http://localhost:8080.

Before enabling public access:
1. Sign in locally and change the temporary administrator password.
2. Add hombal.co.in to Cloudflare and confirm its imported @ and www DNS records.
3. Change only the domain nameservers in GoDaddy to those assigned by Cloudflare.
4. Confirm https://www.hombal.co.in still works.
5. In Cloudflare Zero Trust, create a remotely managed Cloudflared tunnel.
6. Add public hostname audit.hombal.co.in with service URL http://frontend:80.
7. Copy the tunnel token into CLOUDFLARE_TUNNEL_TOKEN in .env. Never share it.

Start the app and tunnel:
  docker compose -f compose.yaml -f compose.cloudflare.yaml up -d --build

Check status:
  docker compose -f compose.yaml -f compose.cloudflare.yaml ps
  docker compose -f compose.yaml -f compose.cloudflare.yaml logs --tail=100 cloudflared

Stop the tunnel but keep the local app running:
  docker compose -f compose.yaml -f compose.cloudflare.yaml stop cloudflared

Start the tunnel again:
  docker compose -f compose.yaml -f compose.cloudflare.yaml start cloudflared

Emergency DNS recovery:
If the existing website stops after changing nameservers, compare Cloudflare DNS with
the GoDaddy records recorded before the change. Restore the missing @ or www record.
Changing nameservers back to the original GoDaddy values is the final rollback.
