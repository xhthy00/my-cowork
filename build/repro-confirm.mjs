import { chromium } from "playwright";

const file = "/Users/tanghaoyu/develop/git-repo/agent/my-cowork/build/confirm-repro.html";
const browser = await chromium.launch({ executablePath: "/Users/tanghaoyu/Library/Caches/ms-playwright/chromium_headless_shell-1200/chrome-headless-shell-mac-arm64/chrome-headless-shell" });
const page = await browser.newPage({ viewport: { width: 640, height: 480 } });
await page.goto("file://" + file);

async function inspect(label, scrollY) {
  const info = await page.evaluate((y) => {
    const msg = document.querySelector(".messages");
    const card = document.querySelector(".card");
    msg.scrollTop = y;
    const cr = card.getBoundingClientRect();
    const mr = msg.getBoundingClientRect();
    return {
      scrollTop: msg.scrollTop,
      scrollHeight: msg.scrollHeight,
      clientHeight: msg.clientHeight,
      cardRect: { top: Math.round(cr.top), bottom: Math.round(cr.bottom), height: Math.round(cr.height), left: Math.round(cr.left), right: Math.round(cr.right), width: Math.round(cr.width) },
      msgRect: { top: Math.round(mr.top), bottom: Math.round(mr.bottom), height: Math.round(mr.height) },
    };
  }, scrollY);
  console.log(label, JSON.stringify(info));
  return info;
}

await inspect("scroll0:", 0);
await page.screenshot({ path: "/tmp/repro-scroll0.png" });

await inspect("scroll400:", 400);
await page.screenshot({ path: "/tmp/repro-scroll400.png" });

await inspect("scrollMax:", 100000);
await page.screenshot({ path: "/tmp/repro-scrollmax.png" });

await browser.close();
