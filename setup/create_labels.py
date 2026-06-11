import os
import sys
from github import Github
from dotenv import load_dotenv

load_dotenv("/opt/agent-system/.env")

g = Github(os.environ["GITHUB_TOKEN"])
repo = g.get_repo(os.environ["GITHUB_REPO"])

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

print(f"Creating labels in: {os.environ['GITHUB_REPO']}")
for name, color, desc in labels:
    try:
        repo.create_label(name=name, color=color, description=desc)
        print(f"  Created:  {name}")
    except Exception as e:
        print(f"  Skipped:  {name} ({e})")

print("\nDone.")
