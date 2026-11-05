"""agentci — tests for agents.

The package is import-safe without Hermes: everything that needs the profile
(state.db) resolves lazily, so the CLI works from any checkout.
"""

__version__ = "0.1.0"
