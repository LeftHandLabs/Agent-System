# Claude Agent System

An autonomous multi-agent system that monitors GitHub repositories for issues, implements fixes using the Claude AI, runs tests, and manages the full issue lifecycle — without human intervention.

## How it works

Label any GitHub issue with `agent:queue` and the system picks it up automatically. It classifies the issue, writes code, pushes a branch, runs your test suite, and closes the issue when tests pass. If something needs clarification, it asks. If tests fail, it files a new fix issue and starts again.

```
Issue labelled agent:queue
        │
        ▼
  Agent 1 (Monitor)
  Polls GitHub on a schedule
        │
        ▼
  Agent 2 (Orchestrator)
  Classifies: coding or testing?
        │
   ─────┴──────
   │           │
   ▼           ▼
Agent 3     Agent 4
(Coder)     (Tester)
Writes      Runs your
the code    test suite
```

**Coder** — clones the repo, creates a branch (`agent/coding/issue-N`), runs Claude (Sonnet) with file tools, commits and pushes, then files a `[TEST]` issue for the Tester.

**Tester** — checks out the branch, runs `pre_test_command` then `test_command`. On pass: closes the issue. On fail: summarises the failure and files a `[FIX]` issue that re-enters the pipeline.

## Requirements

- Python 3.11+
- A GitHub personal access token (repo + project scope)
- Claude Code CLI installed and authenticated (`claude login`) **or** an `ANTHROPIC_API_KEY`
- Git configured on the host machine
- Tools required to test your code

## Setup

```bash
# 1. Install Claude Code CLI
curl -fsSL https://claude.ai/install.sh | bash

# 1a. Verify that claude is working
claude --version

# 1b. Verify you are logged in
claude -p "respond with just the word hello"

# 2. Clone and install
git clone https://github.com/LeftHandLabs/Agent-System /opt/agent-system
cd /opt/agent-system
pip install -r requirements.txt

# Get your project ID
cd /opt/agent-system && source venv/bin/activate
python3 setup/get_project_ids.py

#You will see output like:
#    Title:  LeftHandLabs Agents
#    Number: 1
#    ID:     PVT_kwDOBxxxxxxxxxxxxxxx


# 3a. Go to: https://github.com/settings/tokens/new (this is the classic token page, not fine-grained) Scopes: tick repo (full repo access) and project (full project access)

# 3. Configure
cp .env.example .env
cp config.example.yaml config.yaml
# Edit both files with your details

# 4. Create GitHub labels in each target repo
GITHUB_REPO=owner/repo python setup/create_labels.py

# 5. Run
python3 main.py

# 6. (Optional) Run the dashboard in a separate terminal
python3 dashboard/app.py

# 7. Configure services
```

## Configuration

`config.yaml` controls all runtime behaviour. Key settings:

| Setting | Description |
|---|---|
| `scheduler.interval_minutes` | How often the monitor polls GitHub |
| `usage.threshold_pct` | Skip cycle if 5-hour Claude usage is at or above this % |
| `orchestrator.max_issues_per_cycle` | Max issues processed per poll cycle |
| `coder.model` / `tester.model` | Claude model for each agent (`sonnet`, `haiku`, etc.) |
| `projects[].test_command` | Shell command to run your test suite |
| `projects[].pre_test_command` | Setup command run before tests (e.g. `npm install`) |

The system is language-agnostic — configure `test_command` and `pre_test_command` for any stack (Node, Python, Ruby, Go, etc.).

## GitHub labels

The system tracks state entirely through GitHub issue labels. Create them once with `setup/create_labels.py`.

| Label | Meaning |
|---|---|
| `agent:queue` | Waiting to be picked up — **you apply this to trigger the system** |
| `agent:in-progress` | Currently being worked on |
| `agent:coding` / `agent:testing` | Assigned agent type |
| `agent:done` | Completed and closed |
| `agent:failed` | Agent hit an error — needs human review |
| `agent:clarification-needed` | Agent asked a question; waiting for your reply |

## Dashboard

A Flask dashboard runs on port 5001 and shows issue counts, items needing attention, and recent activity.

```bash
python dashboard/app.py
```

## Multi-project support

Add multiple entries under `projects:` in `config.yaml` to monitor several repositories simultaneously. Each project has its own workspace path, test commands, and GitHub project board.

## Constraints

- The agent will never run database migrations automatically — if a migration is needed it creates the file and notes it in the summary for you to run manually.
- The agent will never modify `.env` files.
- If an issue description is too vague, the agent posts a clarification question as a comment and waits rather than guessing.
