// Rend le panneau de Mange-3MF (Preparer / Apercu) dans Chrome avec un faux pont « orca » et des messages
// reels du plugin (check_panel.py), verifie chaque ecran et chaque geste, et enregistre une capture par ecran.
// Usage : node render_panel.js <panel.html> <dossier_donnees> <dossier_captures> [chemin_chrome]
const { chromium } = require('playwright-core');
const fs = require('fs'), path = require('path');
const [pageFile, dataDir, outDir, chrome] = process.argv.slice(2);
const fail = (msg, x) => { console.error('ECHEC :', msg, x === undefined ? '' : JSON.stringify(x).slice(0, 700)); process.exit(1); };
(async () => {
  const browser = await chromium.launch({ executablePath: chrome || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 340, height: 720 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.addInitScript(() => {
    window.__sent = []; window.__handlers = [];
    window.orca = { postMessage: m => window.__sent.push(JSON.parse(JSON.stringify(m))), onMessage: f => window.__handlers.push(f), close: () => { window.__closed = (window.__closed || 0) + 1; } };
    window.__recv = m => window.__handlers.forEach(f => f(JSON.parse(JSON.stringify(m))));
  });
  await page.goto('file://' + path.resolve(pageFile));
  const load = n => JSON.parse(fs.readFileSync(path.join(dataDir, n)));
  const recv = m => page.evaluate(m => window.__recv(m), m);
  const sent = () => page.evaluate(() => window.__sent);
  const clear = () => page.evaluate(() => { window.__sent.length = 0; });
  const v = () => page.evaluate(() => document.body.getAttribute('data-v'));
  const u1 = () => page.evaluate(() => document.querySelector('#u svg').getAttribute('class'));
  const txt = id => page.evaluate(id => document.getElementById(id).textContent, id);
  const shown = id => page.evaluate(id => { const e = document.getElementById(id); return !!e && !e.classList.contains('hidden') && e.offsetParent !== null; }, id);
  const shot = name => page.screenshot({ path: path.join(outDir, name) });
  const rowsNow = () => page.evaluate(() => [...document.querySelectorAll('#map .r')].map(r => ({ n: r.querySelector('.num').textContent,
    nm: r.querySelector('.nm').textContent, prof: r.querySelector('select') ? r.querySelector('select').selectedOptions[0].textContent : (r.querySelector('em') || {}).textContent,
    base: r.querySelector('select') ? +r.querySelector('select').value : null, pick: r.querySelector('input.pick') ? r.querySelector('input.pick').value : null,
    arrow: !!r.querySelector('.ar'), rm: !!r.querySelector('.rmc'), rst: !!r.querySelector('.rst'), group: r.classList.contains('padg'), free: r.classList.contains('free') })));
  const plansSent = async () => (await sent()).filter(m => m.command === 'plan');
  const html = fs.readFileSync(pageFile, 'utf-8');
  const L = JSON.parse(html.slice(html.indexOf('var L=') + 6, html.indexOf(';\nvar nav')));
  const hello = load('hello.json'), T = L[hello.lang], offer = load('offer.json'), an = load('analysis.json'), plan = load('plan.json');
  const res = load('result.json'), prog = load('progress.json'), real = load('real.json');
  await page.evaluate(() => document.fonts.ready);

  // 0. la page demande ses donnees (un post() d'Orca avant son chargement peut se perdre)
  const first = (await sent())[0];
  if (!first || first.command !== 'init') fail('pas de demande « init » au demarrage', first);

  // 1. au repos : j'ai faim, zone pour deposer un 3MF
  await recv(hello); await recv({ command: 'rest' });
  if (await v() !== 'rest' || await txt('say') !== T.say_idle || await txt('say2') !== T.pn_rest2 || !(await shown('zone'))
      || await txt('zone') !== T.pn_zone || await shown('foot') || await shown('hint')) fail('ecran au repos', { v: await v(), say: await txt('say'), say2: await txt('say2') });
  const pmode = await page.evaluate(() => ({ v: document.getElementById('pmodeSel').value, label: document.querySelector('#pmode span').textContent,
    opts: [...document.querySelectorAll('#pmodeSel option')].map(o => o.value + '=' + o.textContent) }));
  if (!(await shown('pmode')) || pmode.v !== 'panel' || pmode.label !== T.pn_mode_label
      || pmode.opts.join('|') !== ['panel=' + T.pn_opt_panel, 'notif=' + T.pn_opt_notif, 'off=' + T.pn_opt_off].join('|')) fail('reglage du panneau absent au repos', pmode);
  await page.waitForTimeout(300); await shot('1_repos.png');
  await page.hover('#zone');
  if (!/hungry/.test(await u1())) fail('survol de la zone : la U1 n\'a pas faim', await u1());
  await page.mouse.move(2, 2);
  if (/hungry/.test(await u1())) fail('la U1 reste affamee apres le survol');
  const chooser = await Promise.all([page.waitForEvent('filechooser', { timeout: 3000 }), page.click('#zone')]).then(() => true, () => false);
  if (!chooser) fail('clic sur la zone : pas de choix de fichier');

  // 2. un fichier passe sur le panneau : bouche ouverte
  await page.evaluate(() => { const dt = new DataTransfer(); dt.items.add(new File(['x'], 'renne.3mf')); document.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true })); });
  if (await v() !== 'drag' || await txt('say') !== T.pn_drag || await txt('say2') !== T.pn_drag2 || await txt('zone') !== T.pn_zone_drag || !/hungry/.test(await u1()))
    fail('glisser : ecran incorrect', { v: await v(), say: await txt('say') });
  await page.waitForTimeout(300); await shot('2_glisser.png');
  await page.evaluate(() => document.dispatchEvent(new DragEvent('dragleave', { bubbles: true })));
  if (await v() !== 'rest') fail('dragleave : pas de retour au repos');
  if ((await sent()).some(m => m.command === 'view' && m.v === 'drag')) fail('l\'ecran « drag » ne doit pas etre signale au plugin');

  // 3. Miam : projet ouvert dans Orca, pas regle pour la U1
  await clear(); await recv(offer);
  const card = await page.evaluate(() => ({ name: document.querySelector('#card b').textContent, info: document.querySelector('#card small').textContent }));
  const f = offer.file;
  if (await v() !== 'offer' || await txt('say') !== T.pn_offer || await txt('say2') !== T.pn_offer2 || card.name !== f.name
      || card.info !== f.label + ', ' + f.printer || !(await shown('eat')) || !(await shown('later'))
      || await txt('eat') !== T.pn_eat || await txt('later') !== T.pn_later || await txt('hint') !== T.pn_offer_hint || !/hungry/.test(await u1()))
    fail('Miam incorrect', { v: await v(), card });
  if (!(await sent()).some(m => m.command === 'view' && m.v === 'offer')) fail('ecran « offer » pas signale au plugin');
  if (!(await shown('pmode'))) fail('reglage du panneau absent sur Miam');
  await page.waitForTimeout(400); await shot('3_miam.png');

  // 4. Le manger : la U1 mache, Annuler possible
  await clear(); await page.click('#eat');
  if (!(await sent()).some(m => m.command === 'eat') || await v() !== 'busy' || !/chew/.test(await u1()) || !(await shown('cancel'))
      || !(await shown('bar')) || await txt('say') !== T.pn_chew) fail('Le manger : ecran incorrect', { v: await v(), sent: await sent() });
  await recv(prog);
  if (await txt('say2') !== prog.text) fail('progression pas affichee', await txt('say2'));
  await page.waitForTimeout(400); await shot('4_mache.png');

  // 5. Burp : couleurs du modele et profils proposes d'office, cases libres groupees
  await recv(an);
  await page.waitForTimeout(650);
  const burp = await page.evaluate(() => ({ cls: document.querySelector('#u svg').getAttribute('class'), dots: document.querySelectorAll('#u .u-dots circle').length }));
  burp.rows = await rowsNow();
  const models = an.files[0].slots.filter(s => !s.pad), pads = an.files[0].slots.filter(s => s.pad);
  const wantBurp = T.u1_burp.replace('{0}', an.filaments.length + ' ' + (an.filaments.length > 1 ? T.colorN : T.color1));
  if (await v() !== 'an' || !/burp/.test(burp.cls) || burp.dots !== Math.min(an.filaments.length, 8) || await txt('say') !== wantBurp) fail('rot incorrect', burp);
  const modelRows = burp.rows.filter(r => !r.free), padRow = burp.rows.filter(r => r.free);
  if (modelRows.length !== models.length || modelRows.some((r, i) => r.n !== String(models[i].n) || r.prof !== an.profiles[models[i].base].name || !r.pick)
      || (pads.length && (padRow.length !== 1 || !padRow[0].group || padRow[0].prof !== (pads.length > 1 ? T.pn_keep_n : T.pn_keep_1))))
    fail('lignes des couleurs incorrectes', burp.rows);
  if (await txt('convert') !== T.convert || await page.isDisabled('#convert') || await txt('hint') !== T.pn_an_hint) fail('bouton Convertir / aide', await txt('convert'));
  if (await shown('pmode')) fail('reglage du panneau affiche pendant le travail');
  await shot('5_burp.png');
  await page.waitForTimeout(1400);
  if (!/full/.test(await u1())) fail('apres le rot, la U1 n\'est pas pleine', await u1());

  // 5b. tout se change dans le panneau : profil, couleur, couleurs en plus, cases libres ; chaque changement part au plugin
  await clear();
  const mRow = models[0], mIdx = an.files[0].slots.indexOf(mRow), otherBase = an.profiles.findIndex((pr, i) => pr.group === 'slot' && i !== mRow.base);
  await page.selectOption('#map select[data-s="' + mIdx + '"]', String(otherBase));
  let pl = (await plansSent()).slice(-1)[0];
  if (!pl || pl.token !== an.token || pl.files[0].slots[mIdx].base !== otherBase || pl.files[0].slots[mIdx].color !== null) fail('profil change : plan incorrect', pl);
  await page.evaluate(i => { const e = document.querySelector('#map input.pick[data-s="' + i + '"]'); e.value = '#123456'; e.dispatchEvent(new Event('change', { bubbles: true })); }, mIdx);
  pl = (await plansSent()).slice(-1)[0];
  let r1 = (await rowsNow()).find(r => r.n === String(mIdx + 1));
  if (pl.files[0].slots[mIdx].color !== '#123456' || !r1.arrow || !r1.rst || r1.pick !== '#123456' || r1.prof !== an.profiles[otherBase].name) fail('couleur changee : plan ou ligne incorrect', { pl: pl.files[0].slots[mIdx], r1 });
  await page.click('#map button.rst[data-s="' + mIdx + '"]');
  pl = (await plansSent()).slice(-1)[0]; r1 = (await rowsNow()).find(r => r.n === String(mIdx + 1));
  if (pl.files[0].slots[mIdx].color !== null || r1.arrow || r1.rst) fail('retour a la couleur du modele rate', r1);
  // couleur en plus : prochaine case de tes reglages pas encore utilisee, profil et couleur au choix, croix
  if (await page.textContent('#map button.addc') !== T.add_color) fail('bouton « Ajouter une couleur » absent du panneau');
  const nSlots = an.files[0].slots.length;
  await page.click('#map button.addc');
  pl = (await plansSent()).slice(-1)[0];
  const used = new Set(pl.files[0].slots.slice(0, -1).map(x => x.base)), wantBase = an.profiles.findIndex((pr, i) => pr.group === 'slot' && !used.has(i));
  const ex = pl.files[0].slots[nSlots];
  if (pl.files[0].slots.length !== nSlots + 1 || !ex.extra || ex.src.length || ex.base !== (wantBase < 0 ? pl.files[0].slots[nSlots - 1].base : wantBase)) fail('couleur en plus mal ajoutee', ex);
  let exRow = (await rowsNow()).find(r => r.nm === T.extra_name);
  if (!exRow || !exRow.rm || exRow.n !== String(nSlots + 1)) fail('ligne « couleur en plus » absente', await rowsNow());
  const rose = an.profiles.findIndex(pr => pr.name === 'JAYO PLA Rose');
  await page.selectOption('#map select[data-s="' + nSlots + '"]', String(rose));
  pl = (await plansSent()).slice(-1)[0];
  if (pl.files[0].slots[nSlots].base !== rose || String(pl.files[0].slots[nSlots].color).toUpperCase() !== String(an.profiles[rose].color).slice(0, 7).toUpperCase())
    fail('couleur en plus : la couleur du preréglage ne part pas', pl.files[0].slots[nSlots]);
  if (!(await page.evaluate(t => [...document.querySelectorAll('#notes span')].some(x => x.textContent === t), T.extras_note))) fail('note des couleurs en plus absente');
  await page.click('#map button.rmc[data-s="' + nSlots + '"]');
  pl = (await plansSent()).slice(-1)[0];
  if (pl.files[0].slots.length !== nSlots || (await rowsNow()).some(r => r.nm === T.extra_name)) fail('croix : la couleur en plus reste', pl.files[0].slots.length);
  // jusqu'a 16 filaments, puis le bouton se grise
  const maxF = an.max_filaments || 16;
  for (let k = nSlots; k < maxF; k++) await page.click('#map button.addc');
  if (!(await page.isDisabled('#map button.addc')) || await page.textContent('#map .full') !== T.max_colors.replace('{0}', maxF)) fail('limite de filaments absente');
  while ((await rowsNow()).some(r => r.rm)) await page.locator('#map button.rmc').last().click();
  // cases libres : une ligne, a ouvrir pour choisir leur filament
  if (pads.length) {
    await page.click('#map button.padg');
    const pr2 = await rowsNow(), padRows = pr2.filter(r => r.free && !r.group);
    if (padRows.length !== pads.length || pr2.some(r => r.group)) fail('cases libres pas ouvertes', pr2);
    const pIdx = an.files[0].slots.indexOf(pads[0]);
    await page.selectOption('#map select[data-s="' + pIdx + '"]', String(otherBase));
    pl = (await plansSent()).slice(-1)[0];
    if (pl.files[0].slots[pIdx].base !== otherBase || pl.files[0].slots[pIdx].extra) fail('case libre : profil pas envoye', pl.files[0].slots[pIdx]);
    await page.selectOption('#map select[data-s="' + pIdx + '"]', String(pads[0].base));
  }
  await page.selectOption('#map select[data-s="' + mIdx + '"]', String(mRow.base));
  await page.setViewportSize({ width: 340, height: 900 }); await page.waitForTimeout(150); await shot('5b_modifier.png'); await page.setViewportSize({ width: 340, height: 720 });
  // un plan de l'onglet arrive : montre, et pas renvoye
  const nSentPlans = (await plansSent()).length;

  // 6. l'onglet change un profil, une couleur, ajoute une couleur : le panneau montre le meme plan
  const nRows = await page.evaluate(() => document.querySelectorAll('#map .r').length);
  await recv(Object.assign({}, plan, { token: 'autre' }));
  if ((await page.evaluate(() => document.querySelectorAll('#map .r').length)) !== nRows) fail('plan d\'un autre travail pris en compte');
  await recv(plan);
  const pr = await rowsNow();
  const changed = pr.find(r => r.n === String(real.real + 1)), extra = pr.find(r => r.nm === T.extra_name);
  if (!changed || changed.prof !== an.profiles[real.petg].name || !changed.arrow || changed.pick !== '#7b1fa2'
      || !extra || extra.prof !== an.profiles[real.rose].name || extra.arrow || !extra.rm || (await plansSent()).length !== nSentPlans)
    fail('plan de l\'onglet mal montre', pr);
  if (!(await page.evaluate(() => [...document.querySelectorAll('#map .w')].some(w => /PETG/.test(w.textContent))))) fail('alerte de matiere absente (PLA -> PETG)');
  await page.waitForTimeout(200); await shot('6_plan_de_l_onglet.png');

  // 7. Convertir : le plan affiche part au plugin, la U1 mache
  await clear(); await page.click('#convert');
  const conv = (await sent()).find(m => m.command === 'convert');
  if (!conv || conv.token !== an.token || JSON.stringify(conv.files) !== JSON.stringify(plan.files) || await v() !== 'conv' || !/chew/.test(await u1())
      || await shown('cancel') || await txt('say') !== T.pn_conv) fail('Convertir : envoi ou ecran incorrect', conv);
  await recv({ command: 'progress', text: T.p_converting, token: an.token });
  await page.waitForTimeout(300); await shot('7_conversion.png');
  await clear(); await recv({ command: 'built', token: an.token });
  const wr = (await sent()).find(m => m.command === 'write');
  if (!wr || wr.token !== an.token) fail('« built » : pas d\'ecriture demandee', await sent());

  // 8. C'est pret : chemin, Copier le chemin, et comment l'ouvrir
  await recv(res);
  const done = await page.evaluate(() => ({ code: [...document.querySelectorAll('#paths code')].map(c => c.textContent), hint: document.getElementById('hint').innerHTML }));
  if (await v() !== 'done' || await txt('say') !== T.pn_done || done.code.join() !== res.files.map(x => x.path).join() || !(await shown('copy'))
      || !done.hint.includes('<b>' + T.pn_menu.replace(/›/g, '›') + '</b>') || !/full/.test(await u1())) fail('C\'est pret incorrect', done);
  const order = await page.evaluate(() => ['paths', 'copy', 'hint', 'notes'].map(id => document.getElementById(id).getBoundingClientRect().top));
  if (!(order[0] < order[1] && order[1] < order[2] && order[2] < order[3])) fail('C\'est pret : chemin, bouton, aide puis alertes', order);
  await page.click('#copy');
  if (await txt('copy') !== T.copied) fail('Copier le chemin : pas de retour', await txt('copy'));
  await page.waitForTimeout(250); await shot('8_pret.png');
  await recv({ command: 'rest' });
  if (await v() !== 'rest') fail('« rest » du plugin (projet converti ouvert) : pas de retour au repos');

  // 9. Pouah : le 3MF ne passe pas
  await recv(offer); await page.click('#eat');
  const errText = T.pn_err + ' test : archive illisible';
  await recv({ command: 'error', text: errText });
  await page.waitForTimeout(120);
  if (await v() !== 'err' || await txt('say') !== T.pn_err || await txt('say2') !== errText || !/spit/.test(await u1()) || !(await shown('ok'))) fail('erreur incorrecte', await v());
  await page.waitForTimeout(250); await shot('9_pouah.png');
  await page.click('#ok');
  if (await v() !== 'rest') fail('OK apres une erreur : pas de retour au repos');
  await recv({ command: 'error', text: 'sans rapport' });
  if (await v() !== 'rest') fail('erreur hors travail affichee');

  // 10. Annuler pendant l'analyse : la suite de l'analyse annulee est ignoree, le 3MF propose revient
  await recv(offer); await page.click('#eat');
  await recv({ command: 'progress', text: 'Analyse…', token: 't9' });
  await clear(); await page.click('#cancel');
  if (!(await sent()).some(m => m.command === 'cancel') || await v() !== 'rest') fail('Annuler : rien envoye ou mauvais ecran', await sent());
  await recv(Object.assign({}, an, { token: 't9' }));
  await recv({ command: 'error', text: 'trop tard', token: 't9' });
  if (await v() !== 'rest') fail('analyse annulee affichee quand meme', await v());
  await recv(offer);
  if (await v() !== 'offer') fail('le 3MF propose ne revient pas apres Annuler');
  await clear(); await page.click('#later');
  if (!(await sent()).some(m => m.command === 'later') || await v() !== 'rest') fail('Pas maintenant : rien envoye ou mauvais ecran');

  // 11. 3MF lache sur le panneau : envoye par morceaux (numeros « p… »), puis analyse
  const big = await page.evaluate(async () => {
    window.__sent.length = 0; const keep = M3D_UP.CHUNK; M3D_UP.CHUNK = 4;
    const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])], 'glisse.3mf'));
    const texts = []; const ob = new MutationObserver(() => texts.push(document.getElementById('say2').textContent));
    ob.observe(document.getElementById('say2'), { childList: true, subtree: true, characterData: true });
    document.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true }));
    document.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    await new Promise(r => setTimeout(r, 400)); ob.disconnect(); M3D_UP.CHUNK = keep;
    return { sent: window.__sent.filter(m => m.command !== 'view').map(m => ({ c: m.command, i: m.i, n: m.n, id: m.id || m.upload_id, name: m.name, len: m.data ? atob(m.data).length : 0 })),
      texts, view: document.body.getAttribute('data-v') };
  });
  const parts = big.sent.filter(m => m.c === 'upload_part'), last = big.sent[big.sent.length - 1];
  if (parts.length !== 3 || parts.map(m => m.i).join() !== '0,1,2' || parts.map(m => m.len).join() !== '4,4,2' || parts.some(m => m.n !== 3 || m.id !== parts[0].id)
      || !/^p/.test(parts[0].id) || last.c !== 'analyze' || last.id !== parts[0].id || last.name !== 'glisse.3mf' || big.view !== 'busy') fail('glisser-deposer incorrect', big);
  if (!big.texts.some(x => x.includes('(2/3)'))) fail('lecture par morceaux non affichee', big.texts);
  await recv(Object.assign({}, an, { token: 't10' }));
  if (await v() !== 'an') fail('analyse du fichier lache pas affichee');

  // 12. l'onglet convertit ce que montre le panneau : le panneau suit
  await recv({ command: 'progress', text: 'Conversion…', token: 't10' });
  if (await v() !== 'conv') fail('conversion lancee dans l\'onglet : le panneau ne suit pas', await v());
  await recv(Object.assign({}, res, { token: 't10' }));
  if (await v() !== 'done') fail('resultat de l\'onglet pas montre');
  await recv({ command: 'progress', text: 'autre', token: 'zz' });
  if (await v() !== 'done') fail('progression d\'un autre travail prise en compte');

  // 13. Annuler pendant l'envoi : plus de morceaux, le plugin oublie ceux recus
  const stop = await page.evaluate(async () => {
    window.__sent.length = 0; const keep = M3D_UP.CHUNK; M3D_UP.CHUNK = 1;
    const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array(4000)], 'long.3mf'));
    document.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    await new Promise(r => setTimeout(r, 60));
    document.getElementById('cancel').click();
    const s = window.__sent.filter(m => m.command !== 'view'), n = s.length; await new Promise(r => setTimeout(r, 300)); M3D_UP.CHUNK = keep;
    const after = window.__sent.filter(m => m.command !== 'view');
    return { n, after: after.length, cmds: after.slice(-2).map(m => m.command), analyze: after.some(m => m.command === 'analyze'), view: document.body.getAttribute('data-v') };
  });
  if (stop.n !== stop.after || stop.cmds.join() !== 'upload_drop,cancel' || stop.analyze || stop.view !== 'rest') fail('Annuler pendant l\'envoi incorrect', stop);

  // 14. pas un 3MF, ou trop gros : recrache, rien envoye
  const spit = await page.evaluate(async () => {
    window.__sent.length = 0;
    const dt = new DataTransfer(); dt.items.add(new File(['x'], 'photo.png'));
    document.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    const r = { view: document.body.getAttribute('data-v'), say2: document.getElementById('say2').textContent };
    document.getElementById('ok').click();
    const keep = M3D_UP.MAXUP; M3D_UP.MAXUP = 5;
    const dt2 = new DataTransfer(); dt2.items.add(new File([new Uint8Array(10)], 'enorme.3mf'));
    document.dispatchEvent(new DragEvent('drop', { dataTransfer: dt2, bubbles: true, cancelable: true }));
    M3D_UP.MAXUP = keep;
    r.view2 = document.body.getAttribute('data-v'); r.say2b = document.getElementById('say2').textContent;
    r.sent = window.__sent.filter(m => m.command !== 'view').length;
    document.getElementById('ok').click();
    return r;
  });
  if (spit.view !== 'err' || spit.say2 !== T.not_3mf.replace('{0}', 'photo.png') || spit.view2 !== 'err' || !spit.say2b.startsWith(T.too_big.split('{0}')[0]) || spit.sent)
    fail('fichier refuse incorrect', spit);

  // 15. page qui redemarre : le plugin rejoue analyse et resultat, sans animation
  await recv(Object.assign({}, an, { token: 't11', replay: true }));
  if (await v() !== 'an' || /burp/.test(await u1())) fail('rejeu de l\'analyse', { v: await v(), u1: await u1() });
  await recv(Object.assign({}, res, { token: 't11', replay: true }));
  if (await v() !== 'done') fail('rejeu du resultat');

  // 16. langue : le bonjour du plugin suffit, l'ecran est refait
  const other = hello.lang === 'fr' ? 'en' : 'fr';
  await recv(Object.assign({}, hello, { lang: other }));
  if (await txt('say') !== L[other].pn_done || await txt('copy') !== L[other].copy_path || await page.evaluate(() => document.documentElement.lang) !== other)
    fail('changement de langue incorrect', await txt('say'));
  await recv(hello);

  // 17. reglage « notification seulement » : le texte du repos ne promet plus de surveiller Orca
  await recv({ command: 'rest' }); await recv(Object.assign({}, hello, { mode: 'notif' }));
  if (await txt('say2') !== T.pn_rest2b) fail('texte du repos en mode notification', await txt('say2'));
  await recv(hello);

  // 17b. « rien » choisi dans le panneau : il le dit au plugin, explique comment revenir, puis se ferme
  await recv({ command: 'rest' }); await clear();
  await page.selectOption('#pmodeSel', 'off');
  const pmSent = (await sent()).find(m => m.command === 'panel_mode');
  if (!pmSent || pmSent.mode !== 'off' || await v() !== 'bye' || await txt('say') !== T.pn_bye || await txt('say2') !== T.pn_bye2 || await shown('pmode'))
    fail('desactivation depuis le panneau incorrecte', { pmSent, v: await v() });
  await page.waitForTimeout(400); await shot('10_je_me_cache.png');
  await page.waitForTimeout(2400);
  if ((await page.evaluate(() => window.__closed || 0)) !== 1) fail('le panneau ne se ferme pas apres « rien »');
  await recv(hello);
  if (await page.evaluate(() => document.getElementById('pmodeSel').value) !== 'panel') fail('reglage du plugin pas repris');

  // 18. panneau etroit et bas (Orca le laisse redimensionner) : rien ne deborde en largeur
  await recv(Object.assign({}, an, { token: 't12', replay: true })); await recv(Object.assign({}, plan, { token: 't12' }));
  for (const [wd, ht] of [[260, 520], [420, 900]]) {
    await page.setViewportSize({ width: wd, height: ht });
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (over > 1) fail('le panneau deborde en largeur a ' + wd + ' px', over);
  }
  await page.setViewportSize({ width: 340, height: 720 });
  if (errors.length) fail('erreurs JS', errors);
  console.log('panneau OK');
  await browser.close();
})();
