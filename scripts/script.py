#!/usr/bin/env python3
"""Deploy a Node/Vite app behind Nginx with HTTPS on Ubuntu/Debian."""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
ENV_FILE = SCRIPT_DIR / ".env"


def load_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(
            f"Missing {path}. Copy .env.example to .env and configure it."
        )

    values: dict[str, str] = {}

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[7:].strip()

        if "=" not in line:
            raise SystemExit(f"Invalid .env line: {raw}")

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        values[key] = value

    return values


def run(
    command: str | list[str],
    *,
    cwd: Path | None = None,
    env=None,
) -> None:
    printable = command if isinstance(command, str) else shlex.join(command)
    print(f"\n$ {printable}", flush=True)
    subprocess.run(
        command,
        cwd=cwd,
        env=env,
        shell=isinstance(command, str),
        check=True,
    )


def required(cfg: dict[str, str], key: str) -> str:
    value = cfg.get(key, "").strip()

    if not value or value.startswith("CHANGE_ME"):
        raise SystemExit(f"Set {key} in {ENV_FILE}")

    return value


def main() -> None:
    cfg = load_env(ENV_FILE)

    domain = required(cfg, "DOMAIN").lower()
    email = required(cfg, "LETSENCRYPT_EMAIL")
    service_user = required(cfg, "SERVICE_USER")

    app_name = cfg.get("APP_NAME", "barcode-store-manager").strip()
    app_port = cfg.get("APP_PORT", "3000").strip()
    start_command = cfg.get("START_COMMAND", "npm run start").strip()
    build_command = cfg.get("BUILD_COMMAND", "npm run build").strip()
    node_major = cfg.get("NODE_MAJOR", "22").strip()
    install_command = cfg.get("INSTALL_COMMAND", "npm install").strip()

    if not re.fullmatch(r"[a-z_][a-z0-9_-]*[$]?", service_user):
        raise SystemExit(
            "SERVICE_USER must be a valid Linux username in scripts/.env."
        )

    if subprocess.run(
        ["id", "-u", service_user],
        capture_output=True,
        text=True,
    ).returncode != 0:
        raise SystemExit(
            f"Linux user '{service_user}' does not exist. "
            "Set SERVICE_USER to an existing user in scripts/.env."
        )

    service_home_result = subprocess.run(
        ["getent", "passwd", service_user],
        capture_output=True,
        text=True,
        check=True,
    )
    service_home = service_home_result.stdout.strip().split(":")[5]

    if not service_home:
        raise SystemExit(f"Could not determine the home directory of {service_user}.")

    if not os.access(REPO_ROOT, os.R_OK | os.X_OK):
        raise SystemExit(f"The current user cannot access repository: {REPO_ROOT}")

    nginx_site = f"/etc/nginx/sites-available/{app_name}"
    nginx_enabled = f"/etc/nginx/sites-enabled/{app_name}"
    service_file = f"/etc/systemd/system/{app_name}.service"

    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]", domain) or "." not in domain:
        raise SystemExit(f"DOMAIN does not look like a valid domain: {domain}")

    if not app_port.isdigit() or not 1 <= int(app_port) <= 65535:
        raise SystemExit("APP_PORT must be a valid TCP port.")

    if not re.fullmatch(r"[a-zA-Z0-9_-]+", app_name):
        raise SystemExit(
            "APP_NAME may contain only letters, digits, underscores and hyphens."
        )

    if not shutil.which("sudo") and os.geteuid() != 0:
        raise SystemExit("Run as root or install sudo and run this script with sudo.")

    if not (REPO_ROOT / "package.json").is_file():
        raise SystemExit(
            f"package.json not found at {REPO_ROOT}. "
            "Run this from the repository's scripts directory."
        )

    print("Deployment configuration:")
    print(f"  Repository: {REPO_ROOT}")
    print(f"  Domain:     {domain}")
    print(f"  App port:   {app_port}")
    print(f"  App user:   {service_user}")
    print(f"  Home:       {service_home}")

    print(
        "\nThis deployer targets Ubuntu/Debian and assumes DNS for DOMAIN "
        "points to this server."
    )
    print(
        "It installs Node.js, Nginx and Certbot if needed, builds the app, "
        "and configures systemd + HTTPS."
    )

    if cfg.get("CONFIRM_DEPLOY", "no").lower() not in ("yes", "true", "1"):
        raise SystemExit(
            "Set CONFIRM_DEPLOY=yes in scripts/.env after reviewing the settings."
        )

    sudo = [] if os.geteuid() == 0 else ["sudo"]

    run(sudo + ["apt-get", "update"])

    run(
        sudo
        + [
            "apt-get",
            "install",
            "-y",
            "curl",
            "ca-certificates",
            "nginx",
            "certbot",
            "python3-certbot-nginx",
        ]
    )

    run(
        sudo
        + [
            "bash",
            "-lc",
            f"curl -fsSL https://deb.nodesource.com/setup_{shlex.quote(node_major)}.x | bash -",
        ]
    )

    run(sudo + ["apt-get", "install", "-y", "nodejs"])

    # Install dependencies and build as the user running the deploy script.
    run(install_command, cwd=REPO_ROOT)
    run(build_command, cwd=REPO_ROOT)

    # Run the app as SERVICE_USER from .env.
    unit = f"""[Unit]
Description={app_name}
After=network.target

[Service]
Type=simple
User={service_user}
WorkingDirectory={REPO_ROOT}
Environment=HOME={service_home}
Environment=NODE_ENV=production
Environment=PORT={app_port}
ExecStart=/bin/bash -lc {shlex.quote(start_command)}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

    nginx = f"""server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    location / {{
        proxy_pass http://127.0.0.1:{app_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
    }}
}}
"""

    unit_tmp = Path("/tmp") / f"{app_name}.service"
    nginx_tmp = Path("/tmp") / f"{app_name}.nginx"

    unit_tmp.write_text(unit, encoding="utf-8")
    nginx_tmp.write_text(nginx, encoding="utf-8")

    run(sudo + ["install", "-m", "0644", str(unit_tmp), service_file])
    run(sudo + ["install", "-m", "0644", str(nginx_tmp), nginx_site])
    run(sudo + ["ln", "-sfn", nginx_site, nginx_enabled])
    run(sudo + ["nginx", "-t"])
    run(sudo + ["systemctl", "daemon-reload"])
    run(sudo + ["systemctl", "enable", "--now", f"{app_name}.service"])
    run(sudo + ["systemctl", "restart", f"{app_name}.service"])
    run(sudo + ["systemctl", "reload", "nginx"])

    # Request an SSL certificate for the main domain only.
    run(
        sudo
        + [
            "certbot",
            "--nginx",
            "--non-interactive",
            "--agree-tos",
            "--redirect",
            "-m",
            email,
            "-d",
            domain,
        ]
    )

    print("\nDeployment commands completed.")
    print(f"Service status: sudo systemctl status {app_name}")
    print(f"Service logs:   sudo journalctl -u {app_name} -f")
    print(f"HTTPS URL:      https://{domain}")
    print(
        "\nIf Certbot fails, confirm the domain DNS points to this server "
        "and ports 80/443 are reachable."
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(
            f"\nDeployment failed (exit code {exc.returncode}).",
            file=sys.stderr,
        )
        sys.exit(exc.returncode)