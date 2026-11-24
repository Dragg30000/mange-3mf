// Trois ecrans du panneau de Preparer cote a cote, dans des panneaux comme ceux d'Orca (titre « Mange-3MF », croix) :
// la U1 reclame le 3MF, couleurs et profils (une couleur en plus), fichier pret. Pour les modes d'emploi et les visuels.
// Usage : node shoot_panel.js <panel.html> <dossier_messages> <image_sortie.png> <fr|en> [chemin_chrome]
const { chromium } = require('playwright-core');
const fs = require('fs'), path = require('path'), os = require('os');
const [pageFile, dataDir, outFile, lang, chrome] = process.argv.slice(2);
const load = n => JSON.parse(fs.readFileSync(path.join(dataDir, n)));
const STEPS = { fr: ['Elle réclame le 3MF', 'Tu choisis couleurs et profils', 'Le projet est prêt'],
                en: ['She asks for the 3MF', 'You pick colors and profiles', 'The project is ready'] }[lang];
const W = 340, H = 700;
(async () => {
  const browser = await chromium.launch({ executablePath: chrome || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const shots = [];
  async function fresh() {
    const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
    await page.addInitScript(() => {
      window.__handlers = [];
      window.orca = { postMessage: () => {}, onMessage: f => window.__handlers.push(f), close: () => {} };
      window.__recv = m => window.__handlers.forEach(f => f(JSON.parse(JSON.stringify(m))));
    });
    await page.goto('file://' + path.resolve(pageFile));
    await page.evaluate(() => document.fonts.ready);
    return page;
  }
  const recv = (page, m) => page.evaluate(m => window.__recv(m), m);
  const hello = load('hello.json'), offer = load('offer.json'), an = load('analysis.json'), res = load('result.json');
  // 1. Miam
  let page = await fresh();
  await recv(page, hello); await recv(page, Object.assign({}, offer, { replay: true }));
  await page.waitForTimeout(500); shots.push(await page.screenshot({ type: 'png' })); await page.close();
  // 2. couleurs et profils : une couleur en plus avec un de tes prereglages (rose)
  page = await fresh();
  await recv(page, hello); await recv(page, Object.assign({}, an, { replay: true }));
  await page.click('#map button.addc');
  const rose = an.profiles.findIndex(p => p.name === 'JAYO PLA Rose');
  const n = an.files[0].slots.length;
  await page.selectOption('#map select[data-s="' + n + '"]', String(rose));
  await page.waitForTimeout(300); shots.push(await page.screenshot({ type: 'png' })); await page.close();
  // 3. pret : sans l'avertissement PETG du plan de test (l'ecran 2 ne garde que des PLA)
  page = await fresh();
  const done = Object.assign({}, res, { replay: true, files: res.files.map(f => Object.assign({}, f, { warnings: [] })) });
  await recv(page, hello); await recv(page, Object.assign({}, an, { replay: true })); await recv(page, done);
  await page.waitForTimeout(300); shots.push(await page.screenshot({ type: 'png' })); await page.close();
  // planche : trois panneaux d'Orca
  const imgs = shots.map(b => 'data:image/png;base64,' + b.toString('base64'));
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;background:#141518;font:14px/1.3 system-ui,"Segoe UI",sans-serif}
.row{display:inline-flex;gap:22px;padding:22px 24px 26px}
.step{display:flex;flex-direction:column;gap:10px}
.lab{display:flex;align-items:center;gap:9px;color:#E9EAEC;font-weight:650;font-size:15px}
.lab b{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:5px;background:#22B3A5;color:#0C2E2A;font-size:13px}
.dock{width:${W + 2}px;border:1px solid #3A3D43;border-radius:4px;overflow:hidden;background:#1C1D20}
.dock .t{height:24px;display:flex;align-items:center;justify-content:space-between;padding:0 8px;background:#2B2D31;color:#D8D9DC;font-size:12px}
.dock .t i{font-style:normal;font-size:15px;color:#BFC1C5}
.dock img{display:block;width:${W}px;height:${H}px}
</style></head><body><div class="row" id="row">${imgs.map((src, i) => `<div class="step"><div class="lab"><b>${i + 1}</b>${STEPS[i]}</div>
<div class="dock"><div class="t"><span>Mange-3MF</span><i>×</i></div><img src="${src}"></div></div>`).join('')}</div></body></html>`;
  const tmp = path.join(os.tmpdir(), 'mange3mf_planche_' + lang + '.html');
  fs.writeFileSync(tmp, html);
  page = await browser.newPage({ viewport: { width: 1200, height: 800 }, deviceScaleFactor: 2 });
  await page.goto('file://' + tmp);
  await page.waitForTimeout(200);
  await page.locator('#row').screenshot({ path: outFile });
  await browser.close();
})();
