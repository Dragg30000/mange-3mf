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
