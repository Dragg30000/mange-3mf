"""Origine des fichiers : OrcaSlicer 2.5.1 signe ses projets « BambuStudio-02.08.01.55 » et ajoute
l'etiquette « OrcaSlicer 2.5.1 ». Reglages memorises, etiquettes de la liste, projet a convertir ou non."""
import io, json, os, zipfile
from common import ok, done, sample, fake_template, plan_of, OUT
import mange_3mf_any as m
import fake_orca


def project(app, tag=None, printer="Snapmaker U1"):
    """Projet minimal : modele + reglages, signe comme demande."""
    z = zipfile.ZipFile(sample("sample_pokeballs.3mf"))
    files = {n: z.read(n) for n in z.namelist()}
    main = files[m.MAIN_MODEL].decode("utf-8")
    import re
    main = re.sub(r'[ \t]*<metadata name="(Application|OrcaSlicer)">[^<]*</metadata>\r?\n?', "", main)
    meta = ' <metadata name="Application">%s</metadata>\n' % app + (' <metadata name="OrcaSlicer">%s</metadata>\n' % tag if tag else "")
    main = re.sub(r"(<model\b[^>]*>\r?\n?)", lambda mm: mm.group(1) + meta, main, count=1)
    files[m.MAIN_MODEL] = main.encode("utf-8")
    cfg = json.loads(files[m.PROJECT_CFG])
    cfg["printer_model"] = printer
    files[m.PROJECT_CFG] = json.dumps(cfg).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for n, d in files.items():
            out.writestr(n, d)
    return buf.getvalue()


print("== reglages memorises")
cfg = fake_template().config
t = m.Template.from_3mf_bytes(fake_orca.template_3mf_bytes(cfg))
ok(t.application == "BambuStudio-02.08.01.55" and t.orca_tag == "2.5.1", "projet d'OrcaSlicer 2.5.1 accepte (%s, %s)" % (t.application, t.orca_tag))
t2 = m.Template.from_3mf_bytes(project("OrcaSlicer-2.2.0"))
ok(t2.orca_tag == "2.2.0", "ancien OrcaSlicer sans etiquette accepte, etiquette %s" % t2.orca_tag)
for app, tag in (("BambuStudio-02.03.01.51", None), ("Snapmaker_Orca-2.4.2", None), ("Snapmaker_Orca-2.4.2", "2.4.2")):
    try:
        m.Template.from_3mf_bytes(project(app, tag)); ok(False, "%s refuse" % app)
    except m.ConvertError as e:
        ok("OrcaSlicer" in str(e), "%s%s refuse : %s" % (app, " + etiquette" if tag else "", e))

print("== origine d'un 3MF")
cases = [
    (("BambuStudio-02.08.01.55", "2.5.1"), "orca", "OrcaSlicer 2.5.1"),
    (("OrcaSlicer-2.2.0", None), "orca", "OrcaSlicer 2.2.0"),
    (("BambuStudio-02.03.01.51", None), "bambu", "Bambu Studio 02.03.01.51"),
    (("Snapmaker_Orca-2.4.2", None), "snapmaker", "Snapmaker Orca 2.4.2"),
]
for (app, tag), kind, label in cases:
    src = m.Source3MF(project(app, tag), "x.3mf")
    ok(src.kind == kind and src.app_label() == label, "%s%s -> %s, « %s »" % (app, " + OrcaSlicer " + tag if tag else "", src.kind, src.app_label()))

print("== liste des Telechargements : a convertir ou non")
lst = [
    ("orca_u1.3mf", ("BambuStudio-02.08.01.55", "2.5.1"), "Snapmaker U1", "OrcaSlicer", False),
    ("orca_x1c.3mf", ("BambuStudio-02.08.01.55", "2.5.1"), "Bambu Lab X1 Carbon", "OrcaSlicer", True),
    ("bambu_u1.3mf", ("BambuStudio-02.03.01.51", None), "Snapmaker U1", "Bambu Studio", True),
    ("snap_u1.3mf", ("Snapmaker_Orca-2.4.2", None), "Snapmaker U1", "Snapmaker Orca", True),
]
for name, (app, tag), printer, label, todo in lst:
    path = os.path.join(OUT, name)
    open(path, "wb").write(project(app, tag, printer))
    info = m.sniff_3mf(path)
    ok(m.source_label(info) == label and m.needs_conversion(info) == todo,
       "%s : « %s », %s" % (name, m.source_label(info), "à convertir" if m.needs_conversion(info) else "déjà pour la U1"))

print("== projet converti avec des reglages d'un ancien OrcaSlicer : etiquette ajoutee")
src = m.Source3MF(open(sample("sample_dragon.3mf"), "rb").read(), "dragon.3mf")
res = m.convert(src, t2, plan_of(m.analyze(src, t2)))
out = m.Source3MF(res[0]["data"], res[0]["name"])
ok(out.application == "OrcaSlicer-2.2.0" and out.meta.get("OrcaSlicer") == "2.2.0" and out.kind == "orca",
   "Application %s + OrcaSlicer %s" % (out.application, out.meta.get("OrcaSlicer")))
path = os.path.join(OUT, "dragon - U1.3mf")
open(path, "wb").write(res[0]["data"])
info = m.sniff_3mf(path)
ok(not m.needs_conversion(info) and m.source_label(info) == "OrcaSlicer", "le fichier converti n'est plus « à convertir »")

done()
