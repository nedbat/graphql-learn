"""
Find repos with openedx.yaml files and see what they say about openedx-release.
"""

import os

import yaml
from glom import glom
from python_graphql_client import GraphqlClient

client = GraphqlClient(endpoint="https://api.github.com/graphql")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ... on Blob  is an inline fragment:
# https://graphql.org/learn/queries/#inline-fragments

QUERY = """\
    query ($organization: String!, $after: String, $openedx_yaml: String) {
      organization(login: $organization) {
        repositories(
          first: 100,
          privacy: PUBLIC,
          after: $after,
        ) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            url
            openedx_yaml: object(expression: $openedx_yaml) {
              ... on Blob {
                text
              }
            }
          }
        }
      }
    }
"""

#branch = "open-release/maple.master"
branch = "HEAD"
repos = []
for org in ["edx", "openedx"]:
    vars = {"organization": org, "openedx_yaml": f"{branch}:openedx.yaml"}
    after = None
    while True:
        data = client.execute(
                query=QUERY, variables=vars,
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
        if "errors" in data:
            print(data["errors"])
            break
        repo_data = glom(data, "data.organization.repositories")
        nodes = repo_data["nodes"]
        repos.extend(n for n in nodes if n["openedx_yaml"])
        print(f'{len(repos)} repos')
        if not repo_data["pageInfo"]["hasNextPage"]:
            break
        vars["after"] = repo_data["pageInfo"]["endCursor"]

release_repos = []
for repo in repos:
    openedx_data = yaml.safe_load(repo["openedx_yaml"]["text"])
    if openedx_data and (rel := openedx_data.get("openedx-release")):
        maybe = rel.get("maybe", False)
        print(repo["url"], "MAYBE" if maybe else rel["ref"])
        release_repos.append(repo)

print(len(release_repos))
