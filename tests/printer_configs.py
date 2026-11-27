"""Reglages de test pour d'autres imprimantes que la U1 : le vrai profil d'imprimante d'OrcaSlicer
(printers_orca.json : modele, buses, plateau, volume de buse...), avec les filaments et le traitement de
l'exemple U1 (tests/samples/sample_pokeballs.3mf)."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PRINTERS = json.load(open(os.path.join(HERE, "printers_orca.json"), encoding="utf-8"))
AMS = ("#FFFFFF", "#FFEB3B", "#E53935", "#000000")      # bobines chargees (blanc, jaune, rouge, noir)


def config_for(m, base_cfg, name, colors=AMS, types=None, maps=None, extra=None):
    """Reglages « enregistres par Orca » pour l'imprimante name (cle de PRINTERS, ou extra["_base"] : un
    profil imite), avec tes filaments (colors, types) et, pour plusieurs buses, la buse de chacun (maps)."""
    cfg = json.loads(json.dumps(base_cfg))
    extra = dict(extra or {})
    k, old = len(colors), len(cfg["filament_colour"])
    for key in list(cfg):
        v = cfg[key]
        if isinstance(v, list) and len(v) == old and (key in m.FILAMENT_PRESET_KEYS or key.startswith("filament_")):
            cfg[key] = [v[i % old] for i in range(k)]
    cfg["filament_colour"] = list(colors)
    cfg["filament_type"] = list(types or ["PLA"] * k)
    cfg["filament_settings_id"] = ["Mon %s %d" % (t, i + 1) for i, t in enumerate(cfg["filament_type"])]
    cfg.update(json.loads(json.dumps(PRINTERS[name] if name in PRINTERS else extra.pop("_base"))))
    cfg.update(extra)
    n = len(cfg.get("nozzle_diameter") or ["0.4"])
    cfg["flush_multiplier"] = ["1"] * n
    cfg["flush_volumes_matrix"] = [("0" if i == j else "100") for _z in range(n) for i in range(k) for j in range(k)]
    cfg["flush_volumes_vector"] = ["140"] * (2 * k)
    cfg["filament_is_support"] = ["0"] * k
    if maps:
        cfg["filament_map"] = list(maps)
    cfg["print_settings_id"] = "0.20mm Standard"
    return cfg


def imitation(model, nozzles, semm="1", base="Bambu Lab H2D 0.4 nozzle"):
    """Profil imite d'une imprimante qu'Orca n'a pas encore (Bambu Lab H3C, P3C...)."""
    return {"_base": dict(PRINTERS[base], printer_model=model, printer_settings_id=model + " 0.4 nozzle",
                          nozzle_diameter=["0.4"] * nozzles, single_extruder_multi_material=semm,
                          nozzle_volume=["120"] * nozzles, printer_extruder_id=[str(i + 1) for i in range(nozzles)],
                          printer_extruder_variant=["Direct Drive Standard"] * nozzles)}
