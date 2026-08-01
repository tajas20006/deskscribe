"""Point frozen builds at the bundled Flet desktop client."""

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    bundle_root = Path(sys._MEIPASS)
    os.environ["FLET_VIEW_PATH"] = str(bundle_root / "flet_desktop" / "app")
