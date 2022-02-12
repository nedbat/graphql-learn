import json
import os

import yaml
from glom import glom
from python_graphql_client import GraphqlClient

client = GraphqlClient(endpoint="https://api.github.com/graphql")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

def show_json(data):
    print(json.dumps(data, indent=4))

def json_out(data):
    with open("out.json", "w") as j:
        json.dump(data, j, indent=4)

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
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
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
"""

vars = {}
data = client.execute(
        query=QUERY, variables=vars,
        #headers={"Authorization": f"Bearer {TOKEN}"},
    )
#show_json(data)
json_out(data)
