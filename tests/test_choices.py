"""Memoire des choix, profils d'Orca pour une matiere qui te manque, supports de l'auteur au choix (0.6.0),
dans un faux OrcaSlicer (onglet)."""
import importlib, io, json, os, sys, tempfile, zipfile
from common import ok, done, fake_template
import fake_orca, make_samples
from fake_orca import FakePreset, preset_from, orca_serialize

tmp = tempfile.mkdtemp()
home = os.path.join(tmp, "home"); dl = os.path.join(home, "Downloads"); os.makedirs(dl)
os.environ["HOME"] = home; os.environ["USERPROFILE"] = home
storage = os.path.join(tmp, "storage")


def with_config(path, **changes):
    """Reglages du projet changes (matiere d'un filament, supports...)."""
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    cfg = json.loads(files["Metadata/project_settings.config"])
    cfg.update(changes)
    files["Metadata/project_settings.config"] = json.dumps(cfg).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)
    return path


src_path = make_samples.bambu_multiplate(os.path.join(dl, "Pokeballs.3mf"))
types_ = ["PLA"] * 7
types_[2] = "PETG"                                   # la 3e couleur (rouge) est du PETG
with_config(src_path, filament_type=types_, enable_support="1", support_type="normal(auto)", support_filament="5",
            support_interface_filament="0", support_threshold_angle="35")
tcfg = fake_template().config
tcfg["enable_support"] = "0"
tcfg["inherits_group"] = [""] + ["Generic PLA @U1"] * 4 + [""]     # [traitement, filaments..., imprimante]
orca, st, cur = fake_orca.install(storage, tcfg)
st["printer"] = tcfg["printer_settings_id"]


def system(name, slot, typ, printers, compatible=True, temp="240"):
    raw = preset_from(tcfg, slot, name, changes={"filament_type": [typ], "nozzle_temperature": [temp, temp]},
                      inherits="Generic %s @System" % typ)
    raw["compatible_printers"] = orca_serialize(printers, True) if printers else ""
    return FakePreset(name, raw, user=False, system=True, compatible=compatible)


st["presets"] = [
    FakePreset("PLA Rose", preset_from(tcfg, 0, "PLA Rose", changes={"default_filament_colour": ["#FF3EC8"]}), user=True),
    system("Generic PETG @System", 0, "PETG", [], temp="235"),
    system("Bambu PETG Basic @BBL X1C", 0, "PETG", ["Bambu Lab X1 Carbon 0.4 nozzle"], compatible=False),
    system("Generic PETG @U1 0.4 nozzle", 0, "PETG", ["Snapmaker U1 (0.4 nozzle)"], temp="245"),
    system("Generic PLA @U1 0.4 nozzle", 0, "PLA", ["Snapmaker U1 (0.4 nozzle)"]),
    FakePreset("- Default Filament -", {}, user=False, default=True),
]
sys.modules.pop("mange_3mf_any", None)
m = importlib.import_module("mange_3mf_any")
st["plugin"]().register_capabilities()
tab = st["caps"][0]()
w = st["page"]


def count(cmd):
    return len([p for p in w.posts if p["command"] == cmd])


def plan(an):
    return [{"plates": f["plates"], "slots": [{"src": s["src"], "base": s["base"]} for s in f["slots"]]} for f in an["files"]]


def convert(an, files=None):
    n_b, n_r = count("built"), count("result")
    tab.on_message({"command": "convert", "token": an["token"], "template": "saved", "files": files or plan(an)})
    b = w.wait("built", n_b + 1)
    tab.on_message({"command": "write", "token": b["token"]})
    r = w.wait("result", n_r + 1)
    return [m.Source3MF(open(f["path"], "rb").read(), f["name"]) for f in r["files"]]


def analyze():
    n = count("analysis")
    tab.on_message({"command": "analyze", "path": src_path, "template": "saved"})
    return w.wait("analysis", n + 1)


def slot_of(an, src_index):
    return next(s for s in an["files"][0]["slots"] if s["src"] and s["src"][0] == src_index)


tab.on_message({"command": "init"})
w.wait("state")
tab.on_message({"command": "capture"})
state = w.wait("state", 2)
ok(state["choices"] == 0, "rien en memoire au depart")

print("== profils d'Orca pour une matiere qui te manque (PETG)")
an = analyze()
groups = [(p["name"], p["group"]) for p in an["profiles"]]
system_ = [n for n, g in groups if g == "system"]
ok(system_[:2] == ["Generic PETG @U1 0.4 nozzle", "Generic PETG @System"] and "Bambu PETG Basic @BBL X1C" not in system_
   and "Generic PLA @U1 0.4 nozzle" not in system_,
   "profils systeme de la U1 pour le PETG seulement, celui de la U1 d'abord : %s" % system_)
red = slot_of(an, 3)
ok(an["profiles"][red["base"]]["name"] == "Generic PETG @U1 0.4 nozzle", "le rouge en PETG prend « Generic PETG @U1 0.4 nozzle »")
ok(any("Generic PETG @U1 0.4 nozzle" in w_ and "PETG" in w_ for w_ in an["warnings"]), "alerte : %s" % [x for x in an["warnings"] if "PETG" in x])
outs = convert(an)
cfg = outs[0].config
i = cfg["filament_settings_id"].index("Generic PETG @U1 0.4 nozzle")
ok(cfg["filament_type"][i] == "PETG", "projet converti : filament %d = Generic PETG @U1 0.4 nozzle (PETG)" % (i + 1))
temps = cfg["nozzle_temperature"]
ok("245" in [temps[j] for j, fi in enumerate(cfg.get("filament_self_index", [])) if int(fi) == i + 1] or temps[i] == "245",
   "  ses valeurs lues en entier a la conversion (245 °C)")
ok(cfg["inherits_group"][1 + i] == "" and cfg["inherits_group"][1] == "Generic PLA @U1",
   "  profil systeme : pas de parent ecrit (%s)" % cfg["inherits_group"])

print("== memoire des choix")
an = analyze()
blue = slot_of(an, 4)
other = next(j for j in range(4) if j != blue["base"])
files = plan(an)
next(s for s in files[0]["slots"] if s["src"] == blue["src"])["base"] = other
n_ch = count("choices")
convert(an, files)
ch = w.wait("choices", n_ch + 1)
ok(ch["n"] == 1, "profil change a la main pour le bleu : retenu (%d)" % ch["n"])
saved = json.load(open(os.path.join(storage, "choix.json")))["items"]
key = m.choice_key(m.Source3MF(open(src_path, "rb").read(), "x").filament(4))
ok(list(saved) == [key] and saved[key]["name"] == "Mon PLA %d" % (other + 1), "choix.json : %s -> %s" % (key, saved.get(key, {}).get("name")))
an = analyze()
blue2 = slot_of(an, 4)
ok(blue2["base"] == other and blue2["mem"] == other and blue2["auto"] == blue["auto"],
   "analyse suivante : le bleu reprend « Mon PLA %d » (propose d'office : %d)" % (other + 1, blue2["auto"] + 1))
ok(all(s.get("mem") is None for s in an["files"][0]["slots"] if s["src"] != blue["src"]), "  les autres couleurs : profil propose d'office")
tab.on_message({"command": "init"})
ok(w.wait("state", count("state"))["choices"] == 1, "reglages : 1 couleur retenue")
files = plan(an)
next(s for s in files[0]["slots"] if s["src"] == blue["src"])["base"] = blue["auto"]
n_ch = count("choices")
convert(an, files)
ok(w.wait("choices", n_ch + 1)["n"] == 0, "revenir au profil propose d'office : oublie")
files[0]["slots"][0]["base"] = (files[0]["slots"][0]["base"] + 1) % 4
convert(an, files)
n_st = count("state")
tab.on_message({"command": "forget_choices"})
ok(w.wait("state", n_st + 1)["choices"] == 0 and json.load(open(os.path.join(storage, "choix.json")))["items"] == {},
   "« Oublier mes choix » : memoire videe")

print("== memoire : couleurs proches, matieres, taille")
ch = {"PLA|#E53935": {"name": "A", "t": 1}}
ok(m.remembered(ch, {"base": "PLA", "color": "#E53935"}) == "A" and m.remembered(ch, {"base": "PLA", "color": "#E43A36"}) == "A",
   "meme couleur, ou presque")
ok(m.remembered(ch, {"base": "PETG", "color": "#E53935"}) is None and m.remembered(ch, {"base": "PLA", "color": "#1E5BD8"}) is None,
   "autre matiere ou autre couleur : rien")
ok(m.choice_key({"base": "PLA", "color": None}) is None, "couleur inconnue : pas de memoire")
m.save_choices({"PLA|#%06X" % i: {"name": "P", "t": i} for i in range(m.CHOICES_MAX + 5)})
big = m.load_choices()
ok(len(big) == m.CHOICES_MAX and "PLA|#000000" not in big and "PLA|#%06X" % (m.CHOICES_MAX + 4) in big, "au plus %d couleurs, les plus anciennes partent" % m.CHOICES_MAX)
m.save_choices({})

print("== supports de l'auteur, au choix")
an = analyze()
sup = an["supports"]
ok(sup and not sup["keep"] and sup["desc"][0] == "supports normaux" and "support en PLA" in sup["desc"][1],
   "proposes, pas gardes d'office : %s" % sup)
files = plan(an)
pink = next(s for s in files[0]["slots"] if s["src"] == [7])
pink["base"] = 4 + next(j for j, p in enumerate(an["profiles"][4:]) if p["name"] == "PLA Rose")
files[0]["slots"].append({"src": [], "base": 1, "color": "#123456", "extra": True})
tab.on_message({"command": "plan", "token": an["token"], "files": files})
n = count("analysis")
tab.on_message({"command": "replan", "token": an["token"], "template": "saved", "one_per_plate": False, "supports": True})
an2 = w.wait("analysis", n + 1)
ok(an2["kept"] and an2["supports"]["keep"], "coche : nouvelle analyse, supports gardes")
ok(json.load(open(os.path.join(storage, "options.json"))).get("supports") == "model", "choix retenu pour les fois suivantes")
pink2 = next(s for s in an2["files"][0]["slots"] if s["src"] == [7])
extra = [s for s in an2["files"][0]["slots"] if s.get("extra")]
ok(an2["profiles"][pink2["base"]]["name"] == "PLA Rose" and len(extra) == 1 and extra[0]["pick"] == "#123456",
   "tes choix restent : profil change, couleur en plus (%s)" % [(s["base"], s.get("pick")) for s in extra])
outs = convert(an2, [{"plates": f["plates"], "slots": [{"src": s["src"], "base": s["base"], "color": s.get("pick"), "extra": bool(s.get("extra"))}
                                                        for s in f["slots"]]} for f in an2["files"]])
cfg = outs[0].config
new5 = next(s["n"] for s in an2["files"][0]["slots"] if s["src"] == [5])
ok(cfg["enable_support"] == "1" and cfg["support_type"] == "normal(auto)" and cfg["support_filament"] == str(new5)
   and cfg.get("support_threshold_angle") == "35", "converti avec les supports de l'auteur (filament %s)" % cfg["support_filament"])
n = count("analysis")
tab.on_message({"command": "replan", "token": an2["token"], "template": "saved", "one_per_plate": False, "supports": False})
an3 = w.wait("analysis", n + 1)
ok(not an3["supports"]["keep"] and json.load(open(os.path.join(storage, "options.json"))).get("supports") == "mine", "decoche : retenu aussi")
cfg = convert(an3)[0].config
ok(cfg["enable_support"] == "0", "converti avec les supports de tes reglages")
an4 = analyze()
ok(not an4["supports"]["keep"], "fichier suivant : le dernier choix")
done()
