import subprocess
import requests
from github import Github, GithubException
from utils.logger import setup_logger

logger = setup_logger("github_client")


class GitHubClient:
    GRAPHQL_URL = "https://api.github.com/graphql"

    def __init__(self, token, repo_name, project_id, project_number, local_path):
        self.token = token
        self.g = Github(token)
        self.repo = self.g.get_repo(repo_name)
        self.project_id = project_id
        self.project_number = project_number
        self.local_path = local_path
        self._gql_headers = {
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
        }

    def get_issues_by_label(self, label: str) -> list:
        try:
            return list(self.repo.get_issues(state="open", labels=[label]))
        except GithubException as e:
            logger.error(f"get_issues failed: {e}")
            return []

    def create_issue(self, title: str, body: str, labels: list) -> object:
        label_objects = []
        for name in labels:
            try:
                label_objects.append(self.repo.get_label(name))
            except GithubException:
                logger.warning(f"Label not found: {name}")
        issue = self.repo.create_issue(title=title, body=body, labels=label_objects)
        logger.info(f"Created issue #{issue.number}: {title}")
        return issue

    def set_issue_labels(self, issue_number: int, labels: list) -> None:
        issue = self.repo.get_issue(issue_number)
        label_objects = []
        for name in labels:
            try:
                label_objects.append(self.repo.get_label(name))
            except GithubException:
                logger.warning(f"Label '{name}' not found in repo — skipping. Run setup/create_labels.py.")
        issue.set_labels(*label_objects)

    def add_issue_comment(self, issue_number: int, comment: str) -> None:
        self.repo.get_issue(issue_number).create_comment(comment)

    def close_issue(self, issue_number: int) -> None:
        self.repo.get_issue(issue_number).edit(state="closed")

    def create_pull_request(self, title: str, body: str, head: str, base: str) -> object:
        pr = self.repo.create_pull(title=title, body=body, head=head, base=base)
        logger.info(f"Created PR #{pr.number}: {title}")
        return pr

    def assign_issue(self, issue_number: int, username: str) -> None:
        self.repo.get_issue(issue_number).edit(assignees=[username])
        logger.info(f"Assigned #{issue_number} to {username}")

    def get_issue_comments(self, issue_number: int) -> list:
        issue = self.repo.get_issue(issue_number)
        comments = list(issue.get_comments())[-10:]
        return [c.body for c in comments]

    def add_issue_to_project(self, issue_node_id: str) -> str | None:
        mutation = """
        mutation($project: ID!, $content: ID!) {
          addProjectV2ItemById(input: {projectId: $project, contentId: $content}) {
            item { id }
          }
        }"""
        try:
            result = requests.post(
                self.GRAPHQL_URL,
                headers=self._gql_headers,
                json={"query": mutation, "variables": {
                    "project": self.project_id,
                    "content": issue_node_id,
                }},
                timeout=15,
            )
            return result.json()["data"]["addProjectV2ItemById"]["item"]["id"]
        except Exception as e:
            logger.error(f"add_to_project failed: {e}")
            return None

    def ensure_repo_cloned(self) -> None:
        import os
        import git
        git_dir = os.path.join(self.local_path, '.git')
        if os.path.exists(git_dir):
            git.Repo(self.local_path).remotes.origin.fetch()
            logger.info(f"Fetched latest for {self.repo.full_name}")
        else:
            git.Repo.clone_from(
                f"https://x-access-token:{self.token}@github.com/{self.repo.full_name}.git",
                self.local_path,
            )
            logger.info(f"Cloned {self.repo.full_name} to {self.local_path}")

    def create_branch(self, branch_name: str, from_branch: str = "main") -> None:
        import git
        repo = git.Repo(self.local_path)
        repo.remotes.origin.fetch()
        repo.git.checkout(from_branch)
        repo.git.pull("origin", from_branch)
        # Remove stale local branch left over from a previous failed run
        if branch_name in [b.name for b in repo.branches]:
            logger.warning(f"Branch '{branch_name}' already exists locally — deleting and recreating.")
            repo.git.branch("-D", branch_name)
        repo.git.checkout("-b", branch_name)

    def commit_and_push(self, branch_name: str, message: str, files: list) -> str:
        import git
        repo = git.Repo(self.local_path)
        repo.index.add(files)
        commit = repo.index.commit(message)
        repo.remotes.origin.push(branch_name)
        logger.info(f"Pushed {commit.hexsha[:8]} to {branch_name}")
        return commit.hexsha

    def run_command(self, command: str, cwd: str = None) -> tuple:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd or self.local_path,
            timeout=180,
        )
        return proc.returncode, proc.stdout, proc.stderr
