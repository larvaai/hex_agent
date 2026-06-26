"""Live IDE backend for the control-plane UI — runs the real agent and serves a file API.

``python -m ui.ide`` starts the server (control-plane contract + ``/api/files/*``). See
``ui/ide/server.py`` for the HTTP surface and ``plans/260626-0422-control-plane-ide/plan.md``.
"""
from .server import IdeControlServer, main

__all__ = ["IdeControlServer", "main"]
