// Nouveautes de la 0.6.0 dans Chrome (messages reels du plugin, check_060.py) : onglet et panneau de Preparer.
// Usage : node render_060.js <page.html> <panel.html> <dossier_donnees> <dossier_captures> [chemin_chrome]
const { chromium } = require('playwright-core');
const fs = require('fs'), path = require('path');
const [pageFile, panelFile, dataDir, outDir, chrome] = process.argv.slice(2);
const fail = (msg, x) => { console.error('ECHEC :', msg, x === undefined ? '' : JSON.stringify(x).slice(0, 900)); process.exit(1); };
const load = n => JSON.parse(fs.readFileSync(path.join(dataDir, n)));
const texts = f => { const h = fs.readFileSync(f, 'utf-8'); return JSON.parse(h.slice(h.indexOf('var L=') + 6, h.indexOf(';\nvar nav'))); };
const fmt = (s, ...a) => s.replace(/\{(\d+)\}/g, (_, i) => a[+i]);
(async () => {
  const browser = await chromium.launch({ executablePath: chrome || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const bridge = () => {
    window.__sent = []; window.__handlers = [];
    window.orca = { postMessage: m => window.__sent.push(JSON.parse(JSON.stringify(m))), onMessage: f => window.__handlers.push(f), close: () => {} };
    window.__recv = m => window.__handlers.forEach(f => f(JSON.parse(JSON.stringify(m))));
  };
  const state = load('state.json'), rec = load('recent.json'), kept = load('kept.json'), first = load('analysis.json');
  const L = texts(pageFile), lang = state.lang, T = L[lang];

  // ---- onglet
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1.5 });
  const errors = []; page.on('pageerror', e => errors.push(String(e)));
  await page.addInitScript(bridge);
  await page.goto('file://' + path.resolve(pageFile));
  await page.evaluate(() => document.fonts.ready);
  const recv = m => page.evaluate(m => window.__recv(m), m);
  const sent = () => page.evaluate(() => window.__sent);
  const grab = async (loc, file, px, py) => {   // morceau de la page avec une marge, pour les visuels
    const b = await loc.boundingBox();
    await page.screenshot({ path: path.join(outDir, file), clip: { x: b.x - px, y: b.y - py, width: b.width + 2 * px, height: b.height + 2 * py } });
  };
  await recv(Object.assign({}, state, { choices: 1 })); await recv(rec);
  const opts = await page.evaluate(() => [...document.querySelectorAll('#lang option')].map(o => o.value).join(','));
  if (opts !== 'auto,fr,en,de,es,it') fail('cinq langues dans la liste', opts);
  const prusa = await page.evaluate(() => [...document.querySelectorAll('#recent .li')].map(li => ({ nm: li.querySelector('.nm').textContent,
    mt: li.querySelector('.mt').textContent, st: li.querySelector('.st b').textContent, off: li.classList.contains('off') })));
  const pr = prusa.find(x => /Printables/.test(x.nm));
  if (!pr || !/PrusaSlicer/.test(pr.mt) || pr.st !== T.badge_todo || pr.off) fail('projet PrusaSlicer dans la liste, a convertir', prusa);
  await page.waitForTimeout(200);
  await grab(page.locator('#recent .li', { hasText: 'Printables' }), '7a_prusa.png', 14, 1);   // pour les visuels
  if (!first.supports || first.supports.keep) fail('supports proposes, pas gardes d\'office', first.supports);
  await recv(kept);
  if (await page.evaluate(() => document.body.getAttribute('data-v')) !== 'an') fail('pas sur l\'analyse');
  const an = await page.evaluate(() => {
    const ks = document.getElementById('keepSup');
    const rows = [...document.querySelectorAll('#analysis .tr')].map(r => ({ txt: r.textContent, sel: r.querySelector('select') ? r.querySelector('select').selectedOptions[0].textContent : '',
      groups: r.querySelector('select') ? [...r.querySelectorAll('optgroup')].map(g => g.label) : [] }));
    return { ks: ks && { on: ks.checked, label: ks.parentElement.textContent }, rows, notes: document.getElementById('notes').textContent };
  });
  if (!an.ks || !an.ks.on || an.ks.label.indexOf(T.sup_keep) < 0 || an.ks.label.indexOf(T.sup_hint) < 0) fail('case « supports de l\'auteur » cochee', an.ks);
  const petg = an.rows.find(r => /Generic PETG @U1 0\.4 nozzle/.test(r.sel));
  if (!petg || petg.groups.indexOf(T.grp_system) < 0) fail('profil d\'Orca propose pour le PETG, dans « ' + T.grp_system + ' »', an.rows.map(r => [r.sel, r.groups]));
  const mem = an.rows.find(r => r.txt.indexOf(T.mem_used) >= 0);
  if (!mem || !/SUNLU PLA Violet/.test(mem.sel)) fail('profil repris de la memoire, signale', an.rows.map(r => [r.sel, r.txt.slice(0, 60)]));
  if (an.notes.indexOf('Generic PETG @U1 0.4 nozzle') < 0) fail('alerte : profil d\'Orca propose', an.notes);
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(outDir, '7_nouveautes.png') });
  // morceaux pour les visuels : le PETG (profil d'Orca) jusqu'au bleu (memoire), la case des supports
  const box = await page.evaluate(() => { const r = [...document.querySelectorAll('#analysis .tr')], a = r[2].getBoundingClientRect(), b = r[4].getBoundingClientRect();
    return { x: a.left - 14, y: a.top - 4, width: a.width + 28, height: b.bottom - a.top + 8 }; });
  await page.screenshot({ path: path.join(outDir, '7b_profils.png'), clip: box });
  await grab(page.locator('#opWrap label', { has: page.locator('#keepSup') }), '7c_supports.png', 14, 12);
  await page.evaluate(() => { window.__sent.length = 0; });
  await page.click('#keepSup');
  const rp = (await sent()).find(m => m.command === 'replan');
  if (!rp || rp.supports !== false || rp.token !== kept.token || rp.one_per_plate !== false) fail('decocher : nouvelle analyse demandee', await sent());
  await recv(Object.assign({}, kept, { supports: Object.assign({}, kept.supports, { keep: false }) }));
  if (await page.evaluate(() => document.getElementById('keepSup').checked)) fail('case decochee apres la nouvelle analyse');
  // reglages : memoire des choix
  await page.click('#openSet');
  const memMsg = await page.evaluate(() => ({ t: document.getElementById('memMsg').textContent, off: document.getElementById('forget').disabled,
    tip: document.getElementById('forget').title }));
  if (memMsg.t !== fmt(T.mem_count, 1) || memMsg.off || memMsg.tip !== T.mem_text) fail('memoire dans les reglages', memMsg);
  await page.evaluate(() => { window.__sent.length = 0; });
  await page.click('#forget');
  if (!(await sent()).some(m => m.command === 'forget_choices')) fail('« ' + T.mem_forget + ' » : rien envoye');
  await recv(Object.assign({}, state, { choices: 0 }));
  const after = await page.evaluate(() => ({ t: document.getElementById('memMsg').textContent, off: document.getElementById('forget').disabled }));
  if (after.t !== T.mem_forgot || !after.off) fail('memoire videe', after);
  await recv({ command: 'choices', n: 2 });
  if (await page.evaluate(() => document.getElementById('memMsg').textContent) !== fmt(T.mem_count, 2)) fail('message « choices » : compte refait');
  await page.keyboard.press('Escape');
  // les trois nouvelles langues
  for (const l of ['de', 'es', 'it']) {
    await page.selectOption('#lang', l);
    const got = await page.evaluate(() => ({ map: document.querySelector('#s3 h2').textContent, html: document.documentElement.lang,
      sup: document.getElementById('keepSup').parentElement.textContent }));
    if (got.map !== L[l].h_map || got.html !== l || got.sup.indexOf(L[l].sup_keep) < 0) fail('langue ' + l, got);
  }
  if (errors.length) fail('erreurs dans la page de l\'onglet', errors);
  await page.close();

  // ---- panneau de Preparer
  const panel = await browser.newPage({ viewport: { width: 340, height: 900 }, deviceScaleFactor: 2 });
  const perr = []; panel.on('pageerror', e => perr.push(String(e)));
  await panel.addInitScript(bridge);
  await panel.goto('file://' + path.resolve(panelFile));
  await panel.evaluate(() => document.fonts.ready);
  const precv = m => panel.evaluate(m => window.__recv(m), m);
  const pan = load('panel_analysis.json');
  await precv(load('hello.json')); await precv(Object.assign({}, pan, { replay: true }));   // comme au retour sur le panneau
  const pv = await panel.evaluate(() => {
    const ks = document.getElementById('keepSup');
    return { v: document.body.getAttribute('data-v'), ks: ks && { on: ks.checked, label: ks.parentElement.textContent },
      mem: [...document.querySelectorAll('#map .m')].map(x => x.textContent), groups: [...document.querySelectorAll('#map optgroup')].map(g => g.label) };
  });
  if (pv.v !== 'an' || !pv.ks || !pv.ks.on !== !pan.supports.keep || pv.ks.label.indexOf(T.sup_keep) < 0) fail('panneau : case des supports', pv);
  if (pv.mem.length !== 1 || pv.mem[0] !== T.mem_used) fail('panneau : profil repris de la memoire', pv.mem);
  if (pv.groups.indexOf(T.grp_system) < 0) fail('panneau : profils d\'Orca', pv.groups);
  await panel.evaluate(() => { window.__sent.length = 0; });
  await panel.click('#keepSup');
  const prp = (await panel.evaluate(() => window.__sent)).find(m => m.command === 'replan');
  if (!prp || prp.token !== pan.token || prp.supports !== !pan.supports.keep) fail('panneau : nouvelle analyse demandee', prp);
  const pk = Object.assign({}, pan, { kept: true, supports: Object.assign({}, pan.supports, { keep: !pan.supports.keep }) });
  pk.files = JSON.parse(JSON.stringify(pan.files));
  pk.files[0].slots.push({ n: pk.files[0].slots.length + 1, src: [], base: 0, pad: false, extra: true, pick: '#123456' });
  await precv(pk);
  const pv2 = await panel.evaluate(() => ({ on: document.getElementById('keepSup').checked, extra: [...document.querySelectorAll('#map .r .pick')].map(x => x.value) }));
  if (pv2.on === !!pan.supports.keep || pv2.extra.indexOf('#123456') < 0) fail('panneau : analyse gardee (choix et couleurs en plus)', pv2);
  await panel.waitForTimeout(200);
  await panel.screenshot({ path: path.join(require('os').tmpdir(), 'mange3mf_060_panneau_' + lang + '.png'), fullPage: true });   // pour verifier a l'oeil
  if (perr.length) fail('erreurs dans la page du panneau', perr);
  await browser.close();
  console.log('0.6.0 OK');
})();
