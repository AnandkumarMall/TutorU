"""
Rate limiting configuration using slowapi.

Limits are intentionally conservative to prevent:
- Denial-of-wallet attacks on paid Gemini endpoints (SEC-3)
- Database flooding
- Memory exhaustion via unbounded ChromaDB growth

Adjust limits upward if legitimate usage patterns require it.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
