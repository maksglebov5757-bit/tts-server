# FILE: tests/conftest.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Pytest configuration and shared fixtures for all test suites.
#   SCOPE: Project root path injection, shared fixtures
#   DEPENDS: none
#   LINKS: none
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   project_root - Resolved repository root injected into sys.path for tests
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT and MODULE_MAP]
# END_CHANGE_SUMMARY

"""Pytest configuration for tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to Python path - resolve to absolute path
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
