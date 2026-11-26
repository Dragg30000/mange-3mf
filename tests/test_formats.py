"""Autres formats (0.6.0) : projets PrusaSlicer (Printables) et 3MF bruts en couleurs (CAO), relus comme
des projets Orca puis convertis comme les autres."""
import io, os, re, zipfile
import xml.etree.ElementTree as ET
from common import ok, done, sample, fake_template, plan_of, OUT
import mange_3mf_any as m

from make_samples import cube, mesh_xml, prusa_3mf


def used_colors(src):
    return sorted(src.filament(i)["color"] for i in src.plates[0].weights)


def model_objects(text):
    """Objets d'un fichier .model : {id: (nombre de sommets, triangles [(v1, v2, v3)], peintures)}."""
    out = {}
    for mo in re.finditer(r'<object id="(\d+)"[^>]*>(.*?)</object>', text, re.S):
        body = mo.group(2)
        nv = len(re.findall(r"<vertex\b", body))
        tris = [tuple(int(x) for x in t) for t in re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', body)]
        out[mo.group(1)] = (nv, tris, re.findall(r'paint_color="(\w+)"', body))
    return out


print("== projet PrusaSlicer : lecture")
path = prusa_3mf(os.path.join(OUT, "Cubes Prusa.3mf"))
src = m.Source3MF(open(path, "rb").read(), "Cubes Prusa.3mf", path)
ok(src.kind == "prusa" and src.origin == "prusa" and src.app_label() == "PrusaSlicer 2.7.4", "PrusaSlicer 2.7.4 (%s)" % src.kind)
ok(m.PRUSA_CFG not in src.nameset and m.PROJECT_CFG in src.nameset and m.MODEL_CFG in src.nameset,
   "relu comme un projet Orca : %s" % sorted(n for n in src.names if n.startswith("Metadata/")))
ok([(f["color"], f["type"]) for f in src.filaments] == [("#FF0000", "PLA"), ("#00FF00", "PETG"), ("#0000FF", "PLA")],
   "couleurs des extrudeurs (sinon du filament) et matieres : %s" % [(f["color"], f["type"]) for f in src.filaments])
ok(src.printer == "MK4S" and src.bed_rect() == (0.0, 0.0, 250.0, 210.0), "imprimante et plateau : %s %s" % (src.printer, src.bed_rect()))
o1, o2 = src.objects["1"], src.objects["2"]
ok(o1.name == "Deux cubes" and o1.extruder == 1 and [(p.subtype, p.extruder) for p in o1.parts] == [("normal_part", 2), ("modifier_part", None)],
   "objet 1 : piece (filament 2) et modificateur : %s" % [(p.subtype, p.extruder) for p in o1.parts])
ok(o1.keys.get("wall_loops") == "3" and "perimeters" not in o1.keys and "fuzzy_skin" not in o1.keys,
   "reglages par objet aux noms d'Orca (perimeters -> wall_loops) : %s" % sorted(o1.keys))
ok(o2.name == "Cube C" and o2.extruder == 3 and len(o2.instances) == 2, "objet 2 : deux instances (l'alias de PrusaSlicer)")
ok([round(v, 3) for v in o2.instances[1].transform[9:]] == [155.0, 150.0, 10.0], "  seconde instance : decalage du composant compose (%s)" % (o2.instances[1].transform[9:],))
ok(len(src.objects) == 2, "l'alias n'est pas un objet de plus")
p = src.plates[0]
ok(set(p.weights) == {1, 2, 3}, "filaments utilises : piece, peinture, plage de hauteurs, code par hauteur : %s" % sorted(p.weights))
ok(any("fuzzy_skin" in str(w) for w in src.warnings), "reglage par objet non repris signale : %s" % [str(w) for w in src.warnings])
sup = m.author_supports(src)
ok(sup and sup["on"] and sup["type"] == "tree(auto)" and sup["filament"] == 3 and sup["interface"] == 0,
   "supports de l'auteur (organiques, filament 3) : %s" % sup)
sub = src.text("3D/Objects/object_1.model")
objs = model_objects(sub)
ok(sorted(objs) == ["4", "5"] and objs["4"][0] == 8 and objs["5"][0] == 8, "objet 1 : un sous-objet par volume, sommets renumerotes : %s" % {k: v[0] for k, v in objs.items()})
ok(all(max(max(t) for t in v[1]) < v[0] for v in objs.values()), "  triangles dans leurs sommets")
ok(objs["4"][2] == ["8", "0C"] and "slic3rpe:" not in sub and 'paint_supports="4"' in sub,
   "  peinture -> paint_color, supports peints -> paint_supports : %s" % objs["4"][2])
ok(sorted(model_objects(src.text("3D/Objects/object_2.model"))) == ["6"], "numeros des sous-objets uniques dans le projet")
cfg = ET.fromstring(src.raw(m.MODEL_CFG))
parts = [(pe.get("id"), pe.get("subtype")) for pe in cfg.iter("part")]
ok(parts == [("4", "normal_part"), ("5", "modifier_part"), ("6", "normal_part")], "pieces de model_settings : %s" % parts)
gc = ET.fromstring(src.raw(m.CUSTOM_GCODE))
ok([(l.get("top_z"), l.get("type")) for l in gc.iter("layer")] == [("2", "0"), ("4", "1")], "codes par hauteur : changement de couleur, pause")
rg = ET.fromstring(src.raw(m.LAYER_RANGES))
ok(sorted(o.get("opt_key") for o in rg.iter("option")) == ["extruder", "layer_height"], "plages de hauteurs : filament et hauteur de couche")
info = m.sniff_3mf(path)
ok(info["prusa"] and info["printer"] == "MK4S" and info["colors"] == 3 and m.needs_conversion(info) and m.source_label(info) == "PrusaSlicer",
   "apercu rapide : PrusaSlicer, a convertir (%s, %s couleurs)" % (info["printer"], info["colors"]))

print("== projet PrusaSlicer : conversion")
tpl = fake_template()
ana = m.analyze(src, tpl, with_thumbs=False)
ok(ana["source"]["app"] == "PrusaSlicer 2.7.4" and ana["source"]["kind"] == "prusa", "analyse : %s" % ana["source"]["app"])
ok(any("PETG" in w for w in ana["warnings"]), "matiere absente de tes profils (PETG) signalee : %s" % [str(w) for w in ana["warnings"]][-1:])
ok(ana["supports"] and not ana["supports"]["keep"], "supports de l'auteur proposes, pas gardes d'office")
res = m.convert(src, tpl, plan_of(ana))
data = res[0]["data"]
z = zipfile.ZipFile(io.BytesIO(data))
out = m.Source3MF(data, "out.3mf")
ok(out.kind == "orca" and len(out.config["filament_colour"]) == 4, "projet Orca, 3 filaments + 1 case libre")
ok(sorted(out.objects) == ["1", "2"] and len(out.objects["2"].instances) == 2, "objets et instances gardes")
ok(used_colors(out) == used_colors(src), "memes couleurs utilisees : %s" % used_colors(out))
ok(all(n in z.namelist() for n in ("3D/Objects/object_1.model", "3D/Objects/object_2.model", m.CUSTOM_GCODE, m.LAYER_RANGES)),
   "sous-objets, codes par hauteur, plages : %s" % [n for n in z.namelist() if "/" in n])
new_n = {s["src"][0]: s["n"] for s in ana["files"][0]["slots"] if s["src"]}
got = model_objects(z.read("3D/Objects/object_1.model").decode())["4"][2]
ok(got == [m.paint_leaf(new_n[2]), m.paint_leaf(new_n[3])], "peinture gardee, filaments renumerotes : %s" % got)

print("== projet PrusaSlicer : supports de l'auteur gardes")
ana2 = m.analyze(src, tpl, with_thumbs=False, supports=True)
ok(ana2["supports"]["keep"] and src.keep_supports, "supports gardes")
res2 = m.convert(src, tpl, plan_of(ana2))
cfg2 = m.Source3MF(res2[0]["data"], "out.3mf").config
want = [s for s in ana2["files"][0]["slots"] if s["src"] == [3]][0]["n"]
ok(cfg2.get("enable_support") == "1" and cfg2.get("support_type") == "tree(auto)" and cfg2.get("support_filament") == str(want),
   "reglages de supports de l'auteur, filament renumerote : %s %s %s" % (cfg2.get("enable_support"), cfg2.get("support_type"), cfg2.get("support_filament")))
ok(cfg2.get("support_line_width") == tpl.config.get("support_line_width"), "  largeur de ligne : celle de tes reglages")
res3 = m.convert(src, tpl, [dict(f, supports=False) for f in plan_of(ana2)])
cfg3 = m.Source3MF(res3[0]["data"], "out.3mf").config
ok(cfg3.get("enable_support") == tpl.config.get("enable_support") and not src.keep_supports, "decoche : supports de tes reglages")

print("== projet PrusaSlicer pour imprimante resine")
sla = prusa_3mf(os.path.join(OUT, "Resine.3mf"), "SLA")
try:
    m.Source3MF(open(sla, "rb").read(), "Resine.3mf")
    ok(False, "projet SLA refuse")
except m.ConvertError as e:
    ok("SLA" in str(e), "projet SLA refuse : %s" % e)

print("== 3MF brut en couleurs (CAO)")
group = ('  <m:colorgroup id="5"><m:color color="#FF0000FF"/><m:color color="#0000FF"/></m:colorgroup>\n'
         '  <basematerials id="6"><base name="Vert" displaycolor="#00FF00FF"/></basematerials>\n')
main = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">\n <metadata name="Application">Fusion</metadata>\n <resources>\n' + group +
        '  <object id="1" type="model" pid="5" pindex="0" name="Rouge">\n' + mesh_xml([cube(0, 0, 0)], {0: ' pid="5" p1="1" p2="1" p3="1"'}) + '  </object>\n'
        '  <object id="2" type="model" pid="6" pindex="0" name="Vert">\n' + mesh_xml([cube(20, 0, 0)]) + '  </object>\n'
        '  <object id="4" type="model" pid="5" pindex="1" name="Bleu">\n' + mesh_xml([cube(40, 0, 0)]) + '  </object>\n'
        '  <object id="5" type="model" pid="6" pindex="0" name="Vert 2">\n' + mesh_xml([cube(60, 0, 0)]) + '  </object>\n'
        '  <object id="3" type="model" name="Assemblage">\n   <components>\n    <component objectid="4"/>\n    <component objectid="5"/>\n'
        '   </components>\n  </object>\n </resources>\n <build>\n  <item objectid="1" transform="1 0 0 0 1 0 0 0 1 60 60 0"/>\n'
        '  <item objectid="2" transform="1 0 0 0 1 0 0 0 1 90 60 0"/>\n  <item objectid="3" transform="1 0 0 0 1 0 0 0 1 60 120 0"/>\n'
        ' </build>\n</model>\n')
cad = os.path.join(OUT, "Assemblage.3mf")
with zipfile.ZipFile(cad, "w") as zz:
    zz.writestr("3D/3dmodel.model", main)
src = m.Source3MF(open(cad, "rb").read(), "Assemblage.3mf")
ok(src.kind == "plain" and src.origin == "plain", "3MF sans reglages, avec des couleurs")
ok([f["color"] for f in src.filaments] == ["#FF0000", "#00FF00", "#0000FF"], "une couleur par filament, dans l'ordre des objets : %s" % [f["color"] for f in src.filaments])
ok(src.objects["1"].extruder == 1 and src.objects["2"].extruder == 2, "couleur de chaque objet : son filament")
ok([(p.id, p.extruder) for p in src.objects["3"].parts] == [("4", 3), ("5", 2)], "assemblage : chaque piece a sa couleur")
paints = model_objects(src.text(src.main))["1"][2]
ok(paints == [m.paint_leaf(3)] and m.paint_leaf(3) == "0C", "triangle d'une autre couleur : peint (%s)" % paints)
ok(set(src.plates[0].weights) == {1, 2, 3}, "filaments utilises : %s" % sorted(src.plates[0].weights))
res = m.convert(src, tpl, plan_of(m.analyze(src, tpl, with_thumbs=False)))
out = m.Source3MF(res[0]["data"], "out.3mf")
ok(out.kind == "orca" and used_colors(out) == used_colors(src), "converti : memes couleurs")
ok([m.paint_leaf(s) for s in (0, 1, 2, 3, 17, 18, 20)] == ["0", "4", "8", "0C", "EC", "0FC", "2FC"], "codage d'un triangle peint d'un seul filament")
with zipfile.ZipFile(os.path.join(OUT, "Brut.3mf"), "w") as zz:
    zz.writestr("3D/3dmodel.model", main.replace(group, "").replace(' pid="5"', "").replace(' pid="6"', ""))
src = m.Source3MF(open(os.path.join(OUT, "Brut.3mf"), "rb").read(), "Brut.3mf")
ok(src.kind == "plain" and src.origin is None and m.PROJECT_CFG not in src.nameset, "3MF sans couleurs : lu tel quel")

print("== vrais fichiers (pas publies)")
for name, check in (("sample_prusa_drakos.3mf", "prusa"), ("sample_cad_color.3mf", "plain")):
    if not os.path.isfile(sample(name)):
        print("  (pas de %s)" % name)
        continue
    src = m.Source3MF(open(sample(name), "rb").read(), name)
    ana = m.analyze(src, tpl, with_thumbs=False)
    out = m.Source3MF(m.convert(src, tpl, plan_of(ana))[0]["data"], "out.3mf")
    ok(src.kind == check and out.kind == "orca" and used_colors(out) == used_colors(src),
       "%s : %s, converti, memes couleurs %s" % (name, src.kind, used_colors(src)))
done()
