import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions
from agents.base import BaseAgent
from utils import state


class OrchestratorAgent(BaseAgent):
    def __init__(self, config, coder, tester):
        super().__init__(config, "Agent2-Orchestrator")
        self.coder = coder
        self.tester = tester

    def run(self, issue, project, github) -> None:
        task_type = self._keyword_classify(issue)
        used_ai = False

        if task_type is None:
            self.log_info(f"[{project.name}] #{issue.number} ambiguous — calling Haiku.")
            task_type = asyncio.run(self._haiku_classify(issue))
            used_ai = True

        if task_type is None:
            self.log_warn(f"[{project.name}] Could not classify. Defaulting to coding.")
            task_type = "coding"

        method = "Haiku" if used_ai else "keyword match (free)"
        github.add_issue_comment(
            issue.number,
            f"**Agent 2 — Orchestrator** [{project.name}]\n\n"
            f"Classified as `{task_type}` via {method}.\n"
            f"Routing to {'Coder' if task_type == 'coding' else 'Tester'} agent.",
        )

        new_label = "agent:coding" if task_type == "coding" else "agent:testing"
        github.set_issue_labels(issue.number, [new_label])
        state.add_in_progress(project.name, issue.number)
        github.add_issue_to_project(issue.node_id)

        if task_type == "coding":
            self.coder.run(issue, project, github)
        else:
            self.tester.run(issue, project, github)

    def _keyword_classify(self, issue) -> str | None:
        text = f"{issue.title} {issue.body or ''}".lower()
        labels = [l.name.lower() for l in issue.labels]
        if "agent:coding" in labels:
            return "coding"
        if "agent:testing" in labels:
            return "testing"
        has_c = any(k in text for k in self.config.coding_keywords)
        has_t = any(k in text for k in self.config.testing_keywords)
        if has_t and not has_c:
            return "testing"
        if has_c and not has_t:
            return "coding"
        return None

    async def _haiku_classify(self, issue) -> str | None:
        prompt = (
            f"Classify this GitHub issue as one word: 'coding' or 'testing'.\n"
            f"coding = writing or fixing code. testing = verifying existing code.\n\n"
            f"Title: {issue.title}\nBody: {(issue.body or '')[:300]}\n\n"
            f"One word only."
        )
        result = ""
        try:
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(model="haiku", allowed_tools=[], max_turns=1),
            ):
                if hasattr(message, "result"):
                    result = message.result.strip().lower()
        except Exception as e:
            self.log_error(f"Haiku classify failed: {e}")
            return None
        if "coding" in result:
            return "coding"
        if "testing" in result:
            return "testing"
        return None
