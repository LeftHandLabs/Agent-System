import os
import signal
import sys
import time

os.chdir("/opt/agent-system")

from utils.config import Config
from utils.logger import setup_logger
from tools.github_client import GitHubClient
from agents.agent1_monitor import UsageMonitorAgent
from agents.agent2_orchestrator import OrchestratorAgent
from agents.agent3_coder import CoderAgent
from agents.agent4_tester import TesterAgent

logger = setup_logger("main")


def main():
    logger.info("=" * 60)
    logger.info("Claude Agent System starting (multi-project)")
    logger.info("=" * 60)

    try:
        config = Config.load()
    except Exception as e:
        logger.error(f"Config failed: {e}")
        sys.exit(1)

    if not config.enabled_projects:
        logger.error("No enabled projects found in config.yaml. Exiting.")
        sys.exit(1)

    github_clients = {}
    for project in config.enabled_projects:
        github_clients[project.name] = GitHubClient(
            token=config.github_token,
            repo_name=project.repo,
            project_id=project.project_id,
            project_number=project.project_number,
            local_path=project.workspace,
        )
        logger.info(f"  Loaded project: {project.name} ({project.repo})")

    git_config_check()

    coder = CoderAgent(config)
    tester = TesterAgent(config)
    orchestrator = OrchestratorAgent(config, coder, tester)
    monitor = UsageMonitorAgent(config, github_clients, orchestrator)

    monitor.start()

    logger.info("Running immediate startup cycle.")
    try:
        monitor.run()
    except Exception as e:
        logger.error(f"Startup cycle error: {e}")

    def shutdown(signum, frame):
        logger.info("Shutting down.")
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info(f"Running. Next cycle in {config.scheduler_interval} min.")
    while True:
        time.sleep(60)


def git_config_check():
    import subprocess
    name = subprocess.run(
        "git config --global user.name", shell=True,
        capture_output=True, text=True
    ).stdout.strip()
    if not name:
        subprocess.run('git config --global user.name "Claude Agent"', shell=True)
        subprocess.run('git config --global user.email "agent@noreply.local"', shell=True)


if __name__ == "__main__":
    main()
