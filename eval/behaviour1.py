"""Behaviour tests for a refactored fixture (notes app): corrupted storage, hostile titles, empty state, phone width,
zoom, labels, a labelled delete button, and unique ids on fast creates."""
import json, pathlib, re
def run(d):
    d = pathlib.Path(d).resolve()
    from playwright.sync_api import sync_playwright
    res = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        def page(store=None):
            ctx = b.new_context(viewport={"width": 1360, "height": 900}); pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            if store is not None: pg.add_init_script(f"try {{ localStorage.setItem('notes', {json.dumps(store)}); }} catch (e) {{}}")
            pg.goto((d / "index.html").as_uri()); pg.wait_for_timeout(500); return ctx, pg, errs
        ctx, pg, errs = page("{not json"); res["corrupted storage loads without a crash"] = not errs; ctx.close()
        hostile = json.dumps([{"id": "a1", "title": "<img src=x onerror=window.__pwned=1>", "body": "", "updated": 1}])
        ctx, pg, errs = page(hostile); pg.wait_for_timeout(300); res["hostile title is shown as text"] = not pg.evaluate("() => !!window.__pwned || !!document.querySelector('#list img')"); ctx.close()
        ctx, pg, errs = page("[]"); res["empty state shown"] = bool(re.search(r"no notes|nothing here|create|first note|get started", pg.inner_text("body"), re.I)) and not errs
        pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(200); res["no sideways scroll at 390 px"] = pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 2")
        res["zoom allowed"] = not pg.evaluate("() => /maximum-scale\\s*=\\s*1|user-scalable\\s*=\\s*no/.test(document.querySelector('meta[name=viewport]')?.content || '')")
        res["inputs have names"] = pg.evaluate("() => [...document.querySelectorAll('input,textarea')].every(i => i.labels?.length || i.getAttribute('aria-label') || i.getAttribute('aria-labelledby'))"); ctx.close()
        ctx, pg, errs = page(json.dumps([{"id": "a1", "title": "One", "body": "", "updated": 1}])); pg.wait_for_timeout(200)
        res["delete is a labelled button"] = pg.evaluate("() => [...document.querySelectorAll('#list button, #list [role=button]')].some(x => /delete|remove/i.test(x.getAttribute('aria-label') || x.textContent || ''))")
        pg.evaluate("() => { const b = [...document.querySelectorAll('button')].find(x => /new/i.test(x.textContent)); if (b) { b.click(); b.click(); } }"); pg.wait_for_timeout(900)
        ids = pg.evaluate("() => { try { return JSON.parse(localStorage.getItem('notes') || '[]').map(n => String(n.id)); } catch (e) { return []; } }")
        res["two fast creates get different ids"] = len(ids) == len(set(ids)); res["no page errors"] = not errs; ctx.close(); b.close()
    return res
