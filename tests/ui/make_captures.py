"""Fabrique les captures de docs/captures (francais) et docs/captures/en (anglais) : donnees reelles du
plugin (faux OrcaSlicer) + rendu Chrome.
Usage : python tests/ui/make_captures.py   (necessite Node, playwright-core installe ici, Chrome, Pillow)."""
import base64, importlib, io, json, os, shutil, subprocess, sys, tempfile, time
UI = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.dirname(UI)
ROOT = os.path.dirname(TESTS)
sys.path.insert(0, TESTS)
from common import sample, variant_template
import fake_orca, make_samples


def captures(lang, out):
    tmp = tempfile.mkdtemp()
    home = os.path.join(tmp, "home"); dl = os.path.join(home, "Downloads"); os.makedirs(dl)
    os.environ["HOME"] = home; os.environ["USERPROFILE"] = home
    shutil.copy(sample("sample_dragon.3mf"), os.path.join(dl, "cute baby dragon.3mf"))
    make_samples.bambu_multiplate(os.path.join(dl, "Capsulas Pokeballs GachaPop.3mf"), plate_label={"fr": "Plaque", "en": "Plate"}[lang])
    # un projet PrusaSlicer (0.6.0), plus ancien : en bas de la liste
    prusa = make_samples.prusa_3mf(os.path.join(dl, {"fr": "Dragon articulé (Printables).3mf", "en": "Articulated dragon (Printables).3mf"}[lang]))
    os.utime(prusa, (time.time() - 3 * 3600, time.time() - 3 * 3600))
    cfg = variant_template().config   # 5 filaments + 1 couleur melangee, comme dans Orca 2.5
    cfg["filament_colour"] = ["#111111", "#FFE11A", "#D32F2F", "#F5F5F5", "#2E7D32", "#808080"]
    cfg["filament_multi_colour"] = list(cfg["filament_colour"])
    cfg["filament_settings_id"] = ["Elegoo PLA", "Snapmaker PLA Basic", "CAILAB PLA", "Anycubic PLA", "Snapmaker PLA", "Melange 1+2"]
    cfg["filament_type"] = ["PLA"] * 6
    cfg["nozzle_volume_type"] = ["High Flow", "High Flow", "Standard", "High Flow"]
    orca, st, cur = fake_orca.install(os.path.join(tmp, "storage"), cfg)
    st["language"] = {"fr": "fr_FR", "en": "en_US"}[lang]     # langue de l'interface d'Orca
    st["presets"] = [fake_orca.FakePreset(n, fake_orca.preset_from(cfg, 0, n, changes=ch)) for n, ch in (
        ("JAYO PETG", {"filament_type": ["PETG"]}), ("JAYO PLA Rose", {"default_filament_colour": ["#FF3EC8"]}),
        ("SUNLU PLA Violet", {"default_filament_colour": ["#7B1FA2"]}), ("Anycubic PLA", {}))]   # Anycubic PLA : aussi dans tes reglages
    sys.modules.pop("mange_3mf_any", None)
    m = importlib.import_module("mange_3mf_any")
    st["plugin"]().register_capabilities()
    tab = st["caps"][0]()
    html = tab.get_ui()
    w = st["page"]
    tab.on_message({"command": "init"}); w.wait("recent")
    tab.on_message({"command": "capture"}); state = w.wait("state", 2)
    assert state["lang"] == lang, state["lang"]
    tab.on_message({"command": "analyze", "path": os.path.join(dl, "Capsulas Pokeballs GachaPop.3mf"), "template": "saved"})
    an = w.wait("analysis")

    # vignettes de plaques dessinees (les exemples ont tous la meme image)
    try:
        from PIL import Image, ImageDraw
        cols = {f["index"]: f["color"] for f in an["filaments"]}
        for p in an["plates"]:
            im = Image.new("RGB", (240, 160), (28, 30, 34)); d = ImageDraw.Draw(im)
            fs = p["filaments"] or [1]
            for k, f in enumerate(fs):
                x = 120 + (k - (len(fs) - 1) / 2) * 62
                c = cols.get(f, "#808080")
                d.ellipse((x - 26, 54, x + 26, 106), fill=c, outline=(200, 200, 200))
            buf = io.BytesIO(); im.save(buf, "PNG")
            p["thumb"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        pass

    files = [{"plates": f["plates"], "slots": [{"src": s["src"], "base": s["base"]} for s in f["slots"]]} for f in an["files"]]
    tab.on_message({"command": "convert", "token": an["token"], "template": "saved", "files": files})
    b = w.wait("built"); tab.on_message({"command": "write", "token": b["token"]}); res = w.wait("result")
    home_win = "C:\\Users\\Dragg\\"
    def winpath(p): return home_win + os.path.relpath(p, home).replace("/", "\\")
    state["opened"] = None
    rec = [p for p in w.posts if p["command"] == "recent"][0]
    for f in rec["files"]: f["path"] = winpath(f["path"])
    rec["folder"] = winpath(dl)
    for f in res["files"]: f["path"] = winpath(f["path"])
    data = os.path.join(tmp, "data"); os.makedirs(data)
    for name, obj in (("state.json", state), ("recent.json", rec), ("analysis.json", an), ("result.json", res)):
        json.dump(obj, open(os.path.join(data, name), "w"))
    open(os.path.join(tmp, "page.html"), "w", encoding="utf-8").write(html)
    os.makedirs(out, exist_ok=True)
    subprocess.run(["node", os.path.join(UI, "render_page.js"), os.path.join(tmp, "page.html"), data, out] + sys.argv[1:], check=True, cwd=UI)
    print("captures (%s) dans %s" % (lang, out))


captures("fr", os.path.join(ROOT, "docs", "captures"))
captures("en", os.path.join(ROOT, "docs", "captures", "en"))
