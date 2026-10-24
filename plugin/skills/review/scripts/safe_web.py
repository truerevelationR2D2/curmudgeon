"""The browser's network boundary, by construction (SC-66 hardening, after a blind review found WebSockets, redirects,
service workers and symlinks getting past the request-by-request guard). Two parts:

1. serve(folder): the local page server. It serves files on 127.0.0.1 only, never a file whose real path (links
   followed) is outside the folder, and never a directory listing.
2. launch_args(allowed): Chromium starts with every connection sent to a proxy that doesn't exist (127.0.0.1:9, the
   discard port, refuses connections), except the origins in `allowed` (host:port). Chromium's default exemption for
   loopback addresses is switched off (<-loopback>), so another local port is blocked too. Redirects, WebSockets,
   service workers, beacons, prefetches and subresources all go through the same proxy setting, so none can reach
   anything not allowed; WebRTC is kept off UDP that would skip the proxy.

The request-by-request guard stays on top of this for what it does well: refusing methods other than GET, HEAD and
OPTIONS on the allowed origin, and logging what would have been sent."""
import functools, http.server, os, pathlib, threading, urllib.parse

DEAD_PROXY = "http://127.0.0.1:9"

class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def list_directory(self, path):
        self.send_error(404, "not found"); return None
    def translate_path(self, path):
        p = super().translate_path(path)
        base = os.path.realpath(self.directory)
        real = os.path.realpath(p)
        if real != base and not real.startswith(base.rstrip(os.sep) + os.sep): return os.path.join(base, ".curmudgeon-refused", "404")  # outside the folder: not found
        return real

def serve(folder):
    """Start the page server for folder; returns (server, origin, host_port)."""
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Handler, directory=str(pathlib.Path(folder).resolve())))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    hp = f"127.0.0.1:{srv.server_address[1]}"
    return srv, f"http://{hp}", hp

def host_port(url):
    u = urllib.parse.urlsplit(url)
    return f"{u.hostname}:{u.port or (443 if u.scheme == 'https' else 80)}"

def launch_args(allowed):
    """Chromium switches that send everything except the allowed host:port origins to a proxy that doesn't exist."""
    bypass = ";".join(["<-loopback>"] + list(allowed))
    return [f"--proxy-server={DEAD_PROXY}", f"--proxy-bypass-list={bypass}", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp", "--dns-prefetch-disable", "--disable-background-networking"]
