# -*- coding: utf-8 -*-
"""Talks to UniFi Protect's official Integration API with an API key."""
import json
import ssl

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    from urllib.parse import urlencode
except ImportError:  # pragma: no cover
    raise

from resources.lib.wsclient import WebSocket

BASE = "/proxy/protect/integration/v1"


class AuthError(Exception):
    """UniFi said no to the API key."""


def split_host(host):
    host = (host or "").strip()
    for prefix in ("https://", "http://", "wss://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix):]
    host = host.split("/", 1)[0]
    port = 443
    if host.count(":") == 1:
        name, p = host.split(":")
        if p.isdigit():
            host, port = name, int(p)
    return host, port


def make_ssl_context(verify):
    ctx = ssl.create_default_context()
    if not verify:
        # UniFi consoles use a certificate they made for themselves, which nothing trusts.
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


class Protect(object):
    def __init__(self, host, api_key, verify_ssl=False):
        self.host, self.port = split_host(host)
        self.api_key = api_key
        self.ctx = make_ssl_context(verify_ssl)

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg.host, cfg.api_key, cfg.verify_ssl)

    def _get(self, path, query=None, timeout=5):
        url = "https://%s:%d%s%s" % (self.host, self.port, BASE, path)
        if query:
            url += "?" + urlencode(query)
        req = Request(url, headers={"X-API-KEY": self.api_key, "Accept": "*/*"})
        try:
            resp = urlopen(req, context=self.ctx, timeout=timeout)
            try:
                return resp.read()
            finally:
                resp.close()
        except HTTPError as e:
            if e.code in (401, 403):
                raise AuthError("UniFi rejected the API key (HTTP %d)" % e.code)
            raise

    def cameras(self):
        """Return {camera_id: camera_name}."""
        data = json.loads(self._get("/cameras").decode("utf-8"))
        result = {}
        for cam in data if isinstance(data, list) else []:
            if isinstance(cam, dict) and cam.get("id"):
                result[cam["id"]] = cam.get("name") or cam["id"]
        return result

    def snapshot(self, camera_id, high_quality=False):
        """Return a JPEG of what the camera sees right now."""
        return self._get("/cameras/%s/snapshot" % camera_id,
                         {"highQuality": "true" if high_quality else "false"},
                         timeout=4)

    def events_socket(self):
        return WebSocket(self.host, self.port, BASE + "/subscribe/events",
                         {"X-API-KEY": self.api_key}, self.ctx)
