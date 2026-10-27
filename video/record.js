// Record the Ledgerwise demo by driving the real app in Chrome and capturing CDP screencast frames.
//   node video/record.js   (app must be running on :8765 with LEDGERWISE_GATEWAY=zetaris)
// Nothing is mocked: the investigation in the video is a live run. Scenes last as long as the narration.
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const HERE = __dirname;
const BASE = "http://localhost:8765";
const W = 1600, H = 900;
const NARRATION = JSON.parse(fs.readFileSync(path.join(HERE, "narration.json"), "utf8"));
const DUR = {};
for (const k of Object.keys(NARRATION)) {
  DUR[k] = parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path.join(HERE, "audio", `${k}.wav`)]).toString());
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const nowS = () => Date.now() / 1000;
const starts = {};
const smooth = (page, dy) => page.evaluate((d) => window.scrollBy({ top: d, behavior: "smooth" }), dy);

async function scene(key, fn) {
  starts[key] = nowS();
  await fn();
  const remaining = starts[key] + DUR[key] + 0.7 - nowS();
  if (remaining > 0) await sleep(remaining * 1000);
}

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: W, height: H }, colorScheme: "light" });
  const page = await context.newPage();
  const client = await context.newCDPSession(page);
  const frames = [];
  client.on("Page.screencastFrame", async (f) => {
    frames.push({ t: f.metadata.timestamp, data: Buffer.from(f.data, "base64") });
    try { await client.send("Page.screencastFrameAck", { sessionId: f.sessionId }); } catch (e) { /* closing */ }
  });
  await client.send("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: W, maxHeight: H, everyNthFrame: 1 });

  await page.goto(BASE);
  await page.waitForSelector("td.gap-flag", { timeout: 60000 });

  await scene("s1", async () => { await page.mouse.move(800, 300); await sleep(5000); await page.mouse.move(1000, 160); });
  await scene("s2", async () => {
    await sleep(1500);
    await page.mouse.move(1450, 28); await sleep(2500);
    await page.locator("td.gap-flag").first().hover(); await sleep(4500);
    await page.locator(".ask .btn").hover(); await sleep(1200);
    await page.locator(".ask .btn").click();
  });
  await scene("s3", async () => { await sleep(18000); });
  await scene("s4", async () => {
    await page.waitForSelector("#tab-report:not([disabled])", { timeout: 90000 });
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await sleep(2500);
    await page.locator("#timeline .item.plan").first().scrollIntoViewIfNeeded(); await sleep(2500);
    const survived = page.locator("#timeline .item.survived");
    await survived.nth(2).scrollIntoViewIfNeeded(); await sleep(3000);
    await survived.nth(2).locator("button.chip").first().click(); await sleep(5000);
    await page.locator("#evidence").scrollIntoViewIfNeeded();
  });
  await scene("s5", async () => {
    await page.locator("#tab-report").click(); await sleep(4500);
    await smooth(page, 420); await sleep(6500);
    await smooth(page, 420); await sleep(6000);
  });
  await scene("s6", async () => {
    await page.locator(".actions").scrollIntoViewIfNeeded(); await sleep(2500);
    await page.locator(".actions .btn", { hasText: "Approve draft" }).first().click(); await sleep(1500);
    await smooth(page, 250);
  });
  await scene("s7", async () => {
    await page.goto(`${BASE}/eval`); await page.waitForSelector("table");
    await sleep(9000); await smooth(page, 500); await sleep(6000); await smooth(page, 500);
  });
  await scene("s8", async () => {
    await page.goto(BASE); await page.waitForSelector("td.gap-flag"); await sleep(2000);
  });
  const end = nowS();
  await sleep(800);
  await client.send("Page.stopScreencast");
  await browser.close();

  // frames -> constant-rate mp4
  const dir = path.join(HERE, "frames");
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir);
  const t0 = frames[0].t;
  const list = [];
  frames.forEach((f, i) => {
    const name = `f${String(i).padStart(6, "0")}.jpg`;
    fs.writeFileSync(path.join(dir, name), f.data);
    const next = i + 1 < frames.length ? frames[i + 1].t : end + 0.8;
    list.push(`file '${name}'`, `duration ${Math.max(0.01, next - f.t).toFixed(4)}`);
  });
  list.push(`file 'f${String(frames.length - 1).padStart(6, "0")}.jpg'`);
  fs.writeFileSync(path.join(dir, "list.txt"), list.join("\n"));
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", path.join(dir, "list.txt"),
    "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p", "-r", "30", "-fps_mode", "cfr", "-c:v", "libx264", "-preset", "medium", "-crf", "20", path.join(HERE, "silent.mp4")]);
  const rel = {};
  for (const [k, v] of Object.entries(starts)) rel[k] = +(v - t0).toFixed(3);
  fs.writeFileSync(path.join(HERE, "starts.json"), JSON.stringify({ starts: rel, total: end - t0 }, null, 1));
  console.log("frames", frames.length, "total", (end - t0).toFixed(1), rel);
})().catch((e) => { console.error(e); process.exit(1); });
