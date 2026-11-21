import io, json, os, re, zipfile
from common import ok, done, sample, fake_template, plan_of, variant_template, VARIANT_PROFILES, OUT
import mange_3mf_any as m
import make_samples
tpl = fake_template()

def rezip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)
    return buf.getvalue()

print("== Snapmaker Orca, U1, 7 couleurs (comme les Pokeballs)")
p = make_samples.bambu_multiplate(os.path.join(OUT, "synthetic_snorca.3mf"), bed=270.0, printer="Snapmaker U1")
files = {n: zipfile.ZipFile(p).read(n) for n in zipfile.ZipFile(p).namelist()}
files["3D/3dmodel.model"] = files["3D/3dmodel.model"].replace(b"BambuStudio-02.03.01.51", b"Snapmaker_Orca-2.4.2")
cfg = json.loads(files["Metadata/project_settings.config"]); cfg["printable_area"] = ["0.5x1", "270.5x1", "270.5x271", "0.5x271"]
files["Metadata/project_settings.config"] = json.dumps(cfg).encode()
src = m.Source3MF(rezip(files), "Capsulas Pokeballs GachaPop-U1 (1).3mf")
ok(src.kind == "snapmaker" and src.app_label() == "Snapmaker Orca 2.4.2", "source Snapmaker Orca (%s)" % src.app_label())
ana = m.analyze(src, tpl)
ok(len(ana["files"]) == 1 and ana["files"][0]["colors"] == 7, "1 fichier, 7 couleurs")
res = m.convert(src, tpl, plan_of(ana))
for r in res:
    out = m.Source3MF(r["data"], r["name"])
    for j, pl in enumerate(out.plates):
        orig = next(sp for sp in src.plates if sp.name == pl.name)
        sinst = orig.instances[0]; oinst = pl.instances[0]
        sox, soy = src.plate_origin(orig.index)
        ox, oy = m.plate_origin(j, m.compute_column_count(len(out.plates)), 270.0, 270.0)
        same = abs((oinst.transform[9] - ox) - (sinst.transform[9] - sox)) < 1e-6 and abs((oinst.transform[10] - oy) - (sinst.transform[10] - soy)) < 1e-6
        ok(same, "%s : meme position dans la plaque (meme plateau)" % pl.name)
print("   noms :", [r["name"] for r in res])

print("== plateau plus grand (350 mm) avec pieces en bord")
p = make_samples.bambu_multiplate(os.path.join(OUT, "synthetic_h2d.3mf"), bed=350.0, printer="Bambu Lab H2D", plate_count=2, paint_obj8=False)
files = {n: zipfile.ZipFile(p).read(n) for n in zipfile.ZipFile(p).namelist()}
main = files["3D/3dmodel.model"].decode()
# objet 5 pousse au bord droit du plateau 350
main = re.sub(r'(<item objectid="5"[^>]*transform="(?:\S+ ){9})(\S+)', lambda mm: mm.group(1) + "300", main)
files["3D/3dmodel.model"] = main.encode()
src = m.Source3MF(rezip(files), "grand.3mf")
ana = m.analyze(src, tpl)
res = m.convert(src, tpl, plan_of(ana))
for r in res:
    out = m.Source3MF(r["data"], r["name"])
    cols = m.compute_column_count(len(out.plates))
    for j, pl in enumerate(out.plates):
        ox, oy = m.plate_origin(j, cols, 270.0, 270.0)
        for inst in pl.instances:
            b = inst.bbox
            ok(ox + 0.5 <= b[0] and b[3] <= ox + 270.5 and oy + 1 <= b[1] and b[4] <= oy + 271,
               "%s objet %s dans le plateau U1 (%.0f..%.0f)" % (pl.name, inst.obj.id, b[0] - ox, b[3] - ox))

# trop large pour la U1 : alerte
files2 = dict(files)
main2 = re.sub(r'(<item objectid="5"[^>]*transform="(?:\S+ ){9})(\S+)', lambda mm: mm.group(1) + "335", files["3D/3dmodel.model"].decode())
files2["3D/3dmodel.model"] = main2.encode()
src = m.Source3MF(rezip(files2), "trop_grand.3mf")
res = m.convert(src, tpl, plan_of(m.analyze(src, tpl)))
ok(any("trop grande" in w for r in res for w in r["report"]["warnings"]), "alerte plaque trop grande : %s" % [w for r in res for w in r["report"]["warnings"]])

print("== 3MF sans reglages (forme seule)")
z = zipfile.ZipFile(sample("sample_pokeballs.3mf"))
plain = {n: z.read(n) for n in z.namelist() if not n.startswith("Metadata/")}
plain["3D/3dmodel.model"] = re.sub(rb'<metadata name="Application">[^<]*</metadata>', b'<metadata name="Application">Blender</metadata>', plain["3D/3dmodel.model"])
src = m.Source3MF(rezip(plain), "forme.3mf")
ok(src.kind == "plain" and len(src.plates) == 1 and src.plates[0].filaments == {1}, "1 plaque, filament 1")
ana = m.analyze(src, tpl)
res = m.convert(src, tpl, plan_of(ana))
out = m.Source3MF(res[0]["data"], res[0]["name"])
ok(out.kind == "orca" and len(out.plates) == 1 and len(out.plates[0].instances) == 6, "converti : 6 pieces sur 1 plaque")
zz = zipfile.ZipFile(io.BytesIO(res[0]["data"]))
ok(m.MODEL_CFG in zz.namelist() and m.PROJECT_CFG in zz.namelist(), "reglages crees")

print("== fichier deja tranche")
sliced = {"[Content_Types].xml": z.read("[Content_Types].xml"), "_rels/.rels": z.read("_rels/.rels"),
          "3D/3dmodel.model": b'<?xml version="1.0"?><model><metadata name="Application">BambuStudio-02.00</metadata><resources></resources><build/></model>',
          "Metadata/plate_1.gcode": b"G28\n", "Metadata/project_settings.config": z.read("Metadata/project_settings.config")}
try:
    m.analyze(m.Source3MF(rezip(sliced), "x.gcode.3mf"), tpl); ok(False, "refuse")
except m.ConvertError as e:
    ok("tranch" in str(e), "refuse : %s" % e)

print("== pas un 3MF")
try:
    m.Source3MF(b"hello", "x.3mf"); ok(False, "refuse")
except m.ConvertError as e:
    ok(True, "refuse : %s" % e)

print("== plan modifie a la main (interface) : autre profil pour une couleur")
src = m.Source3MF(open(make_samples.bambu_multiplate(os.path.join(OUT, "synthetic_x1c_7colors.3mf")), "rb").read(), "P.3mf")
vt = variant_template()
ana = m.analyze(src, vt)
plan = plan_of(ana)
f0 = ana["files"][0]
ok([p["name"] for p in ana["profiles"]] == [n for _c, _t, n in VARIANT_PROFILES[:5]], "5 profils proposes (pas la couleur melangee)")
ok(ana["heads"] == 4 and len(f0["slots"]) == 7, "4 tetes, 7 filaments")
j_violet = next(s["n"] for s in f0["slots"] if s.get("name") == "violet")
plan[0]["slots"][j_violet - 1]["base"] = 2          # profil PETG Rouge pour le violet (PLA)
res = m.convert(src, vt, plan)
cfg = m.Source3MF(res[0]["data"], res[0]["name"]).config
ok(cfg["filament_settings_id"][j_violet - 1] == "PETG Rouge", "profil choisi : %s" % cfg["filament_settings_id"][j_violet - 1])
ok(m.norm_color(cfg["filament_colour"][j_violet - 1]) == "#6A1B9A", "couleur du modele gardee")
ok(any("veut du PLA" in w and "PETG" in w for w in res[0]["report"]["warnings"]), "alerte de matiere : %s" % res[0]["report"]["warnings"])
bad = plan_of(ana); bad[0]["slots"][0]["src"] = []
try:
    m.convert(src, vt, bad); ok(False, "plan incomplet refuse")
except m.ConvertError as e:
    ok("sans case" in str(e), "plan incomplet refuse : %s" % e)
bad = plan_of(ana); bad[0]["plates"] = bad[0]["plates"][:-1]
try:
    m.convert(src, vt, bad); ok(False, "plaque oubliee refusee")
except m.ConvertError as e:
    ok("oubli" in str(e), "plaque oubliee refusee : %s" % e)
bad = plan_of(ana); bad[0]["slots"][0]["base"] = 5   # la couleur melangee n'est pas un profil
try:
    m.convert(src, vt, bad); ok(False, "profil inconnu refuse")
except m.ConvertError as e:
    ok("profil" in str(e), "profil inconnu refuse : %s" % e)

done()
