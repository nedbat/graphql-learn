"""
Misc helpers.
"""

import json

def json_save(data, filename):
    """Write `data` to `filename` as JSON."""
    with open(filename, "w", encoding="utf-8") as json_out:
        json.dump(data, json_out, indent=4)
