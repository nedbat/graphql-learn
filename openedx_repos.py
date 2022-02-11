# cribbed from https://github.com/simonw/simonw/blob/main/build_readme.py
#
import os

from glom import glom
from python_graphql_client import GraphqlClient

client = GraphqlClient(endpoint="https://api.github.com/graphql")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

QUERY = """\
    query ($organization: String!) {
      organization(login: $organization) {
        repositories(first: 100, privacy: PUBLIC) {
          nodes {
            name
            description
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
data = client.execute(
            query=QUERY, variables=vars,
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
repos = glom(data, "data.organization.repositories.nodes")
print(len(repos))
