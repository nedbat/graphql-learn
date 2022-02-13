import asyncio
import itertools
import json
import os

from glom import glom
from python_graphql_client import GraphqlClient

TOKEN = os.environ.get("GITHUB_TOKEN", "")
client = GraphqlClient(
    endpoint="https://api.github.com/graphql",
    headers={"Authorization": f"Bearer {TOKEN}"},
)

QUERY = """\
fragment authorData on Actor {
    login
    url
    avatarUrl
}
query getIssuesWithComments(
    $owner: String!
    $name: String!
    $since: String!
    $after: String
) {
    repository(owner: $owner, name: $name) {
        issues (first: 100, filterBy: {since: $since}, after: $after) {
            pageInfo {
                hasNextPage
                endCursor
            }
            nodes {
                url
                title
                createdAt
                body
                author {
                    ...authorData
                }
                comments (last: 20) {
                    totalCount
                    nodes {
                        body
                        author {
                            ...authorData
                        }
                    }
                }
            }
        }
    }
}
"""

JSON_NAMES = (f"out_{i:02}.json" for i in itertools.count())

async def gql_execute(query, variables=None):
    data = await client.execute_async(query=query, variables=variables)
    with open(next(JSON_NAMES), "w") as j:
        json.dump(data, j, indent=4)
    if "message" in data:
        raise Exception(data["message"])
    if "errors" in data:
        err = data["errors"][0]
        msg = f"GraphQl error: {err['message']}"
        if "path" in err:
            msg += f" @{'.'.join(err['path'])}"
        loc = err["locations"][0]
        msg += f", line {loc['line']} column {loc['column']}"
        raise Exception(msg)
    return data

async def gql_nodes(query, path, variables=None):
    nodes = []
    vars = dict(variables)
    while True:
        data = await gql_execute(query, vars)
        fetched = glom(data, f"data.{path}")
        nodes.extend(fetched["nodes"])
        if not fetched["pageInfo"]["hasNextPage"]:
            break
        vars["after"] = fetched["pageInfo"]["endCursor"]
    return nodes

vars = dict(owner="nedbat", name="coveragepy", since="2020-01-01T00:00:00")
coro = gql_nodes(query=QUERY, path="repository.issues", variables=vars)
data = asyncio.run(coro)
