from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from agents.base import BaseAgent
from utils import state
from utils.usage import get_usage_pct


class UsageMonitorAgent(BaseAgent):
    def __init__(self, config, github_clients: dict, orchestrator):
        super().__init__(config, "Agent1-Monitor")
        self.github_clients = github_clients
        self.orchestrator = orchestrator
        self.scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1}
        )

    def start(self) -> None:
        self.scheduler.add_job(
            self.run,
            trigger=IntervalTrigger(minutes=self.config.scheduler_interval),
            id="monitor",
            replace_existing=True,
        )
        self.scheduler.start()
        projects = [p.name for p in self.config.enabled_projects]
        self.log_info(
            f"Scheduler started — {self.config.scheduler_interval} min interval — "
            f"watching: {', '.join(projects)}"
        )

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)

    def run(self) -> None:
        self.log_info("Cycle starting.")
        state.record_cycle()

        usage_pct = get_usage_pct()
        threshold = self.config.usage_threshold_pct
        if usage_pct is None:
            self.log_warn("Could not read API usage; proceeding anyway.")
        elif usage_pct >= threshold:
            self.log_info(
                f"5-hour token usage at {usage_pct:.1f}% — "
                f"at or above {threshold}% threshold. Skipping cycle."
            )
            return
        else:
            self.log_info(f"5-hour token usage at {usage_pct:.1f}% — below {threshold}% threshold.")

        all_queued = []
        for project in self.config.enabled_projects:
            github = self.github_clients.get(project.name)
            if not github:
                continue
            issues = github.get_issues_by_label("agent:queue")
            for issue in issues:
                if not state.is_in_progress(project.name, issue.number):
                    all_queued.append((issue, project, github))

        if not all_queued:
            self.log_info(
                f"No queued issues across "
                f"{len(self.config.enabled_projects)} project(s). "
                f"Zero credits used."
            )
            return

        all_queued.sort(key=lambda x: x[0].created_at)

        queued_numbers = {issue.number for issue, _, _ in all_queued}

        processed = 0
        for issue, project, github in all_queued:
            if processed >= self.config.max_issues_per_cycle:
                self.log_info(
                    f"Reached max_issues_per_cycle "
                    f"({self.config.max_issues_per_cycle}). Stopping."
                )
                break

            blockers = github.get_open_blockers(issue)
            if blockers:
                self._handle_blocked(issue, project, github, blockers, queued_numbers)
                continue

            self.log_info(f"[{project.name}] #{issue.number}: {issue.title}")
            try:
                self.orchestrator.run(issue, project, github)
            except Exception as e:
                self.log_error(f"[{project.name}] Orchestrator error: {e}")
            processed += 1

        self.log_info(f"Cycle complete. Processed {processed} issue(s).")

    def _handle_blocked(self, issue, project, github, blockers, queued_numbers: set) -> None:
        blocker_refs = ", ".join(f"#{b.number}" for b in blockers)
        self.log_info(
            f"[{project.name}] #{issue.number} is blocked by {blocker_refs} — skipping."
        )
        newly_queued = []
        for blocker in blockers:
            if blocker.number in queued_numbers:
                self.log_info(
                    f"[{project.name}] #{blocker.number} is already queued — "
                    f"will be picked up this or next cycle."
                )
            else:
                self.log_info(
                    f"[{project.name}] #{blocker.number} is not queued — "
                    f"adding agent:queue so it is picked up next cycle."
                )
                github.add_label_to_issue(blocker.number, "agent:queue")
                queued_numbers.add(blocker.number)
                newly_queued.append(blocker.number)

        if newly_queued:
            refs = ", ".join(f"#{n}" for n in newly_queued)
            github.add_issue_comment(
                issue.number,
                f"**Agent 1 — Monitor**\n\n"
                f"This issue is blocked by {blocker_refs}.\n\n"
                f"Auto-queued {refs} for processing. "
                f"This issue will be picked up once its blockers are resolved.",
            )
