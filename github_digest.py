"""
Summarize issue activity in GitHub repos and projects.
"""

import asyncio
import itertools
import operator
import os

import glom

from graphql_helpers import GraphqlHelper
from helpers import json_save
from jinja_helpers import render_jinja


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
        pullRequests (
            first: 10
            orderBy: { field: UPDATED_AT, direction: DESC }
            after: $after
        ) {
            pageInfo { hasNextPage, endCursor }
            nodes {
                repository {
                    ...repoData
                }
                author {
                    ...authorData
                }
                number
                title
                url
                createdAt
                updatedAt
                closedAt
                merged
                mergedAt
                comments (first: 100) {
                    totalCount
                    nodes {
                        ...commentData
                    }
                }
                latestOpinionatedReviews (first: 100) {
                    totalCount
                    nodes {
                        id
                        state
                        author { login }
                        body
                        updatedAt
                        comments (first: 100) {
                            totalCount
                            nodes {
                                author {login}
                                body
                                url
                                updatedAt
                            }
                        }
                    }
                }
                latestReviews (first: 100) {
                    totalCount
                    nodes {
                        id
                        state
                        author { login }
                        body
                        updatedAt
                        comments (first: 100) {
                            totalCount
                            nodes {
                                author {login}
                                body
                                url
                                updatedAt
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
                                updatedAt
                            }
                        }
                    }
                }
            }
        }
    }
}
""" + REPO_DATA_FRAGMENT + AUTHOR_DATA_FRAGMENT + COMMENT_DATA_FRAGMENT


class Summarizer:
    """
    Use GitHub GraphQL to get data about recent changes.
    """
    def __init__(self, since):
        self.since = since
        token = os.environ.get("GITHUB_TOKEN", "")
        self.gql = GraphqlHelper("https://api.github.com/graphql", token)

    async def get_repo_issues(self, repo):
        """
        Get issues from a repo updated since a date, with comments since that date.

        Args:
            repo (str): a combined owner/name of a repo, like "openedx/edx-platform".

        """
        owner, name = repo.split("/")
        repo, issues = await self.gql.nodes(
            query=REPO_ISSUES_QUERY,
            path="repository.issues",
            variables=dict(owner=owner, name=name, since=self.since),
        )
        issues = await self._populate_issue_comments(issues)
        self._add_reasons(issues)
        for iss in issues:
            iss["comments_to_show"] = iss["comments"]["nodes"]
        repo = glom.glom(repo, "data.repository")
        repo["container_kind"] = "repo"
        repo["kind"] = "issues"
        return repo, issues

    async def get_project_issues(self, org, number, home_repo):
        """
        Get issues from a project.

        Args:
            org (str): the organization owner of the repo.
            number (int): the project number.
            home_repo (str): the owner/name of a repo that most issues are in.
        """
        project, project_data = await self.gql.nodes(
            query=PROJECT_ISSUES_QUERY,
            path="organization.project.items",
            variables=dict(org=org, projectNumber=number),
        )
        issues = [content for data in project_data if (content := data["content"])]
        issues = self._trim_since(issues)
        issues = await self._populate_issue_comments(issues)
        self._add_reasons(issues)
        for iss in issues:
            iss["other_repo"] = (iss["repository"]["nameWithOwner"] != home_repo)
            iss["comments_to_show"] = iss["comments"]["nodes"]
        project = glom.glom(project, "data.organization.project")
        project["container_kind"] = "project"
        project["kind"] = "issues"
        return project, issues

    async def get_pull_requests(self, repo):
        """
        Get pull requests from a repo updated since a date, with comments since that date.

        Args:
            repo (str): a combined owner/name of a repo, like "openedx/edx-platform".
        """
        owner, name = repo.split("/")
        repo, pulls = await self.gql.nodes(
            query=PULL_REQUESTS_QUERY,
            path="repository.pullRequests",
            variables=dict(owner=owner, name=name),
            donefn=(lambda nodes: nodes[-1]["updatedAt"] < SINCE),
        )
        pulls = self._trim_since(pulls)
        for pull in pulls:
            # I don't understand the difference between latestReviews and latestOpinionatedReviews,
            # but they duplicate each other, so combine them.
            reviews = {}
            for rev in pull["latestReviews"]["nodes"]:
                reviews[rev["id"]] = rev
            for rev in pull["latestOpinionatedReviews"]["nodes"]:
                reviews[rev["id"]] = rev

            pull["comments_to_show"] = self._trim_since([
                *pull["comments"]["nodes"],
                *reviews.values(),
                *[c for rev in reviews.values() for c in rev["comments"]["nodes"]],
            ])
        self._add_reasons(pulls)
        repo = glom.glom(repo, "data.repository")
        repo["container_kind"] = "repo"
        repo["kind"] = "pull requests"
        return repo, pulls

    def _trim_since(self, nodes):
        nodes = [n for n in nodes if n["updatedAt"] > self.since]
        nodes.sort(key=operator.itemgetter("updatedAt"))
        return nodes

    async def _populate_issue_comments(self, issues):
        # Need to get full comments.
        queried_issues = []
        issue_queries = []
        for iss in issues:
            if iss["comments"]["totalCount"] > len(iss["comments"]["nodes"]):
                queried_issues.append(iss)
                comments = self.gql.nodes(
                    query=COMMENTS_QUERY,
                    path="repository.issue.comments",
                    variables=dict(
                        owner=iss["repository"]["owner"]["login"],
                        name=iss["repository"]["name"],
                        number=iss["number"],
                    )
                )
                issue_queries.append(comments)
        commentss = await asyncio.gather(*issue_queries)
        for iss, (_, comments) in zip(queried_issues, commentss):
            iss["comments"]["nodes"] = comments

        # Trim comments to those since our since date.
        for iss in issues:
            comments = iss["comments"]
            comments["nodes"] = self._trim_since(comments["nodes"])

        return issues

    def _add_reasons(self, issues):
        # Why were these issues in the list?
        for iss in issues:
            iss["reasonCreated"] = iss["createdAt"] > self.since
            iss["reasonClosed"] = bool(iss["closedAt"] and (iss["closedAt"] > self.since))
            iss["reasonMerged"] = bool(iss.get("mergedAt") and (iss["mergedAt"] > self.since))


SINCE = "2022-02-10T00:00:00"

# Issues in repos: arguments for get_repo_issues
ISSUES = [
    # ("nedbat/coveragepy",),
    # ("openedx/tcril-engineering",),
    # ("edx/open-source-process-wg",),
]

# Issues in projects: arguments for get_project_issues
PROJECTS = [
    ("edx", 7, "edx/open-source-process-wg"),
    ("openedx", 8, "openedx/tcril-engineering"),
]

PULL_REQUESTS = [
    ("openedx/open-edx-proposals",),
]

async def main():
    """
    Summarize all the things!

    Writes digest.html

    """
    summarizer = Summarizer(since=SINCE)
    _, prs = await summarizer.get_pull_requests("openedx/open-edx-proposals")
    json_save(prs, "out_prs.json")

    tasks = [
        *(itertools.starmap(summarizer.get_repo_issues, ISSUES)),
        *(itertools.starmap(summarizer.get_project_issues, PROJECTS)),
        *(itertools.starmap(summarizer.get_pull_requests, PULL_REQUESTS)),
    ]
    results = await asyncio.gather(*tasks)
    json_save(results, "out_digest.json")
    html = render_jinja("digest.html.j2", results=results, since=SINCE)
    with open("digest.html", "w", encoding="utf-8") as html_out:
        html_out.write(html)

asyncio.run(main())
