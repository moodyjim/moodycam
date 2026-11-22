# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import xbmcgui

from resources.lib.events import ALL_KINDS, in_quiet_hours
from resources.lib.protect import Protect

ADDON_ID = "service.moodycam"
SIZES = [(360, 203), (480, 270), (640, 360)]   # small, medium, large (on a 1280x720 grid)


def log(msg, level=xbmc.LOGINFO):
    xbmc.log("[%s] %s" % (ADDON_ID, msg), level)


def notify(msg, time_ms=5000):
    xbmcgui.Dialog().notification("MoodyCam", msg, xbmcgui.NOTIFICATION_INFO, time_ms)


def text(string_id, fallback):
    """A string from resources/language/.../strings.po.

    Kodi keeps an add-on's strings in memory until it restarts, so right
    after an update a new string can come back empty; then use the English
    fallback instead of showing nothing.
    """
    return xbmcaddon.Addon(ADDON_ID).getLocalizedString(string_id) or fallback


def fail(msg):
    xbmcgui.Dialog().ok("MoodyCam", msg)


def load_cameras(cfg, busy=False):
    """Connect and return (api, {camera_id: name}), or None after telling the user why not.

    Shared by the Tools buttons (test.py) and the full-screen view (default.py).
    busy=True shows Kodi's spinner while connecting.
    """
    if not cfg.host or not cfg.api_key:
        fail("Add your UniFi Protect address and API key in the add-on settings first.")
        return None
    api = Protect.from_config(cfg)
    if busy:
        xbmc.executebuiltin("ActivateWindow(busydialognocancel)")
    try:
        cams = api.cameras()
        error = None
    except Exception as e:
        cams, error = None, e
    finally:
        if busy:
            xbmc.executebuiltin("Dialog.Close(busydialognocancel)")
    if error is not None:
        fail("Could not reach UniFi Protect at %s.[CR][CR]%s" % (cfg.host, error))
        return None
    if not cams:
        fail("Connected, but UniFi didn't report any cameras.")
        return None
    return api, cams


class Config(object):
    """A snapshot of the add-on settings."""

    def __init__(self):
        a = xbmcaddon.Addon(ADDON_ID)
        self.host = a.getSettingString("host").strip()
        self.api_key = a.getSettingString("api_key").strip()
        self.verify_ssl = a.getSettingBool("verify_ssl")
        # "Cameras to watch", lower-cased, in the order the user typed them.
        self.camera_order = []
        for n in a.getSettingString("cameras").split(","):
            n = n.strip().lower()
            if n and n not in self.camera_order:
                self.camera_order.append(n)
        self.cameras = set(self.camera_order)
        self.kinds = {k for k in ALL_KINDS if a.getSettingBool("ev_" + k)}
        self.cooldown = a.getSettingInt("cooldown")
        self.quiet_enabled = a.getSettingBool("quiet_enabled")
        self.quiet_start = a.getSettingInt("quiet_start")
        self.quiet_end = a.getSettingInt("quiet_end")
        self.duration = a.getSettingInt("duration")
        self.position = a.getSettingInt("position")
        self.size = SIZES[min(max(a.getSettingInt("size"), 0), len(SIZES) - 1)]
        self.refresh_ms = max(250, a.getSettingInt("refresh_ms"))
        self.high_quality = a.getSettingBool("high_quality")
        self.pause = a.getSettingBool("pause_playback")
        self.debug = a.getSettingBool("debug")

    def connection_key(self):
        return (self.host, self.api_key, self.verify_ssl)

    def is_quiet(self, hour):
        return self.quiet_enabled and in_quiet_hours(hour, self.quiet_start, self.quiet_end)

    def wants_camera(self, name):
        return not self.cameras or (name or "").strip().lower() in self.cameras
