import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const puppeteer = require('/Users/tanghaoyu/.npm/_npx/702923228c2ce1e6/node_modules/puppeteer-core');
const here = path.dirname(fileURLToPath(import.meta.url));
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
  args: ['--disable-gpu', '--no-sandbox', '--disable-setuid-sandbox'],
});

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
  await page.goto(`file://${path.join(here, 'index.html')}`, { waitUntil: 'networkidle0' });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map((image) => image.decode()));
  });
  const size = await page.$eval('#poster', (el) => ({ width: el.scrollWidth, height: el.scrollHeight }));
  await page.screenshot({ path: path.join(here, 'MyCowork-v0.1.1-real-ui-long-poster.png'), fullPage: true, type: 'png' });
  console.log(`Poster rendered: ${size.width} × ${size.height}`);
} finally {
  await browser.close();
}
