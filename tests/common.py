"""Outils communs aux tests de Mange-3MF (sans OrcaSlicer)."""
import json, os, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLES = os.path.join(HERE, "samples")
OUT = tempfile.mkdtemp(prefix="mange3mf_tests_")   # fichiers fabriques pendant les tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

FAIL = []
ORCA_APP = "BambuStudio-02.08.01.55"   # ce qu'ecrit OrcaSlicer 2.5.1, avec l'etiquette « OrcaSlicer 2.5.1 »


def ok(cond, msg):
    print(("  ok  " if cond else "  FAIL") + " " + msg)
    if not cond:
        FAIL.append(msg)


def done():
    if FAIL:
        print("\n%d ECHEC(S)" % len(FAIL))
        sys.exit(1)
    print("\nTOUT OK")


def sample(name):
    return os.path.join(SAMPLES, name)


def fake_template(slot_colors=("#FFFFFF", "#FFEB3B", "#E53935", "#000000"), types=("PLA",) * 4):
    """Reglages « utilisateur » de test : ceux de l'exemple U1, avec 4 cases PLA."""
    import mange_3mf_any as m
    src = zipfile.ZipFile(sample("sample_pokeballs.3mf"))
    cfg = json.loads(src.read(m.PROJECT_CFG))
    cfg["filament_colour"] = list(slot_colors)
    cfg["filament_type"] = list(types)
    cfg["filament_settings_id"] = ["Mon PLA %d" % (i + 1) for i in range(len(slot_colors))]
    cfg["printer_settings_id"] = "Snapmaker U1 (0.4 nozzle)"
    cfg["print_settings_id"] = "0.20 Standard @Snapmaker U1 (0.4 nozzle)"
    return m.Template(cfg, ORCA_APP, "2.5.1")


def plan_of(ana):
    """Plan propose par l'analyse, tel que l'interface le renvoie pour la conversion."""
    return [{"plates": f["plates"], "slots": [{"src": s["src"], "base": s["base"]} for s in f["slots"]]}
            for f in ana["files"]]


VARIANT_PROFILES = [  # (couleur, matiere, profil)
    ("#FFFFFF", "PLA", "PLA Blanc"), ("#000000", "PLA", "PLA Noir"), ("#E53935", "PETG", "PETG Rouge"),
    ("#1E5BD8", "PLA", "PLA Bleu"), ("#2E7D32", "PLA", "PLA Vert"), ("#808080", "PLA", "Melange 1+2"),
]


def variant_template():
    """Reglages « OrcaSlicer 2.5.1 » plus complets : 5 filaments + 1 couleur melangee, deux variantes de
    buse par filament (Standard / Haut debit), purge pour 4 buses, profils de base, tetes prevues."""
    import mange_3mf_any as m
    cfg = dict(fake_template().config)
    k = len(VARIANT_PROFILES)
    old = len(cfg["filament_colour"])
    for key in list(cfg):
        v = cfg[key]
        if isinstance(v, list) and len(v) == old and (key in m.FILAMENT_PRESET_KEYS or key.startswith("filament_")):
            cfg[key] = [v[i % old] for i in range(k)]
    cfg["filament_colour"] = [c for c, _t, _n in VARIANT_PROFILES]
    cfg["filament_multi_colour"] = list(cfg["filament_colour"])
    cfg["filament_colour_type"] = ["1"] * k
    cfg["filament_type"] = [t for _c, t, _n in VARIANT_PROFILES]
    cfg["filament_settings_id"] = [n for _c, _t, n in VARIANT_PROFILES]
    cfg["filament_ids"] = ["ID%d" % (i + 1) for i in range(k)]
    cfg["filament_is_mixed"] = ["0"] * (k - 1) + ["1"]
    cfg["filament_mixed_components"] = [""] * (k - 1) + ["1,2"]
    cfg["filament_mixed_sublayer_ratios"] = [""] * (k - 1) + ["0.5,0.5"]
    cfg["filament_self_index"] = [str(i + 1) for i in range(k) for _v in (0, 1)]
    cfg["filament_extruder_variant"] = ["Direct Drive Standard", "Direct Drive High Flow"] * k
    for key in m.FILAMENT_VARIANT_KEYS:
        if key in cfg and key != "filament_extruder_variant":
            cfg[key] = [str(cfg[key][0]) for _ in range(2 * k)]
    # valeurs distinctes par filament et par variante, pour suivre les recopies
    cfg["nozzle_temperature"] = [str(200 + 10 * i + v) for i in range(k) for v in (0, 5)]
    cfg["pressure_advance"] = ["0.0%d%d" % (i + 1, v) for i in range(k) for v in (1, 2)]
    cfg["filament_density"] = [str(1.20 + i / 100.0) for i in range(k)]
    cfg["inherits_group"] = ["proc"] + ["inh%d" % (i + 1) for i in range(k)] + ["prn"]
    cfg["different_settings_to_system"] = ["dp"] + ["d%d" % (i + 1) for i in range(k)] + ["dprn"]
    cfg["compatible_process_expression_group"] = ["c%d" % (i + 1) for i in range(k)]
    cfg["flush_multiplier"] = ["1", "1", "1", "1"]
    cfg["flush_volumes_vector"] = [str(100 + i) for i in range(2 * k)]
    cfg["flush_volumes_matrix"] = [("0" if i == j else str(1000 * z + 10 * i + j))
                                   for z in range(4) for i in range(k) for j in range(k)]
    cfg["filament_map"] = ["1", "2", "3", "4", "1", "1"]
    cfg["filament_volume_map"] = ["0", "1", "1", "0", "1", "0"]
    cfg["filament_map_mode"] = "Auto For Flush"
    cfg["nozzle_diameter"] = ["0.4"] * 4
    return m.Template(cfg, ORCA_APP, "2.5.1")
