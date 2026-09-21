#!/usr/bin/env python3
"""把 assets/readme-banner.html 渲染成 README 用的 light/dark PNG。"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = ROOT / "assets" / "readme-banner.html"
OUT = ROOT / "assets"


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("需要 playwright：pip install playwright && playwright install chromium")
        sys.exit(1)

    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        for name, dark in (("banner-light", False), ("banner-dark", True)):
            ctx = browser.new_context(
                device_scale_factor=2,
                color_scheme="dark" if dark else "light",
            )
            page = ctx.new_page()
            page.set_viewport_size({"width": 1400, "height": 420})
            page.goto(HTML.resolve().as_uri())
            page.wait_for_timeout(600)
            page.evaluate("document.fonts.ready")
            out = OUT / f"{name}.png"
            page.screenshot(path=str(out))
            print(f"✓ {out}")
            ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
