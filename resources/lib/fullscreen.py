# -*- coding: utf-8 -*-
"""The full-screen camera view: up to 9 cameras in a grid, or one camera on
its own. Opened from the skin's Home menu with
RunScript(service.moodycam,fullscreen) (see default.py).

While it's open, a property on Kodi's Home window tells the background
service not to show corner pop-ups. The view also writes a heartbeat time
next to it every couple of seconds; if the view dies without clearing the
property, the heartbeat goes stale and the service ignores (and clears) it,
so pop-ups can never stay switched off.
"""
import os
import queue
import threading
import time

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib.config import log, text
from resources.lib.grid import MAX_TILES, move, tile_rects
from resources.lib.popup import (ACTION_MOUSE_MOVE, ACTION_NONE, SCREEN_H, SCREEN_W,
                                 PlaybackPauser, _media)

# ---- "is the full-screen view open?" ---------------------------------------
HOME_WINDOW = 10000
PROP_OPEN = "MoodyCam.Fullscreen"
PROP_BEAT = "MoodyCam.Fullscreen.Heartbeat"
BEAT_EVERY = 2      # seconds between heartbeats while open
STALE_AFTER = 15    # a heartbeat older than this means the view is gone


def mark_open():
    win = xbmcgui.Window(HOME_WINDOW)
    win.setProperty(PROP_BEAT, "%d" % time.time())
    win.setProperty(PROP_OPEN, "true")


def heartbeat():
    xbmcgui.Window(HOME_WINDOW).setProperty(PROP_BEAT, "%d" % time.time())


def mark_closed():
    win = xbmcgui.Window(HOME_WINDOW)
    win.clearProperty(PROP_OPEN)
    win.clearProperty(PROP_BEAT)


def is_open():
    """True while a live full-screen view is on screen."""
    win = xbmcgui.Window(HOME_WINDOW)
    if win.getProperty(PROP_OPEN) != "true":
        return False
    try:
        age = abs(time.time() - float(win.getProperty(PROP_BEAT)))
    except ValueError:
        age = STALE_AFTER + 1
    if age > STALE_AFTER:
        log("the full-screen view stopped without closing properly - pop-ups are back on",
            xbmc.LOGWARNING)
        mark_closed()
        return False
    return True


# ---- the window --------------------------------------------------------------
ACTION_MOVE_LEFT = 1
ACTION_MOVE_RIGHT = 2
ACTION_MOVE_UP = 3
ACTION_MOVE_DOWN = 4
ACTION_SELECT_ITEM = 7
ACTION_PARENT_DIR = 9
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
BACK_ACTIONS = (ACTION_PARENT_DIR, ACTION_PREVIOUS_MENU, ACTION_NAV_BACK)
ARROWS = {ACTION_MOVE_LEFT: "left", ACTION_MOVE_RIGHT: "right",
          ACTION_MOVE_UP: "up", ACTION_MOVE_DOWN: "down"}

XBFONT_CENTER_X = 0x00000002
XBFONT_CENTER_Y = 0x00000004
GAP = 4             # space between tiles
BORDER = 3          # highlight border width
NAME_H = 28         # height of the camera-name strip
HIGHLIGHT = "FFE53935"   # same red as the pop-up's alert bar
KEEP_FILES = 3      # pictures kept per camera (Kodi loads them in the background)


class _Window(xbmcgui.WindowDialog):
    # No custom __init__ arguments (see popup.py); the controller sets
    # .handler and builds the controls.
    handler = None

    def onAction(self, action):
        if self.handler is not None:
            self.handler(action.getId())


class _Tile(object):
    """The controls for one camera."""

    def __init__(self, x, y, w, h, name, font):
        white = _media("white.png")
        inner = (x + BORDER, y + BORDER, w - 2 * BORDER, h - 2 * BORDER)
        ix, iy, iw, ih = inner
        name_w = min(iw, 24 + 10 * len(name))
        self.highlight = xbmcgui.ControlImage(x, y, w, h, white, colorDiffuse=HIGHLIGHT)
        self.background = xbmcgui.ControlImage(ix, iy, iw, ih, white, colorDiffuse="FF000000")
        # aspectRatio=2 keeps the picture's shape, with black bars if needed
        self.picture = xbmcgui.ControlImage(ix, iy, iw, ih, "", aspectRatio=2)
        self.name_bar = xbmcgui.ControlImage(ix, iy + ih - NAME_H, name_w, NAME_H, white,
                                             colorDiffuse="99000000")
        self.name = xbmcgui.ControlLabel(ix + 8, iy + ih - NAME_H, name_w - 12, NAME_H, name,
                                         font=font, textColor="FFFFFFFF",
                                         alignment=XBFONT_CENTER_Y)
        self.unavailable = xbmcgui.ControlLabel(ix, iy + ih // 2 - 20, iw, 40,
                                                text(32060, "Unavailable"),
                                                font="font13", textColor="FFBBBBBB",
                                                alignment=XBFONT_CENTER_X | XBFONT_CENTER_Y)

    def controls(self):
        return [self.highlight, self.background, self.picture, self.name_bar, self.name,
                self.unavailable]

    def show(self, visible, highlighted, failed):
        self.highlight.setVisible(visible and highlighted)
        for c in (self.background, self.picture, self.name_bar, self.name):
            c.setVisible(visible)
        self.unavailable.setVisible(visible and failed)


class FullscreenView(object):
    def __init__(self, cfg, api, cameras):
        """cameras: [(camera_id, name), ...], at most 9 are shown."""
        self.cfg = cfg
        self.api = api
        self.cameras = list(cameras)[:MAX_TILES]
        self.n = len(self.cameras)
        self.selected = 0
        self.solo = None            # index of the camera shown on its own, or None (grid)
        self.closing = False
        self.win = None
        self.tiles = []
        self.solo_tile = None
        self.pauser = PlaybackPauser()
        self.results = queue.Queue()
        self.stop_evt = threading.Event()
        self.wake = [threading.Event() for _ in self.cameras]
        self.workers = []
        self.files = [[] for _ in self.cameras]
        self.failed = [False] * self.n
        self.tmp = xbmcvfs.translatePath("special://temp/moodycam/fullscreen/")
        if not os.path.isdir(self.tmp):
            os.makedirs(self.tmp)
        self._clear_tmp()

    # ---- main loop -------------------------------------------------------
    def run(self):
        monitor = xbmc.Monitor()
        mark_open()
        try:
            log("full-screen view: %s" % ", ".join(name for _, name in self.cameras))
            self.pauser.pause(video_only=False)
            self._build()
            self.win.show()
            for evt in self.wake:      # _build's "refresh now" isn't needed for the first fetch
                evt.clear()
            for i in range(self.n):
                t = threading.Thread(target=self._worker, args=(i,), name="moodycam-cam-%d" % i)
                t.daemon = True
                self.workers.append(t)
                t.start()
            last_beat = time.time()
            while not self.closing and not monitor.abortRequested():
                self._apply_results()
                if time.time() - last_beat >= BEAT_EVERY:
                    heartbeat()
                    last_beat = time.time()
                monitor.waitForAbort(0.05)
        finally:
            self._shutdown()

    def _shutdown(self):
        win, self.win = self.win, None
        if win is not None:
            try:
                win.close()
            except Exception:
                pass
            del win
        mark_closed()
        try:
            self.pauser.resume()
        except Exception as e:
            log("could not resume playback: %s" % e, xbmc.LOGWARNING)
        # Stop the picture threads and wait for them (a snapshot request can
        # take up to its 4 s timeout), so none outlive the script.
        self.stop_evt.set()
        for evt in self.wake:
            evt.set()
        deadline = time.time() + 6
        for t in self.workers:
            t.join(max(0.1, deadline - time.time()))
        while True:
            try:
                _, path, _ = self.results.get_nowait()
            except queue.Empty:
                break
            if path:
                self._delete(path)
        for paths in self.files:
            for path in paths:
                self._delete(path)
        self.files = [[] for _ in self.cameras]
        log("full-screen view closed")

    # ---- remote control --------------------------------------------------
    def _on_action(self, action_id):
        if action_id in (ACTION_NONE, ACTION_MOUSE_MOVE):
            return
        if action_id in BACK_ACTIONS:
            if self.solo is not None and self.n > 1:
                self._show_grid()
            else:
                self.closing = True
        elif action_id == ACTION_SELECT_ITEM:
            if self.solo is None and self.n > 1:
                self._show_solo(self.selected)
        elif action_id in ARROWS and self.solo is None:
            new = move(self.selected, ARROWS[action_id], self.n)
            if new != self.selected:
                self.tiles[self.selected].highlight.setVisible(False)
                self.selected = new
                self.tiles[new].highlight.setVisible(True)

    # ---- layout ----------------------------------------------------------
    def _build(self):
        self.win = _Window()
        self.win.handler = self._on_action
        white = _media("white.png")
        controls = [xbmcgui.ControlImage(0, 0, SCREEN_W, SCREEN_H, white, colorDiffuse="FF000000")]
        rects = tile_rects(self.n, SCREEN_W, SCREEN_H, GAP)
        for (x, y, w, h), (_, name) in zip(rects, self.cameras):
            tile = _Tile(x, y, w, h, name, "font12")
            self.tiles.append(tile)
            controls.extend(tile.controls())
        # One extra full-screen tile for "this camera on its own".
        self.solo_tile = _Tile(-BORDER, -BORDER, SCREEN_W + 2 * BORDER, SCREEN_H + 2 * BORDER,
                               "", "font13")
        controls.extend(self.solo_tile.controls())
        self.win.addControls(controls)
        self._show_grid()

    def _show_grid(self):
        self.solo = None
        self.solo_tile.show(False, False, False)
        for i, tile in enumerate(self.tiles):
            tile.show(True, self.n > 1 and i == self.selected, self.failed[i])
        for evt in self.wake:      # refresh every tile right away
            evt.set()

    def _show_solo(self, i):
        self.solo = i
        for tile in self.tiles:
            tile.show(False, False, False)
        name = self.cameras[i][1]
        self.solo_tile.name.setLabel(name)
        self.solo_tile.name_bar.setWidth(min(SCREEN_W, 24 + 10 * len(name)))
        self.solo_tile.name.setWidth(min(SCREEN_W, 24 + 10 * len(name)) - 12)
        if self.files[i]:
            self.solo_tile.picture.setImage(self.files[i][-1], False)
        self.solo_tile.show(True, False, self.failed[i])
        self.wake[i].set()

    # ---- pictures --------------------------------------------------------
    def _active(self, i):
        return self.solo is None or self.solo == i

    def _worker(self, i):
        """Fetches one camera's picture over and over, on its own thread, so a
        slow or broken camera never holds up the others."""
        cam_id = self.cameras[i][0]
        interval = self.cfg.refresh_ms / 1000.0
        count = 0
        while not self.stop_evt.is_set():
            if self._active(i):
                started = time.time()
                try:
                    data = self.api.snapshot(cam_id, self.cfg.high_quality)
                    count += 1
                    # A new file name every time, so Kodi can't show an old cached picture.
                    path = os.path.join(self.tmp, "cam%d_%d_%d.jpg" % (i, int(started), count))
                    with open(path, "wb") as f:
                        f.write(data)
                    self.results.put((i, path, None))
                except Exception as e:
                    self.results.put((i, None, e))
                wait = interval - (time.time() - started)
            else:
                wait = 1.0   # hidden behind another camera; check again soon
            if wait > 0 and not self.stop_evt.is_set():
                self.wake[i].wait(wait)
            self.wake[i].clear()

    def _apply_results(self):
        while True:
            try:
                i, path, err = self.results.get_nowait()
            except queue.Empty:
                return
            name = self.cameras[i][1]
            if err is not None:
                if not self.failed[i]:
                    log("camera %s unavailable: %s" % (name, err), xbmc.LOGWARNING)
                    self.failed[i] = True
                    self._refresh_unavailable(i)
                continue
            if self.failed[i]:
                log("camera %s is back" % name)
                self.failed[i] = False
                self._refresh_unavailable(i)
            self.tiles[i].picture.setImage(path, False)
            if self.solo == i:
                self.solo_tile.picture.setImage(path, False)
            self.files[i].append(path)
            while len(self.files[i]) > KEEP_FILES:
                self._delete(self.files[i].pop(0))

    def _refresh_unavailable(self, i):
        if self.solo is None:
            self.tiles[i].unavailable.setVisible(self.failed[i])
        elif self.solo == i:
            self.solo_tile.unavailable.setVisible(self.failed[i])

    def _clear_tmp(self):
        """Remove pictures left behind if Kodi stopped while the view was open."""
        try:
            for name in os.listdir(self.tmp):
                if name.startswith("cam") and name.endswith(".jpg"):
                    self._delete(os.path.join(self.tmp, name))
        except OSError:
            pass

    @staticmethod
    def _delete(path):
        try:
            os.remove(path)
        except Exception:
            pass
