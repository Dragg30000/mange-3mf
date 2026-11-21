"""Lance tous les tests de Mange-3MF : python tests/run_all.py  (Python 3.12 ou plus, sans OrcaSlicer)."""
import os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = [
    ("test_core.py", "peinture, lecture d'un vrai 3MF MakerWorld, conversion simple"),
    ("test_multi.py", "7 couleurs sur 6 plaques : un fichier, 7 filaments, rien de fusionné"),
    ("test_template.py", "réglages Orca 2.5.1 : variantes de buse, purge, profils de base"),
    ("test_variants.py", "Snapmaker Orca, plateau plus grand, 3MF sans réglages, fichiers refusés, profil changé"),
    ("test_origin.py", "origine des fichiers : projets d'OrcaSlicer 2.5.1, Bambu Studio, Snapmaker Orca"),
    ("test_presets.py", "préréglages d'Orca, couleur choisie, dossier des fichiers convertis"),
    ("test_lang.py", "langues : textes français et anglais, page de l'onglet, retraduction"),
    ("test_plugin.py", "plugin dans un faux OrcaSlicer : onglet, messages, écriture, notifications, langue"),
]

SAMPLES = os.path.join(HERE, "samples")
missing = [n for n in ("sample_dragon.3mf", "sample_pokeballs.3mf") if not os.path.isfile(os.path.join(SAMPLES, n))]
if missing:
    print("Il manque les 3MF d'exemple %s dans tests/samples (ils ne sont pas publiés, pour des raisons de licence)." % ", ".join(missing))
    print("Voir tests/samples/PROVENANCE.md pour les récupérer, puis relance les tests.")
    sys.exit(2)

total_ok = total_fail = 0
failed = []
for name, what in TESTS:
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, name)], capture_output=True, text=True, cwd=HERE)
    out = p.stdout + p.stderr
    n_ok = sum(1 for l in out.splitlines() if l.startswith("  ok  "))
    n_fail = sum(1 for l in out.splitlines() if l.startswith("  FAIL"))
    total_ok += n_ok
    total_fail += n_fail
    status = "OK " if p.returncode == 0 else "ECHEC"
    print("%s  %-17s %4d verifications  %5.1fs  (%s)" % (status, name, n_ok + n_fail, time.time() - t0, what))
    if p.returncode != 0:
        failed.append(name)
        print("\n".join("      " + l for l in out.splitlines() if l.startswith("  FAIL") or "Error" in l or "Traceback" in l))
print("\n%d verifications reussies, %d en echec." % (total_ok, total_fail))
sys.exit(1 if failed else 0)
