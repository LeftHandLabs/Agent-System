import os, sys
os.chdir('/opt/agent-system')
sys.path.insert(0, '/opt/agent-system')
from utils.config import Config
from tools.github_client import GitHubClient
config = Config.load()
for project in config.enabled_projects:
    print(f'Cloning {project.name}...')
    gh = GitHubClient(config.github_token, project.repo,
                      project.project_id, project.project_number,
                      project.workspace)
    gh.ensure_repo_cloned()
    print(f'  Done: {project.workspace}')
print('All workspaces ready.')

