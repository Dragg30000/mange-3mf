"""Verifie dans Chrome les nouveautes de la 0.7.0 (onglet et panneau de Preparer) avec les vrais messages du
plugin (faux OrcaSlicer 2.5.1) : deux imprimantes memorisees (U1 et P1S) et le choix entre elles, la carte de
ton imprimante pour chaque famille (changeur d'outils, une buse + boite, plusieurs buses, une seule bobine),
les alertes de capacite, « Tout en une couleur ». Captures pour verifier a l'oeil dans le dossier donne
(par defaut un dossier temporaire).
Usage : python tests/ui/check_070.py [dossier_captures] [langue]   (Node, playwright-core installe ici, Chrome)."""
import importlib, json, os, shutil, subprocess, sys, tempfile
UI = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.dirname(UI)
ROOT = os.path.dirname(TESTS)
sys.path.insert(0, TESTS)
from common import fake_template, sample
import fake_orca, printer_configs

RIGS = [  # (nom, imprimante d'Orca ou imitation, couleurs, buse de chaque filament)
    ("u1", "Snapmaker U1 (0.4 nozzle)", ("#F5F5F5", "#111111", "#D32F2F", "#FFE11A", "#1E5BD8", "#2E7D32"), None),
    ("p1s", "Bambu Lab P1S 0.4 nozzle", ("#F5F5F5", "#FFE11A", "#D32F2F", "#111111"), None),
    ("kobra", "Anycubic Kobra S1 0.4 nozzle", ("#111111", "#F5F5F5"), None),
    ("mmu3", "Prusa MK4S MMU3 0.4 nozzle", ("#F5F5F5", "#FF7A00", "#1E5BD8", "#111111", "#2E7D32"), None),
    ("xl", "Prusa XL 5T 0.4 nozzle", ("#F5F5F5", "#FF7A00", "#1E5BD8", "#111111", "#2E7D32"), None),
    ("indx", "Prusa CORE One INDX 8T HF 0.4 nozzle", ("#F5F5F5", "#FF7A00", "#1E5BD8", "#111111", "#2E7D32", "#D32F2F", "#FFE11A", "#8E24AA"), None),
    ("h2d", "Bambu Lab H2D 0.4 nozzle", ("#F5F5F5", "#FFE11A", "#D32F2F", "#111111"), ["1", "1", "2", "2"]),
    ("h3c", "Bambu Lab H3C", ("#F5F5F5", "#FF7A00", "#1E5BD8", "#111111", "#2E7D32", "#D32F2F", "#FFE11A", "#8E24AA", "#00ACC1"),
     [str(i + 1) for i in range(9)]),
    ("mini", "Prusa MINI 0.4 nozzle", ("#2E7D32",), None),
]


def prepare(lang):
    tmp = tempfile.mkdtemp()
    home = os.path.join(tmp, "home"); dl = os.path.join(home, "Downloads"); os.makedirs(dl)
    os.environ["HOME"] = home; os.environ["USERPROFILE"] = home
    poke = os.path.join(dl, "Pokeballs.3mf")
    shutil.copy(sample("sample_pokeballs.3mf"), poke)
    base = fake_template().config
    storage = os.path.join(tmp, "storage")
    orca, st, cur = fake_orca.install(storage, base, dock=True)
    st["language"] = {"fr": "fr_FR", "en": "en_US", "de": "de_DE", "es": "es_ES", "it": "it_IT"}[lang]
    sys.modules.pop("mange_3mf_any", None)
    m = importlib.import_module("mange_3mf_any")

    def cfg_of(key):
        _n, name, cols, maps = next(r for r in RIGS if r[0] == key)
        extra = printer_configs.imitation(name, 9) if name not in printer_configs.PRINTERS else None
        return printer_configs.config_for(m, base, name, colors=cols, maps=maps, extra=extra)
    st["plugin"]().register_capabilities()
    tab = st["caps"][0]()
    html = tab.get_ui()
    w = st["page"]
    tab.on_message({"command": "init"}); rec = w.wait("recent")
    cur.clear(); cur.update(cfg_of("u1"))
    tab.on_message({"command": "capture"}); w.wait("state", 2)
    cur.clear(); cur.update(cfg_of("p1s"))
    tab.on_message({"command": "capture"}); state = w.wait("state", 3)
    rec = w.wait("recent", 3)
    tab.on_message({"command": "analyze", "path": poke, "template": "saved"})
    an_p1s = w.wait("analysis")
    # reglages actuels d'Orca : une Kobra S1 a deux bobines, puis une Prusa MINI a une bobine
    cur.clear(); cur.update(cfg_of("kobra"))
    tab.on_message({"command": "analyze", "path": poke, "template": "current"})
    an_kobra = w.wait("analysis", 2)
    cur.clear(); cur.update(cfg_of("mini"))
    tab.on_message({"command": "analyze", "path": poke, "template": "current"})
    an_mini = w.wait("analysis", 3)
    tab.on_message({"command": "replan", "token": an_mini["token"], "one_color": True})
    an_mono = w.wait("analysis", 4)
    # la carte de chaque imprimante (reglages memorises), comme l'onglet la recoit
    rigs = {}
    for key, _name, _cols, _maps in RIGS:
        t = m.Template(cfg_of(key), "BambuStudio-02.08.01.55", "2.5.1")
        s = m.CONVERTER.template_summary(t)
        s["target"] = True
        rigs[key] = json.loads(json.dumps(m.relocalize(s)))
    # panneau : la P1S choisie, un 3MF propose, puis l'analyse de la Kobra (deux bobines)
    tab.on_lifecycle_event("ProjectOpened", type("C", (), {"name": poke})())
    p = st["panels"][0]
    p.send({"command": "init"})
    hello = p.wait("hello"); offer = p.wait("offer")
    data = os.path.join(tmp, "data"); os.makedirs(data)
    winh = "C:\\Users\\Dragg\\"
    for f in rec["files"]:
        f["path"] = winh + os.path.relpath(f["path"], home).replace("/", "\\")
    rec["folder"] = winh + "Downloads"
    state["opened"] = None
    for name, obj in (("state.json", state), ("recent.json", rec), ("an_p1s.json", an_p1s), ("an_kobra.json", an_kobra),
                      ("an_mini.json", an_mini), ("an_mono.json", an_mono), ("rigs.json", rigs), ("hello.json", hello),
                      ("offer.json", offer)):
        json.dump(obj, open(os.path.join(data, name), "w"))
    open(os.path.join(tmp, "page.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(tmp, "panel.html"), "w", encoding="utf-8").write(p.k["html"])
    return tmp, data


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="mange3mf_070_")
    langs = sys.argv[2:] or ["fr", "en"]
    os.makedirs(out, exist_ok=True)
    for lang in langs:
        tmp, data = prepare(lang)
        subprocess.run(["node", os.path.join(UI, "render_070.js"), os.path.join(tmp, "page.html"), os.path.join(tmp, "panel.html"),
                        data, os.path.join(out, lang)], check=True, cwd=UI)
        print("0.7.0 (%s) : captures dans %s" % (lang, os.path.join(out, lang)))
