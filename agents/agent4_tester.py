import asyncio
import re
from claude_agent_sdk import query, ClaudeAgentOptions
from agents.base import BaseAgent
from utils import state


class TesterAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config, "Agent4-Tester")

    def run(self, issue, project, github) -> None:
        self.log_info(f"[{project.name}] Testing: #{issue.number} — {issue.title}")
        try:
            github.set_issue_labels(issue.number, ["agent:testing", "agent:in-progress"])
            github.add_issue_comment(
                issue.number,
                f"**Agent 4 — Tester** [{project.name}]\n\nRunning tests. 🧪",
            )
            branch = self._extract_branch(issue.body)
            if not branch:
                raise ValueError("Could not find branch name in issue body.")
            self._checkout_branch(branch, project.workspace)
            if project.pre_test_command:
                self._run_pre_test(project, github)
            returncode, stdout, stderr = github.run_command(project.test_command)
            output = f"Exit code: {returncode}\n\n{stdout}\n{stderr}"
            self.log_info(f"[{project.name}] Tests exited with code {returncode}")
            if returncode == 0:
                self._handle_pass(issue, project, github, branch, output)
            else:
                self._handle_fail(issue, project, github, output)
        except Exception as e:
            self.log_error(f"[{project.name}] Tester failed #{issue.number}: {e}")
            try:
                github.set_issue_labels(issue.number, ["agent:testing", "agent:failed"])
            except Exception as label_err:
                self.log_error(f"[{project.name}] Could not set agent:failed label: {label_err}")
            try:
                github.add_issue_comment(
                    issue.number,
                    f"**Agent 4 — FAILED** ❌\n\nError: `{e}`\n\nNeeds human review.",
                )
            except Exception as comment_err:
                self.log_error(f"[{project.name}] Could not post failure comment: {comment_err}")
            if self.config.owner_username:
                try:
                    github.assign_issue(issue.number, self.config.owner_username)
                except Exception as assign_err:
                    self.log_error(f"[{project.name}] Could not assign issue: {assign_err}")
        finally:
            state.remove_in_progress(project.name, issue.number)

    def _run_pre_test(self, project, github) -> None:
        rc, _, err = github.run_command(project.pre_test_command)
        if rc != 0:
            self.log_warn(f"[{project.name}] Pre-test warning: {err[:200]}")

    def _handle_pass(self, issue, project, github, branch: str, output: str) -> None:
        self.log_info(f"PASSED #{issue.number} — opening PR")
        pr = github.create_pull_request(
            title=issue.title,
            body=(
                f"Closes #{issue.number}\n\n"
                f"## Changes\n\nImplemented by the coding agent.\n\n"
                f"## Test Results\n\n"
                f"<details><summary>Output</summary>\n\n```\n{output[:2000]}\n```\n</details>"
            ),
            head=branch,
            base=project.base_branch,
        )
        github.add_issue_comment(
            issue.number,
            f"**Agent 4 — PASSED** ✅\n\nAll tests passed.\n\n"
            f"Pull request opened: {pr.html_url}\n\n"
            f"<details><summary>Test output</summary>\n\n```\n{output[:2000]}\n```\n</details>",
        )
        github.set_issue_labels(issue.number, ["agent:testing", "agent:done"])
        github.close_issue(issue.number)

    def _handle_fail(self, issue, project, github, output: str) -> None:
        self.log_info(f"FAILED #{issue.number} — calling Haiku to summarise")
        summary = asyncio.run(self._summarise_failure(output[:4000]))
        github.add_issue_comment(
            issue.number,
            f"**Agent 4 — FAILED** ❌\n\n{summary}\n\nCreating fix task.",
        )
        github.set_issue_labels(issue.number, ["agent:testing", "agent:failed"])
        github.create_issue(
            title=f"[FIX] {issue.title}",
            body=(
                f"## Fix Required\n\nTests failed for #{issue.number}.\n\n"
                f"## Failure Summary\n\n{summary}\n\n"
                f"## Test Output\n\n"
                f"<details><summary>Show output</summary>\n\n"
                f"```\n{output[:3000]}\n```\n</details>\n\n"
                f"## Original Test Issue\n\n#{issue.number}"
            ),
            labels=["agent:queue"],
        )

    async def _summarise_failure(self, output: str) -> str:
        prompt = (
            f"These are test failures. Summarise in 3-5 bullet points.\n"
            f"Be specific: which test failed, what was expected, what needs fixing.\n\n"
            f"```\n{output}\n```"
        )
        result = ""
        try:
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(model="haiku", allowed_tools=[], max_turns=1),
            ):
                if hasattr(message, "result"):
                    result = message.result
        except Exception as e:
            self.log_error(f"Haiku summary failed: {e}")
            result = "Tests failed. See output above."
        return result

    def _extract_branch(self, body: str) -> str | None:
        if not body:
            return None
        m = re.search(r"\*\*Branch:\*\*\s*`([^`]+)`", body)
        return m.group(1) if m else None

    def _checkout_branch(self, branch: str, workspace: str) -> None:
        import git
        repo = git.Repo(workspace)
        repo.remotes.origin.fetch()
        repo.git.reset("--hard")
        repo.git.clean("-fd")
        repo.git.checkout(branch)
        self.log_info(f"Checked out: {branch}")
