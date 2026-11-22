"""Prereglages de filament d'Orca (0.4.0) : lecture, noms sans projet, profils proposes, reglages du
projet faits depuis un prereglage, couleur choisie, dossier des fichiers convertis."""
import json, os, tempfile, types, zipfile
from common import ok, done, sample, variant_template, OUT
import fake_orca
from fake_orca import FakePreset, preset_from
import make_samples
import mange_3mf_any as m

print("== valeurs ecrites par Orca")
S = m.split_serialized
for text, strings, want in [
        ('"Direct Drive Standard";"Direct Drive High Flow"', True, ["Direct Drive Standard", "Direct Drive High Flow"]),
        ("PLA", True, ["PLA"]), ("PLA;PETG", True, ["PLA", "PETG"]), ('""', True, [""]), ("", False, []),
        ("220,225", False, ["220", "225"]), ("nil,1.5", False, ["nil", "1.5"]), ("none,none", False, ["none", "none"]),
        ('"G1 E-1\\nM400"', True, ["G1 E-1\nM400"]), ('"a\\"b";c', True, ['a"b', "c"]), ("a,b", True, ["a,b"])]:
    ok(S(text, strings) == want, "%r -> %s" % (text, S(text, strings)))
for text in (["Direct Drive Standard"], [""], ['say "hi"\nnow'], ["PLA", "PETG"], ["back\\slash x"]):
    ok(S(fake_orca.orca_serialize(text, True), True) == text, "aller-retour %r" % text)

print("== noms sans projet")
for name, want in (("Anycubic PLA(4 inch new grinch nutcracker v1-U1.3mf)(Capsulas Pokeballs GachaPop-U1 (1V2) - U1.3mf)", "Anycubic PLA"),
                   ("Snapmaker PLA SnapSpeed @U1-1(Capsulas Pokeballs GachaPop-U1 (1V2) - U1.3mf)", "Snapmaker PLA SnapSpeed @U1-1"),
                   ("Elegoo PLA @System", "Elegoo PLA @System"), ("PLA (mat)", "PLA (mat)"), ("", "")):
    ok(m.strip_project_suffix(name) == want, "%r -> %r" % (name[:40], m.strip_project_suffix(name)))

print("== prereglages lus dans Orca")
tmp = tempfile.mkdtemp()
tpl = variant_template()
cfg = tpl.config
cfg["filament_settings_id"][1] = "PLA Noir(4 inch grinch-U1.3mf)(Capsulas (1V2) - U1.3mf)"   # copie d'un projet
orca, st, cur = fake_orca.install(os.path.join(tmp, "storage"), cfg)
m.orca = orca                      # le module a ete importe avant le faux Orca
st["printer"] = cfg["printer_settings_id"]
st["presets"] = [
    FakePreset("PLA Noir", preset_from(cfg, 1, "PLA Noir", changes={"nozzle_temperature": ["231", "236"]}), user=True),
    FakePreset("JAYO PETG", preset_from(cfg, 2, "JAYO PETG", changes={"filament_type": ["PETG"], "nozzle_temperature": ["245", "250"]},
                                        inherits="Generic PETG @System", condition="printer_model=~/.*U1.*/",
                                        prints_condition="layer_height>0.1", filament_id="GFG99")),
    FakePreset("Rose Bonbon", preset_from(cfg, 0, "Rose Bonbon", changes={"default_filament_colour": ["#FF3EC8"]},
                                          variants=("Direct Drive Standard",))),
    FakePreset("P1S PLA", preset_from(cfg, 0, "P1S PLA"), compatible=False),
    FakePreset("Generic PLA @System", preset_from(cfg, 0, "Generic PLA @System"), user=False, system=True),
    FakePreset("JAYO PLA(Projet.3mf)", preset_from(cfg, 0, "JAYO PLA(Projet.3mf)"), embedded=True),
    FakePreset("- Default Filament -", {}, user=False, default=True),
]
pr = m.read_filament_presets(tpl)
ok([p.name for p in pr["user"]] == ["JAYO PETG", "Rose Bonbon", "P1S PLA"],
   "tes prereglages (projet, systeme, defaut et doublon ecartes ; autre imprimante a la fin) : %s" % [p.name for p in pr["user"]])
ok(pr["user"][-1].other and not pr["user"][0].other, "« P1S PLA » marque pour une autre imprimante")
ok(set(pr["slots"]) == {1} and pr["slots"][1].name == "PLA Noir", "case 2 : nom de projet retire, prereglage retrouve")
rose = pr["user"][1]
ok(rose.color == "#FF3EC8" and rose.type == "PLA" and rose.variants() == ["Direct Drive Standard"], "couleur, matiere, variantes du prereglage")
tpl.attach(pr)
prof = tpl.profiles
ok([p["group"] for p in prof] == ["slot"] * 5 + ["user", "user", "other"], "groupes : %s" % [p["group"] for p in prof])
ok(prof[1]["name"] == "PLA Noir" and prof[0]["name"] == "PLA Blanc", "noms propres dans la liste : %s" % prof[1]["name"])
ok(prof[1]["user"] and not prof[0]["user"], "case 2 = un de tes prereglages (affiche aussi dans « Tes prereglages ») ; case 1 non")
ok(prof[6]["name"] == "Rose Bonbon" and prof[6]["cname"] == m.color_name("#FF3EC8") and prof[5]["cname"] == "",
   "couleur des prereglages : %r / %r" % (prof[6]["cname"], prof[5]["cname"]))
summ = tpl.summary()
ok(summ["slots"][1]["name"] == "PLA Noir", "reglages memorises affiches sans nom de projet")

print("== profil propose")
ent = {"color": "#FF40C0", "base": "PLA", "src": [1]}
ok(m.default_profile(ent, 6, tpl) == 6, "rose (couleur en plus) : « Rose Bonbon » (%s)" % m.default_profile(ent, 6, tpl))
ok(m.default_profile({"color": "#FFFFFF", "base": "PLA", "src": [1]}, 6, tpl) == 0, "blanc : la case blanche")
ok(m.default_profile({"color": "#00FF00", "base": "PLA", "src": [1]}, 0, tpl) == 0, "case de la bonne matiere : gardee")
tpl2 = variant_template().attach(pr)
for i in range(5):
    tpl2.config["filament_type"][i] = "PLA"
ok(m.default_profile({"color": "#FF0000", "base": "PETG", "src": [1]}, 6, tpl2) == 5,
   "PETG sans case PETG : « JAYO PETG » (%s)" % m.default_profile({"color": "#FF0000", "base": "PETG", "src": [1]}, 6, tpl2))
ok(tpl.profile(5)[:2] == ("JAYO PETG", "PETG") and tpl.profile(5)[3] == 2, "case de base d'un prereglage : la case PETG")

print("== reglages du projet faits depuis un prereglage")
slots = [{"base": 0, "preset": None, "color": "#FFFFFF"},
         {"base": 1, "preset": tpl.slot_presets[1], "color": "#000000"},
         {"base": 2, "preset": tpl.presets[0], "color": "#E53935"},
         {"base": 3, "preset": None, "color": None},
         {"base": 0, "preset": tpl.presets[1], "color": "#FF3EC8"}]
out = m.build_project_config(tpl, slots)
ok(out["filament_settings_id"] == ["PLA Blanc", "PLA Noir", "JAYO PETG", "PLA Bleu", "Rose Bonbon"],
   "noms : %s" % out["filament_settings_id"])
ok(out["filament_self_index"] == ["1", "1", "2", "2", "3", "3", "4", "4", "5"], "lignes : %s" % out["filament_self_index"])
ok(out["filament_extruder_variant"][-1] == "Direct Drive Standard" and len(out["filament_extruder_variant"]) == 9,
   "variantes du prereglage « Rose Bonbon » : une seule")
ok(out["nozzle_temperature"][:6] == ["200", "205", "231", "236", "245", "250"],
   "temperatures : case, prereglage a jour (231/236), JAYO PETG (245/250) : %s" % out["nozzle_temperature"][:6])
ok(out["filament_type"] == ["PLA", "PLA", "PETG", "PLA", "PLA"], "matieres : %s" % out["filament_type"])
ok(out["inherits_group"] == ["proc", "inh1", "", "Generic PETG @System", "inh4", "", "prn"], "parents : %s" % out["inherits_group"])
ok(out["different_settings_to_system"] == ["dp", "d1", "", "", "d4", "", "dprn"],
   "aucun ecart note pour un prereglage : %s" % out["different_settings_to_system"])
ok(out["compatible_process_expression_group"][2] == "layer_height>0.1", "conditions du prereglage")
ok(out["filament_ids"] == ["ID1", "ID2", "GFG99", "ID4", "ID1"], "identifiants : %s" % out["filament_ids"])
ok(out["filament_colour"][4] == "#FF3EC8" and out["default_filament_colour"][4] == "#FF3EC8", "couleurs")
for key in ("nozzle_temperature", "pressure_advance", "filament_extruder_variant"):
    ok(len(out[key]) == len(out["filament_self_index"]), "  %s : une valeur par ligne" % key)
fv = out["flush_volumes_vector"]
ok(fv[4:6] == cfg["flush_volumes_vector"][4:6], "purge du prereglage : celle de sa case de base")

print("== Orca reconnait le prereglage a l'ouverture")
# comme PresetBundle::load_config_file_config : valeurs d'un filament = ses lignes ; sans ecart note, rien
# n'est remis aux valeurs du parent ; le prereglage du meme nom doit avoir exactement ces valeurs
rows = [r for r, fi in enumerate(out["filament_self_index"]) if fi == "3"]
jayo = tpl.presets[0]
same = all(([out[k][r] for r in rows] if len(out[k]) == len(out["filament_self_index"]) and len(out[k]) != 5 else [out[k][2]])
           == jayo.values(k, any("," in x or " " in x or "\n" in x for x in cfg[k])) for k in jayo.raw
           if k not in m.FilamentPreset.SCALARS and k in out and k not in m.FILAMENT_MIXED_DEFAULTS
           and k not in ("filament_settings_id",) and isinstance(out[k], list) and len(out[k]) in (5, 9))
ok(same, "valeurs du filament 3 = celles de « JAYO PETG »")

print("== conversion avec couleur choisie et prereglage")
path = make_samples.bambu_multiplate(os.path.join(OUT, "presets.3mf"))
src = m.Source3MF(open(path, "rb").read(), "presets.3mf")
ana = m.analyze(src, tpl, with_thumbs=False)
f0 = ana["files"][0]
plan = [{"plates": f0["plates"], "slots": [{"src": s["src"], "base": s["base"], "color": None} for s in f0["slots"]]}]
real = next(i for i, s in enumerate(f0["slots"]) if not s["pad"])
plan[0]["slots"][real]["color"] = "#123456"
plan[0]["slots"][real]["base"] = 6                     # « Rose Bonbon »
res = m.convert(src, tpl, plan)
z = zipfile.ZipFile(__import__("io").BytesIO(res[0]["data"]))
pc = json.loads(z.read("Metadata/project_settings.config"))
ok(pc["filament_colour"][real].upper() == "#123456", "couleur choisie ecrite : %s" % pc["filament_colour"][real])
ok(pc["filament_settings_id"][real] == "Rose Bonbon", "prereglage choisi : %s" % pc["filament_settings_id"][real])
ok("(" not in "".join(pc["filament_settings_id"]), "aucun nom de projet dans les profils : %s" % pc["filament_settings_id"])
print("== un meme profil pour plusieurs couleurs")
reals = [i for i, s in enumerate(f0["slots"]) if not s["pad"]]
for base in (6, 2):                                  # un de tes prereglages, puis une case de tes reglages
    same = [{"plates": f0["plates"], "slots": [{"src": s["src"], "base": base if not s["pad"] else s["base"], "color": None}
                                              for s in f0["slots"]]}]
    pc2 = json.loads(zipfile.ZipFile(__import__("io").BytesIO(m.convert(src, tpl, same)[0]["data"])).read("Metadata/project_settings.config"))
    want = [m.norm_color(f0["slots"][i]["color"]) for i in reals]
    got = [m.norm_color(pc2["filament_colour"][i][:7]) for i in reals]
    ok(len(set(pc2["filament_settings_id"][i] for i in reals)) == 1 and len(reals) > 2,
       "%d couleurs avec le meme profil « %s »" % (len(reals), pc2["filament_settings_id"][reals[0]]))
    ok(got == want, "chaque filament garde la couleur du modele : %s" % got)
mix = [{"plates": f0["plates"], "slots": [{"src": s["src"], "base": 6 if not s["pad"] else s["base"],
                                           "color": "#00AA55" if i == reals[1] else None} for i, s in enumerate(f0["slots"])]}]
pc3 = json.loads(zipfile.ZipFile(__import__("io").BytesIO(m.convert(src, tpl, mix)[0]["data"])).read("Metadata/project_settings.config"))
ok(pc3["filament_colour"][reals[1]][:7].upper() == "#00AA55" and pc3["filament_colour"][reals[0]][:7].upper() != "#00AA55",
   "meme profil, une couleur changee pour un seul filament")
bad = [{"plates": f0["plates"], "slots": [dict(s, base=99) for s in plan[0]["slots"]]}]
try:
    m.convert(src, tpl, bad); ok(False, "profil inconnu refuse")
except m.ConvertError as e:
    ok("99" in str(e) or "100" in str(e), "profil inconnu refuse : %s" % e)
odd = [{"plates": f0["plates"], "slots": [dict(s, color="red") for s in plan[0]["slots"]]}]
ok(m.check_plan(src, tpl, odd)[0]["slots"][real]["pick"] is None, "couleur invalide ignoree")

print("== dossier des fichiers convertis")
import shutil
base = tempfile.mkdtemp(dir=os.path.expanduser("~"), prefix=".mange3mf_test_")   # hors de /tmp (dossier temporaire)
home = os.path.join(base, "home"); os.makedirs(os.path.join(home, "Downloads")); os.makedirs(os.path.join(home, "Projets"))
os.environ["HOME"] = home; os.environ["USERPROFILE"] = home
srcp = os.path.join(home, "Projets", "a.3mf")
ok(m.output_folder(srcp, {}) == os.path.join(home, "Projets"), "par defaut : a cote du 3MF")
ok(m.output_folder(srcp, {"out": "downloads"}) == os.path.join(home, "Downloads"), "Telechargements")
ok(m.output_folder(srcp, {"out": "folder", "out_dir": tmp}) == tmp, "dossier choisi")
ok(m.output_folder(srcp, {"out": "folder", "out_dir": os.path.join(tmp, "absent")}) == os.path.join(home, "Projets"),
   "dossier disparu : a cote du 3MF")
ok(m.output_folder("", {"out": "beside"}) == os.path.join(home, "Downloads"), "fichier glisse : Telechargements")
shutil.rmtree(base, ignore_errors=True)
done()
