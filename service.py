# -*- coding: utf-8 -*-
"""MoodyCam: background service.

Two parts:
  * Listener (background thread) - keeps a WebSocket open to UniFi Protect and
    drops every message into a queue. It reconnects on its own if it drops.
  * Service (Kodi's main add-on thread) - reads the queue, decides if an event
    is worth a pop-up, and runs the pop-up. All screen work happens here.
"""
import json
import os
import queue
import sys
import threading
import time

# Make sure "resources" means this add-on's folder (see test.py for why).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE in sys.path:
    sys.path.remove(_HERE)
sys.path.insert(0, _HERE)

import xbmc

from resources.lib import fullscreen
from resources.lib.config import Config, log, notify
from resources.lib.events import EventTracker
from resources.lib.popup import PopupController
from resources.lib.protect import AuthError, Protect
from resources.lib.wsclient import WSClosed, WSHandshakeError, WSIdle

DEAD_AFTER = 90   # seconds with nothing from Protect (not even a pong) = reconnect


class Listener(threading.Thread):
    def __init__(self, cfg, out_q):
        threading.Thread.__init__(self, name="moodycam-listener")
        self.daemon = True
        self.cfg = cfg
        self.out_q = out_q
        self.stop_evt = threading.Event()
        self.ws = None

    def stop(self):
        self.stop_evt.set()
        ws = self.ws
        if ws is not None:
            ws.close()   # breaks the blocking read right away

    def run(self):
        backoff = 5
        while not self.stop_evt.is_set():
            try:
                api = Protect.from_config(self.cfg)
                self.out_q.put(("cameras", api.cameras()))
                self.ws = api.events_socket()
                self.ws.connect()
                self.out_q.put(("status", "connected"))
                backoff = 5
                while not self.stop_evt.is_set():
                    try:
                        text = self.ws.recv_message()
                    except WSIdle:
                        if time.time() - self.ws.last_rx > DEAD_AFTER:
                            raise WSClosed("no answer from UniFi Protect for %ds" % DEAD_AFTER)
                        self.ws.ping()
                        continue
                    if not isinstance(text, str):
                        continue
                    try:
                        msg = json.loads(text)
                    except ValueError:
                        continue
                    self.out_q.put(("event", msg))
            except AuthError as e:
                self.out_q.put(("status", "auth: %s" % e))
                backoff = 60
            except WSHandshakeError as e:
                if e.status in (401, 403):
                    self.out_q.put(("status", "auth: UniFi rejected the API key (HTTP %d)" % e.status))
                    backoff = 60
                else:
                    self.out_q.put(("status", "error: %s" % e))
            except Exception as e:
                if not self.stop_evt.is_set():
                    self.out_q.put(("status", "error: %s" % e))
            finally:
                ws, self.ws = self.ws, None
                if ws is not None:
                    ws.close()
            if self.stop_evt.wait(backoff):
                break
            backoff = min(backoff * 2, 60)


class Service(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self)
        self.settings_changed = False

    def onSettingsChanged(self):
        self.settings_changed = True

    def _start_listener(self, cfg, q):
        if not cfg.host or not cfg.api_key:
            log("no address or API key set yet - not connecting")
            notify("Add your UniFi Protect address and API key in the add-on settings")
            return None
        listener = Listener(cfg, q)
        listener.start()
        log("connecting to UniFi Protect at %s" % cfg.host)
        return listener

    def run(self):
        log("service started")
        cfg = Config()
        api = Protect.from_config(cfg)
        q = queue.Queue()
        tracker = EventTracker()
        popup = PopupController()
        cams = {}
        status = None
        listener = self._start_listener(cfg, q)

        while not self.abortRequested():
            if self.settings_changed:
                self.settings_changed = False
                new_cfg = Config()
                if new_cfg.connection_key() != cfg.connection_key():
                    if listener is not None:
                        listener.stop()
                    q = queue.Queue()
                    status = None
                    cfg = new_cfg
                    api = Protect.from_config(cfg)
                    listener = self._start_listener(cfg, q)
                else:
                    cfg = new_cfg
                    api = Protect.from_config(cfg)

            while True:
                try:
                    kind, payload = q.get_nowait()
                except queue.Empty:
                    break
                if kind == "cameras":
                    cams = payload
                    log("cameras: %s" % ", ".join(sorted(cams.values())))
                elif kind == "status":
                    if payload != status:
                        log("status: %s" % payload)
                        if payload == "connected":
                            if status is not None:
                                notify("Reconnected to UniFi Protect")
                        else:
                            notify(payload.split(": ", 1)[-1][:120], 8000)
                    status = payload
                elif kind == "event":
                    cams = self._handle_event(payload, cfg, api, tracker, popup, cams)

            if popup.showing and fullscreen.is_open():
                popup.close()   # the full-screen view just opened over it
            popup.tick()
            if self.waitForAbort(0.1 if popup.showing else 0.5):
                break

        popup.close()
        if listener is not None:
            listener.stop()
            listener.join(3)
        log("service stopped")

    def _handle_event(self, msg, cfg, api, tracker, popup, cams):
        if cfg.debug:
            log("event: %s" % json.dumps(msg)[:2000])
        res = tracker.feed(msg)
        if not res:
            return cams
        eid, cam_id, kinds = res
        wanted = kinds & cfg.kinds
        if not cam_id or not wanted:
            return cams
        name = cams.get(cam_id)
        if name is None:
            try:
                cams = api.cameras()
            except Exception as e:
                log("could not refresh camera list: %s" % e, xbmc.LOGWARNING)
            name = cams.get(cam_id, cam_id)
        if not cfg.wants_camera(name):
            return cams
        if cfg.is_quiet(time.localtime().tm_hour):
            return cams
        same_cam_up = popup.showing and popup.cam_id == cam_id
        new = tracker.should_alert(eid, cam_id, wanted, time.time(), cfg.cooldown,
                                   bypass_cooldown=same_cam_up)
        if new:
            if fullscreen.is_open():
                # The cameras are already on screen. The event still counts
                # (cooldown), so it doesn't pop up as soon as the view closes.
                log("no pop-up for %s: the full-screen view is open" % name)
            else:
                popup.show(cfg, api, cam_id, name, new)
        return cams


if __name__ == "__main__":
    Service().run()
