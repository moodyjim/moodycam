# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import xbmcgui

from resources.lib.events import ALL_KINDS, in_quiet_hours

ADDON_ID = "service.moodycam"
SIZES = [(360, 203), (480, 270), (640, 360)]   # small, medium, large (on a 1280x720 grid)


def log(msg, level=xbmc.LOGINFO):
    xbmc.log("[%s] %s" % (ADDON_ID, msg), level)


def notify(msg, time_ms=5000):
    xbmcgui.Dialog().notification("MoodyCam", msg, xbmcgui.NOTIFICATION_INFO, time_ms)


class Config(object):
    """A snapshot of the add-on settings."""

    def __init__(self):
        a = xbmcaddon.Addon(ADDON_ID)
        self.host = a.getSettingString("host").strip()
        self.api_key = a.getSettingString("api_key").strip()
        self.verify_ssl = a.getSettingBool("verify_ssl")
        self.cameras = {n.strip().lower() for n in a.getSettingString("cameras").split(",") if n.strip()}
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
