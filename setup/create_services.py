"""
Creates and enables systemd services for the agent system and dashboard.
Must be run with sudo (or as root) so it can write to /etc/systemd/system/.

Usage:
    sudo python3 setup/create_services.py
    sudo python3 setup/create_services.py --dir /opt/agent-system --user myuser
"""

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path


AGENT_SERVICE = "agent-system"
DASHBOARD_SERVICE = "agent-dashboard"


def write_service(name: str, content: str) -> Path:
    path = Path(f"/etc/systemd/system/{name}.service")
    path.write_text(content)
    print(f"  Wrote {path}")
    return path


def run(cmd: list, description: str) -> bool:
    print(f"  {description} ...", end=" ", flush=True)
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("OK")
        return True
    print(f"FAILED (exit {result.returncode})")
    return False


def main():
    parser = argparse.ArgumentParser(description="Create agent-system systemd services")
    parser.add_argument("--dir",  default="/opt/agent-system", help="Install directory")
    parser.add_argument("--user", default=None,                help="User to run services as")
    args = parser.parse_args()

    install_dir = Path(args.install_dir if hasattr(args, "install_dir") else args.dir)
    run_as_user = args.user or os.environ.get("SUDO_USER") or getpass.getuser()
    venv_python = install_dir / "venv" / "bin" / "python3"

    if os.geteuid() != 0:
        print("Error: this script must be run with sudo.")
        sys.exit(1)

    if not install_dir.exists():
        print(f"Error: install directory {install_dir} does not exist.")
        sys.exit(1)

    if not venv_python.exists():
        print(f"Error: venv not found at {venv_python}. Run setup.py first.")
        sys.exit(1)

    print()
    print(f"  Install dir : {install_dir}")
    print(f"  Run as user : {run_as_user}")
    print(f"  Python      : {venv_python}")
    print()

    # ── agent-system.service ─────────────────────────────────────────
    agent_unit = f"""\
[Unit]
Description=Claude Agent System
After=network.target
Wants=network-online.target

[Service]
Type=simple
User={run_as_user}
WorkingDirectory={install_dir}
ExecStart={venv_python} {install_dir}/main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier={AGENT_SERVICE}

[Install]
WantedBy=multi-user.target
"""

    # ── agent-dashboard.service ──────────────────────────────────────
    dashboard_unit = f"""\
[Unit]
Description=Claude Agent System Dashboard
After=network.target
Wants=network-online.target

[Service]
Type=simple
User={run_as_user}
WorkingDirectory={install_dir}
ExecStart={venv_python} {install_dir}/dashboard/app.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier={DASHBOARD_SERVICE}

[Install]
WantedBy=multi-user.target
"""

    print("Writing service files ...")
    write_service(AGENT_SERVICE, agent_unit)
    write_service(DASHBOARD_SERVICE, dashboard_unit)
    print()

    print("Registering and starting services ...")
    ok = True
    ok &= run(["systemctl", "daemon-reload"],                           "Reloading systemd")
    ok &= run(["systemctl", "enable",  AGENT_SERVICE],                  f"Enabling {AGENT_SERVICE}")
    ok &= run(["systemctl", "enable",  DASHBOARD_SERVICE],              f"Enabling {DASHBOARD_SERVICE}")
    ok &= run(["systemctl", "restart", AGENT_SERVICE],                  f"Starting {AGENT_SERVICE}")
    ok &= run(["systemctl", "restart", DASHBOARD_SERVICE],              f"Starting {DASHBOARD_SERVICE}")

    print()
    if ok:
        print("  Services are running. Useful commands:")
        print(f"    sudo systemctl status  {AGENT_SERVICE}")
        print(f"    sudo systemctl status  {DASHBOARD_SERVICE}")
        print(f"    sudo journalctl -fu    {AGENT_SERVICE}")
        print(f"    sudo journalctl -fu    {DASHBOARD_SERVICE}")
        print(f"    sudo systemctl restart {AGENT_SERVICE}")
        print(f"    sudo systemctl restart {DASHBOARD_SERVICE}")
    else:
        print("  One or more steps failed — check output above.")
        sys.exit(1)
    print()


if __name__ == "__main__":
    main()
