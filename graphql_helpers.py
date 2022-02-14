"""
GraphQL helpers.
"""

import itertools

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

    async def nodes(self, query, path, variables=None):
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
            variables["after"] = fetched["pageInfo"]["endCursor"]
        # Remove the nodes from the top-level data we return, to keep things clean.
        fetched["nodes"] = []
        return data, nodes
