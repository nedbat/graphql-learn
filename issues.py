import asyncio
import json
import os

from glom import glom
from python_graphql_client import GraphqlClient

TOKEN = os.environ.get("GITHUB_TOKEN", "")
client = GraphqlClient(
    endpoint="https://api.github.com/graphql",
    headers={"Authorization": f"Bearer {TOKEN}"},
)

def show_json(data):
    print(json.dumps(data, indent=4))

def json_out(data):
    with open("out.json", "w") as j:
        json.dump(data, j, indent=4)

QUERY = """\
query getIssuesWithComments($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    issues (last: 50, filterBy: { since: "2022-02-01T00:00:00" } ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        url
        title
        createdAt
        body
        comments (last: 20) {
          totalCount
          nodes {
            body
          }
        }
      }
    }
  }
}
"""

async def gql_execute(query, variables=None):
    data = await client.execute_async(query=query, variables=variables)
    json_out(data)
    if "message" in data:
        raise Exception(data["message"])
    if "errors" in data:
        err = data["errors"][0]
        loc = err["locations"][0]
        raise Exception(
            f"GraphQl error: {err['message']} " +
            f"@{'.'.join(err['path'])}, " +
            f"line {loc['line']} " +
            f"column {loc['column']}"
        )
    return data

data = asyncio.run(gql_execute(query=QUERY, variables={"owner": "nedbat", "name": "coveragepy"}))
