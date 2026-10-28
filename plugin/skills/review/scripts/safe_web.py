"""The browser's network boundary, by construction (SC-66 hardening, after a blind review found WebSockets, redirects,
service workers and symlinks getting past the request-by-request guard). Two parts:

1. serve(folder): the local page server. It serves files on 127.0.0.1 only, never a file whose real path (links
   followed) is outside the folder, never a dot-named file or folder (.critic/, .git/, .env; .well-known is allowed),
   and never a directory listing.
2. launch_args(allowed): Chromium starts with every connection sent to a proxy that doesn't exist (127.0.0.1:9, the
   discard port, refuses connections), except the origins in `allowed` (host:port). Chromium's default exemption for
   loopback addresses is switched off (<-loopback>), so another local port is blocked too. Redirects, WebSockets,
   service workers, beacons, prefetches and subresources all go through the same proxy setting, so none can reach
   anything not allowed; WebRTC is kept off UDP that would skip the proxy.

The request-by-request guard stays on top of this for what it does well: refusing methods other than GET, HEAD and
OPTIONS on the allowed origin, and logging what would have been sent."""
import functools, http.server, os, pathlib, re, threading, urllib.parse

DEAD_PROXY = "http://127.0.0.1:9"

# Controls named like this are destructive: the browser driver refuses them when writes are real (--allow-writes),
# and the scan clicks them only in the simulation. One list, so the two can't drift apart (round 3, F-6e011ff2).
DESTRUCTIVE = re.compile(r"(?i)\b(delete|remove|destroy|erase|drop|purge|wipe|clear|reset|discard|revoke|terminate|trash|archive|uninstall|truncate|disable|reject|log\s*out|sign\s*out|pay|purchase|buy|checkout|place\s*order|send|transfer|withdraw|submit\s*payment|unsubscribe|cancel\s*(subscription|account)|close\s*account|deactivate)\b")

def hidden(part):
    """A dot-named path part (.critic, .git, .env, .ssh) is never served; .well-known is a public convention and is.
    '.' and '..' are left to the folder check."""
    return part.startswith(".") and part not in (".", "..", ".well-known")

class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def list_directory(self, path):
        self.send_error(404, "not found"); return None
    def translate_path(self, path):
        p = super().translate_path(path)
        base = os.path.realpath(self.directory)
        real = os.path.realpath(p)
        refused = os.path.join(base, ".curmudgeon-refused", "404")
        if real != base and not real.startswith(base.rstrip(os.sep) + os.sep): return refused  # outside the folder: not found
        asked = urllib.parse.unquote(urllib.parse.urlsplit(path).path).replace("\\", "/").split("/")
        if any(hidden(x) for x in asked + os.path.relpath(real, base).split(os.sep)): return refused  # .critic/, .git/, .env ...: never served
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

def words(text):
    """camelCase, snake_case, kebab-case, digits and paths split into words, so deleteBtn, btnDelete1, XMLDelete,
    delete_account and /api/remove_user all read as words to the destructive-control check (browse.py and the scan)."""
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    t = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", t)
    t = re.sub(r"([A-Za-z])(\d)|(\d)([A-Za-z])", lambda m: f"{m.group(1) or m.group(3)} {m.group(2) or m.group(4)}", t)
    return re.sub(r"[_\-/.#?=&]+", " ", t).lower()

def looks_destructive(text, rx, attrs=""):
    """rx (a destructive-word pattern) found in text and attrs split into words, or at the start of an all-capitals run
    in attrs (an id, link, form action or title such as DELETEALL, where no case change marks the word boundary). The
    visible name is left out of the all-capitals test: CSS text-transform makes "Dropdown" read DROPDOWN."""
    if rx.search(words(f"{text} {attrs}")): return True
    for tok in re.findall(r"[A-Z]{6,}", str(attrs)):
        if any(rx.search(tok[:i].lower() + " " + tok[i:].lower()) for i in range(3, len(tok) - 1)): return True
    return False

ATTRS_JS = "el => [el.id || '', el.getAttribute('href') || '', el.form ? (el.form.getAttribute('action') || '') : '', el.getAttribute('formaction') || '', el.getAttribute('title') || '', el.getAttribute('data-action') || ''].join(' ')"

def launch_args(allowed):
    """Chromium switches that send everything except the allowed host:port origins to a proxy that doesn't exist."""
    bypass = ";".join(["<-loopback>"] + list(allowed))
    return [f"--proxy-server={DEAD_PROXY}", f"--proxy-bypass-list={bypass}", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp", "--dns-prefetch-disable", "--disable-background-networking"]
