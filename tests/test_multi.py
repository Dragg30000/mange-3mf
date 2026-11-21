"""Projets a plus de 4 couleurs : un seul fichier, un filament par couleur, rien de fusionne."""
import io, os, re, zipfile
from common import ok, done, fake_template, plan_of, OUT
import mange_3mf_any as m
import make_samples

path = make_samples.bambu_multiplate(os.path.join(OUT, "synthetic_x1c_7colors.3mf"))
src = m.Source3MF(open(path, "rb").read(), "Pokeballs X1C.3mf")
tpl = fake_template()
print("== plan 7 couleurs / 6 plaques / plateau 256 -> U1")
ana = m.analyze(src, tpl)
f0 = ana["files"][0]
print("  ", f0["name"], [(s["n"], s.get("name"), s["src"], s["base"]) for s in f0["slots"]])
ok(len(ana["files"]) == 1, "1 seul fichier")
ok(len(f0["slots"]) == 7 and f0["colors"] == 7 and not any(s["pad"] for s in f0["slots"]), "7 couleurs -> 7 filaments")
ok(sorted(i for s in f0["slots"] for i in s["src"]) == [1, 2, 3, 4, 5, 6, 7], "chaque filament d'origine a sa case")
ok(f0["name"] == "Pokeballs X1C - U1.3mf", "nom du fichier : %s" % f0["name"])
ok(all(p["thumb"].startswith("data:image/png") for p in ana["plates"]), "vignettes des plaques")
# les couleurs qui ressemblent aux bobines prennent leurs cases
tcols = tpl.slot_colors
for s in f0["slots"][:4]:
    ok(m.color_distance(s["color"], tcols[s["n"] - 1]) < 25, "case %d : %s sur la bobine %s" % (s["n"], s["name"], m.color_name(tcols[s["n"] - 1])))

res = m.convert(src, tpl, plan_of(ana))
ok(len(res) == 1 and res[0]["filaments"] == 7 and res[0]["colors"] == 7, "1 fichier de 7 filaments")
r = res[0]
mp = r["map"]
dw = 270.0
out = m.Source3MF(r["data"], r["name"])
print("  ->", r["name"], [p.name for p in out.plates], r["report"]["warnings"])
ok(out.kind == "orca" and len(out.plates) == 6, "6 plaques")
ok(not any("fusionn" in w for w in r["report"]["warnings"]), "aucune fusion")
cfg = out.config
cols = [m.norm_color(c) for c in cfg["filament_colour"]]
ok(len(cols) == 7, "7 couleurs dans le projet")
for idx, j in mp.items():
    ok(cols[j - 1] == src.filament(idx)["color"], "  filament %d = couleur d'origine %d (%s)" % (j, idx, m.color_name(cols[j - 1])))
# toutes les listes de reglages de filament ont 7 valeurs
bad = [k for k, v in cfg.items() if isinstance(v, list) and (k in m.FILAMENT_PRESET_KEYS or k.startswith("filament_"))
       and k not in ("filament_self_index",) and len(v) not in (7,)]
ok(not bad, "reglages de filament a 7 valeurs (%s)" % bad[:5])
nz = 1 if not isinstance(cfg.get("flush_multiplier"), list) else len(cfg["flush_multiplier"])
ok(len(cfg["flush_volumes_matrix"]) == 49 * nz and len(cfg["flush_volumes_vector"]) == 14, "purge 7x7")
ok(all(cfg["flush_volumes_matrix"][i * 7 + i] in ("0", "0.0") for i in range(7)), "pas de purge d'un filament vers lui-meme")
names = set(cfg["filament_settings_id"])
ok(names <= set(tpl.slot_names), "profils pris dans les reglages de l'utilisateur %s" % sorted(names))
# chaque plaque convertie : memes couleurs qu'a l'origine
for j, p in enumerate(out.plates):
    orig = next(sp for sp in src.plates if sp.name == p.name)
    want = sorted({src.filament(i)["color"] for i in orig.filaments})
    got = sorted({cols[i - 1] for i in p.filaments})
    ok(want == got, "  plaque %s : couleurs %s" % (p.name, [m.color_name(c) for c in got]))
    cols_n = m.compute_column_count(len(out.plates))
    ox, oy = m.plate_origin(j, cols_n, dw, dw)
    for inst in p.instances:
        b = inst.bbox
        inside = (ox + 0.5 <= b[0] and b[3] <= ox + 270.5 and oy + 1 <= b[1] and b[4] <= oy + 271)
        ok(inside, "  %s dans sa plaque (%.1f..%.1f, %.1f..%.1f)" % (inst.obj.id, b[0] - ox, b[3] - ox, b[1] - oy, b[4] - oy))
        sinst = src.objects[inst.obj.id].instances[0]
        sox, soy = src.plate_origin(orig.index)
        ok(abs((inst.transform[9] - ox) - (sinst.transform[9] - sox) - 7.25) < 0.6, "  decalage x ~ +7 mm")
# coherence des fichiers internes
z = zipfile.ZipFile(io.BytesIO(r["data"]))
ms = z.read(m.MODEL_CFG).decode()
ids_ms = set(re.findall(r'<object id="(\d+)"', ms))
main = z.read(m.MAIN_MODEL).decode()
ids_build = set(re.findall(r'<item objectid="(\d+)"', main))
ok(ids_ms == ids_build, "objets des reglages = objets construits %s" % sorted(ids_build))
ok(len(cfg["wipe_tower_x"]) == len(out.plates), "tour d'essuyage par plaque")
rels = z.read(m.MAIN_RELS).decode()
for t in re.findall(r'Target="/([^"]+)"', rels):
    ok(t in z.namelist(), "relation vers %s presente" % t)
# peinture : etat 7 (magenta) -> filament du magenta
mesh21 = out.mesh(("3D/Objects/bottom_white_1.model", "21"))
ok(mesh21 is not None and mesh21.states == {mp[7]}, "peinture magenta -> filament %d (%s)" % (mp[7], mesh21 and mesh21.states))
o8 = out.objects["8"]
exts = [p.extruder for p in o8.parts]
ok(exts == [mp[2], mp[6], mp[2], mp[6]], "filaments des pieces de l'objet 8 %s" % exts)

print("== une seule plaque a 7 couleurs : rien de fusionne")
path2 = make_samples.bambu_multiplate(os.path.join(OUT, "synthetic_6colors_one_plate.3mf"),
                                      part_ext={"5": [1, 2, 3, 4], "6": [5, 6, 7, 2]}, paint_obj8=False, plate_count=1)
src2 = m.Source3MF(open(path2, "rb").read(), "six.3mf")
print("   filaments plaque 1 :", sorted(src2.plates[0].filaments))
ana2 = m.analyze(src2, tpl)
n2 = len(src2.plates[0].filaments)
ok(len(ana2["files"]) == 1 and ana2["files"][0]["colors"] == n2 and len(ana2["files"][0]["slots"]) == n2,
   "1 fichier, %d filaments" % n2)
res2 = m.convert(src2, tpl, plan_of(ana2))
out2 = m.Source3MF(res2[0]["data"], res2[0]["name"])
ok(len(out2.config["filament_colour"]) == n2 and not any("fusionn" in w for w in res2[0]["report"]["warnings"]),
   "%d couleurs gardees" % n2)

print("== moins de 4 couleurs : Orca garde 4 cases (une par tete)")
path3 = make_samples.bambu_multiplate(os.path.join(OUT, "synthetic_2colors.3mf"),
                                      part_ext={"5": [1, 3, 1, 3], "6": [3, 1, 3, 1]}, paint_obj8=False, plate_count=1)
src3 = m.Source3MF(open(path3, "rb").read(), "deux.3mf")
used3 = sorted(src3.plates[0].filaments)
ana3 = m.analyze(src3, tpl)
f3 = ana3["files"][0]
print("  ", used3, [(s["n"], s.get("name"), s["src"], s["pad"]) for s in f3["slots"]])
ok(len(f3["slots"]) == 4 and f3["colors"] == len({m.color_key(src3.filament(i)) for i in used3}), "4 cases, %d couleurs" % f3["colors"])
pads = [s for s in f3["slots"] if s["pad"]]
ok(all(s["base"] == s["n"] - 1 for s in pads), "cases libres = bobines actuelles")
res3 = m.convert(src3, tpl, plan_of(ana3))
cfg3 = m.Source3MF(res3[0]["data"], res3[0]["name"]).config
for s in pads:
    ok(m.norm_color(cfg3["filament_colour"][s["n"] - 1]) == tpl.slot_colors[s["n"] - 1], "  case %d inchangee" % s["n"])

print("== un fichier par plaque")
ana4 = m.analyze(src, tpl, one_per_plate=True)
ok(len(ana4["files"]) == 6 and all(len(f["plate_ids"]) == 1 for f in ana4["files"]), "6 fichiers")
res4 = m.convert(src, tpl, plan_of(ana4))
for r4 in res4:
    o = m.Source3MF(r4["data"], r4["name"])
    p = o.plates[0]
    orig = next(sp for sp in src.plates if sp.name == p.name)
    ok(len(o.plates) == 1 and r4["colors"] == len(orig.filaments) and r4["filaments"] == max(4, len(orig.filaments)),
       "  %s : %d couleur(s), %d cases" % (r4["name"], r4["colors"], r4["filaments"]))

done()
