# -*- coding: utf-8 -*-
"""The corner pop-up: a small window that shows a camera picture,
refreshed about once a second, over whatever is playing."""
import os
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib.config import ADDON_ID, log
from resources.lib.events import describe

SCREEN_W, SCREEN_H = 1280, 720   # Kodi's default grid for WindowDialog
MARGIN = 30
LABEL_H = 36
ACTION_NONE = 0
ACTION_MOUSE_MOVE = 107
XBFONT_CENTER_Y = 0x00000004


def _media(name):
    path = xbmcvfs.translatePath(xbmcaddon.Addon(ADDON_ID).getAddonInfo("path"))
    return os.path.join(path, "resources", "media", name)


class PlaybackPauser(object):
    """Pauses what's playing, and later resumes it only if we were the ones
    who paused it (so we never un-pause something the user paused)."""

    def __init__(self, player=None):
        self.player = player or xbmc.Player()
        self.paused_by_us = False

    def pause(self, video_only=True):
        self.paused_by_us = False
        playing = self.player.isPlayingVideo() if video_only else self.player.isPlaying()
        if playing and not xbmc.getCondVisibility("Player.Paused"):
            self.player.pause()
            self.paused_by_us = True

    def resume(self):
        if not self.paused_by_us:
            return
        self.paused_by_us = False
        if self.player.isPlaying() and xbmc.getCondVisibility("Player.Paused"):
            self.player.pause()   # pause() toggles, so this resumes


class _Window(xbmcgui.WindowDialog):
    # No custom __init__ arguments on purpose: Kodi's window classes don't
    # like extra constructor arguments, so the layout is built in build().

    def build(self, x, y, w, h):
        self.dismissed = False
        white = _media("white.png")
        # dark frame behind everything
        self.addControl(xbmcgui.ControlImage(x - 3, y - 3, w + 6, h + LABEL_H + 6, white,
                                             colorDiffuse="E6000000"))
        # the camera picture (aspectRatio=2 keeps its shape, with black bars if needed)
        self.image = xbmcgui.ControlImage(x, y, w, h, "", aspectRatio=2)
        self.addControl(self.image)
        # thin red bar on top so it reads as an alert
        self.addControl(xbmcgui.ControlImage(x - 3, y - 3, w + 6, 4, white,
                                             colorDiffuse="FFE53935"))
        self.label = xbmcgui.ControlLabel(x + 10, y + h + 3, w - 20, LABEL_H - 6, "",
                                          font="font13", textColor="FFFFFFFF",
                                          alignment=XBFONT_CENTER_Y)
        self.addControl(self.label)

    def onAction(self, action):
        if action.getId() in (ACTION_NONE, ACTION_MOUSE_MOVE):
            return
        # Any button press closes the pop-up.
        self.dismissed = True
        self.close()


def _position(cfg):
    w, h = cfg.size
    total_h = h + LABEL_H
    right = SCREEN_W - MARGIN - w
    bottom = SCREEN_H - MARGIN - total_h
    return {
        0: (right, MARGIN),       # top right
        1: (MARGIN, MARGIN),      # top left
        2: (right, bottom),       # bottom right
        3: (MARGIN, bottom),      # bottom left
    }.get(cfg.position, (right, MARGIN))


class PopupController(object):
    def __init__(self):
        self.win = None
        self.cfg = None
        self.api = None
        self.cam_id = None
        self.cam_name = ""
        self.kinds_text = ""
        self.started = 0
        self.expires = 0
        self.next_refresh = 0
        self.pauser = PlaybackPauser()
        self.counter = 0
        self.files = []
        self.tmp = xbmcvfs.translatePath("special://temp/moodycam/")
        if not os.path.isdir(self.tmp):
            os.makedirs(self.tmp)

    @property
    def showing(self):
        return self.win is not None

    def show(self, cfg, api, cam_id, cam_name, kinds):
        now = time.time()
        self.cfg, self.api = cfg, api
        if self.win is None:
            w, h = cfg.size
            x, y = _position(cfg)
            self.win = _Window()
            self.win.build(x, y, w, h)
            self.win.show()
            if cfg.pause:
                self.pauser.pause(video_only=True)
        self.cam_id = cam_id
        self.cam_name = cam_name
        self.kinds_text = describe(kinds)
        self.started = now
        self.expires = now + cfg.duration
        self.next_refresh = 0
        self._update_label()
        log("pop-up: %s (%s)" % (cam_name, self.kinds_text))
        self.tick()

    def tick(self):
        if self.win is None:
            return
        now = time.time()
        if self.win.dismissed or now >= self.expires:
            self.close()
            return
        if now >= self.next_refresh:
            self.next_refresh = now + self.cfg.refresh_ms / 1000.0
            self._refresh()
            self._update_label()

    def close(self):
        win, self.win = self.win, None
        if win is not None:
            try:
                win.close()
            except Exception:
                pass
            del win
        self.pauser.resume()
        for path in self.files:
            self._delete(path)
        self.files = []

    # ---- helpers ----------------------------------------------------------
    def _update_label(self):
        if self.win is None:
            return
        left = max(0, int(self.expires - time.time()))
        self.win.label.setLabel("[B]%s[/B]  ·  %s  ·  %s   [COLOR 99FFFFFF](%ds)[/COLOR]" % (
            self.cam_name, self.kinds_text, time.strftime("%H:%M:%S", time.localtime(self.started)), left))

    def _refresh(self):
        try:
            data = self.api.snapshot(self.cam_id, self.cfg.high_quality)
        except Exception as e:
            log("snapshot failed: %s" % e, xbmc.LOGWARNING)
            return
        # A new file name every time, so Kodi can't show an old cached picture.
        self.counter += 1
        path = os.path.join(self.tmp, "snap_%d_%d.jpg" % (int(time.time()), self.counter))
        try:
            with open(path, "wb") as f:
                f.write(data)
        except Exception as e:
            log("could not save snapshot: %s" % e, xbmc.LOGWARNING)
            return
        if self.win is not None:
            self.win.image.setImage(path, False)
        self.files.append(path)
        # keep the last 3 (Kodi loads pictures in the background)
        while len(self.files) > 3:
            self._delete(self.files.pop(0))

    @staticmethod
    def _delete(path):
        try:
            os.remove(path)
        except Exception:
            pass
