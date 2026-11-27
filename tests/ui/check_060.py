"""Verifie dans Chrome les nouveautes de la 0.6.0 (onglet et panneau de Preparer) avec les vrais messages du
plugin (faux OrcaSlicer 2.5.1) : projet PrusaSlicer dans la liste, profil d'Orca pour une matiere qui te
manque, memoire des choix, supports de l'auteur au choix, cinq langues. Enregistre les captures
docs/captures/7_nouveautes.png (francais) et docs/captures/en/7_nouveautes.png (anglais).
Usage : python tests/ui/check_060.py   (Node, playwright-core installe ici, Chrome)."""
import importlib, json, os, subprocess, sys, tempfile, zipfile
UI = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.dirname(UI)
ROOT = os.path.dirname(TESTS)
sys.path.insert(0, TESTS)
from common import variant_template
import fake_orca, make_samples


def with_config(path, **changes):
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    cfg = json.loads(files["Metadata/project_settings.config"])
    cfg.update(changes)
    files["Metadata/project_settings.config"] = json.dumps(cfg).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)


def prepare(lang):
    tmp = tempfile.mkdtemp()
    home = os.path.join(tmp, "home"); dl = os.path.join(home, "Downloads"); os.makedirs(dl)
    os.environ["HOME"] = home; os.environ["USERPROFILE"] = home
    poke = make_samples.bambu_multiplate(os.path.join(dl, "Capsulas Pokeballs GachaPop.3mf"), plate_count=3,
                                         plate_label={"fr": "Plaque", "en": "Plate"}[lang])
    types_ = ["PLA"] * 7
    types_[2] = "PETG"
    with_config(poke, filament_type=types_, enable_support="1", support_type="tree(auto)", support_filament="2",
                support_interface_filament="0")
    make_samples.prusa_3mf(os.path.join(dl, {"fr": "Dragon articulé (Printables).3mf", "en": "Articulated dragon (Printables).3mf"}[lang]))
    cfg = variant_template().config
    cfg["filament_colour"] = ["#111111", "#FFE11A", "#D32F2F", "#F5F5F5", "#2E7D32", "#808080"]
    cfg["filament_multi_colour"] = list(cfg["filament_colour"])
    cfg["filament_settings_id"] = ["Elegoo PLA", "Snapmaker PLA Basic", "CAILAB PLA", "Anycubic PLA", "Snapmaker PLA", "Melange 1+2"]
    cfg["filament_type"] = ["PLA"] * 6
    storage = os.path.join(tmp, "storage")
    orca, st, cur = fake_orca.install(storage, cfg, dock=True)
    st["language"] = {"fr": "fr_FR", "en": "en_US"}[lang]

    def system(name, typ, printers, vendor):
        raw = fake_orca.preset_from(cfg, 0, name, changes={"filament_type": [typ], "filament_vendor": [vendor]},
                                    inherits="Generic %s @System" % typ)
        raw["compatible_printers"] = fake_orca.orca_serialize(printers, True)
        return fake_orca.FakePreset(name, raw, user=False, system=True)
    st["presets"] = [fake_orca.FakePreset(n, fake_orca.preset_from(cfg, 0, n, changes=ch)) for n, ch in (
        ("JAYO PLA Rose", {"default_filament_colour": ["#FF3EC8"]}), ("SUNLU PLA Violet", {"default_filament_colour": ["#7B1FA2"]}))]
    u1 = ["Snapmaker U1 (0.4 nozzle)"]
    st["presets"] += [system("Generic PETG @U1 0.4 nozzle", "PETG", u1, "Generic"), system("Snapmaker PETG @U1", "PETG", u1, "Snapmaker"),
                      system("Generic PETG HF @U1 0.4 nozzle", "PETG", u1, "Generic"),
                      system("Snapmaker PLA SnapSpeed @U1", "PLA", u1, "Snapmaker"), system("Polymaker PolyTerra PLA @U1", "PLA", u1, "Polymaker")]
    sys.modules.pop("mange_3mf_any", None)
    m = importlib.import_module("mange_3mf_any")
    # memoire : le bleu du modele avait pris « SUNLU PLA Violet » la derniere fois
    os.makedirs(storage, exist_ok=True)
    m.save_choices({"PLA|#1E5BD8": {"name": "SUNLU PLA Violet", "t": 1}})
    st["plugin"]().register_capabilities()
    tab = st["caps"][0]()
    html = tab.get_ui()
    w = st["page"]
    tab.on_message({"command": "init"}); rec = w.wait("recent")
    tab.on_message({"command": "capture"}); state = w.wait("state", 2)
    tab.on_message({"command": "analyze", "path": poke, "template": "saved"})
    an = w.wait("analysis")
    tab.on_message({"command": "replan", "token": an["token"], "template": "saved", "one_per_plate": False, "supports": True})
    kept = w.wait("analysis", 2)
    # panneau : le meme 3MF ouvert dans Orca, mange dans le panneau
    tab.on_lifecycle_event("ProjectOpened", type("C", (), {"name": poke})())
    p = st["panels"][0]
    p.send({"command": "init"})
    hello = p.wait("hello"); p.wait("offer")
    p.send({"command": "eat"})
    pan = p.wait("analysis")
    winh = "C:\\Users\\Dragg\\"
    for f in rec["files"]:
        f["path"] = winh + os.path.relpath(f["path"], home).replace("/", "\\")
    rec["folder"] = winh + "Downloads"
    state["opened"] = None
    data = os.path.join(tmp, "data"); os.makedirs(data)
    for name, obj in (("state.json", state), ("recent.json", rec), ("analysis.json", an), ("kept.json", kept),
                      ("hello.json", hello), ("panel_analysis.json", pan)):
        json.dump(obj, open(os.path.join(data, name), "w"))
    open(os.path.join(tmp, "page.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(tmp, "panel.html"), "w", encoding="utf-8").write(p.k["html"])
    return tmp, data


if __name__ == "__main__":
    for lang, out in (("fr", os.path.join(ROOT, "docs", "captures")), ("en", os.path.join(ROOT, "docs", "captures", "en"))):
        tmp, data = prepare(lang)
        subprocess.run(["node", os.path.join(UI, "render_060.js"), os.path.join(tmp, "page.html"), os.path.join(tmp, "panel.html"),
                        data, out] + sys.argv[1:], check=True, cwd=UI)
        print("0.6.0 (%s) : captures dans %s" % (lang, out))
