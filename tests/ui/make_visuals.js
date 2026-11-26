// Visuels de Mange-3MF pour Orca Cloud et GitHub (docs/visuals) : pages HTML rendues par Chrome, a partir
// des captures de docs/captures (refaites par make_captures.py).
// Usage : node tests/ui/make_visuals.js [chemin_chrome]   (npm install dans tests/ui)
const { chromium } = require('playwright-core');
const fs = require('fs'), os = require('os'), path = require('path');
const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(ROOT, 'docs', 'visuals');
const HERE = fs.mkdtempSync(path.join(os.tmpdir(), 'mange3mf_visuals_'));   // pages et images de travail
const VERSION = (fs.readFileSync(path.join(ROOT, 'mange_3mf_any.py'), 'utf8').match(/^VERSION = "([^"]+)"/m) || [, '?'])[1];
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(path.join(HERE, 'assets'));
fs.copyFileSync(require.resolve('@fontsource-variable/bricolage-grotesque/files/bricolage-grotesque-latin-standard-normal.woff2'),
                path.join(HERE, 'assets', 'bricolage.woff2'));
for (const f of ['1_reglages_et_fichiers.png', '2_analyse.png', '3_resultat.png', '5_reglages.png', '6_panneau.png',
                 '7a_prusa.png', '7b_profils.png', '7c_supports.png'])   // 7* : check_060.py
  fs.copyFileSync(path.join(ROOT, 'docs', 'captures', 'en', f), path.join(HERE, 'assets', f));
fs.copyFileSync(path.join(ROOT, 'docs', 'captures', '1_reglages_et_fichiers.png'), path.join(HERE, 'assets', 'fr_1_reglages_et_fichiers.png'));

// ---- elements communs
const COLORS = [['#151515', 'black'], ['#FFE11A', 'yellow'], ['#E53935', 'red'], ['#F4F4F4', 'white'],
                ['#1E5BD8', 'blue'], ['#6A1B9A', 'purple'], ['#FF3EC8', 'pink']];

function rng(seed) { return () => (seed = (seed * 16807) % 2147483647) / 2147483647; }
function speckle() {   // plateau PEI texture : petits points clairs et sombres
  const r = rng(7), dots = [];
  for (let i = 0; i < 90; i++) {
    const light = r() < 0.6;
    dots.push(`<circle cx="${(r() * 240).toFixed(1)}" cy="${(r() * 240).toFixed(1)}" r="${(0.5 + r() * 1.1).toFixed(2)}" fill="${light ? '#ffffff' : '#000000'}" fill-opacity="${(light ? 0.035 + r() * 0.05 : 0.18).toFixed(3)}"/>`);
  }
  return 'data:image/svg+xml;utf8,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">${dots.join('')}</svg>`);
}

// l'icone : la U1 gourmande qui croque un 3MF (fichiers dans docs/visuals/logo)
const LOGO_DIR = path.join(ROOT, 'docs', 'visuals', 'logo');
const ICON = fs.readFileSync(path.join(LOGO_DIR, 'mange3mf_icon.svg'), 'utf8').replace(/<title>[^<]*<\/title>\s*/, '');
const TAB_ICON = fs.readFileSync(path.join(LOGO_DIR, 'mange3mf_tab_icon.svg'), 'utf8');
let nIcon = 0;
function logo(size) {   // icone en couleur, tuile turquoise
  const id = 'u1mouth' + (++nIcon);
  return ICON.replace('width="512" height="512"', `width="${size}" height="${size}" aria-hidden="true"`)
    .replace(/id="m"/g, `id="${id}"`).replace(/url\(#m\)/g, `url(#${id})`);
}
function tabIcon(size) {   // icone de l'onglet dans Orca (une couleur), comme ICON_SVG du plugin
  return TAB_ICON.replace('viewBox="0 0 24 24"', `viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true"`);
}

function spool(color, size, dark) {   // bobine vue de face
  const w = dark ? 'rgba(255,255,255,.10)' : 'rgba(0,0,0,.16)';
  const rings = [58, 53, 48, 43].map(r => `<circle cx="70" cy="70" r="${r}" fill="none" stroke="${w}" stroke-width="1.4"/>`).join('');
  return `<svg width="${size}" height="${size}" viewBox="0 0 140 140" aria-hidden="true">
  <circle cx="70" cy="70" r="69" fill="#2a313d" stroke="#3b4554" stroke-width="2"/>
  <circle cx="70" cy="70" r="62" fill="${color}"/>${rings}
  <path d="M 26 52 A 48 48 0 0 1 60 22" fill="none" stroke="#fff" stroke-opacity=".28" stroke-width="5" stroke-linecap="round"/>
  <circle cx="70" cy="70" r="30" fill="#2a313d" stroke="#3b4554" stroke-width="2"/>
  <circle cx="70" cy="70" r="13" fill="#0f1520"/>
  <circle cx="70" cy="47" r="4.5" fill="#0f1520"/><circle cx="50" cy="81.5" r="4.5" fill="#0f1520"/><circle cx="90" cy="81.5" r="4.5" fill="#0f1520"/>
</svg>`;
}

const BASE_CSS = `
@font-face{font-family:"Bricolage";src:url(assets/bricolage.woff2) format("woff2-variations");font-weight:200 800;font-stretch:75% 100%}
*{box-sizing:border-box}
html,body{margin:0;background:#0f1520}
.canvas{position:relative;overflow:hidden;color:#eef1f5;font-family:"Bricolage",system-ui,sans-serif;
  background:url("${speckle()}"),#0f1520}
.mark{position:absolute;display:flex;align-items:center;gap:14px;font-size:30px;font-weight:700;letter-spacing:-.01em;color:#dfe5ee}
.mark svg{display:block}
h1,h2,p{margin:0}
`;

function frame(inner, tab) {   // la page dans un onglet d'Orca
  return `<div class="frame"><div class="bar"><span>Prepare</span><span>Preview</span><span>Device</span>
    <span class="on">${tabIcon(26)}${tab || 'Mange-3MF'}</span></div>${inner}</div>`;
}
const FRAME_CSS = `
.frame{border-radius:16px;overflow:hidden;border:1px solid #2c3747;background:#262629;box-shadow:0 36px 90px rgba(0,0,0,.55)}
.frame .bar{height:56px;display:flex;align-items:center;gap:34px;padding:0 26px;background:#1a1f27;border-bottom:1px solid #2c3747;
  font:500 21px/1 "Bricolage",system-ui,sans-serif;color:#8f9aab}
.frame .bar .on{display:flex;align-items:center;gap:9px;color:#eef1f5;height:100%;border-bottom:3px solid #22b3a5;padding-top:3px}
.frame img{display:block;width:100%}
`;

// ---- 1. couverture
function cover() {
  const gray = [1, 2, 3, 4].map(n => `<figure>${spool('#8b919b', 100, false)}<figcaption>${n}</figcaption></figure>`).join('');
  const col = COLORS.map(([c], i) => `<figure>${spool(c, 100, c === '#151515' || c === '#6A1B9A' || c === '#1E5BD8')}<figcaption>${i + 1}</figcaption></figure>`).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><style>${BASE_CSS}
.canvas{width:1920px;height:1080px}
header{position:absolute;left:120px;top:96px;display:flex;align-items:center;gap:46px}
h1{font-size:176px;line-height:.9;font-weight:800;font-stretch:92%;letter-spacing:-.012em}
.tag{margin-top:22px;font-size:50px;font-weight:400;color:#c9d2de;letter-spacing:-.01em}
.duel{position:absolute;left:120px;right:120px;top:452px;height:440px;display:grid;grid-template-columns:690px 1fr;gap:96px}
.side{position:relative;border-radius:28px;padding:42px 48px}
.before{background:#1a1f28;border:2px solid #2c3442;
  -webkit-mask-image:radial-gradient(circle 92px at 100% 0,transparent 91px,#000 92px),radial-gradient(circle 58px at 100% 62%,transparent 57px,#000 58px);
  -webkit-mask-composite:source-in;mask-composite:intersect}
.after{background:radial-gradient(700px 360px at 60% 70%,rgba(34,179,165,.16),transparent 70%),#152230;border:2px solid #22b3a5}
h2{font-size:44px;font-weight:700;letter-spacing:-.015em}
.side p{margin-top:8px;font-size:30px;color:#9aa6b6}
.before h2{color:#c5ccd6}
.spools{position:absolute;left:48px;bottom:40px;display:flex;gap:16px}
figure{margin:0;text-align:center}figure svg{display:block}
figcaption{margin-top:8px;font-size:24px;font-weight:600;color:#7f8a9a}
.after figcaption{color:#a9c9c5}
.crumbs{position:absolute;left:${120 + 690 + 14}px;top:452px;width:70px;height:440px}
.crumbs i{position:absolute;display:block;border-radius:40%;background:#323b4a}
footer{position:absolute;left:120px;right:120px;bottom:70px;display:flex;justify-content:space-between;align-items:baseline;font-size:30px;color:#8f9aab}
footer b{font-weight:700;color:#22b3a5}
</style></head><body><div class="canvas">
<header>${logo(210)}<div><h1>Mange-3MF</h1><p class="tag">Eats any 3MF. Spits out a project for your Snapmaker U1.</p></div></header>
<div class="duel">
  <div class="side before"><h2>Opened as is in Orca</h2><p>4 × Generic ABS, colors 5 to 7 lost</p><div class="spools">${gray}</div></div>
  <div class="side after"><h2>Converted by Mange-3MF</h2><p>7 colors, 7 filaments, your own settings</p><div class="spools">${col}</div></div>
</div>
<div class="crumbs"><i style="left:6px;top:12px;width:16px;height:14px"></i><i style="left:40px;top:58px;width:11px;height:10px"></i><i style="left:20px;top:250px;width:13px;height:12px"></i><i style="left:48px;top:300px;width:8px;height:8px"></i></div>
<footer><span>Free plugin for OrcaSlicer 2.5 and the Snapmaker U1, in 5 languages.</span><b>v${VERSION}</b></footer>
</div></body></html>`;
}

// ---- 2 a 4. une capture et son titre
function shot(title, sub, right, extraCss) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${BASE_CSS}${FRAME_CSS}
.canvas{width:1920px;height:1080px}
.text{position:absolute;left:120px;top:0;bottom:0;width:520px;display:flex;flex-direction:column;justify-content:center}
h1{font-size:92px;line-height:.98;font-weight:800;font-stretch:92%;letter-spacing:-.008em}
.sub{margin-top:30px;font-size:33px;line-height:1.35;color:#aab5c4}
.mark{left:120px;top:72px}
.right{position:absolute;left:720px;right:80px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:center;gap:34px}
${extraCss || ''}
</style></head><body><div class="canvas">
<div class="mark">${logo(46)}Mange-3MF</div>
<div class="text"><h1>${title}</h1><p class="sub">${sub}</p></div>
<div class="right">${right}</div>
</div></body></html>`;
}

function crop(file, x, y, w, h, width) {   // morceau d'une capture, affiche a la largeur voulue
  const s = width / w;
  return `<div class="crop" style="width:${width}px;height:${Math.round(h * s)}px;overflow:hidden;position:relative">
<img src="assets/${file}" style="position:absolute;left:${-x * s}px;top:${-y * s}px;width:${imgW[file] * s}px;max-width:none"></div>`;
}
const imgW = { '1_reglages_et_fichiers.png': 1920, 'fr_1_reglages_et_fichiers.png': 1920, '2_analyse.png': 1920, '3_resultat.png': 1920, '5_reglages.png': 1920,
               '6_panneau.png': 2236 };

function colorsPage() {
  return shot('Exactly the model’s colors',
    '7 colors give 7 filaments, nothing merged. Each color gets the closest of your filament profiles, or the one you pick.',
    frame(`<img src="assets/2_analyse.png">`));
}
function settingsPage() {
  return shot('Your settings, saved in one click',
    'Printer, nozzles, process and plate come from your Orca, not from the model’s author.',
    frame(crop('5_reglages.png', 150, 47, 1620, 1107, 1120)));   // la fenetre Reglages entiere
}
function readyPage() {
  const right = frame(`<img src="assets/3_resultat.png">`) +
    `<div class="langs"><div><span>English</span><div class="lang">${crop('1_reglages_et_fichiers.png', 0, 70, 1000, 142, 550)}</div></div>
     <div><span>Français</span><div class="lang">${crop('fr_1_reglages_et_fichiers.png', 0, 70, 1000, 142, 550)}</div></div></div>`;
  return shot('Ready to open, in your language',
    'The project lands next to the original: open it in Orca and print. The tab follows Orca’s language: English, French, German, Spanish or Italian.',
    right, `.langs{display:flex;gap:18px}
.langs span{display:block;margin:0 0 10px 4px;font-size:26px;font-weight:700;color:#22b3a5}
.lang{position:relative;border-radius:14px;overflow:hidden;border:1px solid #2c3747;background:#262629}`);
}

function preparePage() {   // les trois panneaux de 6_panneau.png (docks de 684 x 1452, tous les 728 px)
  const steps = ['She asks for the 3MF', 'You pick colors and profiles', 'The project is ready'];
  const right = `<div class="docks">${steps.map((t, i) => `<div class="step"><p class="lab"><b>${i + 1}</b>${t}</p>
<div class="dock">${crop('6_panneau.png', 48 + i * 728, 112, 684, 1452, 350)}</div></div>`).join('')}</div>`;
  return shot('She waits in Prepare',
    'Open a 3MF that isn’t set up for the U1: she offers to eat it, lets you pick colors and profiles, and builds the project right there.',
    right, `.docks{display:flex;gap:35px}
.step{width:350px}
.lab{display:flex;align-items:center;gap:11px;margin:0 0 16px 2px;font-size:22px;font-weight:650;color:#dfe5ee;white-space:nowrap}
.lab b{display:inline-grid;place-items:center;flex:none;width:32px;height:32px;border-radius:8px;background:#22b3a5;color:#0c2e2a;font-size:19px;font-weight:800}
.dock{border-radius:10px;overflow:hidden;box-shadow:0 30px 70px rgba(0,0,0,.5)}`);
}

// ---- 6. nouveautes de la 0.6.0 (morceaux de captures faits par check_060.py)
function newPage() {
  const card = (label, img, w) => `<div class="card"><p class="lab">${label}</p><div class="shot" style="width:${w}px"><img src="assets/${img}"></div></div>`;
  return shot('New in 0.6.0',
    'Projects from PrusaSlicer and Printables. An Orca profile when you lack a material. Your choices remembered. The author’s supports if you want them. And German, Spanish, Italian.',
    card('PrusaSlicer and Printables projects', '7a_prusa.png', 1000) +
    card('An Orca profile for a missing material, your choice from last time', '7b_profils.png', 1000) +
    card('The author’s supports, your call', '7c_supports.png', 620),
    `.right{gap:34px}
.card .lab{margin:0 0 12px 2px;font-size:25px;font-weight:650;color:#dfe5ee}
.shot{border-radius:14px;overflow:hidden;border:1px solid #2c3747;background:#1c1d20;box-shadow:0 30px 70px rgba(0,0,0,.45)}
.shot img{display:block;width:100%}`);
}

// ---- GitHub : banniere du README et apercu social
function banner(w, h) {
  const sz = h >= 600 ? 78 : 118;
  const col = COLORS.map(([c]) => spool(c, sz, c === '#151515' || c === '#6A1B9A' || c === '#1E5BD8')).join('');
  const gray = [1, 2, 3, 4].map(() => spool('#8b919b', sz, false)).join('');
  const big = h >= 600;
  return `<!doctype html><html><head><meta charset="utf-8"><style>${BASE_CSS}
.canvas{width:${w}px;height:${h}px}
.in{position:absolute;inset:0;padding:${big ? 74 : 60}px ${big ? 80 : 70}px;display:flex;flex-direction:column;justify-content:${big ? 'space-between' : 'center'};gap:${big ? 0 : 34}px}
.top{display:flex;align-items:center;gap:${big ? 40 : 36}px}
h1{font-size:${big ? 124 : 112}px;line-height:.9;font-weight:800;font-stretch:92%;letter-spacing:-.012em}
.tag{margin-top:14px;font-size:${big ? 32 : 36}px;color:#c9d2de}
.row{display:flex;align-items:center;gap:${big ? 14 : 12}px}
.row svg{display:block;flex:none}
.arrow{margin:0 ${big ? 18 : 16}px;font-size:${big ? 54 : 46}px;font-weight:300;color:#22b3a5;line-height:1}
.gray{opacity:.75;display:flex;gap:${big ? 14 : 12}px}
.foot{font-size:${big ? 27 : 24}px;color:#8f9aab}
</style></head><body><div class="canvas"><div class="in">
<div class="top">${logo(big ? 170 : 150)}<div><h1>Mange-3MF</h1><p class="tag">Eats any 3MF. Spits out a project for your Snapmaker U1.</p></div></div>
<div class="row"><div class="gray">${gray}</div><span class="arrow">→</span>${col}</div>
${big ? '<p class="foot">Free plugin for OrcaSlicer 2.5, in 5 languages</p>' : ''}
</div></div></body></html>`;
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[2] || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const jobs = [
    ['01_cover', cover(), 1920, 1080, 'jpeg'],
    ['before_after', cover(), 1920, 1080, 'jpeg', { x: 0, y: 420, width: 1920, height: 510 }],   // pour le README
    ['02_colors', colorsPage(), 1920, 1080, 'jpeg'],
    ['03_settings', settingsPage(), 1920, 1080, 'jpeg'],
    ['04_ready', readyPage(), 1920, 1080, 'jpeg'],
    ['05_prepare', preparePage(), 1920, 1080, 'jpeg'],
    ['06_new', newPage(), 1920, 1080, 'jpeg'],
    ['github_banner', banner(1760, 520), 1760, 520, 'png'],
    ['github_social_preview', banner(1280, 640), 1280, 640, 'png'],
  ];
  for (const [name, html, w, h, type, clip] of jobs) {
    const file = path.join(HERE, '_' + name + '.html');
    fs.writeFileSync(file, html);
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const errors = []; page.on('pageerror', e => errors.push(String(e)));
    await page.goto('file://' + file);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(150);
    const fam = await page.evaluate(() => document.fonts.check('800 100px "Bricolage"'));
    const out = path.join(OUT, name + (type === 'jpeg' ? '.jpg' : '.png'));
    await page.screenshot({ path: out, type, quality: type === 'jpeg' ? 92 : undefined, clip: clip || { x: 0, y: 0, width: w, height: h } });
    console.log(name, fam ? 'police ok' : 'POLICE ABSENTE', errors.length ? errors : '');
    await page.close();
  }
  await browser.close();
  console.log('visuels dans', OUT);
})();
