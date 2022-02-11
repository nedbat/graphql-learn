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
nodes = []
while True:
    data = client.execute(
            query=QUERY, variables=vars,
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    repos = glom(data, "data.organization.repositories")
    nodes.extend(repos["nodes"])
    print(f'{len(nodes)} nodes, {repos["pageInfo"]["hasNextPage"]=}')
    if not repos["pageInfo"]["hasNextPage"]:
        break
    vars["after"] = repos["pageInfo"]["endCursor"]

print(len(nodes))
