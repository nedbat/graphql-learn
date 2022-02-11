# cribbed from https://github.com/simonw/simonw/blob/main/build_readme.py
#
import os

from glom import glom
from python_graphql_client import GraphqlClient

client = GraphqlClient(endpoint="https://api.github.com/graphql")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

QUERY = """\
    query ($organization: String!, $after: String) {
      organization(login: $organization) {
        repositories(first: 10, privacy: PUBLIC, after: $after) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            url
            content: object(expression: "master:openedx.yaml") {
              ... on Blob {
                text
              }
            }
          }
        }
      }
    }
"""

vars = {"organization": "edx"}
after = None
repos = []
while True:
    data = client.execute(
            query=QUERY, variables=vars,
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    repo_data = glom(data, "data.organization.repositories")
    nodes = repo_data["nodes"]
    repos.extend(n for n in nodes if n["content"])
    print(f'{len(repos)} repos')
    if not repo_data["pageInfo"]["hasNextPage"]:
        break
    vars["after"] = repo_data["pageInfo"]["endCursor"]

print(len(repos))
print(repos[0])
