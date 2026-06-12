import os
import sys

os.chdir("/opt/agent-system")
sys.path.insert(0, "/opt/agent-system")

from dotenv import load_dotenv
from github import Github
from utils.config import Config

load_dotenv("/opt/agent-system/.env")

labels = [
    ("agent:queue",                "0075ca", "Waiting to be picked up by agents"),
    ("agent:coding",               "e4e669", "Assigned to the coder agent"),
    ("agent:testing",              "d93f0b", "Assigned to the tester agent"),
    ("agent:in-progress",          "ededed", "Agent currently working on this"),
    ("agent:done",                 "0e8a16", "Agent completed this task"),
    ("agent:failed",               "b60205", "Agent encountered a failure"),
    ("agent:clarification-needed", "e99695", "Agent needs input from owner"),
    ("agent:needs-human",          "5319e7", "Escalated to human review"),
]

config = Config.load()
g = Github(config.github_token)

repos = sys.argv[1:] if len(sys.argv) > 1 else [p.repo for p in config.enabled_projects]

for repo_name in repos:
    print(f"\nCreating labels in: {repo_name}")
    repo = g.get_repo(repo_name)
    for name, color, desc in labels:
        try:
            repo.create_label(name=name, color=color, description=desc)
            print(f"  Created:  {name}")
        except Exception as e:
            print(f"  Skipped:  {name} ({e})")

print("\nDone.")
