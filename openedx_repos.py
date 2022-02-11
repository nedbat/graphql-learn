# cribbed from https://github.com/simonw/simonw/blob/main/build_readme.py
#
import os

from glom import glom
from python_graphql_client import GraphqlClient

client = GraphqlClient(endpoint="https://api.github.com/graphql")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

QUERY = """\
    query {
      organization(login: "edx") {
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

data = client.execute(
            query=QUERY,
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
repos = glom(data, "data.organization.repositories.nodes")
print(len(repos))
