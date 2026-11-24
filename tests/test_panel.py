"""La U1 dans le panneau de Preparer (faux OrcaSlicer 2.5.1 avec create_dock_panel) : 3MF pas regle pour la
U1 ouvert dans Orca, Le manger / Pas maintenant, Annuler, glisser-deposer, conversion, meme travail que
l'onglet, langue, croix, reglage panneau / notification / rien, Orca sans panneau."""
import base64, importlib, json, os, shutil, sys, tempfile, time, zipfile
from common import ok, done, sample, fake_template
import fake_orca, make_samples

tmp = tempfile.mkdtemp()
home = os.path.join(tmp, "home"); dl = os.path.join(home, "Downloads"); os.makedirs(dl)
os.environ["HOME"] = home; os.environ["USERPROFILE"] = home
storage = os.path.join(tmp, "storage")
DRAGON = os.path.join(dl, "cute baby dragon.3mf")
POKE = os.path.join(dl, "Pokeballs X1C.3mf")
shutil.copy(sample("sample_dragon.3mf"), DRAGON)
make_samples.bambu_multiplate(POKE)
tcfg = fake_template().config
orca, st, cur = fake_orca.install(storage, tcfg, dock=True)
sys.modules.pop("mange_3mf_any", None)
m = importlib.import_module("mange_3mf_any")
st["plugin"]().register_capabilities()
tab = st["caps"][0]()
tab.get_ui()
w = st["page"]
tab.on_message({"command": "init"}); w.wait("state")
tab.on_message({"command": "capture"}); w.wait("state", 2)      # reglages U1 memorises


def opened(path):
    tab.on_lifecycle_event("ProjectOpened", type("C", (), {"name": path})())


def cmds(win, since=0):
    return [x["command"] for x in win.posts[since:]]


def count(win, cmd):
    return len([x for x in win.posts if x["command"] == cmd])


def last(win, cmd):
    got = [x for x in win.posts if x["command"] == cmd]
    return got[-1] if got else None


def until(cond, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.03)
    return False


def b64(b):
    return base64.b64encode(b).decode()


def plan(an):
    return [{"plates": f["plates"], "slots": [{"src": s["src"], "base": s["base"], "color": None, "extra": False}
                                              for s in f["slots"]]} for f in an["files"]]


print("== 3MF pas regle pour la U1 ouvert dans Orca : la U1 le reclame dans le panneau")
ok(m.panel_mode() == "panel", "reglage par defaut : le panneau")
n_notes = len(st["notes"])
opened(DRAGON)
ok(len(st["panels"]) == 1, "panneau cree")
p = st["panels"][0]
ok(p.k["dock"] == "right" and p.k["title"] == "Mange-3MF" and p.k["width"] >= 320, "a droite du plateau, titre « Mange-3MF »")
page = p.k["html"]
ok('<html lang="fr">' in page and '<template id="u1t">' in page and "orca.postMessage" in page and "dragover" in page
   and '"pn_eat"' in page and "M3D" in page, "page du panneau : la U1 de l'onglet, sa police, glisser-deposer, textes")
ok(len(st["notes"]) == n_notes, "pas de notification en plus")
p.send({"command": "init", "nav": "fr-FR"})
hello, offer = p.wait("hello"), p.wait("offer")
ok(hello["lang"] == "fr" and hello["mode"] == "panel" and hello["version"] == m.VERSION, "bonjour : langue, reglage, version")
f = offer["file"]
ok(f["name"] == "cute baby dragon.3mf" and f["label"] == "Bambu Studio" and f["colors"] >= 1 and f["path"] == DRAGON,
   "Miam : %s (%s, %s couleurs)" % (f["name"], f["label"], f["colors"]))
state = last(w, "state")
ok(state["opened"]["name"] == "cute baby dragon.3mf" and state["panel"] == "panel", "l'onglet le sait aussi (et le reglage)")

print("== Le manger : le panneau mache et rote ; l'onglet a la meme analyse")
n_tab_an, n_tab_prog = count(w, "analysis"), count(w, "progress")
p.send({"command": "eat"})
prog, an = p.wait("progress"), p.wait("analysis")
ok(prog.get("token") == an["token"] and an["file"] == "cute baby dragon.3mf" and m.PANEL.offer is None,
   "progression puis analyse : %s" % an["token"])
tan = w.wait("analysis", n_tab_an + 1)
ok(tan["token"] == an["token"], "l'onglet a la meme analyse (pour changer un profil)")
ok(count(w, "progress") == n_tab_prog, "mais pas la progression du panneau")
ok(m.PANEL.token == an["token"] and m.CONVERTER.jobs[an["token"]]["origin"] == "panel"
   and m.CONVERTER.jobs[an["token"]]["template"] == "saved", "travail du panneau, avec les reglages memorises")

print("== l'onglet change un profil et une couleur : le panneau montre et convertit la meme chose")
files = plan(an)
real = next(i for i, s in enumerate(an["files"][0]["slots"]) if not s["pad"])
other = next(i for i, pr in enumerate(an["profiles"]) if pr["group"] == "slot" and i != an["files"][0]["slots"][real]["base"])
files[0]["slots"][real]["base"] = other
files[0]["slots"][real]["color"] = "#123456"
files[0]["slots"].append({"src": [], "base": 0, "color": "#00FF00", "extra": True})
tab.on_message({"command": "plan", "token": an["token"], "files": files})
pl = p.wait("plan")
ok(pl["files"] == files and pl["token"] == an["token"], "plan de l'onglet recu par le panneau")
n = len(w.posts); tab.on_message({"command": "init"}); got = cmds(w, n)
ok("plan" in got and got.index("analysis") < got.index("plan"), "l'onglet qui redemarre : analyse puis plan")
tab.on_message({"command": "plan", "token": "zzz", "files": files})
tab.on_message({"command": "plan", "token": an["token"], "files": "pas une liste"})
ok(count(p, "plan") == 1, "plan d'un autre travail, ou mal forme : ignore")

print("== Convertir dans le panneau")
n_tab_built, n_tab_res = count(w, "built"), count(w, "result")
p.send({"command": "view", "v": "conv"})
p.send({"command": "convert", "token": an["token"], "files": pl["files"]})
b = p.wait("built")
ok(count(w, "built") == n_tab_built, "« built » au panneau seulement : c'est lui qui ecrit")
p.send({"command": "write", "token": b["token"]})
res = p.wait("result")
f0 = res["files"][0]
ok(os.path.isfile(f0["path"]) and os.path.dirname(f0["path"]) == dl and res["token"] == an["token"], "ecrit : %s" % f0["name"])
pc = json.loads(zipfile.ZipFile(f0["path"]).read("Metadata/project_settings.config"))
ok(pc["filament_colour"][real].upper().startswith("#123456") and pc["filament_settings_id"][real] == an["profiles"][other]["name"],
   "profil et couleur choisis dans l'onglet : %s, %s" % (pc["filament_settings_id"][real], pc["filament_colour"][real]))
ok(len(pc["filament_colour"]) == len(an["files"][0]["slots"]) + 1 and pc["filament_colour"][-1].upper().startswith("#00FF00"),
   "la couleur en plus est dans le fichier (%d filaments)" % len(pc["filament_colour"]))
tres = w.wait("result", n_tab_res + 1)
ok(tres["files"][0]["path"] == f0["path"], "l'onglet a aussi le resultat")
ok(not any(x["command"] == "error" for x in w.posts + p.posts), "aucune erreur")

print("== le projet converti s'ouvre dans Orca : le panneau se range")
p.send({"command": "view", "v": "done"})
n_notes = len(st["notes"])
opened(f0["path"])
ok(not p.shown and m.PANEL.view == "rest" and cmds(p)[-1] == "rest" and m.PANEL.token is None, "panneau cache, au repos")
ok(len(st["notes"]) == n_notes, "pas de notification (projet regle pour la U1)")

print("== un autre 3MF pas regle : le meme panneau revient ; Pas maintenant")
opened(POKE)
ok(len(st["panels"]) == 1 and p.shown, "meme panneau, remontre")
ok(p.posts[-1]["command"] == "offer" and p.posts[-1]["file"]["name"] == "Pokeballs X1C.3mf", "Miam : %s" % p.posts[-1]["file"]["name"])
p.send({"command": "later"})
ok(not p.shown and m.PANEL.offer is None and m.PANEL.view == "rest", "Pas maintenant : panneau cache")
opened(POKE)
p.send({"command": "view", "v": "offer"})
tab.on_lifecycle_event("NewProject", None)
ok(not p.shown and m.PANEL.offer is None, "nouveau projet : la proposition s'en va")

print("== Annuler pendant l'analyse : rien n'arrive, le 3MF propose revient")
opened(POKE)
slow = m.analyze
m.analyze = lambda *a, **k: (time.sleep(0.6), slow(*a, **k))[1]
n = len(p.posts)
p.send({"command": "eat"})
tok = m.PANEL.token
p.send({"command": "cancel"})
ok(tok and m.PANEL.token is None and tok not in m.CONVERTER.jobs, "analyse abandonnee")
ok(m.PANEL.offer and m.PANEL.offer["name"] == "Pokeballs X1C.3mf" and p.posts[-1]["command"] == "offer", "le 3MF propose revient")
time.sleep(1.2)
m.analyze = slow
ok(not any(x.get("token") == tok and x["command"] in ("analysis", "error") for x in p.posts[n:] + w.posts),
   "ni analyse ni erreur de l'analyse annulee")
p.send({"command": "later"})

print("== 3MF glisse sur le panneau : par morceaux, a cote d'un envoi de l'onglet")
raw = open(DRAGON, "rb").read()
half = len(raw) // 2
p.send({"command": "upload_part", "id": "p1", "i": 0, "n": 2, "data": b64(raw[:half])})
tab.on_message({"command": "upload_part", "id": "u9", "i": 0, "n": 2, "data": b64(raw[:half])})
p.send({"command": "upload_part", "id": "p1", "i": 1, "n": 2, "data": b64(raw[half:])})
ok(set(m.CONVERTER.uploads) == {"p1", "u9"}, "un envoi par page : %s" % sorted(m.CONVERTER.uploads))
n_an = count(p, "analysis")
p.send({"command": "analyze", "upload_id": "p1", "name": "glisse.3mf"})
an2 = p.wait("analysis", n_an + 1)
ok(an2["file"] == "glisse.3mf" and an2["token"] == m.PANEL.token, "analyse du fichier glisse : %s" % an2["file"])
tab.on_message({"command": "upload_drop", "id": "u9"})
ok(not m.CONVERTER.uploads, "morceaux liberes")

print("== l'onglet analyse autre chose : le travail du panneau reste")
n_tab_an, n_p_an = count(w, "analysis"), count(p, "analysis")
tab.on_message({"command": "analyze", "path": POKE, "template": "saved"})
tan2 = w.wait("analysis", n_tab_an + 1)
ok(an2["token"] in m.CONVERTER.jobs and tan2["token"] in m.CONVERTER.jobs and tan2["token"] != an2["token"],
   "deux travaux gardes : onglet et panneau")
ok(count(p, "analysis") == n_p_an, "le panneau ne suit pas l'analyse de l'onglet")
tab.on_message({"command": "analyze", "path": POKE, "template": "saved"})
tan3 = w.wait("analysis", n_tab_an + 2)
ok(tan2["token"] not in m.CONVERTER.jobs and an2["token"] in m.CONVERTER.jobs, "une nouvelle analyse de l'onglet remplace la sienne seulement")

print("== l'onglet convertit le travail du panneau : le panneau suit")
n_p_prog, n_p_res, n_p_built, n_tab_built = count(p, "progress"), count(p, "result"), count(p, "built"), count(w, "built")
tab.on_message({"command": "convert", "token": an2["token"], "template": "saved", "files": plan(an2)})
bt = w.wait("built", n_tab_built + 1)
ok(bt["token"] == an2["token"] and count(p, "built") == n_p_built, "« built » a l'onglet seulement (c'est lui qui ecrit)")
ok(count(p, "progress") > n_p_prog, "le panneau voit la conversion")
tab.on_message({"command": "write", "token": bt["token"]})
pr = p.wait("result", n_p_res + 1)
ok(pr["files"][0]["name"] == "glisse - U1-by-Dragg.3mf", "le panneau a le resultat : %s" % pr["files"][0]["name"])

print("== langue : le panneau suit l'onglet")
n = len(p.posts)
tab.on_message({"command": "lang", "lang": "en"})
got = p.posts[n:]
ok(got and got[0]["command"] == "hello" and got[0]["lang"] == "en", "bonjour en anglais")
rel = [x for x in got if x.get("relabel") and x["command"] == "analysis"]
ok(rel and rel[0]["token"] == an2["token"] and rel[0]["dest_hint"] == "in Downloads", "analyse du panneau retraduite : %s" % (rel[0]["dest_hint"] if rel else None))
ok('<html lang="en">' in m.panel_html() and 'var lang="en"' in m.panel_html(), "page du panneau en anglais")
tab.on_message({"command": "lang", "lang": "auto"})
ok(p.posts[-1]["command"] in ("hello", "analysis", "result") and [x for x in p.posts if x["command"] == "hello"][-1]["lang"] == "fr", "retour au francais")

print("== page du panneau qui redemarre : tout est renvoye")
n = len(p.posts)
p.send({"command": "init"})
got = cmds(p, n)
rep = [x for x in p.posts[n:] if x.get("replay")]
ok(got[0] == "hello" and "analysis" in got and "result" in got and {x["command"] for x in rep} == {"analysis", "result"},
   "bonjour, analyse et resultat rejoues : %s" % got)

print("== erreurs du panneau : au panneau seulement")
n_tab_err = count(w, "error")
p.send({"command": "analyze", "upload_id": "absent", "name": "x.3mf"})
ok(p.posts[-1]["command"] == "error" and "en entier" in p.posts[-1]["text"], "envoi incomplet : %s" % p.posts[-1].get("text"))
bad = os.path.join(dl, "pas_un_3mf.3mf"); open(bad, "wb").write(b"hello")
with m.PANEL.lock:
    m.PANEL.offer = {"path": bad, "name": "pas_un_3mf.3mf", "label": "", "printer": "", "colors": 0}
n_err = count(p, "error")
p.send({"command": "eat"})
ok(until(lambda: count(p, "error") > n_err) and "3MF" in last(p, "error")["text"], "archive illisible : %s" % last(p, "error")["text"])
ok(count(w, "error") == n_tab_err, "rien dans l'onglet")
os.remove(bad)
m.CONVERTER.opened = None
with m.PANEL.lock:
    m.PANEL.offer = None
p.send({"command": "eat"})
ok(p.posts[-1]["command"] == "error" and "plus de 3MF ouvert" in p.posts[-1]["text"], "plus rien a manger : %s" % p.posts[-1]["text"])
ok(count(w, "error") == n_tab_err, "toujours rien dans l'onglet")

print("== croix du panneau : il revient au prochain 3MF pas regle")
p.close()
ok(m.PANEL.handle is None and m.PANEL.token is None and m.PANEL.view == "rest", "panneau ferme, oublie")
opened(DRAGON)
ok(len(st["panels"]) == 2 and st["panels"][1].shown, "nouveau panneau au prochain 3MF")
p2 = st["panels"][1]
p2.send({"command": "init"})
ok(cmds(p2) == ["hello", "offer"], "il propose le 3MF : %s" % cmds(p2))

print("== il mache deja : le 3MF suivant passe par une notification")
p2.send({"command": "view", "v": "busy"})
n_notes, n_offers = len(st["notes"]), count(p2, "offer")
opened(POKE)
ok(len(st["notes"]) == n_notes + 1 and "Bambu Studio" in st["notes"][-1][1], "notification : %s" % st["notes"][-1][1])
ok(count(p2, "offer") == n_offers and m.PANEL.offer["name"] == "cute baby dragon.3mf", "le panneau garde ce qu'il fait")
p2.send({"command": "view", "v": "rest"})

print("== le panneau se desactive lui-meme (meme reglage que l'onglet)")
n_state = count(w, "state")
p2.send({"command": "panel_mode", "mode": "off"})
ok(m.panel_mode() == "off" and w.wait("state", n_state + 1)["panel"] == "off" and last(p2, "hello")["mode"] == "off",
   "« rien » choisi dans le panneau : garde, l'onglet et le panneau le savent")
p2.send({"command": "panel_mode", "mode": "panel"})
ok(m.panel_mode() == "panel" and last(p2, "hello")["mode"] == "panel", "remis depuis le panneau")

print("== le panneau change le plan : l'onglet le recoit, sans echo")
n_an = count(p2, "analysis")
p2.send({"command": "eat"})
tok = p2.wait("analysis", n_an + 1)["token"]
if tok in m.CONVERTER.jobs and "files" in m.CONVERTER.jobs[tok]:
    pf = [{"plates": f["plates"], "slots": [{"src": s["src"], "base": s["base"], "color": None, "extra": False} for s in f["slots"]]}
          for f in m.CONVERTER.jobs[tok]["files"]]
    pf[0]["slots"].append({"src": [], "base": 0, "color": "#00FF00", "extra": True})
    n_w, n_p = count(w, "plan"), count(p2, "plan")
    p2.send({"command": "plan", "token": tok, "files": pf})
    ok(count(w, "plan") == n_w + 1 and last(w, "plan")["files"] == pf and count(p2, "plan") == n_p, "l'onglet a le plan du panneau, le panneau ne le recoit pas en retour")
    ok(m.CONVERTER.jobs[tok]["plan"] == pf, "garde pour la conversion")
    n = len(p2.posts); p2.send({"command": "init"})
    ok("plan" in cmds(p2, n), "la page du panneau qui redemarre le retrouve")
    p2.send({"command": "plan", "token": "inconnu", "files": pf})
    ok(count(w, "plan") == n_w + 1, "plan d'un travail inconnu : ignore")
else:
    ok(False, "travail du panneau introuvable pour le test du plan")

print("== reglage : notification seule, ou rien")
n_state = count(w, "state")
tab.on_message({"command": "panel_mode", "mode": "notif"})
ok(w.wait("state", n_state + 1)["panel"] == "notif" and m.panel_mode() == "notif", "notification seule : choisie")
ok(p2.posts[-1]["command"] == "hello" and p2.posts[-1]["mode"] == "notif", "le panneau le sait (son texte change)")
p2.close()
n_notes, n_panels = len(st["notes"]), len(st["panels"])
opened(DRAGON)
ok(len(st["notes"]) == n_notes + 1 and len(st["panels"]) == n_panels, "notification, pas de panneau")
tab.on_message({"command": "panel_mode", "mode": "off"})
n_notes = len(st["notes"])
opened(DRAGON)
ok(len(st["notes"]) == n_notes and len(st["panels"]) == n_panels and last(w, "state")["opened"]["name"] == "cute baby dragon.3mf",
   "rien : ni notification ni panneau (l'onglet le montre toujours)")
ok(json.load(open(os.path.join(storage, "options.json"))).get("panel") == "off", "choix garde")
tab.on_message({"command": "panel_mode", "mode": "bidon"})
ok(m.panel_mode() == "panel", "valeur inconnue : le panneau")

print("== bouton des Reglages : la U1 dans Preparer")
tab.on_message({"command": "panel_show"})
ok(len(st["panels"]) == n_panels + 1, "panneau cree")
p3 = st["panels"][-1]
p3.send({"command": "init"})
ok(cmds(p3)[0] == "hello" and cmds(p3)[-1] in ("offer", "rest"), "il s'ouvre : %s" % cmds(p3))
p3.send({"command": "later"})
tab.on_message({"command": "panel_show"})
ok(len(st["panels"]) == n_panels + 1 and p3.shown, "deja la : remontre, pas recree")

print("== projet ouvert hors Telechargements, imprimante d'un autre fabricant")
p3.close()
ext = os.path.join(home, "ailleurs"); os.makedirs(ext)
shutil.copy(DRAGON, os.path.join(ext, "loin.3mf"))
keep = cur.get("printer_model")
cur["printer_model"] = "Bambu Lab H2C"
opened(os.path.join(ext, "loin.3mf"))
p4 = st["panels"][-1]
p4.send({"command": "init"})
o4 = last(p4, "offer")
ok(o4 and o4["file"]["name"] == "loin.3mf" and o4["file"]["printer"] == "Bambu Lab H2C" and o4["file"]["label"] == "",
   "Miam : %s" % (o4["file"] if o4 else None))
n_an = count(p4, "analysis")
p4.send({"command": "eat"})
an4 = p4.wait("analysis", n_an + 1)
ok(an4["file"] == "loin.3mf" and an4["source"]["colors"] >= 1, "mange depuis son dossier : %s, %s couleurs" % (an4["file"], an4["source"]["colors"]))
cur["printer_model"] = keep
p4.send({"command": "view", "v": "an"})
opened(os.path.join(dl, "absent-mais-u1.txt"))
ok(p4.shown and m.PANEL.token == an4["token"], "un projet regle pour la U1 ne range pas une analyse en cours")

print("== Orca sans panneau (version plus ancienne) : notification")
p4.close()
del orca.host.ui.create_dock_panel
n_notes = len(st["notes"])
opened(DRAGON)
ok(len(st["notes"]) == n_notes + 1 and m.PANEL.handle is None, "notification a la place du panneau")
n_err = count(w, "error")
tab.on_message({"command": "panel_show"})
ok(count(w, "error") == n_err + 1 and "2.5.1" in last(w, "error")["text"], "bouton des Reglages : %s" % last(w, "error")["text"])
print("\nsorties :", tmp)
done()
