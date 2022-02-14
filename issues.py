import asyncio
import colorsys
import datetime
import itertools
import json
import operator
import os
from pathlib import Path

import glom
import jinja2
import python_graphql_client

TOKEN = os.environ.get("GITHUB_TOKEN", "")
client = python_graphql_client.GraphqlClient(
    endpoint="https://api.github.com/graphql",
    headers={"Authorization": f"Bearer {TOKEN}"},
)

REPO_DATA_FRAGMENT = """\
fragment repoData on Repository {
    owner { login }
    name
    nameWithOwner
    url
}
"""

AUTHOR_DATA_FRAGMENT = """\
fragment authorData on Actor {
    login
    url
    #avatarUrl
}
"""

COMMENT_DATA_FRAGMENT = """\
fragment commentData on IssueComment {
    url
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
    closedAt
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
    projectNextItems(first: 100) {
        nodes {
            project {
                owner {
                    ... on User { login }
                    ... on Organization { login }
                }
                number
            }
        }
    }
    labels(first:10) {
        nodes {
            color
            name
        }
    }
    # Issues have timelineItems, but added or removed from projectNext isn't listed.
}
"""

REPO_ISSUES_QUERY = """\
query getRepoIssues(
    $owner: String!
    $name: String!
    $since: String!
    $after: String
) {
    repository (owner: $owner, name: $name) {
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
    repository (owner: $owner, name: $name) {
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

PROJECT_ISSUES_QUERY = """\
query getProjectIssues(
    $org: String!
    $projectNumber: Int!
    $after: String
) {
    organization(login: $org) {
        project: projectNext(number: $projectNumber) {
            title
            url
            items (first: 100, after: $after) {
                pageInfo { hasNextPage, endCursor }
                nodes {
                    content {
                        ... on Issue {
                            ...issueData
                        }
                        # ... on PullRequest {
                        #     number
                        # }
                    }
                }
            }
        }
    }
}
""" + REPO_DATA_FRAGMENT + ISSUE_DATA_FRAGMENT + AUTHOR_DATA_FRAGMENT + COMMENT_DATA_FRAGMENT

PULL_REQUESTS_QUERY = """\
query getPullRequests(
    $owner: String!
    $name: String!
    $after: String
) {
    repository (owner: $owner, name: $name) {
        ...repoData
        pullRequests (last: 10, after: $after) {
            pageInfo { hasNextPage, endCursor }
            nodes {
                number
                title
                url
                comments (first: 100) {
                    totalCount
                    nodes {
                        ...commentData
                    }
                }
                latestOpinionatedReviews (first: 100) {
                    totalCount
                    nodes {
                        author { login }
                        body
                        comments (first: 100) {
                            totalCount
                            nodes {
                                author {login}
                                body
                                url
                            }
                        }
                    }
                }
                latestReviews (first: 100) {
                    totalCount
                    nodes {
                        author { login }
                        body
                        comments (first: 100) {
                            totalCount
                            nodes {
                                author {login}
                                body
                                url
                            }
                        }
                    }
                }
                reviewThreads (first: 100) {
                    totalCount
                    nodes {
                        comments (first: 100) {
                            totalCount
                            nodes {
                                author { login }
                                body
                                url
                            }
                        }
                    }
                }
            }
        }
    }
}
""" + REPO_DATA_FRAGMENT + AUTHOR_DATA_FRAGMENT + COMMENT_DATA_FRAGMENT


JSON_NAMES = (f"out_{i:02}.json" for i in itertools.count())

async def gql_execute(query, variables=None):
    """
    Execute one GraphQL query, with logging and error handling.
    """
    args = ", ".join(f"{k}: {v!r}" for k, v in variables.items())
    print(query.splitlines()[0] + args + ")")
    data = await client.execute_async(query=query, variables=variables)
    json_save(data, next(JSON_NAMES))
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
    Execute a GraphQL query, and follow the pagination to get all the nodes.

    Returns the last query result (for the information outside the pagination),
    and the list of all paginated nodes.
    """
    nodes = []
    vars = dict(variables)
    while True:
        data = await gql_execute(query, vars)
        fetched = glom.glom(data, f"data.{path}")
        nodes.extend(fetched["nodes"])
        if not fetched["pageInfo"]["hasNextPage"]:
            break
        vars["after"] = fetched["pageInfo"]["endCursor"]
    # Remove the nodes from the data we return, to keep things clean.
    fetched["nodes"] = []
    return data, nodes

async def get_repo_issues(repo, since):
    """
    Get issues from a repo updated since a date, with comments since that date.
    """
    owner, name = repo.split("/")
    vars = dict(owner=owner, name=name, since=since)
    repo, issues = await gql_nodes(query=REPO_ISSUES_QUERY, path="repository.issues", variables=vars)
    issues = await populate_issues(issues, since)
    repo = glom.glom(repo, "data.repository")
    repo["kind"] = "repo"
    return repo, issues

async def populate_issues(issues, since):
    # Need to get full comments.
    queried_issues = []
    issue_queries = []
    for iss in issues:
        if iss["comments"]["totalCount"] > len(iss["comments"]["nodes"]):
            vars = dict(owner=iss["repository"]["owner"]["login"], name=iss["repository"]["name"], number=iss["number"])
            queried_issues.append(iss)
            comments = gql_nodes(query=COMMENTS_QUERY, path="repository.issue.comments", variables=vars)
            issue_queries.append(comments)
    commentss = await asyncio.gather(*issue_queries)
    for iss, (_, comments) in zip(queried_issues, commentss):
        iss["comments"]["nodes"] = comments

    # Trim comments to those since our since date.
    # Why was this issue in the list?
    for iss in issues:
        comments = iss["comments"]
        comments["nodes"] = [c for c in comments["nodes"] if c["updatedAt"] >= since]
        iss["reasonCreated"] = iss["createdAt"] > since
        iss["reasonClosed"] = bool(iss["closedAt"] and (iss["closedAt"] > since))

    issues.sort(key=operator.itemgetter("updatedAt"))
    return issues

async def get_project_issues(org, number, since):
    vars = dict(org=org, projectNumber=number)
    project, project_data = await gql_nodes(query=PROJECT_ISSUES_QUERY, path="organization.project.items", variables=vars)
    issues = [content for data in project_data if (content := data["content"])]
    issues = [iss for iss in issues if iss["updatedAt"] > since]
    issues = await populate_issues(issues, since)
    project = glom.glom(project, "data.organization.project")
    project["kind"] = "project"
    return project, issues


SINCE = "2022-02-10T00:00:00"

ISSUES = [
    # "nedbat/coveragepy",
    # "openedx/tcril-engineering",
    # "edx/open-source-process-wg",
]

PROJECTS = [
    ("edx", 7),
    ("openedx", 8),
]

PULL_REQUESTS = [
    "openedx/open-edx-proposals",
]

def datetime_format(value, format="%m-%d %H:%M"):
    """Format an ISO datetime string, for Jinja filtering."""
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).strftime(format)

def textcolor(bg):
    """Calculate a text color for a background color `bg`."""
    r, g, b = bg[0:2], bg[2:4], bg[4:6]
    r, g, b = int(r, 16) / 256, int(g, 16) / 256, int(b, 16) / 256
    lightness = colorsys.rgb_to_hsv(r, g, b)[2]
    return "black" if lightness > .5 else "white"

def render_jinja(template_filename, **vars):
    jenv = jinja2.Environment(loader=jinja2.FileSystemLoader(Path(__file__).parent))
    jenv.filters["datetime"] = datetime_format
    jenv.filters["textcolor"] = textcolor
    template = jenv.get_template(template_filename)
    html = template.render(**vars)
    return html

def json_save(data, filename):
    with open(filename, "w") as json_out:
        json.dump(data, json_out, indent=4)


async def main():
    results = await gql_execute(PULL_REQUESTS_QUERY, variables=dict(owner="openedx", name="open-edx-proposals"))
    json_save(results, "out_prs.json")
    tasks = [
        *(get_repo_issues(repo, since=SINCE) for repo in ISSUES),
        *(get_project_issues(org, number, SINCE) for org, number in PROJECTS),
    ]
    results = await asyncio.gather(*tasks)
    json_save(results, "out_results.json")
    html = render_jinja("results.html.j2", results=results, since=SINCE)
    with open("results.html", "w") as html_out:
        html_out.write(html)

asyncio.run(main())
