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

REPO_DATA_FRAGMENT = """\
fragment repoData on Repository {
    nameWithOwner
    url
}
"""

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

ISSUE_DATA_FRAGMENT = """\
fragment issueData on Issue {
    repository {
        ...repoData
    }
    number
    url
    title
    state
    createdAt
    updatedAt
    author {
        ...authorData
    }
    body
    comments (last: 100) {
        totalCount
        nodes {
            ...commentData
        }
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
        ...repoData
        issues (first: 100, filterBy: {since: $since}, after: $after) {
            pageInfo { hasNextPage, endCursor }
            nodes {
                ...issueData
            }
        }
    }
}
""" + REPO_DATA_FRAGMENT + ISSUE_DATA_FRAGMENT + AUTHOR_DATA_FRAGMENT + COMMENT_DATA_FRAGMENT

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
                pageInfo { hasNextPage, endCursor }
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
    if "data" in data and data["data"] is None:
        # Another kind of failure response?
        raise Exception("GraphQL query returned null")
    return data

async def gql_nodes(query, path, variables=None):
    """
    Excecute a GraphQL query, and follow the pagination to get all the nodes.
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
    """
    Get issues from a repo updated since a date, with comments since that date.
    """
    owner, name = repo.split("/")
    vars = dict(owner=owner, name=name, since=since)
    issues = await gql_nodes(query=ISSUES_QUERY, path="repository.issues", variables=vars)

    # Need to get full comments.
    queried_issues = []
    issue_queries = []
    for iss in issues:
        if iss["comments"]["totalCount"] > len(iss["comments"]["nodes"]):
            vars = dict(owner=owner, name=name, number=iss["number"])
            queried_issues.append(iss)
            issue_queries.append(gql_nodes(query=COMMENTS_QUERY, path="repository.issue.comments", variables=vars))
    commentss = await asyncio.gather(*issue_queries)
    for iss, comments in zip(queried_issues, commentss):
        iss["comments"]["nodes"] = comments

    # Trim comments to those since our since date.
    for iss in issues:
        comments = iss["comments"]
        comments["nodes"] = [c for c in comments["nodes"] if c["updatedAt"] >= since]

    issues.sort(key=operator.itemgetter("updatedAt"))
    return issues

SINCE = "2022-02-01T00:00:00"
REPOS = [
    "nedbat/coveragepy",
    "openedx/tcril-engineering",
    "edx/open-source-process-wg",
]

async def main():
    tasks = [get_issues(repo, since=SINCE) for repo in REPOS]
    issuess = await asyncio.gather(*tasks)
    for repo, issues in zip(REPOS, issuess):
        print(f"{repo} has {len(issues)} issues to show")

asyncio.run(main())
# issues = asyncio.run(get_issues("nedbat/coveragepy", since="2022-01-01T00:00:00"))
# for iss in issues:
#     print(f"{iss['number']}: {iss['state']} {iss['updatedAt']} {iss['title']} [{len(iss['comments']['nodes'])}]")
