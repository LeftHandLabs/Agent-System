import os
import json
import time
from flask import Flask, render_template, jsonify
from github import Github
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv("/opt/agent-system/.env")
os.chdir("/opt/agent-system")

app = Flask(__name__, template_folder="templates")

_cache = {"data": None, "ts": 0}
CACHE_TTL = 55


def age_string(dt) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    mins = int(delta.total_seconds() // 60)
    if mins < 2:
        return "just now"
    if mins < 60:
        return f"{mins}m ago"
    if mins < 1440:
        return f"{mins // 60}h ago"
    return f"{delta.days}d ago"


def get_data() -> dict:
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < CACHE_TTL:
        return _cache["data"]

    g = Github(os.environ["GITHUB_TOKEN"])
    repo = g.get_repo(os.environ["GITHUB_REPO"])

    def count(label, s="open"):
        return repo.get_issues(state=s, labels=[label]).totalCount

    counts = {
        "queued":      count("agent:queue"),
        "in_progress": count("agent:in-progress"),
        "needs_human": count("agent:clarification-needed"),
        "failed":      count("agent:failed"),
        "done":        count("agent:done", "closed"),
    }

    attention = []
    for issue in repo.get_issues(state="open", labels=["agent:clarification-needed"]):
        question = ""
        for comment in reversed(list(issue.get_comments())):
            if "Needs Clarification" in comment.body:
                for line in comment.body.splitlines():
                    if line.strip().startswith(">"):
                        question = line.strip().lstrip("> ").strip()
                        break
                break
        attention.append({
            "number": issue.number,
            "title": issue.title,
            "url": issue.html_url,
            "waiting": age_string(issue.updated_at),
            "question": question,
        })

    recent = []
    for issue in repo.get_issues(state="all", sort="updated", direction="desc"):
        agent_labels = [l.name for l in issue.labels if l.name.startswith("agent:")]
        if not agent_labels:
            continue
        recent.append({
            "number": issue.number,
            "title": issue.title,
            "url": issue.html_url,
            "labels": agent_labels,
            "age": age_string(issue.updated_at),
        })
        if len(recent) >= 30:
            break

    state_data = {}
    try:
        with open("/opt/agent-system/state.json") as f:
            state_data = json.load(f)
    except Exception:
        pass

    last_cycle = state_data.get("last_cycle_at", "")
    if last_cycle:
        try:
            dt = datetime.fromisoformat(last_cycle)
            last_cycle = age_string(dt)
        except Exception:
            pass

    data = {
        "counts": counts,
        "attention": attention,
        "recent": recent,
        "last_cycle": last_cycle or "Never",
        "repo": os.environ.get("GITHUB_REPO", ""),
    }
    _cache["data"] = data
    _cache["ts"] = now
    return data


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/overview")
def overview():
    try:
        return jsonify(get_data())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/logs")
def logs():
    try:
        with open("/opt/agent-system/logs/agent-system.log") as f:
            lines = f.readlines()[-150:]
        return jsonify({"lines": [l.rstrip() for l in reversed(lines)]})
    except Exception:
        return jsonify({"lines": ["(No log file found yet)"]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
