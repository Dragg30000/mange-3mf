"""Test du plugin dans un faux OrcaSlicer : onglet, messages, ecriture des fichiers, notifications."""
import importlib, json, os, shutil, sys, tempfile, time
from common import ok, done, sample, fake_template
import fake_orca, make_samples

tmp = tempfile.mkdtemp()
home = os.path.join(tmp, "home"); dl = os.path.join(home, "Downloads"); os.makedirs(dl)
os.environ["HOME"] = home; os.environ["USERPROFILE"] = home
storage = os.path.join(tmp, "storage")
shutil.copy(sample("sample_dragon.3mf"), os.path.join(dl, "cute baby dragon.3mf"))
make_samples.bambu_multiplate(os.path.join(dl, "Pokeballs X1C.3mf"))
tcfg = fake_template().config
orca, st, cur = fake_orca.install(storage, tcfg)
sys.modules.pop("mange_3mf_any", None)
m = importlib.import_module("mange_3mf_any")


def plan(an):
    return [{"plates": f["plates"], "slots": [{"src": s["src"], "base": s["base"]} for s in f["slots"]]} for f in an["files"]]


print("== enregistrement")
st["plugin"]().register_capabilities()
ok(len(st["caps"]) == 1, "1 capacite")
ok(st["perms"] and st["perms"][0]["fs_readwrite"][0].endswith(os.path.join("Downloads", "*")) and st["perms"][0]["threading"], "droits Telechargements + fils")
tab = st["caps"][0]()
ok(isinstance(tab, orca.pages.PagesPluginCapabilityBase), "c'est un onglet")
ok(tab.get_name() == "Mange-3MF", "nom de l'onglet : %s" % tab.get_name())
icon = tab.get_icon()
ok(icon.endswith(".svg") and os.path.isfile(icon) and "<svg" in open(icon, encoding="utf-8").read(), "icone : %s" % icon)
html = tab.get_ui()
ok("<html" in html and "orca.postMessage" in html and "dragover" in html, "page HTML (avec glisser-deposer)")
w = st["page"]

print("== init")
tab.on_message({"command": "init"})
state = w.wait("state")
ok(state["saved"] is None and state["current"]["u1"] and state["version"] == m.VERSION, "pas de reglages memorises, reglages actuels = U1")
rec = w.wait("recent")
names = [f["name"] for f in rec["files"]]
ok(set(names) == {"cute baby dragon.3mf", "Pokeballs X1C.3mf"}, "Telechargements listes %s" % names)
ok(all(f["todo"] for f in rec["files"]), "les deux sont a convertir")
print("  ", [(f["name"], f["label"], f["printer"], f["colors"]) for f in rec["files"]])
tab.on_message(json.dumps({"command": "recent"}))
w.wait("recent", 2)
ok(True, "message recu en texte JSON aussi")

print("== memoriser")
tab.on_message({"command": "capture"})
state = w.wait("state", 2)
ok(state["saved"] and state["saved"]["printer"] == "Snapmaker U1 (0.4 nozzle)" and st["exports"] == 1, "reglages memorises")

print("== analyse + conversion du projet 7 couleurs")
tab.on_message({"command": "analyze", "path": os.path.join(dl, "Pokeballs X1C.3mf"), "template": "saved"})
an = w.wait("analysis")
ok(len(an["files"]) == 1 and len(an["files"][0]["slots"]) == 7 and an["dest_hint"] == "dans Téléchargements",
   "1 fichier de 7 filaments prevu, %s" % an["dest_hint"])
ok(len(an["profiles"]) == 4 and an["heads"] == 4, "profils et tetes pour l'interface")
json.dump(an, open(os.path.join(tmp, "analysis.json"), "w"))
tab.on_message({"command": "replan", "token": an["token"], "template": "saved", "one_per_plate": True})
an2 = w.wait("analysis", 2)
ok(len(an2["files"]) == 6 and an2["one_per_plate"], "un fichier par plaque : 6")
tab.on_message({"command": "replan", "token": an["token"], "template": "saved", "one_per_plate": False})
an3 = w.wait("analysis", 3)
tab.on_message({"command": "convert", "token": an3["token"], "template": "saved", "files": plan(an3)})
b = w.wait("built")
tab.on_message({"command": "write", "token": b["token"]})
res = w.wait("result")
json.dump(res, open(os.path.join(tmp, "result.json"), "w"))
for f in res["files"]:
    ok(os.path.isfile(f["path"]) and os.path.dirname(f["path"]) == dl, "ecrit : %s" % f["name"])
    out = m.Source3MF(open(f["path"], "rb").read(), f["name"])
    ok(out.kind == "orca" and m.is_u1(out.config.get("printer_model")), "  projet Orca pour la U1")
    ok(f["filaments"] == 7 and f["colors"] == 7 and len(out.config["filament_colour"]) == 7, "  7 filaments")
ok(st["exports"] == 1, "pas de nouvel export (reglages memorises)")

print("== la page est reconstruite (onglet rouvert) : derniers resultats renvoyes")
n_posts = len(w.posts)
tab.on_message({"command": "init"})
w.wait("state", 4)
time.sleep(0.2)
after = [p["command"] for p in w.posts[n_posts:]]
ok("analysis" in after and "result" in after, "analyse et resultat renvoyes : %s" % after)

print("== 2e conversion : pas d'ecrasement")
tab.on_message({"command": "convert", "token": an3["token"], "template": "saved", "files": plan(an3)})
b2 = w.wait("built", 2); tab.on_message({"command": "write", "token": b2["token"]})
res2 = w.wait("result", 3)
ok(all("(2)" in f["name"] for f in res2["files"]), "noms libres : %s" % [f["name"] for f in res2["files"]])

print("== projet ouvert dans Orca")
tab.on_lifecycle_event("ProjectOpened", type("C", (), {"name": os.path.join(dl, "cute baby dragon.3mf")})())
note = st["notes"][-1] if st["notes"] else None
ok(note and "Bambu Studio" in note[1] and "onglet Mange-3MF" in note[2], "notification : %s / %s" % (note[1], note[2]) if note else "notification")
n_an = len([p for p in w.posts if p["command"] == "analysis"])
ok(note[3]() is True, "clic sur la notification")
an4 = w.wait("analysis", n_an + 1)
ok(an4["file"] == "cute baby dragon.3mf", "l'onglet a l'analyse du projet ouvert")
deadline = time.time() + 5
while time.time() < deadline and not any("prête" in x[1] for x in st["notes"]):
    time.sleep(0.05)
ok(any("prête" in x[1] and "onglet Mange-3MF" in x[1] for x in st["notes"]), "notification « prête » : %s" % st["notes"][-1][1])
own = res["files"][0]["path"]
n = len(st["notes"])
tab.on_lifecycle_event("ProjectOpened", type("C", (), {"name": own})())
ok(len(st["notes"]) == n, "pas de notification pour un projet deja converti")

print("== langues")
def count(cmd):
    return len([p for p in w.posts if p["command"] == cmd])
EN_COLORS = {m.TEXTS["en"][k] for k in m.TEXTS["en"] if k.startswith("col_")}
html = tab.get_ui()
ok('<html lang="fr">' in html and "English" in html and "Fran\\u00e7ais" in html, "page en francais, avec les deux langues")
state = [p for p in w.posts if p["command"] == "state"][-1]
ok(state["lang"] == "fr" and state["lang_choice"] == "auto", "langue d'Orca (fr_FR) en mode auto")
n_state, n_an = count("state"), count("analysis")
tab.on_message({"command": "lang", "lang": "en", "nav": "fr-FR"})
state = w.wait("state", n_state + 1)
ok(state["lang"] == "en" and state["lang_choice"] == "en" and state["saved"]["when"].startswith("saved "),
   "anglais choisi : %s" % state["saved"]["when"])
an_en = w.wait("analysis", n_an + 1)
ok(an_en.get("relabel") and an_en["token"] == an4["token"] and an_en["dest_hint"] == "in Downloads",
   "analyse affichee renvoyee en anglais : %s" % an_en["dest_hint"])
cn = {s["name"] for f in an_en["files"] for s in f["slots"] if not s["pad"]}
ok(cn and cn <= EN_COLORS and all(p["cname"] in EN_COLORS for p in an_en["profiles"]), "couleurs en anglais %s" % sorted(cn))
ok(json.load(open(os.path.join(storage, "options.json"))) == {"lang": "en"}, "choix memorise")
ok(m.Converter().language_choice() == "en", "garde au redemarrage d'Orca")
ok('<html lang="en">' in tab.get_ui(), "page reconstruite en anglais")
tab.on_message({"command": "capture"})
state = w.wait("state", n_state + 2)
ok(state["cap"] == "Settings saved.", "message « Memoriser » : %s" % state["cap"])
n_res = count("result")
tab.on_message({"command": "convert", "token": an_en["token"], "template": "saved", "files": plan(an_en)})
b3 = w.wait("built", 3); tab.on_message({"command": "write", "token": b3["token"]})
res3 = w.wait("result", n_res + 1)
ok(res3["files"][0]["name"].startswith("cute baby dragon - U1"), "converti : %s" % res3["files"][0]["name"])
n_state, n_an, n_res = count("state"), count("analysis"), count("result")
st["language"] = "de_DE"
tab.on_message({"command": "lang", "lang": "auto"})
state = w.wait("state", n_state + 1)
ok(state["lang"] == "en" and state["lang_choice"] == "auto", "auto avec Orca en allemand : anglais")
st["language"] = "fr_FR"
tab.on_message({"command": "lang", "lang": "auto"})
state = w.wait("state", n_state + 2)
ok(state["lang"] == "fr" and state["saved"]["when"].startswith("mémorisés le "), "auto avec Orca en francais : %s" % state["saved"]["when"])
an_fr = w.wait("analysis", n_an + 2)
res_fr = w.wait("result", n_res + 2)
ok(an_fr.get("relabel") and an_fr["dest_hint"] == "dans Téléchargements" and res_fr.get("relabel"),
   "analyse et resultat renvoyes en francais : %s" % an_fr["dest_hint"])
ok(json.load(open(os.path.join(storage, "options.json"))) == {"lang": "auto"}, "choix « auto » memorise")
tab.on_message({"command": "lang", "lang": "en"})
n_notes = len(st["notes"])
tab.on_lifecycle_event("ProjectOpened", type("C", (), {"name": os.path.join(dl, "cute baby dragon.3mf")})())
note = st["notes"][-1] if len(st["notes"]) > n_notes else None
ok(note and "comes from Bambu Studio" in note[1] and note[2] == "Prepare the conversion in the Mange-3MF tab",
   "notification en anglais : %s / %s" % (note[1], note[2]) if note else "notification en anglais")
n_an = count("analysis")
note[3]()
w.wait("analysis", n_an + 1)
deadline = time.time() + 5
while time.time() < deadline and not any("is ready" in x[1] for x in st["notes"]):
    time.sleep(0.05)
ok(any("is ready: open the Mange-3MF tab" in x[1] for x in st["notes"]), "notification « ready » : %s" % st["notes"][-1][1])
tab.on_message({"command": "analyze", "path": os.path.join(dl, "absent.3mf"), "template": "saved"})
time.sleep(0.2)
errs = [p for p in w.posts if p["command"] == "error"]
ok(errs and errs[-1]["text"].startswith("file not found: "), "erreur en anglais : %s" % (errs[-1]["text"] if errs else None))
w.posts = [p for p in w.posts if p["command"] != "error"]
tab.on_message({"command": "lang", "lang": "fr"})
ok([p for p in w.posts if p["command"] == "state"][-1]["lang"] == "fr", "retour au francais")

print("== prereglages d'Orca et dossier des fichiers convertis")
st["presets"] = [
    fake_orca.FakePreset("JAYO PETG", fake_orca.preset_from(tcfg, 0, "JAYO PETG", changes={"filament_type": ["PETG"]})),
    fake_orca.FakePreset("Rose Bonbon", fake_orca.preset_from(tcfg, 0, "Rose Bonbon", changes={"default_filament_colour": ["#FF3EC8"]})),
    fake_orca.FakePreset("Copie(projet.3mf)", fake_orca.preset_from(tcfg, 0, "Copie(projet.3mf)"), embedded=True)]
n_an = count("analysis")
tab.on_message({"command": "analyze", "path": os.path.join(dl, "cute baby dragon.3mf"), "template": "saved"})
an5 = w.wait("analysis", n_an + 1)
user = [p for p in an5["profiles"] if p["group"] == "user"]
ok([p["name"] for p in user] == ["JAYO PETG", "Rose Bonbon"], "tes prereglages proposes : %s" % [p["name"] for p in user])
ok(user[1]["cname"] == m.color_name("#FF3EC8"), "avec leur couleur : %s" % user[1]["cname"])
n_state = count("state")
tab.on_message({"command": "outdir", "mode": "folder", "dir": os.path.join(home, "absent")})
state = w.wait("state", n_state + 1)
ok(state["out"]["error"] and "absent" in state["out"]["msg"] and state["out"]["mode"] == "beside",
   "dossier introuvable refuse : %s" % state["out"]["msg"])
outdir = os.path.join(home, "Sorties")
os.makedirs(outdir)
n_an = count("analysis")
tab.on_message({"command": "outdir", "mode": "folder", "dir": '"%s"' % outdir})
state = w.wait("state", n_state + 2)
ok(state["out"]["mode"] == "folder" and state["out"]["dir"] == outdir and not state["out"]["error"],
   "dossier choisi : %s (%s)" % (state["out"]["dir"], state["out"]["msg"]))
an6 = w.wait("analysis", n_an + 1)
ok(an6.get("relabel") and an6["dest_hint"] == "dans Sorties", "analyse renvoyee : %s" % an6["dest_hint"])
opts = json.load(open(os.path.join(storage, "options.json")))
ok(opts.get("out") == "folder" and opts.get("out_dir") == outdir, "choix garde : %s" % opts)
files = plan(an5)
real = next(i for i, s in enumerate(an5["files"][0]["slots"]) if not s["pad"])
rose = next(i for i, p in enumerate(an5["profiles"]) if p["name"] == "Rose Bonbon")
files[0]["slots"][real]["base"] = rose
files[0]["slots"][real]["color"] = "#123456"
n_built, n_res = count("built"), count("result")
tab.on_message({"command": "convert", "token": an5["token"], "template": "saved", "files": files})
b5 = w.wait("built", n_built + 1); tab.on_message({"command": "write", "token": b5["token"]})
res5 = w.wait("result", n_res + 1)
p5 = res5["files"][0]["path"]
ok(os.path.dirname(p5) == outdir and os.path.isfile(p5), "ecrit dans le dossier choisi : %s" % p5)
import zipfile
pc = json.loads(zipfile.ZipFile(p5).read("Metadata/project_settings.config"))
ok(pc["filament_settings_id"][real] == "Rose Bonbon" and pc["filament_colour"][real].upper().startswith("#123456"),
   "prereglage et couleur choisis : %s, %s" % (pc["filament_settings_id"][real], pc["filament_colour"][real]))
tab.on_message({"command": "outdir", "mode": "beside", "dir": ""})
ok(json.load(open(os.path.join(storage, "options.json"))).get("out") == "beside", "retour : a cote du 3MF")
st["presets"] = []

print("== erreurs")
tab.on_message({"command": "analyze", "path": os.path.join(dl, "absent.3mf"), "template": "saved"})
time.sleep(0.2)
errs = [p for p in w.posts if p["command"] == "error"]
ok(errs and "introuvable" in errs[-1]["text"], "fichier absent : %s" % (errs[-1]["text"] if errs else None))
w.posts = [p for p in w.posts if p["command"] != "error"]
bad = os.path.join(dl, "pas_un_3mf.3mf"); open(bad, "wb").write(b"hello")
tab.on_message({"command": "analyze", "path": bad, "template": "saved"})
deadline = time.time() + 10
while time.time() < deadline and not any(p["command"] == "error" for p in w.posts): time.sleep(0.05)
errs = [p for p in w.posts if p["command"] == "error"]
ok(errs and "3MF" in errs[-1]["text"], "archive illisible : %s" % (errs[-1]["text"] if errs else None))
print("\nsorties :", tmp)
done()
