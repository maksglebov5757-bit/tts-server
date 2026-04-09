# FILE: server/__init__.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Re-export the FastAPI application instance.
#   SCOPE: barrel re-export for app
#   DEPENDS: M-SERVER
#   LINKS: M-SERVER
#   ROLE: BARREL
#   MAP_MODE: SUMMARY
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   app - Re-export the package-level FastAPI application instance
#   create_app - Re-export the server application factory for tests and bootstrap flows
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT, MODULE_MAP, and function contracts]
# END_CHANGE_SUMMARY

from __future__ import annotations

from server.app import app, create_app

__all__ = ["app", "create_app"]
