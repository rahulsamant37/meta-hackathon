"""Canonical server-side environment module.

This keeps the OpenEnv course layout (server/environment.py) while routing to
the server-contained runtime package.
"""

from server.env.core import ITSMEnvironment

__all__ = ["ITSMEnvironment"]
