"""Ad+ glue package.

Putting the upstream checkout on ``sys.path`` here (and only here) keeps the
rest of the codebase free of path juggling: ``import tools.tool_registry`` and
``import lib.checkpoint`` just work once ``adplus`` is imported.
"""

from __future__ import annotations

import sys

from adplus.paths import VENDOR, ensure_vendor

if VENDOR.is_dir():
    vendor = str(ensure_vendor())
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
