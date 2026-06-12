import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions
from agents.base import BaseAgent
from utils import state


class CoderAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config, "Agent3-Coder")

    def run(self, issue, project, github) -> None:
        self.log_info(f"[{project.name}] Coding: #{issue.number} — {issue.title}")
        branch = f"agent/coding/issue-{issue.number}"
        try:
            github.set_issue_labels(issue.number, ["agent:coding", "agent:in-progress"])
            github.add_issue_comment(
                issue.number, f"**Agent 3 — Coder** [{project.name}]\n\nStarting work. 🤖"
            )
            github.ensure_repo_cloned()
            github.create_branch(branch, project.base_branch)

            result = asyncio.run(self._run_agent(issue, project, github))
            if not result:
                raise RuntimeError("Agent finished without a parseable result.")

            if result.get("needs_clarification"):
                self._request_clarification(issue, project, github, result["question"])
                return

            sha = github.commit_and_push(
                branch,
                f"feat: {issue.title} (closes #{issue.number}) [agent]",
                result["files_changed"],
            )
            github.add_issue_comment(
                issue.number,
                f"**Agent 3 — Done** ✅\n\n"
                f"{result['summary']}\n\n"
                f"Files: {', '.join(f'`{f}`' for f in result['files_changed'])}\n"
                f"Branch: `{branch}` · Commit: `{sha[:8]}`",
            )
            github.set_issue_labels(issue.number, ["agent:coding", "agent:done"])
            if project.skip_testing:
                self._open_pr(issue, project, github, branch, result)
            else:
                self._create_test_issue(issue, project, github, branch, sha, result)
            github.close_issue(issue.number)

        except Exception as e:
            self.log_error(f"[{project.name}] Coder failed #{issue.number}: {e}")
            try:
                github.set_issue_labels(issue.number, ["agent:coding", "agent:failed", "agent:needs-human"])
            except Exception as label_err:
                self.log_error(f"[{project.name}] Could not set agent:failed label: {label_err}")
            try:
                github.add_issue_comment(
                    issue.number,
                    f"**Agent 3 — FAILED** ❌\n\nError: `{e}`\n\nNeeds human review.",
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

    def _request_clarification(self, issue, project, github, question: str) -> None:
        owner = self.config.owner_username
        tag = f"@{owner}" if owner else "Hi"
        self.log_warn(f"[{project.name}] Clarification needed for #{issue.number}")
        github.add_issue_comment(
            issue.number,
            f"**Agent 3 — Needs Clarification** ❓\n\n"
            f"{tag} I need more information before I can implement this:\n\n"
            f"> {question}\n\n"
            f"**How to respond:**\n"
            f"1. Add a comment answering the question\n"
            f"2. Remove the `agent:clarification-needed` label\n"
            f"3. Add the `agent:queue` label to restart\n\n"
            f"The agent will read your answer and proceed.",
        )
        github.set_issue_labels(issue.number, ["agent:clarification-needed"])
        if owner:
            github.assign_issue(issue.number, owner)
        state.remove_in_progress(project.name, issue.number)

    async def _run_agent(self, issue, project, github) -> dict | None:
        prior_comments = github.get_issue_comments(issue.number)
        comment_context = ""
        if prior_comments:
            comment_context = "\n\n## Previous discussion\n"
            for i, body in enumerate(prior_comments, 1):
                comment_context += f"\n[Comment {i}]: {body[:600]}\n"

        if project.skip_testing:
            closing_instructions = (
                f"Otherwise when complete, end with these exact lines:\n"
                f"SUMMARY: one sentence\n"
                f"FILES: comma-separated relative paths\n"
            )
        else:
            closing_instructions = (
                f"Otherwise when complete, end with these exact lines:\n"
                f"SUMMARY: one sentence\n"
                f"FILES: comma-separated relative paths\n"
                f"TEST_INSTRUCTIONS: what the tester should verify\n"
            )

        prompt = (
            f"Implement this GitHub issue in the repository:\n\n"
            f"**#{issue.number}: {issue.title}**\n\n"
            f"{issue.body or '(no description)'}"
            f"{comment_context}\n\n"
            f"Follow the conventions in CLAUDE.md. Restrictions:\n"
            f"- Do NOT run database migrations\n"
            f"- Do NOT modify .env files\n"
            f"- If a migration is needed, create the migration file but note it in your summary\n\n"
            f"If requirements are genuinely unclear, output ONLY:\n"
            f"CLARIFICATION_NEEDED: <your specific question>\n\n"
            f"{closing_instructions}"
        )
        full_output = ""
        transcript_parts = []
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                model=self.config.coder_model,
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                cwd=project.workspace,
                permission_mode="acceptEdits",
                max_turns=self.config.coder_max_turns,
            ),
        ):
            # Capture text content blocks for the transcript
            if hasattr(message, "content"):
                for block in (message.content or []):
                    text = None
                    if hasattr(block, "text") and block.text:
                        text = block.text
                    elif isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                    if text:
                        transcript_parts.append(text)
            if hasattr(message, "result") and message.result:
                full_output = message.result

        self._post_transcript(issue, github, transcript_parts or [full_output])
        return self._parse_result(full_output)

    def _post_transcript(self, issue, github, parts: list) -> None:
        body = "\n\n".join(p for p in parts if p).strip()
        if not body:
            return
        # Truncate to stay within GitHub's comment size limit
        if len(body) > 60000:
            body = body[:60000] + "\n\n… (truncated)"
        try:
            github.add_issue_comment(
                issue.number,
                f"**Agent 3 — Transcript**\n\n"
                f"<details><summary>Show full agent output</summary>\n\n"
                f"```\n{body}\n```\n\n</details>",
            )
        except Exception as e:
            self.log_warn(f"Could not post transcript: {e}")

    def _parse_result(self, output: str) -> dict | None:
        if not output:
            return None
        for line in output.splitlines():
            if line.strip().startswith("CLARIFICATION_NEEDED:"):
                q = line.strip()[21:].strip()
                if q:
                    return {"needs_clarification": True, "question": q}
        result = {
            "needs_clarification": False,
            "summary": "",
            "files_changed": [],
            "test_instructions": "",
        }
        for line in output.splitlines():
            if line.startswith("SUMMARY:"):
                result["summary"] = line[8:].strip()
            elif line.startswith("FILES:"):
                result["files_changed"] = [
                    f.strip() for f in line[6:].split(",") if f.strip()
                ]
            elif line.startswith("TEST_INSTRUCTIONS:"):
                result["test_instructions"] = line[18:].strip()
        if not result["summary"]:
            result["summary"] = output[:200]
        return result

    def _open_pr(self, issue, project, github, branch, result) -> None:
        pr = github.create_pull_request(
            title=issue.title,
            body=(
                f"Closes #{issue.number}\n\n"
                f"## Summary\n\n{result.get('summary', '')}\n\n"
                f"## Files Changed\n\n"
                + "\n".join(f"- `{f}`" for f in result.get("files_changed", []))
            ),
            head=branch,
            base=project.base_branch,
        )
        github.add_issue_comment(
            issue.number,
            f"**Agent 3 — PR Opened** 🔀\n\n"
            f"Testing skipped for this project.\n\n"
            f"Pull request: {pr.html_url}",
        )
        self.log_info(f"[{project.name}] Opened PR for #{issue.number} (testing skipped)")

    def _create_test_issue(self, source_issue, project, github, branch, sha, result) -> None:
        github.create_issue(
            title=f"[TEST] {source_issue.title}",
            body=(
                f"## What to Test\n\n"
                f"{result.get('test_instructions', 'Verify the implementation.')}\n\n"
                f"## Branch / Commit\n\n"
                f"**Branch:** `{branch}`\n**Commit:** `{sha[:8]}`\n\n"
                f"## Test Command\n\n```\n{project.test_command}\n```\n\n"
                f"## Files Changed\n\n"
                + "\n".join(f"- `{f}`" for f in result.get("files_changed", []))
                + f"\n\n## Linked Issue\n\n#{source_issue.number}"
            ),
            labels=["agent:queue"],
        )
