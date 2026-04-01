"""Tool wrappers for the Digital Workforce Platform orchestrator.

Tools are external capabilities (web search, APIs, file operations) that
specialists can invoke during task execution.
"""

from .web_search import web_search

__all__ = ["web_search"]
