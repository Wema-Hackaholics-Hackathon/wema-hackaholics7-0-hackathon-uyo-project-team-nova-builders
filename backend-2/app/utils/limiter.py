"""Rate limiter instance shared across all routers.

Usage in a router:
    from app.utils.limiter import limiter
    from fastapi import Request

    @router.post("/login")
    @limiter.limit("5/minute")
    async def login(request: Request, ...):
        ...

The limiter key defaults to the client IP address.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
