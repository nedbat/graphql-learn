import asyncio
import itertools
import json
import operator
import os

from glom import glom
from python_graphql_client import GraphqlClient

TOKEN = os.environ.get("GITHUB_TOKEN", "")
client = GraphqlClient(
    endpoint="https://api.github.com/graphql",
    headers={"Authorization": f"Bearer {TOKEN}"},
)

AUTHOR_DATA_FRAGMENT = """\
fragment authorData on Actor {
    login
    url
    avatarUrl
}
"""

COMMENT_DATA_FRAGMENT = """\
fragment commentData on IssueComment {
    body
    updatedAt
    author {
        ...authorData
    }
}
"""

ISSUES_QUERY = """\
query getIssues(
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
                number
                url
                title
                state
                createdAt
                updatedAt
                body
                author {
                    ...authorData
                }
                comments (last: 100) {
                    totalCount
                    nodes {
                        ...commentData
                    }
                }
            }
        }
    }
}
""" + AUTHOR_DATA_FRAGMENT + COMMENT_DATA_FRAGMENT

COMMENTS_QUERY = """\
query getIssueComments(
    $owner: String!
    $name: String!
    $number: Int!
    $after: String
) {
    repository(owner: $owner, name: $name) {
        issue (number: $number) {
            comments (first: 100, after: $after) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    ...commentData
                }
            }
        }
    }
}
""" + AUTHOR_DATA_FRAGMENT + COMMENT_DATA_FRAGMENT

JSON_NAMES = (f"out_{i:02}.json" for i in itertools.count())

async def gql_execute(query, variables=None):
    """
    Execute one GraphQL query, with logging and error handling.
    """
    args = ", ".join(f"{k}: {v!r}" for k, v in variables.items())
    print(query.splitlines()[0] + args + ")")
    data = await client.execute_async(query=query, variables=variables)
    with open(next(JSON_NAMES), "w") as j:
        json.dump(data, j, indent=4)
    if "message" in data:
        raise Exception(data["message"])
    if "errors" in data:
        err = data["errors"][0]
        msg = f"GraphQL error: {err['message']}"
        if "path" in err:
            msg += f" @{'.'.join(err['path'])}"
        if "locations" in err:
            loc = err["locations"][0]
            msg += f", line {loc['line']} column {loc['column']}"
        raise Exception(msg)
    return data

async def gql_nodes(query, path, variables=None):
    """
    Excecute a query, and follow the pagination to get all the nodes.
    """
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

async def get_issues(repo, since):
    owner, name = repo.split("/")
    vars = dict(owner=owner, name=name, since=since)
    issues = await gql_nodes(query=ISSUES_QUERY, path="repository.issues", variables=vars)

    # Need to get full comments.
    queried_issues = []
    issue_queries = []
    for i, iss in enumerate(issues):
        if iss["comments"]["totalCount"] > len(iss["comments"]["nodes"]):
            vars = dict(owner=owner, name=name, number=iss["number"])
            queried_issues.append(i)
            issue_queries.append(gql_nodes(query=COMMENTS_QUERY, path="repository.issue.comments", variables=vars))
    commentss = await asyncio.gather(*issue_queries)
    for i, comments in zip(queried_issues, commentss):
        issues[i]["comments"]["nodes"] = comments

    # Trim comments to those since our since date.
    for iss in issues:
        iss["comments"]["nodes"] = [c for c in iss["comments"]["nodes"] if c["updatedAt"] >= since]

    issues.sort(key=operator.itemgetter("updatedAt"))
    return issues

issues = asyncio.run(get_issues("nedbat/coveragepy", since="2022-01-01T00:00:00"))
for iss in issues:
    print(f"{iss['number']}: {iss['state']} {iss['updatedAt']} {iss['title']} [{len(iss['comments']['nodes'])}]")
