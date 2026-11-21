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
  // tes prereglages sont proposes dans un groupe a part
  const groups = await sel.locator('optgroup').evaluateAll(gs => gs.map(g => g.children.length));
  if (groups.length < 2 || groups[1] < 1) { console.error('prereglages absents de la liste', groups); process.exit(1); }
  await sel.selectOption(String(choice));
  if (await page.locator('select[data-f="0"][data-s="4"]').inputValue() !== String(choice)) { console.error('choix du profil perdu'); process.exit(1); }
  // couleur changee a la main pour le 1er filament : signalee, gardee et envoyee
  await page.evaluate(() => { const i = document.querySelector('input.pick[data-cf="0"][data-cs="0"]'); i.value = '#123456'; i.dispatchEvent(new Event('change')); });
  if (!(await page.locator('a.reset').count())) { console.error('couleur changee non signalee'); process.exit(1); }
  if (await page.locator('select[data-f="0"][data-s="4"]').inputValue() !== String(choice)) { console.error('choix du profil perdu apres la couleur'); process.exit(1); }
  await page.click('#convert');
  const conv = (await sent()).slice(-1)[0];
  if (conv.command !== 'convert' || conv.files[0].slots[4].base !== choice || conv.files[0].slots[0].color !== '#123456'
      || conv.files[0].slots[1].color !== null) { console.error('plan envoye incorrect', JSON.stringify(conv).slice(0, 400)); process.exit(1); }
  // pendant la conversion, le message s'affiche sous le bouton Convertir
  if (!(await page.locator('#cstatus .msg').count())) { console.error('pas de message sous Convertir'); process.exit(1); }
  await recv({ command: 'built', token: conv.token });
  await recv(load('result.json'));
  await page.locator('#s4').screenshot({ path: path.join(outDir, '3_resultat.png') });
  // la U1 gourmande : dans la liste des 3MF, et en grand quand on glisse un fichier sur l'onglet
  const html = fs.readFileSync(pageFile, 'utf-8');
  const L = JSON.parse(html.slice(html.indexOf('var L=') + 6, html.indexOf(';\nvar nav')));
  const T = L[load('state.json').lang];
  if (!(await page.locator('#u1small svg.u1').count())) { console.error('U1 absente de la liste des 3MF'); process.exit(1); }
  const chooser = await Promise.all([page.waitForEvent('filechooser', { timeout: 3000 }), page.click('#u1zone')]).then(() => true, () => false);
  if (!chooser) { console.error('clic sur la U1 : pas de choix de fichier'); process.exit(1); }
  await page.evaluate(() => { const dt = new DataTransfer(); dt.items.add(new File(['x'], 'faim.3mf')); document.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true })); });
  await page.waitForTimeout(450);
  await page.screenshot({ path: path.join(outDir, '4_glouton.png') });
  await page.evaluate(() => document.dispatchEvent(new DragEvent('dragleave', { bubbles: true })));
  if (!(await page.evaluate(() => document.getElementById('eat').classList.contains('hidden')))) { console.error('grande U1 pas cachee apres dragleave'); process.exit(1); }
  // 3MF lache : lu par la page et envoye a l'analyse ; la U1 avale puis mache
  await page.evaluate(() => { window.__sent.length = 0; });
  const dropped = await page.evaluate(async () => {
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array([80, 75, 3, 4, 1, 2, 3])], 'glisse.3mf'));
    const big = () => document.querySelector('#eatU svg').getAttribute('class');
    document.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true }));
    const hungry = { shown: !document.getElementById('eat').classList.contains('hidden'), cls: big(), cap: document.getElementById('eatCap').textContent };
    document.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    const chomp = big();
    await new Promise(r => setTimeout(r, 1200));
    return { hungry, chomp, chew: big(), cap: document.getElementById('eatCap').textContent, sent: window.__sent.slice(-1)[0] };
  });
  if (!dropped.hungry.shown || !/hungry/.test(dropped.hungry.cls) || dropped.hungry.cap !== T.drop || !/chomp/.test(dropped.chomp)
      || !/chew/.test(dropped.chew) || dropped.cap !== T.u1_chew
      || !dropped.sent || dropped.sent.command !== 'analyze' || dropped.sent.name !== 'glisse.3mf' || !dropped.sent.upload) {
    console.error('glisser-deposer incorrect', JSON.stringify(dropped).slice(0, 400)); process.exit(1);
  }
  // analyse recue : la U1 rote les couleurs du modele, puis le grand cadre se ferme
  const an = load('analysis.json');
  const nCols = new Set(an.filaments.map(f => String(f.color).slice(0, 7))).size;
  await recv(an);
  await page.waitForTimeout(150);
  const burp = await page.evaluate(() => ({ cls: document.querySelector('#eatU svg').getAttribute('class'), dots: document.querySelectorAll('#eatU .u-dots circle').length, cap: document.getElementById('eatCap').textContent }));
  if (!/burp/.test(burp.cls) || burp.dots !== Math.min(nCols, 8) || !burp.cap.startsWith('Burp')) { console.error('rot incorrect', JSON.stringify(burp), nCols); process.exit(1); }
  await page.waitForTimeout(2000);
  if (!(await page.evaluate(() => document.getElementById('eat').classList.contains('hidden')))) { console.error('grande U1 pas fermee apres le rot'); process.exit(1); }
  // pas un 3MF : recrache, avec le message d'erreur
  const spit = await page.evaluate(async () => {
    const dt = new DataTransfer(); dt.items.add(new File(['x'], 'photo.png'));
    document.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true }));
    document.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    const r = { cls: document.querySelector('#eatU svg').getAttribute('class'), cap: document.getElementById('eatCap').textContent, err: !!document.querySelector('#status .msg.err') };
    await new Promise(res => setTimeout(res, 1900));
    r.hidden = document.getElementById('eat').classList.contains('hidden');
    return r;
  });
  if (!/spit/.test(spit.cls) || spit.cap !== T.u1_spit || !spit.err || !spit.hidden) { console.error('fichier refuse incorrect', JSON.stringify(spit)); process.exit(1); }
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
  // dossier des fichiers convertis : choix envoye au plugin
  await page.evaluate(() => { window.__sent.length = 0; });
  await page.check('input[name=out][value=downloads]');
  await page.fill('#outDir', 'C:\\Users\\Dragg\\3D');
  await page.click('#outOk');
  const outs = (await sent()).filter(m => m.command === 'outdir');
  if (outs.length !== 2 || outs[0].mode !== 'downloads' || outs[1].mode !== 'folder' || outs[1].dir !== 'C:\\Users\\Dragg\\3D') {
    console.error('choix du dossier incorrect', JSON.stringify(outs)); process.exit(1);
  }
  // lien Ko-fi : copie, sans quitter l'onglet
  await page.click('#kofi');
  const kofi = await page.evaluate(() => ({ text: document.getElementById('kofi').textContent, url: location.href }));
  if (!kofi.text.includes('✓') || !kofi.url.startsWith('file:')) { console.error('lien Ko-fi incorrect', JSON.stringify(kofi)); process.exit(1); }
  if (errors.length) { console.error('Erreurs JS :', errors); process.exit(1); }
  console.log('captures OK');
  await browser.close();
})();
