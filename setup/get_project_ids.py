import os, requests
from dotenv import load_dotenv
load_dotenv("/opt/agent-system/.env")

token = os.environ["GITHUB_TOKEN"]
headers = {"Authorization": f"bearer {token}", "Content-Type": "application/json"}
query = '{ viewer { projectsV2(first: 20) { nodes { id number title } } } }'
r = requests.post("https://api.github.com/graphql", headers=headers,
                  json={"query": query}, timeout=15)
data = r.json()
print("Your GitHub Projects:\n")
for p in data["data"]["viewer"]["projectsV2"]["nodes"]:
    print(f"  Title:  {p['title']}")
    print(f"  Number: {p['number']}")
    print(f"  ID:     {p['id']}")
    print()
