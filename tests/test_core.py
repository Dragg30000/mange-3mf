"""Tests du coeur : peinture, lecture d'un vrai 3MF MakerWorld, conversion simple."""
import io, re, time, zipfile
from common import ok, done, sample, fake_template, plan_of
import mange_3mf_any as m

# ---------------------------------------------------------------- paint codec
print("== peinture")
ok(m.paint_leaf_states("8") == {2}, "8 -> etat 2")
ok(m.paint_leaf_states("0C") == {3}, "0C -> etat 3")
ok(m.paint_leaf_states("1C") == {4}, "1C -> etat 4")
ok(m.paint_leaf_states("4") == {1}, "4 -> etat 1")
ok(m.remap_paint("8", {2: 3}) == "0C", "2->3 : 8 -> 0C")
ok(m.remap_paint("0C", {3: 1}) == "4", "3->1 : 0C -> 4")
ok(m.remap_paint("1C", {4: 2}) == "8", "4->2 : 1C -> 8")
ok(m.remap_paint("4", {1: 20}) == "2FC", "1->20 : 4 -> 2FC (etat >= 18)")
ok(m.paint_leaf_states("2FC") == {20}, "2FC -> etat 20")
ok(m.paint_leaf_states("ZZ") is None and m.remap_paint("ZZ", {1: 2}) == "ZZ", "chaine illisible gardee")
z = zipfile.ZipFile(sample("sample_dragon.3mf"))
dragon_model = z.read("3D/Objects/character_1_1.model").decode()
uniq = set(re.findall(r'paint_color="([0-9A-F]+)"', dragon_model))
bad = [s for s in uniq if m.remap_paint(s, {1: 1, 2: 2, 3: 3, 4: 4}) != s]
ok(not bad, "identite : %d chaines uniques inchangees (%s)" % (len(uniq), bad[:3]))
perm = {1: 4, 2: 1, 3: 2, 4: 3}
inv = {v: k for k, v in perm.items()}
bad = [s for s in uniq if m.remap_paint(m.remap_paint(s, perm), inv) != s]
ok(not bad, "permutation aller-retour sur toutes les chaines (%s)" % bad[:3])
bad = [s for s in uniq if m.paint_leaf_states(m.remap_paint(s, perm)) != {perm.get(x, x) if x else 0 for x in m.paint_leaf_states(s)}]
ok(not bad, "etats renumerotes = etats d'origine permutes")

# ---------------------------------------------------------------- lecture
print("== lecture dragon")
t0 = time.time()
src = m.Source3MF(open(sample("sample_dragon.3mf"), "rb").read(), "dragon.3mf")
print("   lu en %.2fs" % (time.time() - t0))
ok(src.kind == "bambu", "type bambu (%s)" % src.kind)
ok(len(src.plates) == 1 and src.plates[0].name == "printmon - character", "1 plaque nommee")
ok(src.plates[0].filaments == {1, 2, 3, 4}, "filaments utilises 1-4 (%s)" % src.plates[0].filaments)
mesh = src.mesh(("3D/Objects/character_1_1.model", "1"))
ok(mesh is not None and mesh.triangles == 557360 and mesh.painted == 284475, "maillage %r" % ((mesh.triangles, mesh.painted) if mesh else None,))
ok(mesh.states >= {1, 2, 3, 4}, "etats peints %s" % mesh.states)
inst = src.plates[0].instances[0]
ok(inst.bbox is not None and 0 < inst.bbox[0] < 256 and 0 < inst.bbox[3] < 270, "boite de l'instance %s" % (inst.bbox,))

print("== lecture pokeballs")
srcp = m.Source3MF(open(sample("sample_pokeballs.3mf"), "rb").read(), "pokeballs.3mf")
ok(len(srcp.object_order) == 6 and all(len(o.instances) == 1 for o in srcp.objects.values()), "6 objets")
ok(srcp.plates[0].filaments == {1, 3, 4}, "filaments plaque 1 = 1,3,4 (%s)" % srcp.plates[0].filaments)
ok(all(o.parts and o.parts[0].component for o in srcp.objects.values()), "pieces reliees aux maillages")

# ---------------------------------------------------------------- conversion simple (meme machine)
print("== conversion dragon (4 couleurs, U1 -> U1)")
tpl = fake_template()
ana = m.analyze(src, tpl)
ok(len(ana["files"]) == 1 and len(ana["files"][0]["slots"]) == 4, "1 fichier, 4 filaments")
ok(ana["source"]["colors"] == 4 and ana["files"][0]["colors"] == 4, "4 couleurs")
print("   plan:", [(s["n"], s["name"], s["src"], s["base"]) for s in ana["files"][0]["slots"]])
t0 = time.time()
res = m.convert(src, tpl, plan_of(ana))
print("   converti en %.2fs, %d octets" % (time.time() - t0, len(res[0]["data"])))
mp = res[0]["map"]
out = m.Source3MF(res[0]["data"], res[0]["name"])
ok(out.application == "BambuStudio-02.08.01.55" and out.meta.get("OrcaSlicer") == "2.5.1", "etiquettes d'OrcaSlicer 2.5.1")
ok(out.app_label() == "OrcaSlicer 2.5.1", "affiche comme projet OrcaSlicer : %s" % out.app_label())
ok(out.kind == "orca", "relu comme projet Orca")
cfg = out.config
ok(len(cfg["filament_colour"]) == 4 and len(cfg["filament_settings_id"]) == 4, "4 filaments dans le projet")
for idx, slot in mp.items():
    ok(m.norm_color(cfg["filament_colour"][slot - 1]) == src.filament(int(idx))["color"], "filament %d = couleur du filament %s" % (slot, idx))
omesh = out.mesh(("3D/Objects/character_1_1.model", "1"))
want = {int(k): v for k, v in mp.items()}
ok(omesh.states == {want.get(s, s) if s else 0 for s in mesh.states}, "peinture renumerotee %s -> %s" % (mesh.states, omesh.states))
oinst = out.plates[0].instances[0]
ok(abs(oinst.transform[9] - inst.transform[9]) < 1e-6 and abs(oinst.transform[10] - inst.transform[10]) < 1e-6, "position gardee (meme plateau)")
ok(out.plates[0].name == "printmon - character", "nom de plaque garde")
names = zipfile.ZipFile(io.BytesIO(res[0]["data"])).namelist()
ok(not any(n.startswith("Metadata/plate_1") for n in names), "vignettes de l'auteur retirees")
ok(any(n.startswith("Auxiliaries/") for n in names), "images du modele gardees")
print("   alertes:", res[0]["report"]["warnings"])

done()
