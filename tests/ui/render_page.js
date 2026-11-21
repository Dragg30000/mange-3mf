// Rend l'onglet de Mange-3MF dans Chrome avec un faux pont « orca » et des donnees de test,
// puis enregistre les captures de la documentation.
// Usage : node render_page.js <page.html> <dossier_donnees> <dossier_captures> [chemin_chrome]
const { chromium } = require('playwright-core');
const fs = require('fs'), path = require('path');
const [pageFile, dataDir, outDir, chrome] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({ executablePath: chrome || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1200, height: 700 }, deviceScaleFactor: 1.5 });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.addInitScript(() => {
    window.__sent = []; window.__handlers = [];
    window.orca = { postMessage: m => window.__sent.push(JSON.parse(JSON.stringify(m))), onMessage: f => window.__handlers.push(f), close: () => {} };
    window.__recv = m => window.__handlers.forEach(f => f(m));
  });
  await page.goto('file://' + path.resolve(pageFile));
  await page.evaluate(() => { const r = document.documentElement.style; r.setProperty('--orca-bg', '#262629'); r.setProperty('--orca-fg', '#e4e4e7'); r.setProperty('--orca-muted', '#9b9ba3'); r.setProperty('--orca-border', '#36363b'); });
  const load = n => JSON.parse(fs.readFileSync(path.join(dataDir, n)));
  const recv = m => page.evaluate(m => window.__recv(m), m);
  const sent = () => page.evaluate(() => window.__sent);
  await recv(load('state.json'));
  await recv(load('recent.json'));
  await page.screenshot({ path: path.join(outDir, '1_reglages_et_fichiers.png') });
  await page.click('#recent button[data-p]');
  await recv(load('analysis.json'));
  // l'analyse s'affiche en haut de l'onglet, au-dessus des reglages et de la liste des 3MF
  const order = await page.evaluate(() => ['s3', 's1', 's2'].map(id => document.getElementById(id).getBoundingClientRect().top));
  if (!(order[0] < order[1] && order[1] < order[2])) { console.error('analyse pas en haut', order); process.exit(1); }
  await page.locator('#s3').screenshot({ path: path.join(outDir, '2_analyse.png') });
  // autre profil pour la 5e couleur : garde apres le nouveau rendu et envoye a la conversion
  const sel = page.locator('select[data-f="0"][data-s="4"]');
  const choice = (await sel.locator('option').count()) - 1;
  await sel.selectOption(String(choice));
  if (await page.locator('select[data-f="0"][data-s="4"]').inputValue() !== String(choice)) { console.error('choix du profil perdu'); process.exit(1); }
  await page.click('#convert');
  const conv = (await sent()).slice(-1)[0];
  if (conv.command !== 'convert' || conv.files[0].slots[4].base !== choice) { console.error('plan envoye incorrect', JSON.stringify(conv).slice(0, 300)); process.exit(1); }
  // pendant la conversion, le message s'affiche sous le bouton Convertir
  if (!(await page.locator('#cstatus .msg').count())) { console.error('pas de message sous Convertir'); process.exit(1); }
  await recv({ command: 'built', token: conv.token });
  await recv(load('result.json'));
  await page.locator('#s4').screenshot({ path: path.join(outDir, '3_resultat.png') });
  // glisser-deposer d'un 3MF dans l'onglet : lu par la page et envoye a l'analyse
  await page.evaluate(() => { window.__sent.length = 0; });
  const dropped = await page.evaluate(async () => {
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array([80, 75, 3, 4, 1, 2, 3])], 'glisse.3mf'));
    document.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true }));
    const shown = document.body.classList.contains('dropping');
    document.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    await new Promise(r => setTimeout(r, 300));
    return { shown, gone: !document.body.classList.contains('dropping'), sent: window.__sent.slice(-1)[0] };
  });
  if (!dropped.shown || !dropped.gone || !dropped.sent || dropped.sent.command !== 'analyze' || dropped.sent.name !== 'glisse.3mf' || !dropped.sent.upload) {
    console.error('glisser-deposer incorrect', JSON.stringify(dropped).slice(0, 300)); process.exit(1);
  }
  // langue : changee dans l'en-tete, textes de la page refaits tout de suite et choix envoye au plugin
  const lang = load('state.json').lang;
  const other = lang === 'fr' ? 'en' : 'fr';
  await page.evaluate(() => { window.__sent.length = 0; });
  await page.selectOption('#lang', other);
  const switched = await page.evaluate(() => ({ h2: document.querySelector('#s4 h2').textContent, html: document.documentElement.lang,
    sent: window.__sent.slice(-1)[0], options: Array.from(document.querySelectorAll('#lang option')).map(o => o.value) }));
  const want = { fr: 'Fichiers prêts', en: 'Files ready' }[other];
  if (switched.h2 !== want || switched.html !== other || !switched.sent || switched.sent.command !== 'lang' || switched.sent.lang !== other
      || switched.options.join(',') !== 'auto,fr,en') {
    console.error('changement de langue incorrect', JSON.stringify(switched)); process.exit(1);
  }
  // lien Ko-fi : copie, sans quitter l'onglet
  await page.click('#kofi');
  const kofi = await page.evaluate(() => ({ text: document.getElementById('kofi').textContent, url: location.href }));
  if (!kofi.text.includes('✓') || !kofi.url.startsWith('file:')) { console.error('lien Ko-fi incorrect', JSON.stringify(kofi)); process.exit(1); }
  if (errors.length) { console.error('Erreurs JS :', errors); process.exit(1); }
  console.log('captures OK');
  await browser.close();
})();
