# -*- coding: utf-8 -*-
"""Buttons on the Tools page of the settings.

  test.py popup    - show a test pop-up from one of your cameras
  test.py cameras  - list the camera names UniFi reports
"""
import os
import sys

# When run with RunScript(<path>), Kodi doesn't put this add-on's folder on
# Python's search path, so "resources" can resolve to another add-on's folder.
# Put ours first and forget any "resources" package that was already loaded.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE in sys.path:
    sys.path.remove(_HERE)
sys.path.insert(0, _HERE)
for _name in [m for m in sys.modules if m == "resources" or m.startswith("resources.")]:
    del sys.modules[_name]

import xbmc
import xbmcgui

from resources.lib.config import Config, load_cameras
from resources.lib.popup import PopupController


def main(mode):
    cfg = Config()
    loaded = load_cameras(cfg)
    if loaded is None:
        return
    api, cams = loaded

    if mode == "cameras":
        lines = ["%s%s" % (name, "   [COLOR FF4CAF50](watched)[/COLOR]" if cfg.wants_camera(name) else "")
                 for name in sorted(cams.values(), key=str.lower)]
        xbmcgui.Dialog().textviewer("MoodyCam - your cameras",
                                    "[CR]".join(lines) +
                                    "[CR][CR]Type names exactly like this into Alerts > Cameras to watch.")
        return

    cam_id = next((cid for cid, n in cams.items() if cfg.wants_camera(n)), next(iter(cams)))
    popup = PopupController()
    popup.show(cfg, api, cam_id, cams[cam_id], {"test"})
    monitor = xbmc.Monitor()
    while popup.showing and not monitor.abortRequested():
        popup.tick()
        monitor.waitForAbort(0.1)
    popup.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "popup")
