"""
GraphQL helpers.
"""

import itertools
import re

import glom
import python_graphql_client

from helpers import json_save


JSON_NAMES = (f"out_{i:02}.json" for i in itertools.count())

class GraphqlHelper:
    """
    A helper for GraphQL, including error handling and pagination.
    """

    def __init__(self, endpoint, token):
        self.client = python_graphql_client.GraphqlClient(
            endpoint=endpoint,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def execute(self, query, variables=None):
        """
        Execute one GraphQL query, with logging and error handling.
        """
        args = ", ".join(f"{k}: {v!r}" for k, v in variables.items())
        print(query.splitlines()[0] + args + ")")
        data = await self.client.execute_async(query=query, variables=variables)
        await json_save(data, next(JSON_NAMES))
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

    async def nodes(self, query, path, variables=None, donefn=None):
        """
        Execute a GraphQL query, and follow the pagination to get all the nodes.

        Returns the last query result (for the information outside the pagination),
        and the list of all paginated nodes.
        """
        nodes = []
        variables = dict(variables)
        while True:
            data = await self.execute(query, variables)
            fetched = glom.glom(data, f"data.{path}")
            nodes.extend(fetched["nodes"])
            if not fetched["pageInfo"]["hasNextPage"]:
                break
            if donefn is not None and donefn(fetched["nodes"]):
                break
            variables["after"] = fetched["pageInfo"]["endCursor"]
        # Remove the nodes from the top-level data we return, to keep things clean.
        fetched["nodes"] = []
        return data, nodes


def build_query(gql_filename):
    """Read a GraphQL file, and complete it with requested fragments."""
    filenames = [gql_filename]
    query = []

    seen_filenames = set()
    while filenames:
        next_filenames = []
        for filename in filenames:
            with open(filename, encoding="utf-8") as gql_file:
                gtext = gql_file.read()
            query.append(gtext)

            for match in re.finditer(r"#\s*fragment: ([.\w]+)", gtext):
                frag_name = match[1]
                if frag_name not in seen_filenames:
                    next_filenames.append(frag_name)
                    seen_filenames.add(frag_name)
        filenames = next_filenames

    return "\n".join(query)
