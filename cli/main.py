# FILE: cli/main.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Implement the interactive CLI loop for synthesis commands.
#   SCOPE: Command parsing, synthesis dispatch, audio playback
#   DEPENDS: M-APPLICATION, M-CONTRACTS, M-CONFIG
#   LINKS: M-CLI
#   ROLE: RUNTIME
#   MAP_MODE: NONE
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT, MODULE_MAP, and function contracts]
# END_CHANGE_SUMMARY

from __future__ import annotations

from cli.runtime import run_cli


if __name__ == "__main__":
    run_cli()
