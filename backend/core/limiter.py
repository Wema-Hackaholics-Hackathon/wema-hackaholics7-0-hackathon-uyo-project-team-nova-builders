from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# class RateLimiter:
#     def __init__(self, limit_string: str):
#         self.limit_string = limit_string

#     async def __call__(self, request: Request):
#         # Programmatically check the limit against the request context
#         limiter.check(request, self.limit_string)