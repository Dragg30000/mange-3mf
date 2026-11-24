"""Langues : table des textes complete, page de l'onglet, retraduction, analyse et conversion en anglais."""
import json, os, re, string
from common import ok, done, sample, fake_template, plan_of, OUT
import make_samples
import mange_3mf_any as m

SRC = open(m.__file__, encoding="utf-8").read()
FMT = string.Formatter()


def fields(text):
    return {int(f[1]) for f in FMT.parse(text) if f[1] is not None and f[1].isdigit()}


print("== table des textes")
langs = list(m.TEXTS)
ok(langs[:2] == ["fr", "en"] and m.DEFAULT_LANG in m.TEXTS, "langues : %s" % langs)
ref = set(m.TEXTS["fr"])
for lang in langs:
    keys = set(m.TEXTS[lang])
    ok(keys == ref, "%s : memes textes que le francais (en trop %s, manquants %s)" % (lang, sorted(keys - ref), sorted(ref - keys)))
bad = []
for key in ref:
    want = fields(m.TEXTS["fr"][key])
    for lang in langs:
        text = m.TEXTS[lang].get(key, "")
        got = fields(text)
        if key == "when_saved":       # jour, mois, annee, heure, minute : chaque langue prend ce qu'elle veut
            if not got <= set(range(5)):
                bad.append((lang, key))
        elif got != want:
            bad.append((lang, key))
        try:
            text.format(1, 2, 3, 4, 5)
        except (ValueError, IndexError, KeyError) as e:
            bad.append((lang, key, str(e)))
ok(not bad, "memes valeurs {0} {1}... dans chaque langue, textes formatables (%s)" % bad[:5])
ok(all(m.TEXTS[lang]["lang_name"] for lang in langs), "nom de chaque langue")
ok(not any("%s" in t or "%d" in t for lang in langs for t in m.TEXTS[lang].values()), "pas de %s / %d oublies")

print("== textes demandes par le code et par la page")
code = SRC[:SRC.index("TEXTS = {")] + SRC[SRC.index("DEFAULT_LANG = "):SRC.index('PAGE = r"""')] + SRC[SRC.index("def page_html"):]
used = set(re.findall(r'\btr\(\s*"(\w+)"', code))
used |= set(re.findall(r'"((?:err|w|n|p|out|cap)_\w+)"', code))
used -= {"out_dir"}   # cle des options, pas un texte
missing = sorted(k for k in used if k not in ref and not k.endswith("_"))   # "col_" + nom : plus bas
ok(len(used) > 40 and not missing, "%d textes utilises par le plugin, tous traduits (manquants %s)" % (len(used), missing))
page = m.PAGE
ui = set(re.findall(r'data-t[hpt]?="(\w+)"', page)) | set(re.findall(r'\bt\("(\w+)"', page)) | set(re.findall(r'"(bed_\w+)"', page))
missing = sorted(k for k in ui if k not in ref)
ok(len(ui) > 60 and not missing, "%d textes utilises par la page, tous traduits (manquants %s)" % (len(ui), missing))
keys = set()
for r in range(0, 256, 15):
    for g in range(0, 256, 15):
        for b in range(0, 256, 15):
            keys.add(m._color_key("#%02X%02X%02X" % (r, g, b)))
missing = sorted(k for k in keys if k and "col_" + k not in ref)
ok(None not in keys and not missing, "%d noms de couleur, tous traduits (%s)" % (len(keys), missing))

print("== page de l'onglet")
for lang in langs:
    html = m.page_html(lang)
    ok('<html lang="%s">' % lang in html and '"__LANG__"' not in html and "__TEXTS__" not in html, "page en %s" % lang)
    j = html.index("var L=") + len("var L=")
    blob = html[j:html.index(";\nvar nav", j)]
    ok("</" not in blob and json.loads(blob) == m.TEXTS, "  textes dans la page (JSON sans « </ »)")
ok('var lang="en"' in m.page_html("en") and 'var lang="fr"' in m.page_html("fr"), "langue de depart dans la page")

print("== page du panneau de Preparer")
panel = m.PANEL_PAGE
used = set(re.findall(r'data-t="(\w+)"', panel)) | set(re.findall(r'\bt\("(\w+)"', panel))
used |= {k for pair in re.findall(r'\?"(\w+)":"(\w+)"', panel) for k in pair if k in ref or k.startswith("pn_")}
missing = sorted(k for k in used if k not in ref)
ok(len(used) > 30 and not missing, "%d textes utilises par le panneau, tous traduits (manquants %s)" % (len(used), missing))
for lang in langs:
    html = m.panel_html(lang)
    ok('<html lang="%s">' % lang in html and not any(x in html for x in ("__LANG__", "__TEXTS__", "__FONT__", "__U1CSS__", "__U1SVG__")),
       "panneau en %s" % lang)
    j = html.index("var L=") + len("var L=")
    blob = html[j:html.index(";\nvar nav", j)]
    texts = json.loads(blob)
    ok("</" not in blob and set(texts) == set(langs) and all(used <= set(texts[x]) for x in texts),
       "  ses textes dans chaque langue (%d)" % len(texts[lang]))
ok(m.panel_html("en").count('<template id="u1t">') == 1 and m.panel_html("en").count("@font-face") == 1,
   "la U1 et la police de l'onglet, une fois")

print("== langue d'Orca ou du systeme")
for code_, want in (("fr_FR", "fr"), ("fr-CA", "fr"), ("FR", "fr"), ("French_France", "fr"), ("fr_FR.UTF-8", "fr"),
                    ("en_US", "en"), ("en-GB", "en"), ("de_DE", "en"), ("zh_CN", "en"), ("", "en"), (None, "en"), ("C", "en")):
    ok(m.lang_of(code_) == want, "%r -> %s" % (code_, m.lang_of(code_)))
ok(m.current_language() == "fr", "langue du systeme des tests : fr (LANGUAGE=fr_FR)")

print("== retraduction")
m.set_language("fr")
w = m.tr("w_plate", 2, m.tr("unnamed"), m.tr("w_too_big", 300.4, 199.6))
ok(w == "Plaque 2 « sans nom » : trop grande pour le plateau de la U1 (300 x 200 mm).", "francais : %s" % w)
m.set_language("en")
ok(m.relocalize(w) == "Plate 2 “unnamed”: too large for the U1 bed (300 x 200 mm).", "anglais : %s" % m.relocalize(w))
data = {"a": [w, m.color_name("#E53935"), 3, None], "b": {"c": m.tr("dest_in", m.tr("downloads"))}}
loc = m.relocalize(data)
ok(loc == {"a": ["Plate 2 “unnamed”: too large for the U1 bed (300 x 200 mm).", "red", 3, None], "b": {"c": "in Downloads"}},
   "dict et listes retraduits : %s" % loc)
ok(all(type(x) is str for x in (loc["a"][0], loc["a"][1], loc["b"]["c"])), "  chaines ordinaires (JSON)")
m.set_language("de")
ok(m.current_language() == "en", "langue inconnue -> anglais")
ok(m.tr("no_such_key") == "no_such_key", "texte absent : sa cle")

print("== analyse et conversion en anglais")
m.set_language("en")
path = make_samples.bambu_multiplate(os.path.join(OUT, "Pokeballs.3mf"))      # 7 couleurs, 6 plaques
src = m.Source3MF(open(path, "rb").read(), "Pokeballs.3mf")
tpl = fake_template(types=("PLA", "PLA", "PETG", "PLA"))
ana = m.analyze(src, tpl, one_per_plate=True, with_thumbs=False)
names = {s["name"] for f in ana["files"] for s in f["slots"] if not s["pad"]}
english = {m.TEXTS["en"][k] for k in m.TEXTS["en"] if k.startswith("col_")}
ok(names and names <= english, "couleurs en anglais : %s" % sorted(names))
ok(all(p["cname"] in english for p in ana["profiles"]), "profils en anglais : %s" % [p["cname"] for p in ana["profiles"]])
multi = [f["name"] for f in ana["files"] if len(f["plate_ids"]) == 1]
ok(multi and all(re.search(r" - U1-by-Dragg - plate \d+\.3mf$", n) for n in multi), "noms des fichiers : %s" % multi[:2])
plan = plan_of(ana)
j = next(i for i, s in enumerate(ana["files"][0]["slots"]) if not s["pad"] and s["ftype"] == "PLA")
plan[0]["slots"][j]["base"] = 2                      # profil PETG pour une couleur en PLA
res = m.convert(src, tpl, plan)
warns = [w for r in res for w in r["report"]["warnings"]]
ok(any("the model wants PLA" in w and "PETG" in w for w in warns), "alerte de matiere en anglais : %s" % warns[:1])
ok(m.output_name(src, [src.plates[0], src.plates[1]], True).endswith(" - U1-by-Dragg - plates 1-2.3mf"), "nom pour 2 plaques")
src2 = m.Source3MF(open(path, "rb").read(), "Pokeballs - U1 - plaques 1-2.3mf")
ok(m.output_name(src2, [src2.plates[0]], False) == "Pokeballs - U1-by-Dragg.3mf", "ancien suffixe francais retire")
src3 = m.Source3MF(open(path, "rb").read(), "Pokeballs - U1-by-Dragg - plate 2.3mf")
ok(m.output_name(src3, [src3.plates[0]], False) == "Pokeballs - U1-by-Dragg.3mf", "suffixe U1-by-Dragg pas double")
ok(m.output_name(src3, [src3.plates[1]], True) == "Pokeballs - U1-by-Dragg - plate 2.3mf", "suffixe U1-by-Dragg pas double (plaque)")
try:
    m.Source3MF(b"hello", "x.3mf"); ok(False, "archive refusee")
except m.ConvertError as e:
    ok(str(e) == "this file is not a 3MF (unreadable archive)", "erreur en anglais : %s" % e)
    m.set_language("fr")
    ok(m.relocalize(m.message_of(e)) == "ce fichier n'est pas un 3MF (archive illisible)", "  et retraduite en francais")
done()
