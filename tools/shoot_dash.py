"""Headless check of the dash-server console: every tab, every question, a DICOM render, the agent tab.
    .venv/bin/python tools/shoot_dash.py <outdir> [step ...]   steps: over demo:<k> render agent flow"""
import sys, time
from playwright.sync_api import sync_playwright
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hcconfig  # noqa: E402

URL = f"http://127.0.0.1:{hcconfig.DASH_PORT}/apps/{hcconfig.APP}/"
out, steps = sys.argv[1], sys.argv[2:] or ["over"]
errs = []


def snap(pg, path):
    """full_page does not grow past the viewport here (the app root scrolls), so size the viewport to the content."""
    h = pg.evaluate("() => Math.max(document.body.scrollHeight, document.querySelector('.page').scrollHeight)")
    pg.set_viewport_size({"width": 1600, "height": min(h + 40, 9000)}); time.sleep(1)
    pg.screenshot(path=path)
    pg.set_viewport_size({"width": 1600, "height": 1200})

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 1200})
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(URL); pg.wait_for_selector(".hw-pic", timeout=120000); time.sleep(2)
    for s in steps:
        if s == "over":
            pg.get_by_text("1 · Overview", exact=True).click(); time.sleep(1)
            snap(pg, f"{out}/over.png")
        elif s.startswith("demo:"):
            k = s.split(":")[1]
            pg.get_by_text("2 · Live demo", exact=True).click(); time.sleep(1)
            n = {"who": 1, "allergy": 2, "scans": 3, "similar": 4, "readmit": 5, "chain": 6}[k]
            pg.locator(".qbtns button").nth(n - 1).click()
            pg.wait_for_selector(".ans .big3", timeout=120000); time.sleep(4)
            snap(pg, f"{out}/demo_{k}.png")
        elif s == "render":
            pg.locator("text=Render it from the DICOM file now").nth(1).click()
            pg.wait_for_selector("text=Rendered here from the original DICOM file", timeout=60000); time.sleep(2)
            snap(pg, f"{out}/render.png")
        elif s == "simtext":
            pg.fill("#sim-text", "elderly diabetic, fever and cough, crackles at the right base")
            pg.click("#sim-go"); time.sleep(1)
            pg.wait_for_selector("text=Searched for", timeout=120000); time.sleep(2)
            snap(pg, f"{out}/simtext.png")
        elif s == "agent":
            pg.get_by_text("3 · Who is asking", exact=True).click(); time.sleep(1)
            pg.click("#ag-ask"); pg.wait_for_selector("text=What the agent did", timeout=150000); time.sleep(1)
            pg.click("#ag-bypass"); pg.wait_for_selector(".ag-no, .cached", timeout=150000); time.sleep(1)
            pg.click("#ag-audit"); pg.wait_for_selector(".ag-aud", timeout=60000); time.sleep(1)
            snap(pg, f"{out}/agent.png")
        elif s == "flow":
            pg.get_by_text("4 · How it works", exact=True).click(); pg.wait_for_selector(".hw3", timeout=60000)
            pg.click("#flow-trace"); pg.wait_for_selector(".fw-tr.tot", timeout=60000); time.sleep(1)
            snap(pg, f"{out}/flow.png")
        print("ok", s, flush=True)
    b.close()
print("console errors:", errs[:5])
