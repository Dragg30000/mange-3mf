// Rend l'onglet de Mange-3MF dans Chrome avec un faux pont « orca » et des donnees de test,
// verifie chaque ecran et chaque action, puis enregistre les captures de la documentation.
// Usage : node render_page.js <page.html> <dossier_donnees> <dossier_captures> [chemin_chrome]
const { chromium } = require('playwright-core');
const fs = require('fs'), path = require('path');
const [pageFile, dataDir, outDir, chrome] = process.argv.slice(2);
const fail = (msg, x) => { console.error(msg, x === undefined ? '' : JSON.stringify(x).slice(0, 500)); process.exit(1); };
(async () => {
  const browser = await chromium.launch({ executablePath: chrome || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1.5 });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.addInitScript(() => {
    window.__sent = []; window.__handlers = [];
    window.orca = { postMessage: m => window.__sent.push(JSON.parse(JSON.stringify(m))), onMessage: f => window.__handlers.push(f), close: () => {} };
    window.__recv = m => window.__handlers.forEach(f => f(m));
  });
  await page.goto('file://' + path.resolve(pageFile));
  const load = n => JSON.parse(fs.readFileSync(path.join(dataDir, n)));
  const recv = m => page.evaluate(m => window.__recv(m), m);
  const sent = () => page.evaluate(() => window.__sent);
  const viewNow = () => page.evaluate(() => document.body.getAttribute('data-v'));
  const html = fs.readFileSync(pageFile, 'utf-8');
  const L = JSON.parse(html.slice(html.indexOf('var L=') + 6, html.indexOf(';\nvar nav')));
  const lang0 = load('state.json').lang, T = L[lang0];
  await page.evaluate(() => document.fonts.ready);

  // 1. accueil : la U1, les derniers 3MF, tes reglages (une colonne par tete)
  await recv(load('state.json'));
  await recv(load('recent.json'));
  if (await viewNow() !== 'home') fail('pas sur l\'accueil');
  const home = await page.evaluate(() => ({ title: document.getElementById('hTitle').textContent, heads: document.querySelectorAll('#rig .tc .t').length,
    rows: document.querySelectorAll('#recent .li').length, u1: !!document.querySelector('#u1small svg.u1'), ver: document.getElementById('ver').textContent }));
  if (home.title !== T.h_src || home.heads !== 4 || !home.rows || !home.u1 || !/^v\d/.test(home.ver)) fail('accueil incorrect', home);
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(outDir, '1_reglages_et_fichiers.png') });

  // 2. analyse demandee depuis la liste : la U1 mache, puis les couleurs s'affichent
  await page.click('#recent button[data-p]');
  const asked = (await sent()).slice(-1)[0];
  if (asked.command !== 'analyze' || !asked.path || await viewNow() !== 'busy') fail('analyse non demandee', asked);
  if (!/chew/.test(await page.evaluate(() => document.querySelector('#u1small svg').getAttribute('class')))) fail('la U1 ne mache pas pendant l\'analyse');
  await recv({ command: 'progress', text: 'Analyse de test…' });
  if ((await page.textContent('#hSub')) !== 'Analyse de test…') fail('progression pas affichee');
  await recv(load('analysis.json'));
  const an = load('analysis.json');
  if (await viewNow() !== 'an') fail('analyse pas affichee');
  const shown = await page.evaluate(() => ({ rows: document.querySelectorAll('#analysis .tr:not(.pad)').length, plates: document.querySelectorAll('#plates .plate').length,
    legend: document.querySelectorAll('#legend span').length, notes: document.querySelectorAll('#notes > div').length, convert: document.getElementById('convert').offsetParent !== null }));
  const nSlots = an.files.reduce((n, f) => n + f.slots.filter(s => !s.pad).length, 0);
  if (shown.rows !== nSlots || shown.plates !== an.plates.length || !shown.legend || !shown.notes || !shown.convert) fail('ecran des couleurs incorrect', shown);
  await page.waitForTimeout(1900);
  // capture de toute la hauteur (la barre du bas reste collee en bas de la fenetre)
  const fullH = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width: 1280, height: fullH });
  await page.screenshot({ path: path.join(outDir, '2_analyse.png') });
  await page.setViewportSize({ width: 1280, height: 800 });
  // case libre de la U1 (pas de couleur du modele) : couleur et profil modifiables
  const padAn = load('analysis.json'); padAn.token = 'pads'; padAn.files[0].slots.push({ n: 8, src: [], base: 4, pad: true });
  await recv(padAn);
  const pad = await page.evaluate(() => { const r = document.querySelector('#analysis .tr.pad'); return r && { name: r.querySelector('b').textContent,
    sel: r.querySelector('select') && r.querySelector('select').value, col: r.querySelector('input.pick') && r.querySelector('input.pick').value,
    pl: r.querySelector('.pl').textContent, num: r.querySelector('.num').className }; });
  if (!pad || pad.name !== T.pad_name || pad.sel !== '4' || pad.col !== String(an.profiles[4].fill).slice(0, 7).toLowerCase() || pad.pl !== '—' || !/gr/.test(pad.num)
      || !(await page.textContent('#analysis')).includes(T.pads_one.replace('{0}', 8))) fail('case libre incorrecte', pad);
  await page.evaluate(() => { window.__sent.length = 0; });
  await page.locator('#analysis .tr.pad select').selectOption('6');
  if (await page.locator('#analysis .tr.pad input.pick').inputValue() !== String(an.profiles[6].fill).slice(0, 7).toLowerCase()) fail('case libre : la couleur ne suit pas le profil');
  await recv(load('analysis.json'));
  // couleurs en plus : la prochaine case de tes reglages, couleur au choix, retrait, limite, gardees d'un plan a l'autre
  const exRows = () => page.evaluate(() => [...document.querySelectorAll('#analysis .tr.ex')].map(r => ({ n: +r.querySelector('.num').textContent,
    base: +r.querySelector('select').value, col: r.querySelector('input.pick').value, name: r.querySelector('b').textContent,
    pl: r.querySelector('.pl').textContent, reset: !!r.querySelector('a.reset') })));
  const before = await page.evaluate(() => [...document.querySelectorAll('#analysis select[data-f="0"]')].map(x => +x.value));
  const slotIdx = an.profiles.map((p, i) => p.group === 'slot' ? i : -1).filter(i => i >= 0);
  const freeSlot = slotIdx.find(i => !before.includes(i));
  const want = freeSlot !== undefined ? freeSlot : before[before.length - 1];
  if ((await page.textContent('button.addc[data-af="0"]')) !== T.add_color) fail('bouton « Ajouter une couleur » absent');
  await page.click('button.addc[data-af="0"]');
  let ex = await exRows();
  if (ex.length !== 1 || ex[0].n !== before.length + 1 || ex[0].base !== want || ex[0].col !== String(an.profiles[want].fill).slice(0, 7).toLowerCase()
      || ex[0].name !== T.extra_name || ex[0].pl !== '—') fail('couleur en plus mal ajoutee', { ex, want });
  if (!(await page.textContent('#analysis')).includes(T.extras_note)) fail('explication des couleurs en plus absente');
  if (await page.locator('#legend span').count() !== an.files[0].slots.filter(x => !x.pad).length) fail('couleur en plus dans la legende du modele');
  const exIdx = before.length;
  await page.evaluate(i => { const x = document.querySelector('input.pick[data-cf="0"][data-cs="' + i + '"]'); x.value = '#aa00aa'; x.dispatchEvent(new Event('change')); }, exIdx);
  ex = await exRows();
  if (ex[0].col !== '#aa00aa' || !ex[0].reset) fail('couleur de la couleur en plus non gardee', ex);
  if (!(await page.textContent('#analysis')).includes(T.color_reset_prof)) fail('« remettre celle du profil » absent');
  await page.click('button.addc[data-af="0"]');
  await page.click('button.rmc[data-rs="' + (exIdx + 1) + '"]');
  ex = await exRows();
  if (ex.length !== 1 || ex[0].col !== '#aa00aa' || ex[0].n !== exIdx + 1) fail('retrait d une couleur en plus incorrect', ex);
  const maxF = an.max_filaments;
  for (let k = before.length + 1; k < maxF; k++) await page.click('button.addc[data-af="0"]');
  if (!(await page.locator('button.addc[data-af="0"]').isDisabled()) || (await exRows()).length !== maxF - before.length
      || !(await page.textContent('#analysis')).includes(T.max_colors.replace('{0}', maxF))) fail('limite de filaments non respectee', (await exRows()).length);
  while ((await exRows()).length > 1) await page.locator('#analysis .tr.ex button.rmc').last().click();
  // nouvelle langue (meme plan) : choix et couleurs en plus gardes
  await page.locator('select[data-f="0"][data-s="6"]').selectOption('0');
  await recv(Object.assign(load('analysis.json'), { relabel: true }));
  ex = await exRows();
  if (ex.length !== 1 || ex[0].col !== '#aa00aa' || ex[0].base !== want || await page.locator('select[data-f="0"][data-s="6"]').inputValue() !== '0')
    fail('changement de langue : choix perdus', ex);
  // nouveau plan du meme fichier (un fichier par plaque, puis un seul) : la couleur en plus suit
  const two = load('analysis.json'); two.files = [JSON.parse(JSON.stringify(two.files[0])), JSON.parse(JSON.stringify(two.files[0]))];
  await recv(two);
  ex = await exRows();
  if (ex.length !== 2 || ex.some(e => e.col !== '#aa00aa' || e.base !== want)) fail('nouveau plan : couleurs en plus perdues', ex);
  await recv(load('analysis.json'));
  ex = await exRows();
  if (ex.length !== 1 || ex[0].col !== '#aa00aa') fail('retour a un fichier : couleur en plus en double ou perdue', ex);
  await page.waitForTimeout(1900);
  // autre profil pour la 5e couleur : garde apres le nouveau rendu et envoye a la conversion
  const sel = page.locator('select[data-f="0"][data-s="4"]');
  const choice = +(await sel.locator('option').last().getAttribute('value'));   // le dernier profil propose
  const groups = await sel.locator('optgroup').evaluateAll(gs => gs.map(g => g.children.length));
  if (groups.length < 2 || groups[1] < 1) fail('prereglages absents de la liste', groups);
  // un prereglage deja dans tes reglages est aussi dans « Tes preregl. », avec le meme numero de profil
  const dup = await sel.locator('optgroup').nth(1).locator('option').evaluateAll(os => os.map(o => [o.textContent, o.value]));
  const any = dup.find(d => d[0].startsWith('Anycubic PLA'));
  if (!any || an.profiles[+any[1]].group !== 'slot') fail('prereglage de tes reglages absent de « Tes preregl. »', dup);
  if (dup.map(d => d[0].toLowerCase()).join('|') !== dup.map(d => d[0].toLowerCase()).sort().join('|')) fail('preregl. pas dans l ordre', dup);
  await sel.selectOption(String(choice));
  if (await page.locator('select[data-f="0"][data-s="4"]').inputValue() !== String(choice)) fail('choix du profil perdu');
  // le meme profil pour une autre couleur : possible, et chaque couleur reste celle du modele
  await page.locator('select[data-f="0"][data-s="3"]').selectOption(String(choice));
  const labels = await sel.locator('option').evaluateAll(os => os.map(o => o.textContent));
  if (labels.some(l => /\((noir|blanc|rouge|jaune|vert|black|white|red|yellow|green)\)/i.test(l))) fail('couleur dans le nom des profils', labels);
  // couleur changee a la main pour le 1er filament : signalee, gardee et envoyee
  await page.evaluate(() => { const i = document.querySelector('input.pick[data-cf="0"][data-cs="0"]'); i.value = '#123456'; i.dispatchEvent(new Event('change')); });
  if (!(await page.locator('a.reset').count())) fail('couleur changee non signalee');
  if (await page.locator('select[data-f="0"][data-s="4"]').inputValue() !== String(choice)) fail('choix du profil perdu apres la couleur');
  // un fichier par plaque : demande au plugin
  await page.evaluate(() => { window.__sent.length = 0; });
  if (an.plates.length > 1) {
    await page.check('#onePer');
    const rp = (await sent()).slice(-1)[0];
    if (!rp || rp.command !== 'replan' || rp.one_per_plate !== true) fail('un fichier par plaque non demande', rp);
    await page.uncheck('#onePer');
  }
  await page.click('#convert');
  const conv = (await sent()).slice(-1)[0];
  if (conv.command !== 'convert' || conv.files[0].slots[4].base !== choice || conv.files[0].slots[3].base !== choice
      || conv.files[0].slots[3].color !== null || conv.files[0].slots[0].color !== '#123456' || conv.files[0].slots[1].color !== null) fail('plan envoye incorrect', conv);
  const exSent = conv.files[0].slots[an.files[0].slots.length];
  if (conv.files[0].slots.length !== an.files[0].slots.length + 1 || !exSent.extra || exSent.src.length || exSent.color !== '#AA00AA'
      || exSent.base !== want || conv.files[0].slots.slice(0, -1).some(x => x.extra)) fail('couleur en plus mal envoyee', conv.files[0].slots);
  if (!(await page.locator('#cstatus .msg').count())) fail('pas de message pres de Convertir');
  if (!(await page.locator('#cancel').isDisabled())) fail('Annuler possible pendant la conversion');

  // 3. projet pret : trois gestes pour l'ouvrir dans Orca
  await recv({ command: 'built', token: conv.token });
  await recv(load('result.json'));
  if (await viewNow() !== 'res') fail('resultat pas affiche');
  if (await page.locator('#cancel').isDisabled()) fail('Annuler reste grise apres la conversion');
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(outDir, '3_resultat.png') });
  await page.click('#result button[data-c]');
  const step = await page.evaluate(() => ({ on: Array.from(document.querySelectorAll('#result .g')).map(g => g.classList.contains('on')), segs: document.querySelector('#segs i.on') && Array.from(document.querySelectorAll('#segs i')).indexOf(document.querySelector('#segs i.on')) }));
  if (step.on[0] || !step.on[1] || step.segs !== 1) fail('geste suivant pas mis en avant apres la copie', step);
  await page.click('#back');
  if (await viewNow() !== 'an') fail('retour aux couleurs impossible');
  await recv(load('result.json'));
  await page.click('#again');
  if (await viewNow() !== 'home') fail('retour a l\'accueil impossible');

  // Annuler : depuis les couleurs, et pendant l'analyse (le resultat qui arrive ensuite est ignore)
  await recv(an);
  if (await viewNow() !== 'an' || !(await page.locator('#cancel').isVisible())) fail('bouton Annuler absent des couleurs');
  if ((await page.locator('#cancel').textContent()) !== T.cancel) fail('texte du bouton Annuler', await page.locator('#cancel').textContent());
  await page.click('#cancel');
  if (await viewNow() !== 'home') fail('Annuler ne ramene pas a l\'accueil');
  await page.fill('#path', 'C:\\Users\\Test\\Downloads\\annule.3mf');
  await page.click('#go');
  if (await viewNow() !== 'busy' || !(await page.locator('#cancel').isVisible())) fail('bouton Annuler absent pendant l\'analyse');
  await page.click('#cancel');
  await recv(an);
  if (await viewNow() !== 'home') fail('analyse annulee affichee quand meme');
  await recv(an);
  if (await viewNow() !== 'an') fail('analyse suivante pas affichee apres une annulation');
  await page.click('#cancel');
  await page.fill('#path', '');

  // la U1 gourmande : clic = choix d'un fichier ; en grand quand on glisse un fichier sur l'onglet
  const chooser = await Promise.all([page.waitForEvent('filechooser', { timeout: 3000 }), page.click('#u1zone')]).then(() => true, () => false);
  if (!chooser) fail('clic sur la U1 : pas de choix de fichier');
  await page.evaluate(() => { const dt = new DataTransfer(); dt.items.add(new File(['x'], 'faim.3mf')); document.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true })); });
  await page.waitForTimeout(450);
  await page.screenshot({ path: path.join(outDir, '4_glouton.png') });
  await page.evaluate(() => document.dispatchEvent(new DragEvent('dragleave', { bubbles: true })));
  if (!(await page.evaluate(() => document.getElementById('eat').classList.contains('hidden')))) fail('grande U1 pas cachee apres dragleave');
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
    return { hungry, chomp, chew: big(), cap: document.getElementById('eatCap').textContent, sent: window.__sent.slice(-1)[0], parts: window.__sent.filter(m => m.command === 'upload_part'), view: document.body.getAttribute('data-v'), title: document.getElementById('hTitle').textContent };
  });
  if (!dropped.hungry.shown || !/hungry/.test(dropped.hungry.cls) || dropped.hungry.cap !== T.drop || !/chomp/.test(dropped.chomp)
      || !/chew/.test(dropped.chew) || dropped.cap !== T.u1_chew || dropped.view !== 'busy' || dropped.title !== 'glisse.3mf'
      || !dropped.sent || dropped.sent.command !== 'analyze' || dropped.sent.name !== 'glisse.3mf' || dropped.parts.length !== 1
      || dropped.parts[0].n !== 1 || dropped.sent.upload_id !== dropped.parts[0].id || atob(dropped.parts[0].data).length !== 7) fail('glisser-deposer incorrect', dropped);
  // analyse recue : la U1 rote les couleurs du modele, puis le grand cadre se ferme
  const nCols = new Set(an.filaments.map(f => String(f.color).slice(0, 7))).size;
  await recv(an);
  await page.waitForTimeout(150);
  const burp = await page.evaluate(() => ({ cls: document.querySelector('#eatU svg').getAttribute('class'), dots: document.querySelectorAll('#eatU .u-dots circle').length, cap: document.getElementById('eatCap').textContent }));
  if (!/burp/.test(burp.cls) || burp.dots !== Math.min(nCols, 8) || !burp.cap.startsWith('Burp')) fail('rot incorrect', [burp, nCols]);
  await page.waitForTimeout(2000);
  if (!(await page.evaluate(() => document.getElementById('eat').classList.contains('hidden')))) fail('grande U1 pas fermee apres le rot');
  // gros fichier : envoye par morceaux (ici morceaux de 4 octets), le texte suit la lecture
  const big = await page.evaluate(async () => {
    window.__sent.length = 0; const keep = M3D_UP.CHUNK; M3D_UP.CHUNK = 4;
    const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])], 'gros.3mf'));
    const texts = []; const ob = new MutationObserver(() => texts.push(document.getElementById('hSub').textContent));
    ob.observe(document.getElementById('hSub'), { childList: true, subtree: true, characterData: true });
    document.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    await new Promise(r => setTimeout(r, 400)); ob.disconnect(); M3D_UP.CHUNK = keep;
    return { sent: window.__sent.map(m => ({ c: m.command, i: m.i, n: m.n, id: m.id || m.upload_id, len: m.data ? atob(m.data).length : 0 })), texts };
  });
  const parts = big.sent.filter(m => m.c === 'upload_part');
  if (parts.length !== 3 || parts.map(m => m.i).join() !== '0,1,2' || parts.map(m => m.len).join() !== '4,4,2' || parts.some(m => m.n !== 3 || m.id !== parts[0].id)
      || big.sent.slice(-1)[0].c !== 'analyze' || big.sent.slice(-1)[0].id !== parts[0].id) fail('envoi par morceaux incorrect', big.sent);
  if (!big.texts.some(x => x.includes('(2/3)')) || !big.texts.some(x => x.includes('(3/3)'))) fail('lecture par morceaux non affichee', big.texts);
  await recv(an);
  await page.waitForTimeout(2100);
  // Annuler pendant l'envoi : plus de morceaux, le plugin oublie ceux recus
  const stop = await page.evaluate(async () => {
    window.__sent.length = 0; const keep = M3D_UP.CHUNK; M3D_UP.CHUNK = 1;
    const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array(4000)], 'long.3mf'));
    document.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    await new Promise(r => setTimeout(r, 60));
    document.getElementById('cancel').click();
    const n = window.__sent.length; await new Promise(r => setTimeout(r, 300)); M3D_UP.CHUNK = keep;
    return { n, after: window.__sent.length, last: window.__sent.slice(-1)[0].command, analyze: window.__sent.some(m => m.command === 'analyze'), view: document.body.getAttribute('data-v') };
  });
  if (stop.n !== stop.after || stop.last !== 'upload_drop' || stop.analyze || stop.view !== 'home' || stop.n > 3999) fail('Annuler pendant l envoi incorrect', stop);
  // trop gros (au-dela de MAXUP) : recrache, rien envoye
  const huge = await page.evaluate(async () => {
    window.__sent.length = 0; const keep = M3D_UP.MAXUP; M3D_UP.MAXUP = 5;
    const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array(10)], 'enorme.3mf'));
    document.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    M3D_UP.MAXUP = keep; const err = document.querySelector('#status .msg.err');
    await new Promise(r => setTimeout(r, 1900));
    return { sent: window.__sent.length, err: err && err.textContent };
  });
  if (huge.sent || !huge.err || !huge.err.startsWith(T.too_big.split('{0}')[0])) fail('fichier trop gros mal refuse', huge);
  await page.evaluate(() => { document.getElementById('status').innerHTML = ''; });
  await recv(an);                                   // retour aux couleurs pour la suite
  await page.waitForTimeout(300);
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
  if (!/spit/.test(spit.cls) || spit.cap !== T.u1_spit || !spit.err || !spit.hidden) fail('fichier refuse incorrect', spit);

  // 5. fenetre des reglages : reglages choisis, dossier des fichiers convertis
  await page.evaluate(() => { document.getElementById('status').innerHTML = ''; });
  await page.click('#openSet');
  if (await page.evaluate(() => document.getElementById('dlg').classList.contains('hidden'))) fail('fenetre des reglages pas ouverte');
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(outDir, '5_reglages.png') });
  await page.evaluate(() => { window.__sent.length = 0; });
  await page.check('input[name=out][value=downloads]');
  await page.fill('#outDir', 'C:\\Users\\Dragg\\3D');
  await page.click('#outOk');
  await page.click('#capture');
  const outs = (await sent()).filter(m => m.command === 'outdir');
  if (outs.length !== 2 || outs[0].mode !== 'downloads' || outs[1].mode !== 'folder' || outs[1].dir !== 'C:\\Users\\Dragg\\3D') fail('choix du dossier incorrect', outs);
  if (!(await sent()).some(m => m.command === 'capture')) fail('memoriser les reglages : rien envoye');
  if ((await page.locator('input[name=tc]').count()) >= 2) {
    await page.check('input[name=tc][value=current]');
    if (!(await page.evaluate(() => document.querySelector('.choice.on input').value === 'current'))) fail('choix des reglages actuels perdu');
    await page.check('input[name=tc][value=saved]');
  }
  await page.keyboard.press('Escape');
  if (!(await page.evaluate(() => document.getElementById('dlg').classList.contains('hidden')))) fail('fenetre des reglages pas fermee par Echap');

  // langue : changee dans la barre du haut, textes refaits tout de suite et choix envoye au plugin
  const other = lang0 === 'fr' ? 'en' : 'fr';
  await page.evaluate(() => { window.__sent.length = 0; });
  await page.selectOption('#lang', other);
  const switched = await page.evaluate(() => ({ h2: document.querySelector('#s4 h2').textContent, map: document.querySelector('#s3 h2').textContent, html: document.documentElement.lang,
    sent: window.__sent.slice(-1)[0], options: Array.from(document.querySelectorAll('#lang option')).map(o => o.value), view: document.body.getAttribute('data-v') }));
  if (switched.h2 !== L[other].h_open || switched.map !== L[other].h_map || switched.html !== other || !switched.sent || switched.sent.command !== 'lang'
      || switched.sent.lang !== other || switched.options.join(',') !== 'auto,fr,en' || switched.view !== 'an') fail('changement de langue incorrect', switched);
  await page.selectOption('#lang', lang0);

  // lien Ko-fi : copie, sans quitter l'onglet
  await page.click('#kofi');
  const kofi = await page.evaluate(() => ({ text: document.getElementById('kofi').textContent, url: location.href }));
  if (!kofi.text.includes('✓') || !kofi.url.startsWith('file:')) fail('lien Ko-fi incorrect', kofi);
  // ecran etroit : tout reste lisible sur une colonne
  await page.setViewportSize({ width: 760, height: 800 });
  const narrow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  if (!narrow) fail('l\'onglet deborde en largeur sur un ecran etroit');
  if (errors.length) fail('Erreurs JS :', errors);
  console.log('captures OK');
  await browser.close();
})();
