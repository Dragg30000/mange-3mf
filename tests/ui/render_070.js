// Nouveautes de la 0.7.0 dans Chrome (messages reels du plugin, check_070.py) : onglet et panneau de Preparer.
// Usage : node render_070.js <page.html> <panel.html> <dossier_donnees> <dossier_captures> [chemin_chrome]
const { chromium } = require('playwright-core');
const fs = require('fs'), path = require('path');
const [pageFile, panelFile, dataDir, outDir, chrome] = process.argv.slice(2);
const fail = (msg, x) => { console.error('ECHEC :', msg, x === undefined ? '' : JSON.stringify(x).slice(0, 1200)); process.exit(1); };
const load = n => JSON.parse(fs.readFileSync(path.join(dataDir, n)));
const texts = f => { const h = fs.readFileSync(f, 'utf-8'); return JSON.parse(h.slice(h.indexOf('var L=') + 6, h.indexOf(';\nvar nav'))); };
const fmt = (s, ...a) => s.replace(/\{(\d+)\}/g, (_, i) => a[+i]);
fs.mkdirSync(outDir, { recursive: true });
(async () => {
  const browser = await chromium.launch({ executablePath: chrome || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const bridge = () => {
    window.__sent = []; window.__handlers = [];
    window.orca = { postMessage: m => window.__sent.push(JSON.parse(JSON.stringify(m))), onMessage: f => window.__handlers.push(f), close: () => {} };
    window.__recv = m => window.__handlers.forEach(f => f(JSON.parse(JSON.stringify(m))));
  };
  const state = load('state.json'), rec = load('recent.json'), rigs = load('rigs.json');
  const L = texts(pageFile), lang = state.lang, T = L[lang];

  // ---- onglet : deux imprimantes memorisees
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1.5 });
  const errors = []; page.on('pageerror', e => errors.push(String(e)));
  await page.addInitScript(bridge);
  await page.goto('file://' + path.resolve(pageFile));
  await page.evaluate(() => document.fonts.ready);
  const recv = m => page.evaluate(m => window.__recv(m), m);
  const sent = () => page.evaluate(() => window.__sent);
  const clear = () => page.evaluate(() => { window.__sent.length = 0; });
  await recv(state); await recv(rec);
  if (state.printers.length !== 2 || state.saved.short !== 'P1S') fail('etat : U1 et P1S memorisees, P1S choisie', state.printers);
  const home = await page.evaluate(() => ({ sub: document.querySelector('.bar [data-t=sub]').textContent,
    pick: [...document.querySelectorAll('#prnHome .prn button')].map(b => [b.textContent, b.classList.contains('on')]),
    rig: document.getElementById('rig').textContent, nozzles: [...document.querySelectorAll('#rig .bus .tc .t')].map(x => x.textContent),
    spools: document.querySelectorAll('#rig .sp .spool').length, wires: document.querySelectorAll('#rig .rg:nth-child(2) .wire').length,
    badges: [...document.querySelectorAll('#recent .st b')].map(x => x.textContent) }));
  if (home.sub !== T.sub) fail('titre : n\'importe quel 3MF -> ton imprimante', home.sub);
  if (JSON.stringify(home.pick) !== JSON.stringify([['P1S', true], ['U1', false]])) fail('accueil : choix de l\'imprimante', home.pick);
  if (home.spools !== 4 || home.wires !== 4 || JSON.stringify(home.nozzles) !== JSON.stringify([T.nozzle_card]) || home.rig.indexOf(fmt(T.kind_box, 4)) < 0)
    fail('carte de la P1S : 4 bobines reliees a une buse', home);
  if (home.badges.indexOf(T.badge_todo) < 0) fail('liste des 3MF : a convertir pour la P1S', home.badges);
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(outDir, '1_accueil_p1s.png') });
  await clear();
  await page.click('#prnHome button[data-pk="snapmaker u1"]');
  const tg = (await sent()).find(x => x.command === 'target');
  if (!tg || tg.key !== 'snapmaker u1') fail('clic sur « U1 » : imprimante choisie', await sent());
  // reglages : une carte par imprimante, les retirer
  await page.click('#openSet');
  const dlg = await page.evaluate(() => ({ cards: [...document.querySelectorAll('#tplChoices .choice')].map(c => [c.querySelector('b').textContent, c.classList.contains('on'), !!c.querySelector('button.fp')]),
    hint: document.querySelector('#tplChoices p.muted') && document.querySelector('#tplChoices p.muted').textContent,
    title: document.getElementById('dlgRigTitle').textContent, sub: document.getElementById('rigSubDlg').textContent }));
  if (JSON.stringify(dlg.cards.slice(0, 2)) !== JSON.stringify([['P1S', true, true], ['U1', false, true]]) || dlg.cards.length !== 3 || dlg.cards[2][2])
    fail('reglages : P1S (choisie), U1, puis les reglages actuels d\'Orca', dlg.cards);
  if (dlg.hint !== T.printers_hint || dlg.title !== T.tpl_saved + ' · P1S' || dlg.sub !== T.rig_sub_box) fail('reglages : textes', dlg);
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(outDir, '2_reglages.png') });
  await clear();
  await page.click('#tplChoices button[data-fk="snapmaker u1"]');
  const fg = await sent();
  if (!fg.some(x => x.command === 'forget_printer' && x.key === 'snapmaker u1') || fg.some(x => x.command === 'target')) fail('« ' + T.forget_printer + ' » : U1 oubliee, rien d\'autre', fg);
  await clear();
  await page.click('#tplChoices input[value="saved:snapmaker u1"]');
  if (!(await sent()).some(x => x.command === 'target' && x.key === 'snapmaker u1')) fail('carte U1 cochee : imprimante choisie', await sent());
  await page.keyboard.press('Escape');

  // ---- la carte de chaque famille
  const shots = {};
  for (const [key, x] of Object.entries(rigs)) {
    await recv(Object.assign({}, state, { saved: x, printers: [x], target: x.key, choice: 'saved' }));
    const r = await page.evaluate(() => ({ cols: getComputedStyle(document.querySelector('#rig .rg')).gridTemplateColumns.split(' ').length,
      heads: [...document.querySelectorAll('#rig .rg .tc .t')].map(e => e.textContent), ex: [...document.querySelectorAll('#rig .tc.ex')].map(e => e.textContent),
      bus: [...document.querySelectorAll('#rig .bus .tc')].map(e => e.textContent), kv: document.querySelector('#rig .kv').textContent,
      wide: document.querySelector('#rig').scrollWidth <= document.querySelector('#rig').clientWidth + 1 }));
    shots[key] = r;
    await page.locator('#rig').screenshot({ path: path.join(outDir, '3_carte_' + key + '.png') });
  }
  const s = shots;
  const want = (c, msg) => { if (!c) fail(msg, s); };
  want(s.u1.heads.join() === 'T1,T2,T3,T4' && s.u1.ex[0] === T.via_ace && s.u1.cols === 5, 'U1 : 4 tetes et « via multiACE »');
  want(s.xl.heads.join() === 'T1,T2,T3,T4,T5' && !s.xl.ex.length && s.xl.kv.indexOf(fmt(T.kind_tools, 5)) >= 0, 'XL 5T : 5 tetes');
  want(s.indx.heads.join() === 'T1,T2,T3,T4,T5' && s.indx.ex[0] === fmt(T.heads_more, 6, 8), 'INDX 8T : T1 a T5, puis « tetes 6 a 8 »');
  want(s.h2d.bus[0].indexOf(T.nozzle_left) === 0 && s.h2d.bus[1].indexOf(T.nozzle_right) === 0 && s.h2d.bus[0].indexOf(fmt(T.n_filaments, 2)) > 0
       && s.h2d.kv.indexOf(fmt(T.kind_multi, 2, 4)) >= 0, 'H2D : buse gauche, buse droite, 2 filaments chacune');
  want(s.h3c.bus.length === 5 && s.h3c.bus[0].indexOf(fmt(T.nozzle_n, 1)) === 0 && s.h3c.ex.indexOf(fmt(T.nozzles_more, 5, 9)) >= 0
       && s.h3c.kv.indexOf(fmt(T.kind_multi, 9, 9)) >= 0, 'H3C : buses 1 a 4, puis « buses 5 a 9 »');
  want(s.mini.bus.length === 1 && s.mini.kv.indexOf(T.kind_single) >= 0 && s.mini.cols === 2, 'MINI : une bobine, une buse');
  want(s.mmu3.kv.indexOf(fmt(T.kind_box, 5)) >= 0 && s.mmu3.cols === 6, 'MK4S MMU3 : 5 bobines');
  want(s.ad5x.kv.indexOf(fmt(T.kind_box, 4)) >= 0 && s.ad5x.bus.length === 1, 'Flashforge AD5X : 4 bobines (IFS), une buse');
  want(s.c5p.heads.join() === 'T1,T2,T3,T4' && s.c5p.ex[0] === T.via_more && s.c5p.kv.indexOf(fmt(T.kind_tools, 4)) >= 0,
       'Flashforge Creator 5 Pro : 4 tetes, le 5e filament « en plus » (pas multiACE)');
  want(s.j1.heads.join() === 'T1,T2' && !s.j1.ex.length && s.j1.kv.indexOf(fmt(T.kind_tools, 2)) >= 0, 'Snapmaker J1 (IDEX) : 2 tetes');
  want(Object.values(s).every(r => r.wide), 'aucune carte ne deborde');
  await recv(state);

  // ---- analyse pour la P1S : emplacement libre de la boite
  const an = load('an_p1s.json');
  await recv(an);
  const a1 = await page.evaluate(() => ({ v: document.body.getAttribute('data-v'), pads: [...document.querySelectorAll('#analysis .muted.small')].map(e => e.textContent),
    pick: [...document.querySelectorAll('#prnAn .prn button')].map(b => b.textContent), notes: document.getElementById('notes').textContent,
    name: document.querySelector('#dest').textContent }));
  if (a1.v !== 'an' || a1.pads.indexOf(fmt(T.pads_box_one, 2)) < 0) fail('P1S : case 2 = emplacement libre de ta boite', a1);
  if (a1.pick.join() !== 'P1S,U1') fail('analyse : choix de l\'imprimante', a1.pick);
  await page.screenshot({ path: path.join(outDir, '4_analyse_p1s.png') });
  // Kobra S1 a deux bobines : 3 couleurs
  await recv(load('an_kobra.json'));
  const a2 = await page.evaluate(() => document.getElementById('notes').textContent);
  if (a2.indexOf(fmt(T.need_box, 3, 2, 'Kobra S1')) < 0) fail('Kobra S1 : 3 couleurs pour 2 emplacements', a2);
  // Prusa MINI : une seule bobine
  const mini = load('an_mini.json');
  await recv(mini);
  const a3 = await page.evaluate(() => ({ notes: document.getElementById('notes').textContent, oc: !!document.getElementById('oneCol'),
    on: document.getElementById('oneCol') && document.getElementById('oneCol').checked }));
  if (a3.notes.indexOf(fmt(T.need_one, 3)) < 0 || !a3.oc || a3.on) fail('MINI : alerte et « Tout en une couleur » propose', a3);
  await clear();
  await page.click('#oneCol');
  const rp = (await sent()).find(x => x.command === 'replan');
  if (!rp || rp.one_color !== true || rp.token !== mini.token) fail('« Tout en une couleur » : nouvelle analyse demandee', await sent());
  await recv(load('an_mono.json'));
  const a4 = await page.evaluate(() => ({ rows: [...document.querySelectorAll('#analysis .tr')].map(r => r.querySelector('.tx b').textContent),
    legend: document.getElementById('legend').textContent, on: document.getElementById('oneCol').checked, notes: document.getElementById('notes').textContent }));
  if (a4.rows.length !== 1 || a4.rows[0] !== fmt(T.all_colors, 3) || !a4.on || a4.legend.toLowerCase().indexOf(fmt(T.all_colors, 3).toLowerCase()) < 0 || a4.notes.indexOf(fmt(T.need_one, 3)) >= 0)
    fail('une ligne « toutes les couleurs (3) »', a4);
  await page.screenshot({ path: path.join(outDir, '5_une_couleur.png') });
  await clear();
  await page.click('#convert');
  const cv = (await sent()).find(x => x.command === 'convert');
  if (!cv || cv.files[0].slots.length !== 1 || cv.files[0].slots[0].src.length !== 3) fail('conversion : une case, trois couleurs', cv);
  for (const l of ['de', 'es', 'it', 'en']) {
    await page.selectOption('#lang', l);
    const got = await page.evaluate(() => ({ row: document.querySelector('#analysis .tr .tx b').textContent, sub: document.querySelector('.bar [data-t=sub]').textContent }));
    if (got.row !== fmt(L[l].all_colors, 3) || got.sub !== L[l].sub) fail('langue ' + l, got);
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
  const hello = load('hello.json');
  if (hello.printer !== 'P1S') fail('panneau : « hello » avec l\'imprimante choisie', hello);
  await precv(hello); await precv(load('offer.json'));
  const off = await panel.evaluate(() => ({ v: document.body.getAttribute('data-v'), say2: document.getElementById('say2').textContent }));
  if (off.v !== 'offer' || off.say2 !== fmt(T.pn_offer2, 'P1S')) fail('panneau : « pas reglé pour ta P1S »', off);
  await panel.screenshot({ path: path.join(outDir, '6_panneau_offre.png') });
  await precv(Object.assign({}, load('an_kobra.json'), { replay: true }));
  const pk = await panel.evaluate(() => document.getElementById('notes').textContent);
  if (pk.indexOf(fmt(T.need_box, 3, 2, 'Kobra S1')) < 0) fail('panneau : 3 couleurs pour 2 emplacements', pk);
  await precv(Object.assign({}, load('an_mini.json'), { replay: true }));
  await panel.evaluate(() => { window.__sent.length = 0; });
  await panel.click('#oneCol');
  const pr = (await panel.evaluate(() => window.__sent)).find(x => x.command === 'replan');
  if (!pr || pr.one_color !== true) fail('panneau : « Tout en une couleur »', pr);
  await precv(Object.assign({}, load('an_mono.json'), { replay: true }));
  const pm = await panel.evaluate(() => [...document.querySelectorAll('#map .r .nm')].map(x => x.textContent));
  if (pm.length !== 1 || pm[0].toLowerCase() !== fmt(T.all_colors, 3).toLowerCase()) fail('panneau : une ligne pour toutes les couleurs', pm);
  await panel.screenshot({ path: path.join(outDir, '7_panneau_une_couleur.png'), fullPage: true });
  if (perr.length) fail('erreurs dans la page du panneau', perr);
  await browser.close();
  console.log('0.7.0 OK');
})();
