import os
import yaml
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ProjectConfig:
    name: str
    repo: str
    project_id: str
    project_number: int
    workspace: str
    base_branch: str
    test_command: str
    pre_test_command: str
    enabled: bool
    skip_testing: bool = False


@dataclass
class Config:
    github_token: str
    owner_username: str
    projects: List[ProjectConfig] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Config":
        with open("config.yaml") as f:
            raw = yaml.safe_load(f)

        projects = []
        for p in raw.get("projects", []):
            projects.append(ProjectConfig(
                name=p["name"],
                repo=p["repo"],
                project_id=p["project_id"],
                project_number=int(p.get("project_number", 1)),
                workspace=p["workspace"],
                base_branch=p.get("base_branch", "main"),
                test_command=p.get("test_command", ""),
                pre_test_command=p.get("pre_test_command", ""),
                enabled=p.get("enabled", True),
                skip_testing=p.get("skip_testing", False),
            ))

        return cls(
            github_token=os.environ["GITHUB_TOKEN"],
            owner_username=raw.get("github", {}).get("owner_username", ""),
            projects=projects,
            raw=raw,
        )

    @property
    def enabled_projects(self) -> List[ProjectConfig]:
        return [p for p in self.projects if p.enabled]

    @property
    def scheduler_interval(self) -> int:
        return self.raw["scheduler"]["interval_minutes"]

    @property
    def max_issues_per_cycle(self) -> int:
        return self.raw["orchestrator"]["max_issues_per_cycle"]

    @property
    def coder_model(self) -> str:
        return self.raw["coder"]["model"]

    @property
    def coder_max_turns(self) -> int:
        return int(self.raw.get("coder", {}).get("max_turns", 30))

    @property
    def tester_model(self) -> str:
        return self.raw["tester"]["model"]

    @property
    def coding_keywords(self) -> list:
        return self.raw["orchestrator"]["coding_keywords"]

    @property
    def testing_keywords(self) -> list:
        return self.raw["orchestrator"]["testing_keywords"]

    @property
    def usage_threshold_pct(self) -> float:
        return float(self.raw.get("usage", {}).get("threshold_pct", 80))
