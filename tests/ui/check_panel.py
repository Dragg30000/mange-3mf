"""Verifie le panneau de Preparer dans Chrome : messages reels du plugin (faux OrcaSlicer 2.5.1 avec
create_dock_panel), puis rendu et gestes par render_panel.js. Une capture par ecran dans le dossier donne.
Usage : python tests/ui/check_panel.py [dossier_captures]   (Node, playwright-core installe ici, Chrome)."""
import importlib, json, os, shutil, subprocess, sys, tempfile
UI = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.dirname(UI)
sys.path.insert(0, TESTS)
from common import sample, variant_template
import fake_orca, make_samples


def prepare(lang, name="Candy cane.3mf"):
    """Fait tourner le plugin dans un faux OrcaSlicer 2.5.1 (3MF Bambu ouvert, mange dans le panneau, plan venu de
    l'onglet, conversion) et garde ses vrais messages. Rend (page du panneau, dossier des messages)."""
    tmp = tempfile.mkdtemp()
    home = os.path.join(tmp, "home"); dl = os.path.join(home, "Downloads"); os.makedirs(dl)
    os.environ["HOME"] = home; os.environ["USERPROFILE"] = home
    renne = make_samples.bambu_multiplate(os.path.join(dl, name), plate_count=1, paint_obj8=False,
                                          part_ext={k: [3, 2, 3, 2] for k in ("5", "6", "7", "8", "9", "10")},
                                          printer="Bambu Lab H2C")
    cfg = variant_template().config   # les reglages des captures de l'onglet
    cfg["filament_colour"] = ["#111111", "#FFE11A", "#D32F2F", "#F5F5F5", "#2E7D32", "#808080"]
    cfg["filament_multi_colour"] = list(cfg["filament_colour"])
    cfg["filament_settings_id"] = ["Elegoo PLA", "Snapmaker PLA Basic", "CAILAB PLA", "Anycubic PLA", "Snapmaker PLA", "Melange 1+2"]
    cfg["filament_type"] = ["PLA"] * 6
    orca, st, cur = fake_orca.install(os.path.join(tmp, "storage"), cfg, dock=True)
    st["language"] = {"fr": "fr_FR", "en": "en_US"}[lang]
    st["presets"] = [fake_orca.FakePreset(n, fake_orca.preset_from(cfg, 0, n, changes=ch)) for n, ch in (
        ("JAYO PETG", {"filament_type": ["PETG"]}), ("JAYO PLA Rose", {"default_filament_colour": ["#FF3EC8"]}))]
    sys.modules.pop("mange_3mf_any", None)
    m = importlib.import_module("mange_3mf_any")
    st["plugin"]().register_capabilities()
    tab = st["caps"][0]()
    tab.get_ui()
    w = st["page"]
    tab.on_message({"command": "init"}); w.wait("recent")
    tab.on_message({"command": "capture"}); w.wait("state", 2)
    tab.on_lifecycle_event("ProjectOpened", type("C", (), {"name": renne})())
    p = st["panels"][0]
    p.send({"command": "init"})
    hello, offer = p.wait("hello"), p.wait("offer")
    assert hello["lang"] == lang, hello
    p.send({"command": "eat"})
    prog, an = p.wait("progress"), p.wait("analysis")
    # ce que l'onglet renverrait apres un changement : autre profil et couleur pour la 1re couleur du modele,
    # une couleur en plus avec un de tes prereglages
    files = [{"plates": f["plates"], "slots": [{"src": s["src"], "base": s["base"], "color": None, "extra": False}
                                               for s in f["slots"]]} for f in an["files"]]
    real = next(i for i, s in enumerate(an["files"][0]["slots"]) if not s["pad"])
    rose = next(i for i, pr in enumerate(an["profiles"]) if pr["name"] == "JAYO PLA Rose")
    petg = next(i for i, pr in enumerate(an["profiles"]) if pr["name"] == "JAYO PETG")
    files[0]["slots"][real]["base"] = petg
    files[0]["slots"][real]["color"] = "#7B1FA2"
    files[0]["slots"].append({"src": [], "base": rose, "color": "#FF3EC8", "extra": True})
    tab.on_message({"command": "plan", "token": an["token"], "files": files})
    plan = p.wait("plan")
    p.send({"command": "convert", "token": an["token"], "files": plan["files"]})
    b = p.wait("built"); p.send({"command": "write", "token": b["token"]}); res = p.wait("result")
    for f in res["files"]:
        f["path"] = "C:\\Users\\Dragg\\" + os.path.relpath(f["path"], home).replace("/", "\\").replace("Downloads", {"fr": "Téléchargements", "en": "Downloads"}[lang])
    data = os.path.join(tmp, "data"); os.makedirs(data)
    for name, obj in (("hello.json", hello), ("offer.json", offer), ("progress.json", prog), ("analysis.json", an),
                      ("plan.json", plan), ("result.json", res), ("real.json", {"real": real, "petg": petg, "rose": rose})):
        json.dump(obj, open(os.path.join(data, name), "w"))
    page = os.path.join(tmp, "panel.html")
    open(page, "w", encoding="utf-8").write(p.k["html"])
    return page, data


def run(lang, out):
    page, data = prepare(lang)
    os.makedirs(out, exist_ok=True)
    subprocess.run(["node", os.path.join(UI, "render_panel.js"), page, data, out], check=True, cwd=UI)
    print("panneau (%s) : captures dans %s" % (lang, out))


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "mange3mf_panneau")
    run("fr", os.path.join(base, "fr"))
    run("en", os.path.join(base, "en"))
