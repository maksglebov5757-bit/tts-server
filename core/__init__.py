# FILE: core/__init__.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Re-export public API of the core runtime package.
#   SCOPE: barrel re-exports for CoreRuntime, CoreSettings, build_runtime
#   DEPENDS: M-BOOTSTRAP, M-CONFIG
#   LINKS: M-BOOTSTRAP
#   ROLE: BARREL
#   MAP_MODE: SUMMARY
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   CoreRuntime - Frozen dataclass holding all wired runtime components
#   CoreSettings - Shared runtime configuration
#   build_runtime - Factory function to assemble CoreRuntime
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT, MODULE_MAP, and function contracts]
# END_CHANGE_SUMMARY

from core.bootstrap import CoreRuntime, build_runtime
from core.config import CoreSettings

__all__ = ["CoreRuntime", "CoreSettings", "build_runtime"]
