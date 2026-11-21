"""Reglages du projet converti a partir de reglages « OrcaSlicer 2.5.1 » complets : une valeur par
filament, une valeur par variante de buse (Standard / Haut debit), purge, profils de base."""
import os
from common import ok, done, plan_of, variant_template, VARIANT_PROFILES, OUT
import mange_3mf_any as m
import make_samples

vt = variant_template()
tc = vt.config
k = len(VARIANT_PROFILES)
ok(vt.slot_count == 5 and vt.filament_total == 6 and vt.head_count == 4, "5 vrais filaments, 1 melange, 4 tetes")

print("== 7 filaments construits depuis les cases 1,2,3,4,5,2,1")
bases = [0, 1, 2, 3, 4, 1, 0]
cols = ["#111111", "#222222", "#333333", None, "#555555", "#666666", "#777777"]
cfg = m.build_project_config(vt, [{"base": b, "color": c} for b, c in zip(bases, cols)])
n = len(bases)
ok(cfg["filament_settings_id"] == [VARIANT_PROFILES[b][2] for b in bases], "profils %s" % cfg["filament_settings_id"])
ok(cfg["filament_ids"] == ["ID%d" % (b + 1) for b in bases], "identifiants des profils")
ok(cfg["filament_type"] == [VARIANT_PROFILES[b][1] for b in bases], "matieres")
ok(cfg["filament_density"] == [tc["filament_density"][b] for b in bases], "reglage a une valeur par filament")
ok(cfg["filament_colour"] == ["#111111", "#222222", "#333333", "#1E5BD8", "#555555", "#666666", "#777777"],
   "couleurs du modele, case sans couleur gardee : %s" % cfg["filament_colour"])
ok(cfg["filament_multi_colour"] == cfg["filament_colour"] and cfg["filament_colour_type"] == ["1"] * n, "couleurs pleines")
# variantes de buse : deux lignes par filament
ok(cfg["filament_self_index"] == [str(j + 1) for j in range(n) for _ in (0, 1)], "filament_self_index %s" % cfg["filament_self_index"])
ok(cfg["filament_extruder_variant"] == ["Direct Drive Standard", "Direct Drive High Flow"] * n, "variantes")
ok(cfg["nozzle_temperature"] == [tc["nozzle_temperature"][2 * b + v] for b in bases for v in (0, 1)],
   "temperatures Standard / Haut debit du bon profil %s" % cfg["nozzle_temperature"])
ok(cfg["pressure_advance"] == [tc["pressure_advance"][2 * b + v] for b in bases for v in (0, 1)], "pressure advance par variante")
bad = [key for key in m.FILAMENT_VARIANT_KEYS if key in cfg and isinstance(cfg[key], list) and len(cfg[key]) != 2 * n]
ok(not bad, "tous les reglages a variantes ont 2 x 7 valeurs (%s)" % bad[:5])
bad = [key for key, v in cfg.items() if isinstance(v, list) and key in m.FILAMENT_PRESET_KEYS
       and key not in m.FILAMENT_VARIANT_KEYS and len(v) != n]
ok(not bad, "tous les autres reglages de filament ont 7 valeurs (%s)" % bad[:5])
# tete et buse prevues : par place pour les 5 premieres, sinon celles du profil
ok(cfg["filament_map"] == ["1", "2", "3", "4", "1", "2", "1"], "tetes prevues %s" % cfg["filament_map"])
ok(cfg["filament_volume_map"] == ["0", "1", "1", "0", "1", "1", "0"], "buses prevues %s" % cfg["filament_volume_map"])
ok(cfg["filament_map_mode"] == "Auto For Flush", "mode d'attribution des tetes inchange")
# couleurs melangees retirees
ok(cfg["filament_is_mixed"] == ["0"] * n and cfg["filament_mixed_components"] == [""] * n
   and cfg["filament_mixed_sublayer_ratios"] == [""] * n, "plus de couleur melangee")
# profils de base
ok(cfg["inherits_group"] == ["proc"] + ["inh%d" % (b + 1) for b in bases] + ["prn"], "inherits_group")
ok(cfg["different_settings_to_system"] == ["dp"] + ["d%d" % (b + 1) for b in bases] + ["dprn"], "different_settings_to_system")
ok(cfg["compatible_process_expression_group"] == ["c%d" % (b + 1) for b in bases], "compatible_process_expression_group")
# purge
ok(cfg["flush_volumes_vector"] == [tc["flush_volumes_vector"][2 * b + v] for b in bases for v in (0, 1)], "purge par filament")
mat = cfg["flush_volumes_matrix"]
ok(len(mat) == 4 * n * n, "matrice 7x7 pour 4 buses")
good = True
for z in range(4):
    for i, bi in enumerate(bases):
        for j, bj in enumerate(bases):
            v = mat[z * n * n + i * n + j]
            if i == j:
                want = "0"
            elif bi != bj:
                want = str(1000 * z + 10 * bi + bj)
            else:
                want = m._fmt_num(float(cfg["flush_volumes_vector"][2 * i]) + float(cfg["flush_volumes_vector"][2 * j + 1]))
            if v != want:
                good = False
                print("   buse %d, %d -> %d : %s au lieu de %s" % (z, i, j, v, want))
ok(good, "purge recopiee entre profils differents, calculee entre couleurs du meme profil")
ok(tc["filament_settings_id"] == [p for _c, _t, p in VARIANT_PROFILES], "reglages memorises intacts")

print("== moins de couleurs que de cases")
cfg4 = m.build_project_config(vt, [{"base": b, "color": None} for b in (0, 1, 2, 3)])
ok(len(cfg4["filament_colour"]) == 4 and len(cfg4["nozzle_temperature"]) == 8 and len(cfg4["flush_volumes_matrix"]) == 64,
   "4 filaments, 8 lignes, purge 4x4x4")

print("== conversion complete avec ces reglages")
path = make_samples.bambu_multiplate(os.path.join(OUT, "synthetic_x1c_7colors.3mf"))
src = m.Source3MF(open(path, "rb").read(), "P.3mf")
ana = m.analyze(src, vt)
f0 = ana["files"][0]
print("  ", [(s["n"], s.get("name"), s["src"], ana["profiles"][s["base"]]["name"]) for s in f0["slots"]])
ok(all(ana["profiles"][s["base"]]["base"] == "PLA" for s in f0["slots"]), "couleurs PLA -> profils PLA (pas le PETG)")
res = m.convert(src, vt, plan_of(ana))
out = m.Source3MF(res[0]["data"], res[0]["name"])
ok(len(out.config["filament_colour"]) == 7 and len(out.config["filament_self_index"]) == 14, "projet a 7 filaments, 14 lignes")
ok(not res[0]["report"]["warnings"], "pas d'alerte : %s" % res[0]["report"]["warnings"])

print("== couleur PETG : profil PETG meme hors de sa case")
e = {"src": [9], "color": "#00AA00", "base": "PETG"}
ok(m.default_profile(e, 0, vt) == 2, "profil PETG Rouge (case 3) pour du PETG vert en case 1")
e = {"src": [9], "color": "#00AA00", "base": "TPU"}
ok(m.default_profile(e, 1, vt) == 1, "pas de profil TPU : on garde la case")
e = {"src": [9], "color": "#2F7F33", "base": "PLA"}
ok(m.default_profile(e, 6, vt) == 4, "7e couleur PLA verte -> profil PLA Vert")

done()
