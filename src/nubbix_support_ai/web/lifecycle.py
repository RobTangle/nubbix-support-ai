import asyncio
from typing import Any

from anyio import CancelScope


async def cancel_and_drain(*tasks: asyncio.Task[Any]) -> None:
    """Cancel once and shield cleanup from Starlette's repeated cancellation."""
    for task in tasks:
        if not task.cancelling():
            task.cancel()
    with CancelScope(shield=True):
        await asyncio.gather(*tasks, return_exceptions=True)
