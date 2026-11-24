"""Captures du panneau de Preparer pour les modes d'emploi : docs/captures/6_panneau.png (francais) et
docs/captures/en/6_panneau.png (anglais). Trois ecrans du vrai panneau cote a cote : la U1 reclame le 3MF,
couleurs et profils (avec une couleur en plus), fichier pret. Messages reels du plugin (check_panel.prepare).
Usage : python tests/ui/make_panel_captures.py   (Node, playwright-core installe ici, Chrome)."""
import os, subprocess, sys
UI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(UI))
sys.path.insert(0, UI)
import check_panel

for lang, out in (("fr", os.path.join(ROOT, "docs", "captures")), ("en", os.path.join(ROOT, "docs", "captures", "en"))):
    page, data = check_panel.prepare(lang)
    subprocess.run(["node", os.path.join(UI, "shoot_panel.js"), page, data, os.path.join(out, "6_panneau.png"), lang], check=True, cwd=UI)
    print("panneau (%s) : %s" % (lang, os.path.join(out, "6_panneau.png")))
