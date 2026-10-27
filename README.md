# Deployment helper

Targets Ubuntu/Debian servers and configures a Node.js app behind Nginx with Let's Encrypt TLS.

## Setup

1. From the repository root, copy the template:

   ```bash
   cp scripts/.env.example scripts/.env
   vim scripts/.env
   ```

2. Set `DOMAIN`, `LETSENCRYPT_EMAIL`, `APP_PORT`, and the commands that match your `package.json`.
3. Confirm DNS records for both `DOMAIN` and `www.DOMAIN` point to the server. Ensure inbound TCP ports 80 and 443 are open.
4. Review the script, then set `CONFIRM_DEPLOY=yes` in `scripts/.env`.
5. Run:

   ```bash
   chmod +x scripts/deploy.sh
   ./scripts/deploy.sh
   ```

## Important project-specific checks

- The deployer does not upload or clone files. Run it on the server from the existing repository.
- `START_COMMAND` must run a persistent production server and the application must listen on `PORT` / `APP_PORT`. A Vite `preview` server is not usually the ideal production server for an application with a backend.
- The defaults assume `npm ci`, `npm run build`, and `npm run start` are defined. Verify `package.json` first.
- The systemd service runs as `SERVICE_USER` with the repository as its working directory. That user must be able to read the project and write to any runtime data directories the app needs. Do not blindly change ownership of the whole repository if it contains deployment credentials.
- This script installs packages with apt and configures system-wide Nginx/systemd files. Run it only on a server you administer. Back up existing Nginx/service configuration first if names conflict.
- If the app is a static-only Vite frontend, use an Nginx static-file configuration instead of a reverse proxy. This helper assumes a Node server exists.
