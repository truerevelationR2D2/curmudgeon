"""Behaviour tests for a refactored fixture2 (OrderDesk). The app is served over a local HTTP server (so a fix that moves
the API to the same origin works). The API is mocked by path on any origin: /orders returns ORDERS, /refund(s) returns
HTTP 500 (so a refund must NOT report success). The app's own files are served as-is; any other host gets 404."""
import json, pathlib, re
ORDERS = [{"id": f"o{i}", "customer": {"name": f"Cust {i:02d}", "tier": "gold" if i % 3 == 0 else "std"}, "total": 10 + i, "status": ["paid", "refunded", "pending"][i % 3]} for i in range(1, 24)]
ORDERS[0]["customer"]["name"] = "<img src=x onerror=window.__pwned=1>"
def run(d: pathlib.Path):
    d = pathlib.Path(d).resolve()
    from playwright.sync_api import sync_playwright
    src = "\n".join(p.read_text(errors="ignore") for p in d.rglob("*") if p.suffix in (".js", ".html", ".css"))
    res = {"no live secret key in client files": "sk_live_" not in src}
    import functools, http.server, threading
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(d)))
    threading.Thread(target=srv.serve_forever, daemon=True).start(); origin = f"http://127.0.0.1:{srv.server_address[1]}"
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        def page(data, w=1360):
            ctx = b.new_context(viewport={"width": w, "height": 900}); pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda dl: dl.accept())
            def route(r):
                u = r.request.url
                path = re.sub(r"^\w+://[^/]*", "", u).split("?")[0]
                if re.search(r"/refunds?\b", path) and not re.search(r"\.(js|css|html)$", path): return r.fulfill(status=500, body='{"error":"refunds are down"}', content_type="application/json")
                if re.search(r"/orders\b", path) and not re.search(r"\.(js|css|html)$", path): return r.fulfill(status=200, body=json.dumps(data), content_type="application/json")
                if u.startswith(origin): return r.continue_()
                return r.fulfill(status=404, body="{}", content_type="application/json")
            ctx.route("**/*", route)
            pg.goto(origin + "/index.html"); pg.wait_for_timeout(900); return ctx, pg, errs
        ctx, pg, errs = page(ORDERS)
        body = pg.inner_text("body")
        res["hostile customer name shown as text"] = "<img src=x" in body and not pg.evaluate("() => !!window.__pwned || !!document.querySelector('tbody img')")
        res["first page shows the first orders"] = "Cust 02" in body
        rows = pg.evaluate("() => { const t = document.querySelector('tbody') || document.querySelector('[role=table],[role=grid],ul,ol'); return t ? t.innerText : ''; }")
        res["status readable without colour"] = bool(re.search(r"\bpaid\b", rows, re.I)) and bool(re.search(r"\bpending\b", rows, re.I))
        res["refund is a real button"] = pg.evaluate("() => [...document.querySelectorAll('button,[role=button]')].some(b => /refund/i.test(b.textContent + (b.getAttribute('aria-label')||'')))")
        res["search and status have names"] = pg.evaluate("() => [...document.querySelectorAll('input:not([type=checkbox]),select')].every(i => i.labels?.length || i.getAttribute('aria-label') || i.getAttribute('aria-labelledby'))")
        css = "\n".join(p.read_text(errors="ignore") for p in d.rglob("*.css"))
        res["focus not removed without replacement"] = ("outline: none" not in css and "outline:none" not in css) or ":focus-visible" in css
        res["reduced motion respected"] = "infinite" not in css or "prefers-reduced-motion" in css
        # refund that fails must not be reported as done
        pg.evaluate("() => { const c = document.querySelector('tbody input[type=checkbox]'); if (c) { c.click(); } }")
        btn = pg.query_selector("button:has-text('Refund'), [role=button]:has-text('Refund')")
        if btn:
            try: btn.click(timeout=3000)
            except Exception: pass
            pg.wait_for_timeout(400)
        dlg = pg.query_selector("dialog[open] button:has-text('Refund'), [role=dialog] button:has-text('Refund'), dialog[open] button:has-text('Confirm'), [role=dialog] button:has-text('Confirm')")
        if dlg:
            try: dlg.click(timeout=3000)
            except Exception: pass
        pg.wait_for_timeout(900); after = pg.inner_text("body")
        res["failed refund not reported as success"] = bool(btn) and not re.search(r"refunded \d+|refund(ed)? (complete|succe)", after, re.I)
        res["failed refund tells the user"] = bool(btn) and bool(re.search(r"couldn|could not|failed|error|didn.t|not refunded|try again", after, re.I))
        res["no page errors (full list)"] = not errs; ctx.close()
        ctx, pg, errs = page([]); body = pg.inner_text("body")
        res["empty list: no NaN, says so"] = "NaN" not in body and bool(re.search(r"no orders|nothing|none|0 orders|no results", body, re.I)) and not errs; ctx.close()
        ctx, pg, errs = page(ORDERS, 390)
        res["no sideways scroll at 390 px"] = pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 2"); ctx.close()
        b.close()
    srv.shutdown()
    return res
