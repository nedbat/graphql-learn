import os

import yaml
from glom import glom
from python_graphql_client import GraphqlClient

client = GraphqlClient(endpoint="https://api.github.com/graphql")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

QUERY = """\
    {
      search(query: "org:openedx is:issue created:>2022-02-01", type: ISSUE, last: 10) {
        edges {
          node {
            ... on Issue {
              url
              title
              createdAt
              body
              comments (last: 10) {
                nodes {
                    body
                }
              }
            }
          }
        }
      }
    }
"""

QUERY = """\
    query {
      repository(owner: "nedbat", name: "coveragepy") {
        issues (last: 10) {
          edges {
          node {
              url
              title
              createdAt
              body
              comments (last: 10) {
                nodes {
                    body
                }
              }
          }
        }
        }
      }
    }
"""

vars = {}
data = client.execute(
        query=QUERY, variables=vars,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
import pprint; pprint.pprint(data)
