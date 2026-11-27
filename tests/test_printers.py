"""Mange-3MF 0.7.0 / 0.7.1 : toutes les imprimantes (0.7.1 : Flashforge et d'autres marques verifiees). Les reglages de test sont faits des vrais profils d'imprimante
d'OrcaSlicer (tests/printers_orca.json : modele, buses, plateau, volume de buse...), avec les filaments et le
traitement de l'exemple U1. Les Bambu Lab H3C et P3C ne sont pas encore dans Orca : elles sont imitees."""
import importlib, json, os, shutil, sys, tempfile, zipfile
from common import ok, done, sample, fake_template, plan_of, HERE, ORCA_APP
import fake_orca

tmp = tempfile.mkdtemp()
home = os.path.join(tmp, "home"); dl = os.path.join(home, "Downloads"); os.makedirs(dl)
os.environ["HOME"] = home; os.environ["USERPROFILE"] = home
storage = os.path.join(tmp, "storage")
U1CFG = fake_template().config
orca, st, cur = fake_orca.install(storage, U1CFG)
sys.modules.pop("mange_3mf_any", None)
m = importlib.import_module("mange_3mf_any")

from printer_configs import PRINTERS, AMS, imitation
import printer_configs


def config_for(name, **kw):
    return printer_configs.config_for(m, U1CFG, name, **kw)


def template_for(name, **kw):
    return m.Template(config_for(name, **kw), ORCA_APP, "2.5.1")


def poke():
    return m.Source3MF(open(sample("sample_pokeballs.3mf"), "rb").read(), "pokeballs.3mf")


def project_cfg(data):
    return json.loads(zipfile.ZipFile(__import__("io").BytesIO(data)).read(m.PROJECT_CFG))


print("== les familles, avec les vrais profils d'Orca")
want = {
    "Snapmaker U1 (0.4 nozzle)": ("U1", "tools", 4),
    "Prusa XL 5T 0.4 nozzle": ("XL 5T", "tools", 5),
    "Prusa CORE One INDX 4T HF 0.4 nozzle": ("CORE One INDX 4T", "tools", 4),
    "Prusa CORE One INDX 8T HF 0.4 nozzle": ("CORE One INDX 8T", "tools", 8),
    "Bambu Lab H2D 0.4 nozzle": ("H2D", "multi", 2),
    "Bambu Lab H2C 0.4 nozzle": ("H2C", "multi", 2),
    "Bambu Lab X2D 0.4 nozzle": ("X2D", "multi", 2),
    # 0.7.1 : Flashforge et d'autres marques, toujours avec leurs vrais profils d'Orca
    "Bambu Lab H2D Pro 0.4 nozzle": ("H2D Pro", "multi", 2),
    "Flashforge Creator 5 0.4 nozzle": ("Creator 5", "tools", 4),
    "Flashforge Creator 5 Pro 0.4 nozzle": ("Creator 5 Pro", "tools", 4),
    "Flashforge AD5X 0.4 nozzle": ("AD5X", "box", 1),
    "Flashforge Adventurer 5M Pro 0.4 Nozzle": ("Adventurer 5M Pro", "box", 1),
    "Flashforge Guider4 Pro 0.4 nozzle": ("Guider4 Pro", "box", 1),
    "Flashforge Adventurer 3 Series 0.4 Nozzle": ("Adventurer 3 Series", "multi", 2),   # deux buses dans son profil d'Orca
    "Snapmaker J1 (0.4 nozzle)": ("J1", "tools", 2),
    "Snapmaker Artisan (0.4 nozzle)": ("Artisan", "tools", 2),
    "Snapmaker A350 Dual (0.4 nozzle)": ("A350 Dual", "tools", 2),
    "UltiMaker S5 0.4 nozzle": ("S5", "tools", 2),
    "UltiMaker 2+ 0.4 nozzle": ("UltiMaker 2+", "box", 1),
    "RatRig V-Core 4 IDEX 400 0.4 nozzle": ("V-Core 4 IDEX 400", "tools", 2),
    "RatRig V-Core 4 IDEX 400 COPY MODE 0.4 nozzle": ("V-Core 4 IDEX 400 COPY MODE", "tools", 2),
    "Z-Bolt S300 Dual 0.4 nozzle": ("S300 Dual", "tools", 2),
    "Xplorer IDEX 0.4 nozzle": ("Xplorer IDEX", "tools", 2),
    "Xplorer IQEX 0.4 nozzle": ("Xplorer IQEX", "tools", 4),
    "WonderMaker ZR Ultra 0.4 nozzle": ("ZR Ultra", "tools", 4),
    "Raise3D Pro3 0.4 nozzle (Dual)": ("Pro3", "multi", 2),
    "Elegoo Neptune 2D 0.4 nozzle": ("Neptune 2D", "multi", 2),
    "Sovol SV02 0.4 nozzle": ("SV02", "multi", 2),
    "Creality Hi 0.4 nozzle": ("Hi", "box", 1),
    "Creality K1_CFS-C 0.4 nozzle": ("K1_CFS-C", "box", 1),
    "Qidi X-Plus 4 0.4 nozzle": ("X-Plus 4", "box", 1),
    "Voron 2.4 350 0.4 nozzle": ("Voron 2.4 350", "box", 1),
    "Voron Trident 300 0.4 nozzle": ("Trident 300", "box", 1),
    "Voron 0.1 0.4 nozzle": ("Voron 0.1", "box", 1),
    "Co Print ChromaSet 0.4 nozzle": ("ChromaSet", "box", 1),
    "LH Stinger MMU 0.4 nozzle": ("Stinger MMU", "box", 1),
    "Phrozen Arco 0.4 nozzle": ("Arco", "box", 1),
    "Anker M5C 0.4 nozzle": ("M5C", "box", 1),
}
for name in PRINTERS:
    t = template_for(name)
    short, kind, heads = want.get(name, (None, "box", 1))
    good = t.kind == kind and t.nozzle_count == heads and (short is None or t.short == short)
    good = good and t.head_count == (heads if kind == "tools" else 1) and t.positions == (heads if kind == "tools" else 4)
    good = good and t.capacity == (heads if kind == "tools" else 4) and t.usable()
    ok(good, "%s : %s (%s), %d buse(s), places %d, capacite %d" % (name, t.short, t.kind, t.nozzle_count, t.positions, t.capacity))
shorts = {n: template_for(n).short for n in PRINTERS}
ok(shorts["Bambu Lab P1S 0.4 nozzle"] == "P1S" and shorts["Anycubic Kobra S1 0.4 nozzle"] == "Kobra S1"
   and shorts["Elegoo Centauri Carbon 2 0.4 nozzle"] == "Centauri Carbon 2" and shorts["Prusa MK4S MMU3 0.4 nozzle"] == "MK4S MMU3"
   and shorts["Creality K2 Plus 0.4 nozzle"] == "K2 Plus" and shorts["Qidi Q2 0.4 nozzle"] == "Q2"
   and shorts["Prusa MINI IS 0.4 nozzle" if "Prusa MINI IS 0.4 nozzle" in shorts else "Prusa MINIIS 0.4 nozzle"] == "MINI IS",
   "noms courts : %s" % sorted(set(shorts.values())))
for name in ("Prusa MINI 0.4 nozzle", "Prusa MK4S 0.4 nozzle", "Prusa CORE One 0.4 nozzle", "Bambu Lab A1 mini 0.4 nozzle"):
    t = template_for(name, colors=("#FFFFFF",))
    ok(t.kind == "single" and t.capacity == 1 and t.head_count == 1, "%s avec une bobine : une seule couleur a la fois" % name)
t = template_for("Prusa MK4S MMU3 0.4 nozzle", colors=AMS + ("#1E5BD8",))
ok(t.kind == "box" and t.capacity == 5, "Prusa MK4S MMU3 : 5 emplacements")

print("== Bambu Lab H3C et P3C (pas encore dans Orca) : imitees")
for model, n, semm, kind in (("Bambu Lab H3C", 9, "1", "multi"), ("Bambu Lab P3C", 6, "1", "multi"), ("Bambu Lab H3C", 9, "0", "tools")):
    ex = imitation(model, n, semm)
    cols = tuple("#%02X%02X%02X" % (20 * i, 255 - 20 * i, 90) for i in range(9))
    t = m.Template(config_for(model, colors=cols, extra=ex, maps=[str(i % n + 1) for i in range(9)]), ORCA_APP, "2.5.1")
    src = poke()
    ana = m.analyze(src, t)
    res = m.convert(src, t, plan_of(ana))
    cfg = project_cfg(res[0]["data"])
    nf = len(cfg["filament_colour"])
    ok(t.kind == kind and t.short == model.split()[-1] and t.nozzle_count == n and ana["printer"]["heads"] == n
       and len(cfg["flush_volumes_matrix"]) == n * nf * nf and len(cfg["nozzle_diameter"]) == n
       and res[0]["name"] == "pokeballs - %s-by-Dragg.3mf" % model.split()[-1],
       "%s (%d buses, %s) : %s, %d filaments, purge %d valeurs, %s" % (model, n, kind, t.kind, nf, len(cfg["flush_volumes_matrix"]), res[0]["name"]))
    if kind == "tools":
        ok(nf == 9, "changeur de 9 outils : une case par tete (%d)" % nf)

print("== 0.7.1 : Flashforge et d'autres marques, convertis avec leurs vrais profils d'Orca")
for name, n_heads, nf_want in (("Flashforge AD5X 0.4 nozzle", 1, 4), ("Flashforge Creator 5 Pro 0.4 nozzle", 4, 4),
                               ("Snapmaker J1 (0.4 nozzle)", 2, 3), ("UltiMaker S5 0.4 nozzle", 2, 3),
                               ("Raise3D Pro3 0.4 nozzle (Dual)", 2, 4), ("Creality Hi 0.4 nozzle", 1, 4),
                               ("WonderMaker ZR Ultra 0.4 nozzle", 4, 4)):
    t = template_for(name)
    src = poke()
    ana = m.analyze(src, t)
    res = m.convert(src, t, plan_of(ana))
    cfg = project_cfg(res[0]["data"])
    nf, nn = len(cfg["filament_colour"]), len(cfg["nozzle_diameter"])
    fl = [float(x) for x in cfg["flush_volumes_matrix"]]
    diag = all(fl[z * nf * nf + i * nf + i] == 0 for z in range(nn) for i in range(nf))
    off = all(fl[z * nf * nf + i * nf + j] > 0 for z in range(nn) for i in range(nf) for j in range(nf) if i != j)
    ok(nf == nf_want and nn == t.nozzle_count and len(fl) == nn * nf * nf and ana["printer"]["heads"] == n_heads
       and res[0]["name"] == "pokeballs - %s-by-Dragg.3mf" % t.short and (t.kind == "tools" or (diag and off)),
       "%s (%s) : %d filaments, %d buse(s), purge %d valeurs, %s" % (name, t.kind, nf, nn, len(fl), res[0]["name"]))
t = template_for("Snapmaker J1 (0.4 nozzle)")
ok(t.capacity == 2 and t.head_count == 2 and not t.printer_info()["u1"],
   "Snapmaker J1 (IDEX) : 2 tetes, 2 couleurs a la fois, pas de multiACE (c'est pour la U1)")
ok(m.printer_short("UltiMaker 2+") == "UltiMaker 2+" and m.printer_short("Voron 2.4 350") == "Voron 2.4 350"
   and m.printer_short("Voron Trident 300") == "Trident 300" and m.printer_short("Anycubic 4Max Pro") == "Anycubic 4Max Pro"
   and m.printer_short("Flashforge AD5X") == "AD5X" and m.printer_short("Co Print ChromaSet") == "ChromaSet",
   "noms courts : la marque reste quand le reste commence par un chiffre (UltiMaker 2+, Voron 2.4 350)")

print("== Prereglages systeme d'une autre marque (Orca reglee sur une autre imprimante) : par leur liste d'imprimantes")
from fake_orca import FakePreset, preset_from, orca_serialize


class _Coll:
    def __init__(self, presets): self.p = presets
    def size(self): return len(self.p)
    def preset(self, i): return self.p[i]


def _sys(name, typ, printers):
    raw = preset_from(U1CFG, 0, name, changes={"filament_type": [typ], "filament_vendor": ["Flashforge"]},
                      inherits="Generic %s @System" % typ)
    raw["compatible_printers"] = orca_serialize(printers, True) if printers else ""
    return FakePreset(name, raw, user=False, system=True, compatible=False)


coll = _Coll([_sys("Flashforge PETG Basic @FF C5P", "PETG", ["Flashforge Creator 5 Pro 0.4 nozzle", "Flashforge Creator 5 Pro 0.6 nozzle"]),
              _sys("Flashforge PETG Basic @FF AD5X", "PETG", ["Flashforge AD5X 0.4 nozzle"]),
              _sys("Generic PETG @System", "PETG", [])])
for name, want_names in (("Flashforge Creator 5 Pro 0.4 nozzle", ["Flashforge PETG Basic @FF C5P", "Generic PETG @System"]),
                         ("Flashforge AD5X 0.4 nozzle", ["Flashforge PETG Basic @FF AD5X", "Generic PETG @System"])):
    got = [p.name for p in m._system_presets(coll, template_for(name), False)]
    ok(got == want_names, "%s : %s" % (name, got))

print("== P1S (une buse + AMS) : les couleurs vont dans les emplacements de leur bobine")
t = template_for("Bambu Lab P1S 0.4 nozzle")
src = poke()
ana = m.analyze(src, t)
slots = ana["files"][0]["slots"]
ok([s["pad"] for s in slots] == [False, True, False, False] and [s.get("color") for s in slots if not s["pad"]] == ["#FFFFFF", "#FF0000", "#000000"],
   "blanc en 1, jaune libre en 2, rouge en 3, noir en 4 : %s" % [(s["n"], s.get("color"), s["pad"]) for s in slots])
ok(ana["printer"]["kind"] == "box" and ana["printer"]["capacity"] == 4 and ana["printer"]["short"] == "P1S" and ana["heads"] == 1,
   "analyse : imprimante %s" % ana["printer"])
res = m.convert(src, t, plan_of(ana))
cfg = project_cfg(res[0]["data"])
ok(res[0]["name"] == "pokeballs - P1S-by-Dragg.3mf", "nom : %s" % res[0]["name"])
ok(cfg["printer_model"] == "Bambu Lab P1S" and cfg["nozzle_diameter"] == ["0.4"] and cfg["single_extruder_multi_material"] == "1",
   "projet pour la P1S : une buse")
mat, cols = cfg["flush_volumes_matrix"], cfg["filament_colour"]
mins = m.min_flush_volumes(cfg, 0, 4)
ok(mins == [107] * 4, "purge minimale : le volume de la buse de la P1S (%s)" % mins)
kept = all(mat[i * 4 + j] == "100" for i in (0, 1, 3) for j in (0, 1, 3) if i != j)
calc = all(mat[i * 4 + j] == str(m.flush_volume(cols[i], cols[j], 107)) for i in range(4) for j in range(4) if i != j and 2 in (i, j))
ok(kept and calc and all(mat[i * 5] == "0" for i in range(4)),
   "purge : la tienne entre tes bobines restees en place, calculee comme Orca pour le rouge du modele (%s)" % mat)
ok(int(mat[3 * 4 + 2]) > int(mat[2 * 4 + 3]), "purge : plus pour passer du noir au rouge que du rouge au noir (%s > %s)" % (mat[14], mat[11]))
ok(m.flush_volume("#000000", "#FFFFFF") > m.flush_volume("#FFFFFF", "#000000") > 0 and m.flush_volume("#123456", "#123456") == 60
   and m.flush_volume("#FFFFFF00", "#FFFFFF") == 60, "formule d'Orca : noir -> blanc > blanc -> noir, meme couleur 60, transparent = blanc")
t2 = template_for("Bambu Lab P1S 0.4 nozzle")
t2.config["filament_is_support"] = ["0", "1", "0", "0"]
res2 = m.convert(src, t2, plan_of(m.analyze(src, t2)))
mat2 = project_cfg(res2[0]["data"])["flush_volumes_matrix"]
ok(mat2[2 * 4 + 1] == "230" and int(mat2[1 * 4 + 2]) >= 700, "filament de support : 230 vers lui, au moins 700 depuis lui (%s, %s)" % (mat2[9], mat2[6]))

print("== peu d'emplacements : la suite apres")
t = template_for("Anycubic Kobra S1 0.4 nozzle", colors=("#000000", "#FFFFFF"))
ana = m.analyze(poke(), t)
slots = ana["files"][0]["slots"]
ok([s.get("color") for s in slots] == ["#000000", "#FFFFFF", "#FF0000"] and not any(s["pad"] for s in slots),
   "Kobra S1 (2 bobines : noir, blanc) : noir 1, blanc 2, rouge 3 (%s)" % [s.get("color") for s in slots])
ok(ana["printer"]["capacity"] == 2, "capacite 2 : l'onglet previent (3 couleurs)")

print("== H2D (deux buses) : buse prevue de chaque emplacement, purge par buse")
t = template_for("Bambu Lab H2D 0.4 nozzle", maps=["1", "1", "2", "2"])
src = poke()
ana = m.analyze(src, t)
res = m.convert(src, t, plan_of(ana))
cfg = project_cfg(res[0]["data"])
ok(cfg["filament_map"] == ["1", "1", "2", "2"] and len(cfg["flush_volumes_matrix"]) == 32, "filament_map %s, purge 2 x 4 x 4" % cfg["filament_map"])
ids, vols = cfg["printer_extruder_id"], cfg["nozzle_volume"]
right = float(vols[[i for i, e in enumerate(ids) if e == "2"][0]])
ok(m.min_flush_volumes(cfg, 1, 4)[0] == int(right) and m.min_flush_volumes(cfg, 0, 4)[0] == int(float(vols[0])),
   "purge minimale par buse (volumes par variante d'Orca 2.5) : %s / %s" % (m.min_flush_volumes(cfg, 0, 1), m.min_flush_volumes(cfg, 1, 1)))
mat, cols = cfg["flush_volumes_matrix"], cfg["filament_colour"]
ok(mat[16 + 3 * 4 + 2] == str(m.flush_volume(cols[3], cols[2], int(right))), "purge de la buse droite calculee avec son volume")
s = t.summary()
ok(s["kind"] == "multi" and s["heads"] == 2 and s["maps"] == ["1", "1", "2", "2"] and s["short"] == "H2D", "resume pour l'onglet : %s" % {k: s[k] for k in ("kind", "heads", "maps", "short")})

print("== changeurs d'outils Prusa : une case par tete")
for name, n in (("Prusa XL 5T 0.4 nozzle", 5), ("Prusa CORE One INDX 8T HF 0.4 nozzle", 8)):
    cols = AMS + ("#1E5BD8", "#2E7D32", "#8E24AA", "#F57C00")[:n - 4]
    t = template_for(name, colors=cols)
    src = poke()
    ana = m.analyze(src, t)
    slots = ana["files"][0]["slots"]
    res = m.convert(src, t, plan_of(ana))
    cfg = project_cfg(res[0]["data"])
    ok(len(slots) == n and sum(1 for s in slots if s["pad"]) == n - 3 and len(cfg["filament_colour"]) == n and cfg["flush_volumes_matrix"][:2] == ["0", "100"],
       "%s : %d cases dont %d libres, purge gardee comme la U1" % (t.short, len(slots), n - 3))

print("== une seule bobine : « Tout en une couleur »")
t = template_for("Prusa MINI 0.4 nozzle", colors=("#2E7D32",))
src = poke()
ana = m.analyze(src, t)
ok(len(ana["files"][0]["slots"]) == 3 and ana["printer"]["kind"] == "single" and ana["printer"]["capacity"] == 1 and not ana["one_color"],
   "sans l'option : 3 filaments (l'onglet propose « Tout en une couleur »)")
ana = m.analyze(src, t, one_color=True)
slots = ana["files"][0]["slots"]
ok(len(slots) == 1 and slots[0]["merged"] == 3 and len(slots[0]["src"]) == 3 and ana["one_color"] and slots[0]["auto"] is None,
   "avec : une case pour les 3 couleurs (%s)" % slots)
res = m.convert(src, t, plan_of(ana))
cfg = project_cfg(res[0]["data"])
z = zipfile.ZipFile(__import__("io").BytesIO(res[0]["data"]))
paint = set()
for n_ in z.namelist():
    if n_.endswith(".model"):
        txt = z.read(n_).decode("utf-8", "replace")
        for mm in __import__("re").finditer(r'(?:paint_color|slic3rpe:mmu_segmentation)="([^"]*)"', txt):
            paint |= m.paint_leaf_states(mm.group(1))
mcfg = z.read(m.MODEL_CFG).decode("utf-8")
ext = set(__import__("re").findall(r'key="extruder" value="(\d+)"', mcfg))
ok(cfg["filament_colour"] == ["#2E7D32"] and paint <= {0, 1} and ext <= {"1"} and res[0]["name"] == "pokeballs - MINI-by-Dragg.3mf",
   "projet : 1 filament (ta bobine verte), peinture %s, pieces %s, %s" % (sorted(paint), sorted(ext), res[0]["name"]))
ana = m.analyze(src, t, one_color=True)
pl = plan_of(ana)
pl[0]["slots"][0]["color"] = "#FFD600"
res = m.convert(src, t, pl)
ok(project_cfg(res[0]["data"])["filament_colour"] == ["#FFD600"], "couleur choisie pour la bobine unique")

print("== reglages memorises par imprimante")
ok(m.load_saved_template() is None and m.saved_templates() == ([], None), "rien au debut")
old = m.Template(dict(U1CFG), ORCA_APP, "2.5.1", captured_at=1000.0)
os.makedirs(storage, exist_ok=True)
json.dump(old.to_json(), open(os.path.join(storage, "reglages_memorises.json"), "w"))
lst, target = m.saved_templates()
ok(len(lst) == 1 and target == "snapmaker u1" and m.load_saved_template().short == "U1", "fichier d'une version 0.6 relu : la U1")
p1s = template_for("Bambu Lab P1S 0.4 nozzle")
p1s.captured_at = 2000.0
m.save_template(p1s)
lst, target = m.saved_templates()
ok([k for k, _t in lst] == ["bambu lab p1s", "snapmaker u1"] and target == "bambu lab p1s" and m.load_saved_template().short == "P1S",
   "P1S memorisee en plus, et choisie : %s" % [k for k, _t in lst])
raw = json.load(open(os.path.join(storage, "reglages_memorises.json")))
ok(raw.get("v") == 2 and raw["config"]["printer_model"] == "Bambu Lab P1S" and set(raw["printers"]) == {"bambu lab p1s", "snapmaker u1"},
   "fichier : les deux imprimantes, et celle choisie en tete (une version 0.6 la relit)")
ok(m.set_target("snapmaker u1") and m.load_saved_template().short == "U1" and not m.set_target("prusa xl"), "choisir la U1 ; pas une imprimante absente")
again = template_for("Bambu Lab P1S 0.4 nozzle", colors=("#000000",) * 4)
m.save_template(again)
lst, target = m.saved_templates()
ok(len(lst) == 2 and m.load_saved_template("bambu lab p1s").slot_colors == ["#000000"] * 4, "memoriser la P1S a nouveau remplace ses reglages")
ok(m.forget_printer("bambu lab p1s") and m.saved_templates()[1] == "snapmaker u1" and len(m.saved_templates()[0]) == 1,
   "oublier la P1S : la U1 reste, choisie")
ok(m.forget_printer("snapmaker u1") and m.load_saved_template() is None and not os.path.exists(os.path.join(storage, "reglages_memorises.json")),
   "oublier la derniere : plus de reglages")

print("== a convertir ou non, selon ton imprimante")
cases = [
    ({"app": "BambuStudio-02.08.01.55", "orca_tag": "2.5.1", "printer": "Bambu Lab P1S"}, "Bambu Lab P1S", False),
    ({"app": "BambuStudio-02.03.01.51", "orca_tag": "", "printer": "Bambu Lab P1S"}, "Bambu Lab P1S", False),
    ({"app": "BambuStudio-02.03.01.51", "orca_tag": "", "printer": "Bambu Lab X1 Carbon"}, "Bambu Lab P1S", True),
    ({"app": "BambuStudio-02.03.01.51", "orca_tag": "", "printer": "Snapmaker U1"}, "Snapmaker U1", True),
    ({"app": "Snapmaker_Orca-2.4.2", "orca_tag": "", "printer": "Snapmaker U1"}, "Snapmaker U1", True),
    ({"app": "BambuStudio-02.08.01.55", "orca_tag": "2.5.1", "printer": "Snapmaker U1"}, "Bambu Lab P1S", True),
    ({"app": "BambuStudio-02.08.01.55", "orca_tag": "2.5.1", "printer": "Prusa XL 5T"}, "Prusa XL 5T", False),
    ({"app": "PrusaSlicer-2.8.1", "orca_tag": "", "printer": "Prusa XL 5T"}, "Prusa XL 5T", True),
    ({"app": "BambuStudio-02.08.01.55", "orca_tag": "2.5.1", "printer": "Bambu Lab X1 Carbon"}, "", False),
    ({"app": "BambuStudio-02.03.01.51", "orca_tag": "", "printer": "Bambu Lab X1 Carbon"}, "", True),
]
for info, target, todo in cases:
    ok(m.needs_conversion(info, target) == todo, "%s (%s) pour %s : %s" % (info["app"], info["printer"], target or "personne",
                                                                          "a convertir" if todo else "pret"))

print("== noms des fichiers convertis")
fake = m.Source3MF(open(sample("sample_pokeballs.3mf"), "rb").read(), "x.3mf")
for name, tag, want_ in (("Dragon - U1-by-Dragg.3mf", "P1S-by-Dragg", "Dragon - P1S-by-Dragg.3mf"),
                         ("Dragon - P1S-by-Dragg.3mf", "U1-by-Dragg", "Dragon - U1-by-Dragg.3mf"),
                         ("Dragon - X-Plus-by-Dragg.3mf", "Kobra S1-by-Dragg", "Dragon - Kobra S1-by-Dragg.3mf"),
                         ("Dragon - U1.3mf", "P1S-by-Dragg", "Dragon - P1S-by-Dragg.3mf"),
                         ("Moi - mon dragon.3mf", "P1S-by-Dragg", "Moi - mon dragon - P1S-by-Dragg.3mf")):
    fake.name = name
    got = m.output_name(fake, [], False, tag)
    ok(got == want_, "%s -> %s" % (name, got))
fake.name = "Dragon - K2 Plus-by-Dragg - plaque 2.3mf"
ok(m.output_name(fake, [], False, "XL 5T-by-Dragg") == "Dragon - XL 5T-by-Dragg.3mf", "plaque d'une conversion d'avant retiree aussi")
ok(m.out_tag(template_for("Prusa CORE One INDX 8T HF 0.4 nozzle")) == "CORE One INDX 8T-by-Dragg" and m.out_tag(None) == "U1-by-Dragg",
   "signature avec le nom de l'imprimante")

print("== profils d'Orca faits pour ton imprimante")
p1s = template_for("Bambu Lab P1S 0.4 nozzle")
ok(m._for_printer("Generic PLA @BBL P1S", p1s) and not m._for_printer("Bambu PLA Basic @BBL X1C", p1s) and not m._for_printer("Generic PLA", p1s),
   "« @BBL P1S » oui, « @BBL X1C » non")
ok(m._for_printer("Snapmaker PLA @U1", template_for("Snapmaker U1 (0.4 nozzle)")), "« @U1 » pour la U1")
ok(m._for_printer("Anycubic PLA @Anycubic Kobra S1 0.4 nozzle", template_for("Anycubic Kobra S1 0.4 nozzle")), "« @Anycubic Kobra S1 »")

print("== dans le faux Orca : deux imprimantes, l'une puis l'autre")


def nxt(cmd, timeout=60):
    """Prochain message cmd envoye a la page apres ceux deja recus."""
    n = sum(1 for p in w.posts if p.get("command") == cmd)
    return lambda: w.wait(cmd, n + 1, timeout=timeout)
st["plugin"]().register_capabilities()
tab = st["caps"][0]()
w = st["page"]
shutil.copy(sample("sample_pokeballs.3mf"), os.path.join(dl, "pokeballs.3mf"))
tab.on_message({"command": "init"})
state = w.wait("state")
ok(state["saved"] is None and state["printers"] == [] and state["current"]["kind"] == "tools", "rien de memorise ; Orca est sur la U1")
tab.on_message({"command": "capture"})
state = w.wait("state", 2)
ok(state["target"] == "snapmaker u1" and [p["short"] for p in state["printers"]] == ["U1"] and state["cap"] == "Réglages de ta U1 mémorisés.",
   "U1 memorisee : %s" % state["cap"])
cur.clear(); cur.update(config_for("Bambu Lab P1S 0.4 nozzle"))
tab.on_message({"command": "capture"})
state = w.wait("state", 3)
ok(state["target"] == "bambu lab p1s" and sorted(p["short"] for p in state["printers"]) == ["P1S", "U1"] and state["saved"]["short"] == "P1S"
   and state["saved"]["kind"] == "box", "P1S memorisee en plus, choisie : %s" % [(p["short"], p["target"]) for p in state["printers"]])
rec = w.wait("recent", 3)
ok(any(f["name"] == "pokeballs.3mf" and f["todo"] for f in rec["files"]), "Telechargements revus pour la P1S")
tab.on_message({"command": "analyze", "path": os.path.join(dl, "pokeballs.3mf"), "template": "saved"})
an = w.wait("analysis")
ok(an["printer"]["short"] == "P1S" and an["files"][0]["name"] == "pokeballs - P1S-by-Dragg.3mf", "analyse pour la P1S : %s" % an["files"][0]["name"])
tab.on_message({"command": "target", "key": "snapmaker u1", "token": an["token"]})
state = w.wait("state", 4)
an2 = w.wait("analysis", 2)
ok(state["target"] == "snapmaker u1" and an2["printer"]["short"] == "U1" and an2["files"][0]["name"] == "pokeballs - U1-by-Dragg.3mf"
   and an2["heads"] == 4, "choisir la U1 : l'analyse est refaite pour elle (%s)" % an2["files"][0]["name"])
tab.on_message({"command": "convert", "token": an2["token"], "template": "saved", "files": plan_of(an2)})
w.wait("built")
tab.on_message({"command": "write", "token": an2["token"]})
r = w.wait("result")
ok(r["files"][0]["name"] == "pokeballs - U1-by-Dragg.3mf" and os.path.isfile(r["files"][0]["path"]), "fichier ecrit pour la U1")
cfgw = json.loads(zipfile.ZipFile(r["files"][0]["path"]).read(m.PROJECT_CFG))
ok(cfgw["printer_model"] == "Snapmaker U1" and len(cfgw["nozzle_diameter"]) == 4, "avec les reglages de la U1")
nx = nxt("state")
tab.on_message({"command": "forget_printer", "key": "bambu lab p1s"})
state = nx()
ok([p["short"] for p in state["printers"]] == ["U1"] and state["target"] == "snapmaker u1", "P1S oubliee")
cur.clear(); cur.update(config_for("Prusa MINI 0.4 nozzle", colors=("#2E7D32",)))
tab.on_message({"command": "analyze", "path": os.path.join(dl, "pokeballs.3mf"), "template": "current", "one_color": True})
an3 = w.wait("analysis", 3)
ok(an3["printer"]["kind"] == "single" and an3["one_color"] and len(an3["files"][0]["slots"]) == 1 and not an3["not_ready"],
   "reglages actuels d'Orca (Prusa MINI), « Tout en une couleur » : une case")
tab.on_message({"command": "replan", "token": an3["token"], "one_color": False})
an4 = w.wait("analysis", 4)
ok(not an4["one_color"] and len(an4["files"][0]["slots"]) == 3, "option decochee : 3 cases")
cur.clear(); cur.update(dict(U1CFG, printer_technology="SLA"))
nx = nxt("state", timeout=3)
tab.on_message({"command": "capture"})
err = None
try:
    nx()
except AssertionError as e:
    err = str(e)
ok(err is not None and "filament" in err, "imprimante resine refusee : %s" % err)

done()
