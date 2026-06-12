"""
Interactive setup wizard for the agent system.
Run this once to generate .env and config.yaml.
"""

import subprocess
import sys
from pathlib import Path
from getpass import getpass

try:
    import requests
    import yaml
except ImportError:
    print("Missing dependencies. Run: pip install requests pyyaml")
    sys.exit(1)

BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"
CONFIG_FILE = BASE_DIR / "config.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ask(prompt, default=None, secret=False):
    suffix = f" [{default}]" if default is not None else ""
    display = f"{prompt}{suffix}: "
    value = (getpass(display) if secret else input(display)).strip()
    return value if value else default


def yn(prompt, default=True):
    hint = "Y/n" if default else "y/N"
    raw = input(f"{prompt} [{hint}]: ").strip().lower()
    if not raw:
        return default
    return raw.startswith("y")


def pick_one(items, label_fn, prompt):
    for i, item in enumerate(items, 1):
        print(f"  {i}. {label_fn(item)}")
    while True:
        raw = input(f"{prompt} (number): ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(items):
                return items[idx]
        except ValueError:
            pass
        print("  Invalid — try again.")


def pick_many(items, label_fn, prompt):
    for i, item in enumerate(items, 1):
        print(f"  {i}. {label_fn(item)}")
    print(f"  0. All of the above")
    while True:
        raw = input(f"{prompt} (comma-separated numbers, or 0 for all): ").strip()
        if raw == "0":
            return list(items)
        try:
            indices = [int(x.strip()) - 1 for x in raw.split(",")]
            selected = [items[i] for i in indices if 0 <= i < len(items)]
            if selected:
                return selected
        except (ValueError, IndexError):
            pass
        print("  Invalid — try again.")


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def gh_get(token, path, params=None):
    resp = requests.get(
        f"https://api.github.com{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        params=params or {},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def gh_graphql(token, query, variables=None):
    resp = requests.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def validate_token(token):
    try:
        return gh_get(token, "/user")
    except Exception:
        return None


def fetch_repos(token, username):
    repos = []
    page = 1
    while True:
        batch = gh_get(token, f"/user/repos", {
            "per_page": 100, "page": page, "sort": "updated", "affiliation": "owner"
        })
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_user_projects(token):
    query = "{ viewer { projectsV2(first: 50) { nodes { id number title } } } }"
    try:
        data = gh_graphql(token, query)
        return data["data"]["viewer"]["projectsV2"]["nodes"]
    except Exception:
        return []


def detect_stack(token, owner, repo):
    """Return (test_command, pre_test_command) by probing the repo for known config files."""
    checks = [
        ("composer.json",    "php artisan test --no-ansi 2>&1", "composer install --no-interaction --quiet"),
        ("package.json",     "npm test 2>&1",                   "npm install --silent"),
        ("pyproject.toml",   "pytest 2>&1",                     "pip install -e . --quiet"),
        ("requirements.txt", "pytest 2>&1",                     "pip install -r requirements.txt --quiet"),
        ("Cargo.toml",       "cargo test 2>&1",                 ""),
        ("go.mod",           "go test ./... 2>&1",              ""),
    ]
    for filename, test_cmd, pre_cmd in checks:
        try:
            gh_get(token, f"/repos/{owner}/{repo}/contents/{filename}")
            return test_cmd, pre_cmd
        except Exception:
            pass
    return "", ""


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------

def main():
    print()
    print("=" * 62)
    print("   Agent System — Setup Wizard")
    print("=" * 62)
    print()

    # ── Step 1: GitHub token ──────────────────────────────────────────
    print("Step 1 of 5: GitHub Personal Access Token")
    print("  Create one at: https://github.com/settings/tokens")
    print("  Required scopes: repo, project, read:org")
    print()

    token = None
    user_info = None
    while not user_info:
        token = ask("GitHub Personal Access Token", secret=True)
        if not token:
            print("  Token is required.\n")
            continue
        print("  Validating ...", end=" ", flush=True)
        user_info = validate_token(token)
        if user_info:
            print(f"OK (logged in as {user_info['login']})")
        else:
            print("FAILED — check the token and try again.")
    username = user_info["login"]
    print()

    # ── Step 2: Anthropic API key ─────────────────────────────────────
    print("Step 2 of 5: Anthropic API Key")
    print("  Get one at: https://console.anthropic.com/")
    print()
    anthropic_key = ask("Anthropic API Key (leave blank to add manually later)", secret=True) or ""
    print()

    # ── Step 3: Choose repos ──────────────────────────────────────────
    print("Step 3 of 5: Select repositories to monitor")
    print("  Fetching your repositories ...", end=" ", flush=True)
    try:
        all_repos = fetch_repos(token, username)
    except Exception as e:
        print(f"FAILED ({e})")
        sys.exit(1)
    print(f"found {len(all_repos)}.")
    print()

    if not all_repos:
        print("No repositories found. Check that the token has 'repo' scope.")
        sys.exit(1)

    selected_repos = pick_many(
        all_repos,
        lambda r: f"{r['full_name']}{' (private)' if r['private'] else ''}",
        "Which repos should the agent monitor?",
    )
    print()

    # ── Step 4: Configure each repo ───────────────────────────────────
    print("Step 4 of 5: Configure each selected repository")
    print()

    # Pick one project board for all repos — issues are routed by which
    # repo they are filed in, not by the board. The board is only used
    # to add cards for visibility.
    print("  Fetching your GitHub Projects ...", end=" ", flush=True)
    user_projects = fetch_user_projects(token)
    if user_projects:
        print(f"found {len(user_projects)}.")
    else:
        print("none found — you can add project_id / project_number manually in config.yaml later.")
    print()

    shared_project_id = ""
    shared_project_number = 0
    if user_projects:
        if len(user_projects) == 1:
            proj = user_projects[0]
            print(f"  Using project board: #{proj['number']} {proj['title']}")
            shared_project_id = proj["id"]
            shared_project_number = proj["number"]
        else:
            print("  All repos will share one project board for issue tracking.")
            print("  (Routing to the right codebase is determined by which repo the issue is filed in.)")
            print()
            proj = pick_one(
                user_projects,
                lambda p: f"#{p['number']} {p['title']}",
                "  Which project board should all repos use?",
            )
            shared_project_id = proj["id"]
            shared_project_number = proj["number"]
    print()

    workspace_base = "/opt/agent-system/workspace"
    projects = []

    for repo in selected_repos:
        full_name = repo["full_name"]
        repo_name = repo["name"]
        owner = repo["owner"]["login"]
        default_branch = repo.get("default_branch", "main")

        print(f"  ── {full_name} ──")

        project_id = shared_project_id
        project_number = shared_project_number

        # Auto-detect test stack
        print(f"  Detecting test stack ...", end=" ", flush=True)
        detected_test, detected_pre = detect_stack(token, owner, repo_name)
        if detected_test:
            print(f"detected ({detected_test.split()[0]})")
        else:
            print("not detected")

        workspace   = ask("  Local workspace path", default=f"{workspace_base}/{repo_name}")
        base_branch = ask("  Base branch",          default=default_branch)
        test_cmd    = ask("  Test command",          default=detected_test or "")
        pre_cmd     = ask("  Pre-test command",      default=detected_pre or "")
        print()

        projects.append({
            "name":            repo_name,
            "repo":            full_name,
            "project_id":      project_id,
            "project_number":  project_number,
            "workspace":       workspace,
            "base_branch":     base_branch,
            "test_command":    test_cmd,
            "pre_test_command": pre_cmd,
            "enabled":         True,
        })

    # ── Step 5: Agent behaviour ───────────────────────────────────────
    print("Step 5 of 5: Agent behaviour settings")
    print()

    existing_cfg = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            existing_cfg = yaml.safe_load(f) or {}

    interval        = int(ask("Monitor interval (minutes)",             default=str(existing_cfg.get("scheduler", {}).get("interval_minutes", 60))))
    max_issues      = int(ask("Max issues per cycle",                   default=str(existing_cfg.get("orchestrator", {}).get("max_issues_per_cycle", 1))))
    usage_threshold = int(ask("API usage threshold % (pause if above)", default=str(existing_cfg.get("usage", {}).get("threshold_pct", 80))))
    coder_model     = ask("Coder agent model",                          default=existing_cfg.get("coder", {}).get("model", "sonnet"))
    coder_turns     = int(ask("Coder max turns",                        default=str(existing_cfg.get("coder", {}).get("max_turns", 15))))
    print()

    # ── Write files ───────────────────────────────────────────────────
    print("Writing configuration files ...")

    env_content = (
        f"GITHUB_TOKEN={token}\n"
        f"ANTHROPIC_API_KEY={anthropic_key}\n"
        "LOG_LEVEL=INFO\n"
    )
    ENV_FILE.write_text(env_content)
    print(f"  Wrote {ENV_FILE}")

    config = {
        "scheduler": {
            "interval_minutes": interval,
        },
        "usage": {
            "threshold_pct": usage_threshold,
        },
        "orchestrator": {
            "max_issues_per_cycle": max_issues,
            "coding_keywords": existing_cfg.get("orchestrator", {}).get("coding_keywords", [
                "fix", "bug", "implement", "add", "build", "create",
                "refactor", "update", "feature", "change",
            ]),
            "testing_keywords": existing_cfg.get("orchestrator", {}).get("testing_keywords", [
                "test", "verify", "check", "validate", "qa", "coverage",
            ]),
        },
        "coder":  {"model": coder_model, "max_turns": coder_turns},
        "tester": {"model": "haiku",     "max_turns": 1},
        "github": {
            "default_base_branch": "main",
            "owner_username":      username,
        },
        "projects": projects,
    }

    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"  Wrote {CONFIG_FILE}")
    print()

    # ── Post-install steps ────────────────────────────────────────────
    print()
    if yn("Run post-setup steps now? (venv, pip install, create labels, clone workspaces)", default=True):
        venv_python = BASE_DIR / "venv" / "bin" / "python3"
        venv_pip    = BASE_DIR / "venv" / "bin" / "pip"

        steps = [
            ("Creating virtual environment",  [sys.executable, "-m", "venv", str(BASE_DIR / "venv")]),
            ("Installing dependencies",        [str(venv_pip), "install", "-r", str(BASE_DIR / "requirements.txt")]),
            ("Creating GitHub labels",         [str(venv_python), str(BASE_DIR / "setup" / "create_labels.py")]),
            ("Cloning workspaces",             [str(venv_python), str(BASE_DIR / "setup" / "clone_workspaces.py")]),
        ]

        all_ok = True
        for description, cmd in steps:
            print(f"\n  {description} ...")
            result = subprocess.run(cmd, cwd=str(BASE_DIR))
            if result.returncode != 0:
                print(f"  ✗ Failed (exit {result.returncode}). Fix the issue and re-run this step manually.")
                all_ok = False
                if not yn("  Continue with remaining steps?", default=False):
                    break
            else:
                print(f"  ✓ Done.")

        print()
        if all_ok:
            print("  All steps completed successfully.")
        else:
            print("  Some steps failed — see output above.")
    else:
        print()
        print("  Run these manually when ready:")
        print("    python3 -m venv venv && source venv/bin/activate")
        print("    pip install -r requirements.txt")
        print("    python3 setup/create_labels.py")
        print("    python3 setup/clone_workspaces.py")

    # ── Systemd services ──────────────────────────────────────────────
    print()
    if yn("Create and start systemd services? (requires sudo)", default=True):
        venv_python = BASE_DIR / "venv" / "bin" / "python3"
        service_script = BASE_DIR / "setup" / "create_services.py"
        cmd = ["sudo", str(venv_python), str(service_script), "--dir", str(BASE_DIR)]
        result = subprocess.run(cmd, cwd=str(BASE_DIR))
        if result.returncode != 0:
            print("  Service setup failed — run manually:")
            print(f"    sudo python3 setup/create_services.py")
    else:
        print()
        print("  Run manually when ready:")
        print("    sudo python3 setup/create_services.py")

    # ── Summary ───────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print("  Setup complete!")
    print()
    print(f"  Configured {len(projects)} project(s):")
    for p in projects:
        print(f"    - {p['repo']}")
    print()
    print("  Services:")
    print("    sudo systemctl status agent-system")
    print("    sudo systemctl status agent-dashboard")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
