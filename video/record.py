"""Record the Ledgerwise demo: drive the real app in Chrome, then add the AI voice track.

    .venv/bin/python video/record.py

The app must be running on :8765 with LEDGERWISE_GATEWAY=zetaris. Nothing is mocked: the
investigation in the video is a live run. Scene length follows the narration length.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import time

from playwright.sync_api import Page, sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
BASE = "http://localhost:8765"
W, H = 1600, 900

NARRATION = json.loads((HERE / "narration.json").read_text())
DUR = {
    k: float(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(HERE / "audio" / f"{k}.wav")]
        )
    )
    for k in NARRATION
}
starts: dict[str, float] = {}
t0 = 0.0


def now() -> float:
    return time.monotonic() - t0


def smooth(page: Page, dy: int) -> None:
    page.evaluate("dy => window.scrollBy({top: dy, behavior: 'smooth'})", dy)


def scene(key: str, page: Page, fn) -> None:
    starts[key] = now()
    fn()
    remaining = starts[key] + DUR[key] + 0.7 - now()
    if remaining > 0:
        page.wait_for_timeout(int(remaining * 1000))


def s1(page: Page) -> None:
    page.mouse.move(800, 300)
    page.wait_for_timeout(5000)
    page.mouse.move(1000, 160)


def s2(page: Page) -> None:
    page.wait_for_timeout(1500)
    page.mouse.move(1450, 28)  # status badges
    page.wait_for_timeout(2500)
    gap = page.locator("td.gap-flag").first
    gap.hover()
    page.wait_for_timeout(4500)
    page.locator(".ask .btn").hover()
    page.wait_for_timeout(1200)
    page.locator(".ask .btn").click()


def s3(page: Page) -> None:
    page.wait_for_timeout(18000)


def s4(page: Page) -> None:
    page.wait_for_selector("#tab-report:not([disabled])", timeout=90000)
    page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    page.wait_for_timeout(2500)
    page.locator("#timeline .item.plan").first.scroll_into_view_if_needed()
    page.wait_for_timeout(2500)
    survived = page.locator("#timeline .item.survived")
    survived.nth(2).scroll_into_view_if_needed()
    page.wait_for_timeout(3000)
    survived.nth(2).locator("button.chip").first.click()  # open the falsification evidence
    page.wait_for_timeout(5000)
    page.locator("#evidence").scroll_into_view_if_needed()


def s5(page: Page) -> None:
    page.locator("#tab-report").click()
    page.wait_for_timeout(4500)
    smooth(page, 420)
    page.wait_for_timeout(6500)  # summary and the Meterless receipt line
    smooth(page, 420)
    page.wait_for_timeout(6000)


def s6(page: Page) -> None:
    page.locator(".actions").scroll_into_view_if_needed()
    page.wait_for_timeout(2500)
    page.locator(".actions .btn", has_text="Approve draft").first.click()
    page.wait_for_timeout(1500)
    smooth(page, 250)


def s7(page: Page) -> None:
    page.goto(f"{BASE}/eval")
    page.wait_for_selector("table")
    page.wait_for_timeout(9000)
    smooth(page, 500)
    page.wait_for_timeout(6000)
    smooth(page, 500)


def s8(page: Page) -> None:
    page.goto(BASE)
    page.wait_for_selector("td.gap-flag")
    page.wait_for_timeout(2000)


def main() -> None:
    global t0
    raw = HERE / "raw"
    raw.mkdir(exist_ok=True)
    for old in raw.glob("*.webm"):
        old.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(raw),
            record_video_size={"width": W, "height": H},
            color_scheme="light",
        )
        page = context.new_page()
        t0 = time.monotonic()
        page.goto(BASE)
        page.wait_for_selector("td.gap-flag", timeout=60000)
        for key, fn in (("s1", s1), ("s2", s2), ("s3", s3), ("s4", s4), ("s5", s5), ("s6", s6), ("s7", s7), ("s8", s8)):
            scene(key, page, lambda fn=fn: fn(page))
        total = now()
        video_path = page.video.path()
        context.close()
        browser.close()
    (HERE / "starts.json").write_text(json.dumps({"starts": starts, "total": total}, indent=1))
    print("recorded", video_path, "total", round(total, 1), starts)


if __name__ == "__main__":
    main()
