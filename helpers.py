"""
Misc helpers.
"""

import json

import aiofiles

async def json_save(data, filename):
    """Write `data` to `filename` as JSON."""
    async with aiofiles.open(filename, "w", encoding="utf-8") as json_out:
        await json_out.write(json.dumps(data, indent=4))
