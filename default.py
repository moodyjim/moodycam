# -*- coding: utf-8 -*-
"""MoodyCam's launch entry: the full-screen camera view.

  RunScript(service.moodycam,fullscreen)   - from the skin's Home menu
  (no argument)                            - from Add-ons / Programs

Both open the same view.
"""
import os
import sys

# Same search-path fix as test.py: make "resources" mean this add-on's folder.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE in sys.path:
    sys.path.remove(_HERE)
sys.path.insert(0, _HERE)
for _name in [m for m in sys.modules if m == "resources" or m.startswith("resources.")]:
    del sys.modules[_name]

import traceback

import xbmc

from resources.lib import fullscreen
from resources.lib.config import Config, fail, load_cameras, log, notify, text
from resources.lib.grid import MAX_TILES


def pick_cameras(cfg, cams):
    """[(camera_id, name), ...] for the view: the "Cameras to watch" in the
    order they were typed, or every camera by name if that setting is blank."""
    items = list(cams.items())
    if not cfg.camera_order:
        return sorted(items, key=lambda item: item[1].lower())
    rank = {name: i for i, name in enumerate(cfg.camera_order)}
    chosen = [item for item in items if item[1].strip().lower() in rank]
    return sorted(chosen, key=lambda item: rank[item[1].strip().lower()])


def main(args):
    mode = args[0] if args and args[0] else "fullscreen"
    if mode != "fullscreen":
        log("unknown argument %r - opening the full-screen view anyway" % mode, xbmc.LOGWARNING)
    if fullscreen.is_open():
        log("the full-screen view is already open")
        return
    cfg = Config()
    loaded = load_cameras(cfg, busy=True)
    if loaded is None:
        return
    api, cams = loaded
    chosen = pick_cameras(cfg, cams)
    if not chosen:
        fail(text(32062, 'None of the cameras in "Cameras to watch" were found. '
                         'Check the names with Tools > List my cameras.'))
        return
    if len(chosen) > MAX_TILES:
        notify(text(32061, "Showing the first 9 cameras"))
    fullscreen.FullscreenView(cfg, api, chosen[:MAX_TILES]).run()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        log("full-screen view failed:\n%s" % traceback.format_exc(), xbmc.LOGERROR)
        fail(text(32063, "The camera view closed because of an error. kodi.log has the details."))
