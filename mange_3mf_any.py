# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Mange-3MF (Snapmaker U1)"
# description = "Tab that converts any 3MF (MakerWorld / Bambu Studio, Snapmaker Orca, other Orca forks) into an OrcaSlicer project for the Snapmaker U1: exactly the model's colors, painting and plates kept, with your own settings. In English or French."
# author = "Dragg avec son ami Claude"
# version = "0.4.0"
# ///
"""Mange-3MF - convertit un 3MF d'un autre logiciel en projet OrcaSlicer pour la Snapmaker U1.

Sources acceptees : projets Bambu Studio (MakerWorld), Snapmaker Orca, OrcaSlicer et ses variantes
(Creality, Elegoo, Anycubic...), 3MF sans reglages. Pas les fichiers deja tranches (.gcode.3mf).

Ce que fait la conversion :

* la couleur de chaque piece est gardee : filament des objets et des pieces, peinture, plages de
  couches, changements d'outil, filaments par fonction (parois, remplissage...) ;
* exactement les couleurs du modele : un seul fichier avec toutes les plaques et un filament par
  couleur (7 couleurs -> 7 filaments), sans decoupage ni fusion. Orca garde au moins un filament
  par tete de la U1 (4) : les cases en trop restent les bobines actuelles, sans servir ;
* les plaques sont gardees (noms, pieces dessus), replacees sur le plateau de la U1 ;
* les reglages viennent de TON OrcaSlicer (imprimante, buses, profil, plaque, filaments), memorises
  d'un clic : rien n'est repris des reglages de l'auteur. Chaque couleur prend le profil d'un de tes
  filaments (meme matiere, couleur la plus proche), avec ses reglages Haut debit / Standard ;
* les couleurs vont si possible dans les cases dont la bobine actuelle est la plus proche.

L'interface est un onglet « Mange-3MF » d'Orca, en francais ou en anglais (langue d'Orca, ou au
choix dans l'onglet ; tous les textes sont dans TEXTS). Le fichier converti s'ouvre ensuite avec
Fichier > Ouvrir (Ctrl+O) : un plugin ne peut pas ouvrir un projet lui-meme.

Plugin communautaire, non officiel. Licence GPL-3.0.
"""

import base64
import io
import itertools
import json
import math
import os
import re
import threading
import time
import zipfile
import xml.etree.ElementTree as ET

try:
    import orca
except ImportError:  # tests hors d'OrcaSlicer
    orca = None

VERSION = "0.4.1"
PLUGIN_NAME = "Mange-3MF"

# --------------------------------------------------------------------------- fichiers du 3MF

MAIN_MODEL = "3D/3dmodel.model"
MAIN_RELS = "3D/_rels/3dmodel.model.rels"
PKG_RELS = "_rels/.rels"
PROJECT_CFG = "Metadata/project_settings.config"
MODEL_CFG = "Metadata/model_settings.config"
LAYER_RANGES = "Metadata/layer_config_ranges.xml"
CUSTOM_GCODE = "Metadata/custom_gcode_per_layer.xml"
LAYER_HEIGHTS = "Metadata/layer_heights_profile.txt"
BRIM_EARS = "Metadata/brim_ear_points.txt"
CUT_INFO = "Metadata/cut_information.xml"
PRUSA_CFG = "Metadata/Slic3r_PE.config"

# Fichiers de la source qu'on ne recopie pas : vignettes et resultats de tranchage de l'auteur,
# reglages embarques de l'auteur, fichiers recrees par la conversion.
_DROP = re.compile(r"""^Metadata/(
      plate_\d+(_small)?\.png | plate_no_light_\d+\.png | top_\d+\.png | pick_\d+\.png
    | plate_\d+\.json | .*\.gcode | .*\.gcode\.md5 | slice_info\.config
    | _rels/model_settings\.config\.rels | filament_sequence\.json | print_profile\.config
    | (print_setting|process_settings|filament_settings|machine_settings)_\d+\.config
    | project_settings\.config | model_settings\.config
)$""", re.X | re.I)

# Reglages qui designent un filament (numero a partir de 1, 0 = par defaut).
FILAMENT_KEYS_NEW = (
    "sparse_infill_filament_id", "outer_wall_filament_id", "inner_wall_filament_id",
    "internal_solid_filament_id", "top_surface_filament_id", "bottom_surface_filament_id",
    "support_filament", "support_interface_filament", "wipe_tower_filament",
)
# Anciens noms (Bambu Studio, vieux projets) : "1" voulait dire "par defaut".
FILAMENT_KEYS_LEGACY = {
    "sparse_infill_filament": "sparse_infill_filament_id", "infill_extruder": "sparse_infill_filament_id",
    "solid_infill_filament": "internal_solid_filament_id", "solid_infill_extruder": "internal_solid_filament_id",
    "top_solid_infill_filament": "top_surface_filament_id",
    "bottom_solid_infill_filament": "bottom_surface_filament_id",
    "wall_filament": "outer_wall_filament_id", "perimeter_extruder": "outer_wall_filament_id",
    "wall_filament_id": "outer_wall_filament_id", "outer_wall_filament": "outer_wall_filament_id",
    "inner_wall_filament": "inner_wall_filament_id",
    "support_material_extruder": "support_filament",
    "support_material_interface_extruder": "support_interface_filament",
}
_LEGACY_ONE_IS_DEFAULT = {k for k, v in FILAMENT_KEYS_LEGACY.items() if v.endswith("_filament_id")}

# Reglages d'un profil de filament (liste de Preset::filament_options() d'OrcaSlicer 2.5.1). Dans les
# reglages d'un projet, chacun a une valeur par filament...
FILAMENT_PRESET_KEYS = frozenset("""
    default_filament_colour required_nozzle_HRC filament_diameter pellet_flow_coefficient
    volumetric_speed_coefficients filament_type filament_soluble filament_is_support
    filament_printable filament_extruder_compatibility filament_max_volumetric_speed
    filament_adaptive_volumetric_speed filament_flow_ratio filament_density
    filament_adhesiveness_category filament_cost filament_minimal_purge_on_wipe_tower
    filament_tower_interface_pre_extrusion_dist filament_tower_interface_pre_extrusion_length
    filament_tower_ironing_area filament_tower_interface_purge_volume
    filament_tower_interface_print_temp nozzle_temperature nozzle_temperature_initial_layer
    cool_plate_temp textured_cool_plate_temp eng_plate_temp hot_plate_temp textured_plate_temp
    cool_plate_temp_initial_layer textured_cool_plate_temp_initial_layer
    eng_plate_temp_initial_layer hot_plate_temp_initial_layer textured_plate_temp_initial_layer
    supertack_plate_temp_initial_layer supertack_plate_temp temperature_vitrification
    reduce_fan_stop_start_freq dont_slow_down_outer_wall slow_down_for_layer_cooling fan_min_speed
    fan_max_speed enable_overhang_bridge_fan overhang_fan_speed overhang_fan_threshold
    close_fan_the_first_x_layers close_additional_fan_first_x_layers first_x_layer_fan_speed
    full_fan_speed_layer initial_layer_fan_speed additional_fan_full_speed_layer
    fan_cooling_layer_time slow_down_layer_time slow_down_min_speed filament_start_gcode
    filament_end_gcode filament_change_extrusion_role_gcode activate_air_filtration
    activate_air_filtration_during_print activate_air_filtration_on_completion
    during_print_exhaust_fan_speed complete_print_exhaust_fan_speed filament_deretraction_speed
    filament_retract_after_wipe filament_retract_before_wipe filament_retract_lift_above
    filament_retract_lift_below filament_retract_lift_enforce filament_retract_restart_extra
    filament_retract_when_changing_layer filament_retraction_length
    filament_retraction_minimum_travel filament_retraction_speed filament_retract_length_toolchange
    filament_retract_restart_extra_toolchange filament_wipe filament_z_hop filament_z_hop_types
    filament_vendor compatible_prints compatible_prints_condition compatible_printers
    compatible_printers_condition inherits filament_wipe_distance additional_cooling_fan_speed
    nozzle_temperature_range_low nozzle_temperature_range_high filament_extruder_variant
    enable_pressure_advance pressure_advance adaptive_pressure_advance
    adaptive_pressure_advance_model adaptive_pressure_advance_overhangs
    adaptive_pressure_advance_bridges chamber_temperature filament_shrink
    filament_shrinkage_compensation_z support_material_interface_fan_speed internal_bridge_fan_speed
    filament_notes ironing_fan_speed filament_ironing_flow filament_ironing_spacing
    filament_ironing_inset filament_ironing_speed filament_loading_speed
    filament_loading_speed_start filament_unloading_speed filament_unloading_speed_start
    filament_toolchange_delay filament_cooling_moves filament_stamping_loading_speed
    filament_stamping_distance filament_cooling_initial_speed filament_cooling_final_speed
    filament_ramming_parameters filament_multitool_ramming filament_multitool_ramming_volume
    filament_multitool_ramming_flow activate_chamber_temp_control chamber_minimal_temperature
    filament_long_retractions_when_cut filament_retraction_distances_when_cut idle_temperature
    filament_change_length filament_flush_volumetric_speed filament_flush_temp
    filament_flush_temp_fast filament_cooling_before_tower filament_ramming_volumetric_speed
    filament_ramming_volumetric_speed_nc filament_ramming_travel_time
    filament_ramming_travel_time_nc filament_pre_cooling_temperature
    filament_pre_cooling_temperature_nc filament_preheat_temperature_delta
    filament_retract_length_nc filament_change_length_nc filament_prime_volume
    filament_prime_volume_nc long_retractions_when_ec retraction_distances_when_ec
    filament_plugin_config_overrides filament_dev_ams_drying_ams_limitations
    filament_dev_ams_drying_temperature filament_dev_ams_drying_time
    filament_dev_ams_drying_heat_distortion_temperature filament_dev_chamber_drying_bed_temperature
    filament_dev_chamber_drying_time filament_dev_drying_softening_temperature
    filament_dev_drying_cooling_temperature
""".split())
# ... sauf ceux-ci, qui ont une valeur par variante de buse de chaque filament (Haut debit /
# Standard sur la U1) : les lignes de chaque filament sont reperees par filament_self_index.
FILAMENT_VARIANT_KEYS = frozenset("""
    filament_flow_ratio filament_max_volumetric_speed filament_ramming_volumetric_speed
    filament_pre_cooling_temperature filament_ramming_travel_time
    filament_ramming_volumetric_speed_nc filament_pre_cooling_temperature_nc
    filament_ramming_travel_time_nc filament_retract_length_nc filament_preheat_temperature_delta
    filament_extruder_variant filament_retraction_length filament_z_hop filament_z_hop_types
    filament_retract_lift_above filament_retract_lift_below filament_retract_lift_enforce
    filament_retract_restart_extra filament_retract_length_toolchange
    filament_retract_restart_extra_toolchange filament_retraction_speed filament_deretraction_speed
    filament_retraction_minimum_travel filament_retract_when_changing_layer filament_wipe
    filament_wipe_distance filament_retract_before_wipe filament_retract_after_wipe
    filament_long_retractions_when_cut filament_retraction_distances_when_cut
    long_retractions_when_ec retraction_distances_when_ec nozzle_temperature_initial_layer
    nozzle_temperature filament_flush_volumetric_speed filament_flush_temp
    filament_cooling_before_tower volumetric_speed_coefficients filament_adaptive_volumetric_speed
    filament_ironing_flow filament_ironing_spacing filament_ironing_inset filament_ironing_speed
    enable_pressure_advance pressure_advance adaptive_pressure_advance
    adaptive_pressure_advance_model adaptive_pressure_advance_overhangs
    adaptive_pressure_advance_bridges fan_min_speed fan_max_speed additional_cooling_fan_speed
    filament_minimal_purge_on_wipe_tower filament_multitool_ramming
    filament_multitool_ramming_volume filament_multitool_ramming_flow nozzle_temperature_range_low
    nozzle_temperature_range_high activate_air_filtration activate_air_filtration_during_print
    activate_air_filtration_on_completion during_print_exhaust_fan_speed
    complete_print_exhaust_fan_speed
""".split())

# Reglages du projet lies a la place du filament (tete et buse prevues pour lui).
FILAMENT_POSITION_KEYS = ("filament_map", "filament_volume_map", "filament_nozzle_map")
# Couleurs melangees d'Orca : remises a zero (le projet converti n'a que des filaments pleins).
FILAMENT_MIXED_DEFAULTS = {
    "filament_is_mixed": "0", "filament_mixed_components": "", "filament_mixed_sublayer_ratios": "",
    "filament_mixed_gradient": "0", "filament_mixed_gradient_range": "", "filament_mixed_gradient_curve": "",
    "filament_mixed_gradient_per_part": "0",
}
# Listes [traitement, filaments..., imprimante] ou [filaments...] des profils utilises.
PRESET_GROUP_KEYS = ("inherits_group", "compatible_machine_expression_group",
                     "compatible_process_expression_group", "different_settings_to_system")
# Orca ne sait peindre que 16 filaments (EnforcerBlockerType::Extruder16).
MAX_PAINT_FILAMENTS = 16

LOGICAL_PART_PLATE_GAP = 1.0 / 5.0


# --------------------------------------------------------------------------- langues

# Tous les textes montres a l'utilisateur, une table par langue : messages du plugin et textes de
# l'onglet (la page recoit toute la table). Pour ajouter une langue : copier le bloc "en", traduire
# chaque texte en gardant les {0}, {1}... (valeurs inserees, avec leur format eventuel) et le HTML
# (<b>...</b>), puis ajouter son nom anglais dans _LANG_WORDS. Un texte absent est pris en anglais.
TEXTS = {
    "fr": {
        "lang_name": "Français",
        "lang_auto": "Auto (langue d'Orca)",
        "lang_title": "Langue de l'onglet",
        # --- onglet
        "sub": "n'importe quel 3MF → ta Snapmaker U1",
        "lead": "MakerWorld / Bambu Studio, Snapmaker Orca, autres Orca : exactement les couleurs du modèle "
                "(un filament par couleur), la peinture et les plaques, avec <b>tes</b> réglages.",
        "h_analysis": "Analyse",
        "h_result": "Fichiers prêts",
        "h_tpl": "Tes réglages pour la conversion",
        "h_src": "Le 3MF à manger",
        "capture": "Mémoriser les réglages actuels d'Orca",
        "recent_title": "Derniers 3MF de tes Téléchargements",
        "refresh": "Actualiser",
        "searching": "Recherche…",
        "path_ph": "Ou colle le chemin d'un 3MF (clic droit sur le fichier › Copier en tant que chemin d'accès)",
        "analyse": "Analyser",
        "browse": "Parcourir…",
        "drop_hint": "Glisse un 3MF sur la U1 : elle a faim.",
        "drop": "Miam ! Lâche-le…",
        "u1_click": "ou clique dessus pour choisir un fichier",
        "u1_title": "Glisse un 3MF ici, ou clique pour en choisir un",
        "u1_chomp": "Crounch !",
        "u1_chew": "Ça mâche…",
        "u1_burp": "Burp ! {0}",
        "u1_spit": "Pouah ! Ce n'est pas un 3MF.",
        "u1_sick": "Pouah ! Celui-là ne passe pas.",
        "tpl_saved": "Réglages mémorisés",
        "tpl_current": "Réglages actuels d'Orca",
        "badge_not_u1": "pas une U1",
        "badge_foreign": "viennent du projet ouvert",
        "tpl_hint": "Choisis tes réglages habituels dans Orca (U1, buses, profil, plaque, filaments) puis clique "
                    "« Mémoriser » : ils serviront à chaque conversion.",
        "nozzles": "buses",
        "except": "sauf",
        "hf": "Haut débit",
        "std": "Standard",
        "bed_tpei": "plaque PEI texturée",
        "bed_cool": "plaque Cool",
        "bed_eng": "plaque Engineering",
        "bed_hot": "plaque haute température",
        "bed_tack": "plaque SuperTack",
        "bed_tcool": "plaque Cool texturée",
        "badge_unreadable": "illisible",
        "badge_sliced": "déjà tranché",
        "badge_todo": "à convertir",
        "badge_ok": "déjà pour la U1",
        "color1": "couleur",
        "colorN": "couleurs",
        "mb": "Mo",
        "kb": "Ko",
        "ago_now": "à l'instant",
        "ago_min": "il y a {0} min",
        "ago_h": "il y a {0} h",
        "ago_d": "il y a {0} j",
        "opened_in_orca": "ouvert dans Orca",
        "no_3mf": "Aucun 3MF dans {0}.",
        "analysing": "Analyse en cours…",
        "by": "par",
        "nozzle": "buse",
        "bed": "plateau",
        "plate1": "plaque",
        "plateN": "plaques",
        "one_per_plate": "Un fichier par plaque",
        "file_n": "Fichier {0} : ",
        "n_filaments": "{0} filaments",
        "th_color": "Couleur du modèle",
        "th_profile": "Profil de filament (tes réglages)",
        "pad_row": "pas de couleur du modèle : reste ta bobine actuelle ({0}, {1})",
        "warn_material": "le modèle veut du {0}, ce profil est du {1}",
        "mixed": "couleur mélangée",
        "same_n": "{0} filaments identiques",
        "pads_one": "Orca garde au moins une case par tête de la U1 : la case {0} ne sert pas.",
        "pads_many": "Orca garde au moins une case par tête de la U1 : les cases {0} et {1} ne servent pas.",
        "to_know": "À savoir",
        "convert": "Convertir",
        "convert_n": "Convertir en {0} fichiers",
        "created_1": "Le fichier est créé {0}. Un filament par couleur du modèle, avec le profil choisi.",
        "created_n": "Les fichiers sont créés {0}. Un filament par couleur du modèle, avec le profil choisi.",
        "converting": "Conversion en cours…",
        "copy_path": "Copier le chemin",
        "copied": "Copié ✓",
        "open_hint": "Dans Orca : <b>Fichier › Ouvrir un projet</b> (Ctrl+O), colle le chemin et valide. "
                     "Tes réglages et les couleurs sont déjà dedans.",
        "not_3mf": "Ce n'est pas un fichier 3MF : {0}",
        "too_big": "Fichier trop gros pour être lu ici ({0}) : mets-le dans Téléchargements ou colle son chemin.",
        "reading": "Lecture de {0}…",
        "grp_slots": "Dans tes réglages",
        "grp_user": "Tes préréglages",
        "grp_other": "Pour une autre imprimante",
        "pick_color": "Changer la couleur de ce filament",
        "color_changed": "couleur changée",
        "color_reset": "remettre celle du modèle",
        "out_title": "Fichiers convertis :",
        "out_beside": "à côté du 3MF d'origine",
        "out_downloads": "dans Téléchargements",
        "out_folder": "dans ce dossier",
        "out_ph": "Chemin du dossier (clic droit sur le dossier › Copier en tant que chemin d'accès)",
        "out_ok": "OK",
        "support": "Le plugin te plaît ? Offre un café à Dragg ☕",
        "copy_link": "Copier le lien",
        # --- messages du plugin
        "when_saved": "mémorisés le {0:02d}/{1:02d} à {3:02d}:{4:02d}",
        "cap_saved": "Réglages mémorisés.",
        "cap_current": "Réglages actuels mémorisés pour la conversion.",
        "out_saved": "Dossier enregistré.",
        "err_out_dir": "Dossier introuvable : {0}",
        "dest_in": "dans {0}",
        "downloads": "Téléchargements",
        "out_plate1": "{0} - {2} - plaque {1}.3mf",
        "out_plateN": "{0} - {2} - plaques {1}.3mf",
        "unknown_app": "logiciel inconnu",
        "another_slicer": "un autre logiciel",
        "unknown": "inconnu",
        "unnamed": "sans nom",
        "mix": "mélange {0}+{1}",
        "p_analysing": "Analyse de {0}…",
        "p_converting": "Conversion en cours…",
        "p_file": "Fichier {0} sur {1}…",
        "need_u1": "Il me faut tes réglages U1 : choisis ta Snapmaker U1 et tes profils dans Orca (ou ouvre un de "
                   "tes projets U1), puis clique « Mémoriser les réglages actuels d'Orca ».",
        "w_cfg_unreadable": "Les réglages du projet d'origine sont illisibles : ils sont ignorés.",
        "w_obj_unreadable": "Les réglages des objets sont illisibles : couleurs des objets ignorées.",
        "w_mixed_orca": "Le projet utilise des couleurs mélangées (filaments mixtes d'Orca) : chacune devient une "
                        "couleur pleine, avec son propre filament.",
        "w_mixed_fs": "Le projet utilise des couleurs mélangées (Full Spectrum de Snapmaker Orca) : chacune devient "
                      "une couleur pleine, avec son propre filament.",
        "w_paint": "Une partie de la peinture est illisible : elle est gardée telle quelle.",
        "w_paint_max": "Plus de {0} couleurs : Orca ne sait peindre que les {0} premiers filaments.",
        "w_plate": "Plaque {0} « {1} » : {2}.",
        "w_too_big": "trop grande pour le plateau de la U1 ({0:.0f} x {1:.0f} mm)",
        "w_material": "Filament {0} ({1}) : le modèle veut du {2}, le profil choisi « {3} » est du {4}. "
                      "Change-le dans Orca si besoin.",
        "err_not_3mf": "ce fichier n'est pas un 3MF (archive illisible)",
        "err_no_model": "ce 3MF ne contient pas de modèle 3D",
        "err_ref_unreadable": "projet de référence illisible ({0})",
        "err_ref_not_orca": "le projet de référence doit venir d'OrcaSlicer (trouvé : {0})",
        "err_prusa": "fichier PrusaSlicer : pas encore géré. Ouvre-le directement dans Orca (il garde la forme "
                     "et la peinture).",
        "err_sliced": "c'est un fichier déjà tranché (.gcode.3mf) : il ne contient pas le modèle. Télécharge le "
                      "projet 3MF d'origine.",
        "err_no_part": "aucune pièce dans ce 3MF",
        "err_profile": "profil {0} inconnu : refais l'analyse",
        "err_no_slot": "filament {0} sans case : refais l'analyse",
        "err_plates_missing": "plaque(s) {0} oubliée(s) dans le plan",
        "err_not_found": "fichier introuvable : {0}",
        "err_lost": "analyse perdue : relance l'analyse du fichier",
        "err_not_u1": "le projet ouvert n'est pas réglé pour une Snapmaker U1",
        "err_nothing": "rien à écrire : relance la conversion",
        "err_denied": "Accès refusé par Orca : {0}",
        "err_generic": "Erreur : {0}",
        "err_in_file": "{0} : {1}",
        "err_analyse": "Analyse impossible de {0} : {1}",
        "err_convert": "Conversion impossible : {0}",
        "err_storage": "dossier de stockage du plugin indisponible",
        "n_foreign": "« {0} » vient de {1}{2} : couleurs et réglages pas adaptés à ta U1.",
        "n_link": "Préparer la conversion dans l'onglet Mange-3MF",
        "n_ready": "Conversion de « {0} » prête : ouvre l'onglet Mange-3MF.",
        "n_error": "Mange-3MF : {0}",
        # --- noms de couleurs
        "col_black": "noir",
        "col_white": "blanc",
        "col_lightgrey": "gris clair",
        "col_grey": "gris",
        "col_darkgrey": "gris foncé",
        "col_brown": "marron",
        "col_beige": "beige",
        "col_red": "rouge",
        "col_orange": "orange",
        "col_yellow": "jaune",
        "col_green": "vert",
        "col_turquoise": "turquoise",
        "col_blue": "bleu",
        "col_purple": "violet",
        "col_pink": "rose",
        "col_lightpink": "rose clair",
    },
    "en": {
        "lang_name": "English",
        "lang_auto": "Auto (Orca's language)",
        "lang_title": "Tab language",
        # --- tab
        "sub": "any 3MF → your Snapmaker U1",
        "lead": "MakerWorld / Bambu Studio, Snapmaker Orca, other Orca forks: exactly the model's colors "
                "(one filament per color), the painting and the plates, with <b>your</b> settings.",
        "h_analysis": "Analysis",
        "h_result": "Files ready",
        "h_tpl": "Your settings for the conversion",
        "h_src": "The 3MF to eat",
        "capture": "Save Orca's current settings",
        "recent_title": "Latest 3MFs in your Downloads",
        "refresh": "Refresh",
        "searching": "Searching…",
        "path_ph": "Or paste the path of a 3MF (right-click the file › Copy as path)",
        "analyse": "Analyze",
        "browse": "Browse…",
        "drop_hint": "Drop a 3MF on the U1: it's hungry.",
        "drop": "Yum! Drop it…",
        "u1_click": "or click it to pick a file",
        "u1_title": "Drop a 3MF here, or click to pick one",
        "u1_chomp": "Crunch!",
        "u1_chew": "Chewing…",
        "u1_burp": "Burp! {0}",
        "u1_spit": "Yuck! That's not a 3MF.",
        "u1_sick": "Yuck! That one won't go down.",
        "tpl_saved": "Saved settings",
        "tpl_current": "Orca's current settings",
        "badge_not_u1": "not a U1",
        "badge_foreign": "from the open project",
        "tpl_hint": "Select your usual settings in Orca (U1, nozzles, process, plate, filaments), then click "
                    "“Save”: they will be used for every conversion.",
        "nozzles": "nozzles",
        "except": "except",
        "hf": "High Flow",
        "std": "Standard",
        "bed_tpei": "Textured PEI Plate",
        "bed_cool": "Cool Plate",
        "bed_eng": "Engineering Plate",
        "bed_hot": "High Temp Plate",
        "bed_tack": "SuperTack Plate",
        "bed_tcool": "Textured Cool Plate",
        "badge_unreadable": "unreadable",
        "badge_sliced": "already sliced",
        "badge_todo": "to convert",
        "badge_ok": "already for the U1",
        "color1": "color",
        "colorN": "colors",
        "mb": "MB",
        "kb": "KB",
        "ago_now": "just now",
        "ago_min": "{0} min ago",
        "ago_h": "{0} h ago",
        "ago_d": "{0} d ago",
        "opened_in_orca": "open in Orca",
        "no_3mf": "No 3MF in {0}.",
        "analysing": "Analyzing…",
        "by": "by",
        "nozzle": "nozzle",
        "bed": "bed",
        "plate1": "plate",
        "plateN": "plates",
        "one_per_plate": "One file per plate",
        "file_n": "File {0}: ",
        "n_filaments": "{0} filaments",
        "th_color": "Model color",
        "th_profile": "Filament profile (your settings)",
        "pad_row": "no model color: keeps your current spool ({0}, {1})",
        "warn_material": "the model wants {0}, this profile is {1}",
        "mixed": "mixed color",
        "same_n": "{0} identical filaments",
        "pads_one": "Orca keeps at least one slot per U1 head: slot {0} is not used.",
        "pads_many": "Orca keeps at least one slot per U1 head: slots {0} and {1} are not used.",
        "to_know": "Good to know",
        "convert": "Convert",
        "convert_n": "Convert into {0} files",
        "created_1": "The file is created {0}. One filament per model color, with the chosen profile.",
        "created_n": "The files are created {0}. One filament per model color, with the chosen profile.",
        "converting": "Converting…",
        "copy_path": "Copy path",
        "copied": "Copied ✓",
        "open_hint": "In Orca: <b>File › Open Project</b> (Ctrl+O), paste the path and confirm. "
                     "Your settings and the colors are already in it.",
        "not_3mf": "This is not a 3MF file: {0}",
        "too_big": "File too large to be read here ({0}): put it in Downloads or paste its path.",
        "reading": "Reading {0}…",
        "grp_slots": "In your settings",
        "grp_user": "Your presets",
        "grp_other": "For another printer",
        "pick_color": "Change this filament's color",
        "color_changed": "color changed",
        "color_reset": "back to the model's color",
        "out_title": "Converted files:",
        "out_beside": "next to the original 3MF",
        "out_downloads": "in Downloads",
        "out_folder": "in this folder",
        "out_ph": "Folder path (right-click the folder › Copy as path)",
        "out_ok": "OK",
        "support": "Like the plugin? Buy Dragg a coffee ☕",
        "copy_link": "Copy link",
        # --- plugin messages
        "when_saved": "saved {2:04d}-{1:02d}-{0:02d} {3:02d}:{4:02d}",
        "cap_saved": "Settings saved.",
        "cap_current": "Current settings saved for the conversion.",
        "out_saved": "Folder saved.",
        "err_out_dir": "Folder not found: {0}",
        "dest_in": "in {0}",
        "downloads": "Downloads",
        "out_plate1": "{0} - {2} - plate {1}.3mf",
        "out_plateN": "{0} - {2} - plates {1}.3mf",
        "unknown_app": "unknown software",
        "another_slicer": "another slicer",
        "unknown": "unknown",
        "unnamed": "unnamed",
        "mix": "mix {0}+{1}",
        "p_analysing": "Analyzing {0}…",
        "p_converting": "Converting…",
        "p_file": "File {0} of {1}…",
        "need_u1": "I need your U1 settings: select your Snapmaker U1 and your profiles in Orca (or open one of "
                   "your U1 projects), then click “Save Orca's current settings”.",
        "w_cfg_unreadable": "The original project's settings are unreadable: they are ignored.",
        "w_obj_unreadable": "The object settings are unreadable: object colors are ignored.",
        "w_mixed_orca": "The project uses mixed colors (Orca mixed filaments): each one becomes a solid color "
                        "with its own filament.",
        "w_mixed_fs": "The project uses mixed colors (Snapmaker Orca Full Spectrum): each one becomes a solid "
                      "color with its own filament.",
        "w_paint": "Part of the painting is unreadable: it is kept as is.",
        "w_paint_max": "More than {0} colors: Orca can only paint with the first {0} filaments.",
        "w_plate": "Plate {0} “{1}”: {2}.",
        "w_too_big": "too large for the U1 bed ({0:.0f} x {1:.0f} mm)",
        "w_material": "Filament {0} ({1}): the model wants {2}, the chosen profile “{3}” is {4}. "
                      "Change it in Orca if needed.",
        "err_not_3mf": "this file is not a 3MF (unreadable archive)",
        "err_no_model": "this 3MF contains no 3D model",
        "err_ref_unreadable": "unreadable reference project ({0})",
        "err_ref_not_orca": "the reference project must come from OrcaSlicer (found: {0})",
        "err_prusa": "PrusaSlicer file: not supported yet. Open it directly in Orca (it keeps the shape and "
                     "the painting).",
        "err_sliced": "this is an already sliced file (.gcode.3mf): it does not contain the model. Download the "
                      "original 3MF project.",
        "err_no_part": "no part in this 3MF",
        "err_profile": "unknown profile {0}: analyze the file again",
        "err_no_slot": "filament {0} has no slot: analyze the file again",
        "err_plates_missing": "plate(s) {0} left out of the plan",
        "err_not_found": "file not found: {0}",
        "err_lost": "analysis lost: analyze the file again",
        "err_not_u1": "the open project is not set up for a Snapmaker U1",
        "err_nothing": "nothing to write: run the conversion again",
        "err_denied": "Access denied by Orca: {0}",
        "err_generic": "Error: {0}",
        "err_in_file": "{0}: {1}",
        "err_analyse": "Could not analyze {0}: {1}",
        "err_convert": "Conversion failed: {0}",
        "err_storage": "plugin storage folder unavailable",
        "n_foreign": "“{0}” comes from {1}{2}: colors and settings are not set up for your U1.",
        "n_link": "Prepare the conversion in the Mange-3MF tab",
        "n_ready": "Conversion of “{0}” is ready: open the Mange-3MF tab.",
        "n_error": "Mange-3MF: {0}",
        # --- color names
        "col_black": "black",
        "col_white": "white",
        "col_lightgrey": "light gray",
        "col_grey": "gray",
        "col_darkgrey": "dark gray",
        "col_brown": "brown",
        "col_beige": "beige",
        "col_red": "red",
        "col_orange": "orange",
        "col_yellow": "yellow",
        "col_green": "green",
        "col_turquoise": "turquoise",
        "col_blue": "blue",
        "col_purple": "purple",
        "col_pink": "pink",
        "col_lightpink": "light pink",
    },
}
DEFAULT_LANG = "en"
_LANG_WORDS = {"french": "fr", "english": "en"}   # noms de langue de Windows (« French_France »)
_LANG = DEFAULT_LANG                              # langue courante (voir set_language)


class Msg(str):
    """Texte traduit qui garde sa cle et ses valeurs : relocalize() le refait si la langue change."""

    def __new__(cls, key, *args):
        self = str.__new__(cls, _render(key, args))
        self.key = key
        self.args = args
        return self

    def again(self):
        return Msg(self.key, *[a.again() if isinstance(a, Msg) else a for a in self.args])


def _render(key, args):
    text = (TEXTS.get(_LANG) or {}).get(key)
    if text is None:
        text = TEXTS[DEFAULT_LANG].get(key, key)
    if not args:
        return text
    try:
        return text.format(*args)
    except (IndexError, KeyError, ValueError):
        return text + " " + " ".join(str(a) for a in args)


def tr(key, *args):
    """Texte de TEXTS dans la langue courante, {0}, {1}... remplaces par args."""
    return Msg(key, *args)


def relocalize(obj):
    """Copie de obj (dict, liste...) ou chaque texte traduit est refait dans la langue courante."""
    if isinstance(obj, Msg):
        return str(obj.again())
    if isinstance(obj, dict):
        return {k: relocalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [relocalize(v) for v in obj]
    return obj


def set_language(code):
    global _LANG
    _LANG = code if code in TEXTS else DEFAULT_LANG


def current_language():
    return _LANG


def lang_of(code):
    """« fr_FR », « fr-CA », « French_France »... -> langue connue ("fr", "en"...), sinon l'anglais."""
    c = (code or "").strip().lower().replace("-", "_")
    base = re.split(r"[_.@]", c)[0] if c else ""
    if base in TEXTS:
        return base
    return _LANG_WORDS.get(base, DEFAULT_LANG)


def system_language():
    """Langue du systeme, si Orca ne donne pas la sienne (« fr_FR », « French_France »...)."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = (os.environ.get(var) or "").split(":")[0].strip()
        if v and v.upper() not in ("C", "POSIX") and not v.upper().startswith("C."):
            return v
    try:
        import locale
        return locale.getlocale()[0] or ""
    except Exception:
        return ""


def orca_language():
    """Langue de l'interface d'Orca (« fr_FR »...), lue sur le fil de l'interface ; "" sinon."""
    try:
        return str(orca.host.app_info().get("language") or "")
    except Exception:
        return ""


def message_of(error):
    """Texte d'une erreur, en gardant sa traduction si c'en est une."""
    return error.args[0] if error.args and isinstance(error.args[0], Msg) else str(error)


set_language(lang_of(system_language()))


class ConvertError(Exception):
    """Erreur a montrer telle quelle a l'utilisateur."""


# --------------------------------------------------------------------------- couleurs

def norm_color(value):
    """'#rrggbb', '#RRGGBBAA', 'rrggbb'... -> '#RRGGBB' (None si illisible)."""
    c = (value or "").strip().strip('"').strip()
    if c.startswith("#"):
        c = c[1:]
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if re.fullmatch(r"[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", c):
        return "#" + c[:6].upper()
    return None


def _rgb(hexc):
    return tuple(int(hexc[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def _lab(hexc):
    def lin(u):
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(u) for u in _rgb(hexc))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0
    fx, fy, fz = f(x), f(y), f(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def color_distance(a, b):
    """Ecart de couleur (Delta E CIE76) entre deux '#RRGGBB'."""
    if not a or not b:
        return 100.0
    la, lb = _lab(a), _lab(b)
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(la, lb)))


def color_name(hexc):
    """Nom de couleur approximatif, pour les messages."""
    key = _color_key(hexc)
    return tr("col_" + key) if key else "?"


def _color_key(hexc):
    if not hexc:
        return None
    r, g, b = _rgb(hexc)
    mx, mn = max(r, g, b), min(r, g, b)
    v, s = mx, (mx - mn) / mx if mx else 0.0
    if v < 0.2:
        return "black"
    if s < 0.14:
        if v > 0.86:
            return "white"
        return "lightgrey" if v > 0.62 else ("grey" if v > 0.38 else "darkgrey")
    d = mx - mn
    if mx == r:
        h = (60.0 * ((g - b) / d)) % 360.0
    elif mx == g:
        h = 60.0 * ((b - r) / d) + 120.0
    else:
        h = 60.0 * ((r - g) / d) + 240.0
    if 15 <= h < 50 and v < 0.62:
        return "brown"
    if 20 <= h < 55 and s < 0.38 and v > 0.7:
        return "beige"
    for limit, name in ((12, "red"), (40, "orange"), (68, "yellow"), (165, "green"), (195, "turquoise"),
                        (255, "blue"), (290, "purple"), (335, "pink"), (361, "red")):
        if h < limit:
            if name in ("red", "pink") and v > 0.85 and s < 0.45:
                return "lightpink"
            return name
    return None


def base_type(value):
    """Famille de matiere : 'PLA', 'PETG', 'TPU'..."""
    t = (value or "").upper()
    for key in ("PETG", "PCTG", "PLA", "ABS", "ASA", "TPU", "PVA", "HIPS", "PET", "PPA", "PA", "PC", "PP"):
        if key in t:
            return {"PCTG": "PETG", "PPA": "PA"}.get(key, key)
    return t.strip() or "?"


# --------------------------------------------------------------------------- peinture (paint_color)
# Format d'OrcaSlicer (TriangleSelector::serialize / FacetsAnnotation::get_triangle_as_string) :
# une chaine hexadecimale par triangle, lue de droite a gauche, un quartet par noeud de l'arbre de
# decoupe. Quartet = 2 bits de nombre de cotes coupes + 2 bits (etat de la feuille ou cote special).
# Feuille d'etat >= 3 : '11' puis un quartet (etat - 3) ; etat >= 18 : quartet 0b1111 puis (etat - 18).
# L'etat d'une feuille est le numero du filament (0 = filament de la piece).

_HEXV = {c: i for i, c in enumerate("0123456789ABCDEF")}
_HEXV.update({c.lower(): i for c, i in list(_HEXV.items()) if c.isalpha()})
_HEXC = "0123456789ABCDEF"


def _walk_paint(text, on_leaf):
    """Parcourt un arbre de peinture ; on_leaf(etat) -> nouvel etat. Retourne la liste des
    quartets reecrits (ordre du flux), ou None si la chaine est illisible."""
    try:
        nib = [_HEXV[c] for c in reversed(text)]
    except KeyError:
        return None
    n = len(nib)
    if n == 0:
        return None
    out = []
    pos, pending = 0, 1
    while pending:
        if pos >= n:
            return None
        code = nib[pos]
        pos += 1
        pending -= 1
        split = code & 3
        if split:
            if (code >> 2) == 3 and split != 3:
                return None
            pending += split + 1
            out.append(code)
            continue
        hi = code >> 2
        if hi == 3:
            if pos >= n:
                return None
            v = nib[pos]
            pos += 1
            if v == 15:
                if pos >= n:
                    return None
                state = nib[pos] + 18
                pos += 1
            else:
                state = v + 3
        else:
            state = hi
        new = on_leaf(state)
        if new < 3:
            out.append(new << 2)
        elif new <= 17:
            out.extend((12, new - 3))
        else:
            out.extend((12, 15, new - 18))
    if pos != n:
        return None
    return out


def paint_leaf_states(text):
    """Etats (numeros de filament, 0 = non peint) presents dans une chaine paint_color."""
    states = set()

    def leaf(st):
        states.add(st)
        return st
    return states if _walk_paint(text, leaf) is not None else None


def remap_paint(text, mapping):
    """Renumerote les filaments d'une chaine paint_color (mapping {ancien: nouveau})."""
    out = _walk_paint(text, lambda st: mapping.get(st, st) if st else 0)
    if out is None:
        return text
    return "".join(_HEXC[v] for v in reversed(out))


_RE_PAINT_ATTR = re.compile(r'(\s(?:paint_color|slic3rpe:mmu_segmentation)=")([0-9A-Fa-f]+)(")')


def remap_paint_in_xml(xml_text, mapping):
    """Applique remap_paint a toutes les peintures de couleur d'un fichier .model."""
    if not mapping or all(k == v for k, v in mapping.items()):
        return xml_text
    if "paint_color" not in xml_text and "mmu_segmentation" not in xml_text:
        return xml_text
    cache = {}

    def sub(m):
        s = m.group(2)
        r = cache.get(s)
        if r is None:
            r = cache[s] = remap_paint(s, mapping)
        return m.group(1) + r + m.group(3)
    return _RE_PAINT_ATTR.sub(sub, xml_text)


# --------------------------------------------------------------------------- outils XML / geometrie

_RE_ATTR = re.compile(r'([\w:.-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')


def tag_attrs(inner):
    return {m.group(1): (m.group(2) if m.group(2) is not None else m.group(3)) for m in _RE_ATTR.finditer(inner)}


def xml_unescape(s):
    return (s or "").replace("&quot;", '"').replace("&apos;", "'").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def xml_escape(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


IDENT = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


def parse_transform(s):
    try:
        v = tuple(float(x) for x in (s or "").split())
    except ValueError:
        return IDENT
    return v if len(v) == 12 else IDENT


def format_transform(t):
    return " ".join(_fmt_num(v) for v in t)


def _fmt_num(v):
    if abs(v) < 1e-12:
        return "0"
    s = "%.9g" % v
    return s


def apply_transform(t, p):
    x, y, z = p
    return (x * t[0] + y * t[3] + z * t[6] + t[9],
            x * t[1] + y * t[4] + z * t[7] + t[10],
            x * t[2] + y * t[5] + z * t[8] + t[11])


def transform_bbox(t, bbox):
    """Boite englobante (alignee) d'une boite transformee. bbox = (minx, miny, minz, maxx, maxy, maxz)."""
    if bbox is None:
        return None
    xs, ys, zs = [], [], []
    for x in (bbox[0], bbox[3]):
        for y in (bbox[1], bbox[4]):
            for z in (bbox[2], bbox[5]):
                p = apply_transform(t, (x, y, z))
                xs.append(p[0])
                ys.append(p[1])
                zs.append(p[2])
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def merge_bbox(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3]), max(a[4], b[4]), max(a[5], b[5]))


def area_rect(printable_area):
    """['0x0', '256x0', ...] -> (minx, miny, maxx, maxy)."""
    xs, ys = [], []
    for pt in printable_area or []:
        try:
            x, y = str(pt).lower().split("x")
            xs.append(float(x))
            ys.append(float(y))
        except ValueError:
            continue
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def compute_column_count(count):
    """Meme calcul qu'OrcaSlicer (PartPlateList) pour la grille des plaques."""
    value = math.sqrt(float(count))
    round_value = float(round(value))
    return int(round_value + 1) if value > round_value else int(round_value)


def plate_origin(index, cols, width, depth):
    row, col = index // cols, index % cols
    return (col * width * (1.0 + LOGICAL_PART_PLATE_GAP), -row * depth * (1.0 + LOGICAL_PART_PLATE_GAP))


def _cfg_list(cfg, key):
    v = cfg.get(key)
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def _cfg_str(cfg, key, default=""):
    v = cfg.get(key)
    if isinstance(v, list):
        return str(v[0]) if v else default
    return default if v is None else str(v)


def _int(value, default=0):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- lecture d'un 3MF

class Mesh:
    __slots__ = ("bbox", "triangles", "painted", "states", "state_weight", "unreadable_paint")

    def __init__(self):
        self.bbox = None
        self.triangles = 0
        self.painted = 0
        self.states = set()
        self.state_weight = {}   # etat -> nombre (approche) de triangles
        self.unreadable_paint = False

    @property
    def has_unpainted(self):
        return self.triangles > self.painted or 0 in self.states


class Part:
    __slots__ = ("id", "subtype", "extruder", "keys", "component", "name")

    def __init__(self, pid, subtype, extruder, keys, name=""):
        self.id = pid
        self.subtype = subtype or "normal_part"
        self.extruder = extruder
        self.keys = keys
        self.component = None
        self.name = name


class Obj:
    __slots__ = ("id", "name", "extruder", "keys", "parts", "components", "instances", "rank", "own_mesh")

    def __init__(self, oid):
        self.id = oid
        self.name = ""
        self.extruder = 1
        self.keys = {}
        self.parts = []
        self.components = []   # (fichier, objectid, transform)
        self.instances = []    # Instance, dans l'ordre des elements <item>
        self.rank = 0          # position (1..) parmi les objets du modele
        self.own_mesh = None   # (fichier, id) si l'objet porte lui-meme un maillage


class Instance:
    __slots__ = ("obj", "index", "transform", "plate", "bbox")

    def __init__(self, obj, index, transform):
        self.obj = obj
        self.index = index
        self.transform = transform
        self.plate = None
        self.bbox = None


class Plate:
    __slots__ = ("index", "id", "name", "elem", "instances", "filaments", "weights", "keys", "merges")

    def __init__(self, index, pid, name, elem):
        self.index = index
        self.id = pid
        self.name = name
        self.elem = elem
        self.instances = []
        self.filaments = set()
        self.weights = {}
        self.keys = {}
        self.merges = []


class Source3MF:
    """Un 3MF ouvert en memoire, analyse (objets, plaques, filaments utilises)."""

    def __init__(self, data, name="projet.3mf", path=""):
        if not data or data[:2] != b"PK":
            raise ConvertError(tr("err_not_3mf"))
        try:
            self.zip = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise ConvertError(tr("err_not_3mf"))
        self.data = data
        self.name = name
        self.path = path
        self.names = [i.filename for i in self.zip.infolist() if not i.filename.endswith("/")]
        self.nameset = set(self.names)
        self.main = self._main_model_name()
        if self.main not in self.nameset:
            raise ConvertError(tr("err_no_model"))
        self._texts = {}
        self.warnings = []
        self.config = {}
        if PROJECT_CFG in self.nameset:
            try:
                self.config = json.loads(self.zip.read(PROJECT_CFG).decode("utf-8", "replace"))
            except (ValueError, UnicodeDecodeError):
                self.config = {}
                self.warnings.append(tr("w_cfg_unreadable"))
        self.meta = self._model_metadata()
        self.application = self.meta.get("Application", "")
        self.objects = {}
        self.object_order = []
        self.meshes = {}
        self.plates = []
        self.identify = {}
        self.filaments = []
        self.n_filaments = 0
        self._parse()

    # ---- acces aux fichiers
    def text(self, name):
        t = self._texts.get(name)
        if t is None:
            t = self.zip.read(name).decode("utf-8", "replace")
            self._texts[name] = t
        return t

    def raw(self, name):
        return self.zip.read(name)

    def _main_model_name(self):
        if PKG_RELS in self.nameset:
            try:
                rels = self.zip.read(PKG_RELS).decode("utf-8", "replace")
                for m in re.finditer(r"<Relationship\b([^>]*)>", rels):
                    a = tag_attrs(m.group(1))
                    if a.get("Type", "").endswith("/3dmodel") and a.get("Target"):
                        target = a["Target"].lstrip("/")
                        if target in self.nameset:
                            return target
            except KeyError:
                pass
        for n in self.names:
            if n.lower() == MAIN_MODEL.lower():
                return n
        for n in self.names:
            if n.lower().endswith(".model") and n.lower().startswith("3d/"):
                return n
        return MAIN_MODEL

    def _model_metadata(self):
        head = self.text(self.main)
        res = head.find("<resources")
        head = head[: res if res > 0 else 200000]
        meta = {}
        for m in re.finditer(r'<metadata\s+name="([^"]+)"\s*>(.*?)</metadata>', head, re.S):
            meta[m.group(1)] = xml_unescape(m.group(2)).strip()
        return meta

    # ---- origine du fichier
    @property
    def kind(self):
        app = self.application.lower()
        if PRUSA_CFG in self.nameset:
            return "prusa"
        if not self.config:
            return "plain"
        if app.startswith("snapmaker"):
            return "snapmaker"
        # OrcaSlicer (2.3.2 et plus) signe « BambuStudio-<version Bambu> » et ajoute l'etiquette
        # « OrcaSlicer » : c'est elle qui dit que le projet vient d'Orca.
        if "OrcaSlicer" in self.meta or app.startswith("orcaslicer"):
            return "orca"
        if app.startswith("bambustudio"):
            return "bambu"
        return "orca-fork"

    def app_label(self):
        if self.kind == "orca" and self.meta.get("OrcaSlicer"):
            return "OrcaSlicer " + self.meta["OrcaSlicer"]
        return app_label(self.application)

    @property
    def printer(self):
        return _cfg_str(self.config, "printer_model") or _cfg_str(self.config, "printer_settings_id")

    @property
    def is_sliced_only(self):
        return not any(o.instances for o in self.objects.values()) and any(n.lower().endswith(".gcode") for n in self.names)

    # ---- analyse
    def _parse(self):
        self._parse_filaments()
        main = self.text(self.main)
        self._parse_model_file(self.main, main, top=True)
        self._parse_build(main)
        self._parse_model_settings()
        self._load_component_meshes()
        self._parse_plates()
        self._compute_bboxes()
        self._compute_usage()

    def _parse_filaments(self):
        cfg = self.config
        colours = _cfg_list(cfg, "filament_colour")
        types = _cfg_list(cfg, "filament_type")
        names = _cfg_list(cfg, "filament_settings_id")
        vendors = _cfg_list(cfg, "filament_vendor")
        mixed = _cfg_list(cfg, "filament_mixed_components")
        n = len(colours) if colours else 1
        self.n_filaments = n
        self.filaments = []
        for i in range(n):
            col = norm_color(colours[i]) if i < len(colours) else None
            ftype = types[i] if i < len(types) else ""
            fname = names[i] if i < len(names) else ""
            self.filaments.append({
                "index": i + 1, "color": col, "type": ftype, "base": base_type(ftype),
                "name": fname, "vendor": vendors[i] if i < len(vendors) else "",
                "mixed": bool(i < len(mixed) and mixed[i].strip()),
            })
        # Couleurs melangees de Snapmaker Orca (Full Spectrum) : filaments "virtuels" apres les vrais.
        self.virtual = {}
        defs = _cfg_str(cfg, "mixed_filament_definitions")
        if defs:
            rows = [r for r in defs.split(";") if r.strip()]
            k = 0
            for row in rows:
                f = row.split(",")
                if len(f) < 5 or f[2].strip() != "1":
                    continue
                a, b, pct = _int(f[0]), _int(f[1]), _int(f[4], 50)
                k += 1
                self.virtual[n + k] = (a, b, pct)

    def filament(self, idx):
        if 1 <= idx <= len(self.filaments):
            return self.filaments[idx - 1]
        v = self.virtual.get(idx)
        if v:
            a, b, pct = v
            ca, cb = self.filament(a)["color"], self.filament(b)["color"]
            col = _blend(ca, cb, pct / 100.0)
            main = a if pct <= 50 else b
            f = dict(self.filament(main))
            f.update({"index": idx, "color": col, "mixed": True, "name": tr("mix", a, b)})
            return f
        return {"index": idx, "color": None, "type": "", "base": "?", "name": "filament %d" % idx,
                "vendor": "", "mixed": False}

    def _parse_model_file(self, fname, text, top=False):
        """Repere les objets d'un fichier .model : maillages et composants."""
        for m in re.finditer(r"<object\b([^>]*)>", text):
            a = tag_attrs(m.group(1))
            oid = a.get("id")
            end = text.find("</object>", m.end())
            if oid is None or end < 0:
                continue
            body_start, body_end = m.end(), end
            if text.find("<mesh", body_start, body_end) >= 0:
                self.meshes[(fname, oid)] = (body_start, body_end, None)
            comps = []
            if text.find("<component", body_start, body_end) >= 0:
                for c in re.finditer(r"<component\b([^>]*)/?>", text[body_start:body_end]):
                    ca = tag_attrs(c.group(1))
                    path = (ca.get("p:path") or ca.get("path") or "").lstrip("/") or fname
                    comps.append((path, ca.get("objectid", ""), parse_transform(ca.get("transform"))))
            if top:
                obj = Obj(oid)
                obj.name = a.get("name", "")
                obj.components = comps
                if (fname, oid) in self.meshes:
                    obj.own_mesh = (fname, oid)
                self.objects[oid] = obj
                self.object_order.append(oid)
                obj.rank = len(self.object_order)

    def _parse_build(self, main):
        b = main.find("<build")
        if b < 0:
            return
        e = main.find("</build>", b)
        section = main[b: e if e > 0 else len(main)]
        for m in re.finditer(r"<item\b([^>]*)/?>", section):
            a = tag_attrs(m.group(1))
            obj = self.objects.get(a.get("objectid"))
            if obj is None:
                continue
            inst = Instance(obj, len(obj.instances), parse_transform(a.get("transform")))
            obj.instances.append(inst)

    def _parse_model_settings(self):
        self.model_cfg = None
        if MODEL_CFG not in self.nameset:
            return
        try:
            root = ET.fromstring(self.raw(MODEL_CFG))
        except ET.ParseError:
            self.warnings.append(tr("w_obj_unreadable"))
            return
        self.model_cfg = root
        for oe in root.findall("object"):
            obj = self.objects.get(oe.get("id"))
            if obj is None:
                continue
            meta = {md.get("key"): md.get("value") for md in oe.findall("metadata")}
            obj.name = meta.get("name") or obj.name
            obj.extruder = max(1, _int(meta.get("extruder"), 1))
            obj.keys = meta
            obj.parts = []
            for pe in oe.findall("part"):
                pm = {md.get("key"): md.get("value") for md in pe.findall("metadata")}
                ext = _int(pm.get("extruder"), 0) or None
                obj.parts.append(Part(pe.get("id"), pe.get("subtype"), ext, pm, pm.get("name", "")))

    def _load_component_meshes(self):
        """Associe pieces et maillages, et lit les maillages utilises (boites, peinture)."""
        needed = set()
        for obj in self.objects.values():
            if not obj.instances:
                continue
            if obj.own_mesh:
                needed.add(obj.own_mesh)
            for path, sub, _ in obj.components:
                needed.add((path, sub))
            # pieces <-> composants : par identifiant si possible, sinon dans l'ordre
            by_id = {c[1]: c for c in obj.components}
            for i, part in enumerate(obj.parts):
                part.component = by_id.get(part.id) if part.id in by_id and len(by_id) == len(obj.components) else None
                if part.component is None and i < len(obj.components):
                    part.component = obj.components[i]
        files = {}
        for fname, sub in needed:
            files.setdefault(fname, set()).add(sub)
        for fname, ids in files.items():
            if fname not in self.nameset:
                continue
            text = self.text(fname)
            if fname != self.main:
                self._parse_model_file(fname, text)
            for oid in ids:
                spec = self.meshes.get((fname, oid))
                if spec is None or isinstance(spec, Mesh):
                    continue
                self.meshes[(fname, oid)] = _read_mesh(text, spec[0], spec[1])

    def mesh(self, key):
        m = self.meshes.get(key)
        return m if isinstance(m, Mesh) else None

    def _parse_plates(self):
        root = self.model_cfg
        plates = []
        if root is not None:
            for i, pe in enumerate(root.findall("plate")):
                meta = {md.get("key"): md.get("value") for md in pe.findall("metadata")}
                pid = _int(meta.get("plater_id"), i + 1)
                plates.append(Plate(i, pid, meta.get("plater_name", "") or "", pe))
        plates.sort(key=lambda p: p.id)
        for i, p in enumerate(plates):
            p.index = i
        if not plates:
            plates = [Plate(0, 1, "", None)]
        self.plates = plates
        self.identify = {}
        listed = set()
        for p in plates:
            if p.elem is None:
                continue
            for mi in p.elem.findall("model_instance"):
                meta = {md.get("key"): md.get("value") for md in mi.findall("metadata")}
                obj = self.objects.get(meta.get("object_id"))
                idx = _int(meta.get("instance_id"), 0)
                if obj is None or idx >= len(obj.instances):
                    continue
                inst = obj.instances[idx]
                if meta.get("identify_id"):
                    self.identify[(obj.id, idx)] = meta.get("identify_id")
                if inst.plate is None:
                    inst.plate = p
                    p.instances.append(inst)
                    listed.add(id(inst))
        self._orphans = [inst for o in self.objects.values() for inst in o.instances if id(inst) not in listed]

    def bed_rect(self):
        r = area_rect(_cfg_list(self.config, "printable_area"))
        return r or (0.0, 0.0, 256.0, 256.0)

    def plate_origin(self, index):
        minx, miny, maxx, maxy = self.bed_rect()
        cols = compute_column_count(max(1, len(self.plates)))
        return plate_origin(index, cols, maxx - minx, maxy - miny)

    def _compute_bboxes(self):
        for obj in self.objects.values():
            local = None
            if obj.own_mesh:
                m = self.mesh(obj.own_mesh)
                local = merge_bbox(local, m.bbox if m else None)
            for path, sub, tf in obj.components:
                m = self.mesh((path, sub))
                if m is not None and m.bbox is not None:
                    local = merge_bbox(local, transform_bbox(tf, m.bbox))
            for inst in obj.instances:
                inst.bbox = transform_bbox(inst.transform, local) if local else None
        # Instances qui ne sont sur aucune plaque : on les range d'apres leur position.
        minx, miny, maxx, maxy = self.bed_rect()
        for inst in self._orphans:
            cx, cy = inst.transform[9], inst.transform[10]
            if inst.bbox:
                cx, cy = (inst.bbox[0] + inst.bbox[3]) / 2, (inst.bbox[1] + inst.bbox[4]) / 2
            best = self.plates[0]
            for p in self.plates:
                ox, oy = self.plate_origin(p.index)
                if ox + minx - 1 <= cx <= ox + maxx + 1 and oy + miny - 1 <= cy <= oy + maxy + 1:
                    best = p
                    break
            inst.plate = best
            best.instances.append(inst)

    # ---- filaments utilises
    def object_filaments(self, obj):
        """Filaments utilises par un objet, avec un poids (importance approchee)."""
        used = {}

        def add(f, w):
            if f >= 1:
                used[f] = used.get(f, 0.0) + w
        for key in list(FILAMENT_KEYS_NEW) + list(FILAMENT_KEYS_LEGACY):
            v = _int(obj.keys.get(key), 0)
            if v > 1 or (v == 1 and key not in _LEGACY_ONE_IS_DEFAULT):
                add(v, 0.5)
        parts = obj.parts or [Part("1", "normal_part", None, {})]
        for part in parts:
            sub = part.subtype
            if sub in ("negative_part", "support_blocker", "support_enforcer"):
                continue
            ext = part.extruder or obj.extruder
            for key in list(FILAMENT_KEYS_NEW) + list(FILAMENT_KEYS_LEGACY):
                v = _int(part.keys.get(key), 0)
                if v > 1 or (v == 1 and key not in _LEGACY_ONE_IS_DEFAULT):
                    add(v, 0.5)
            if sub == "modifier_part":
                if part.extruder:
                    add(part.extruder, 0.3)
                continue
            mesh = None
            if part.component is not None:
                mesh = self.mesh((part.component[0], part.component[1]))
            elif not obj.parts and obj.own_mesh:
                mesh = self.mesh(obj.own_mesh)
            if mesh is None or not mesh.painted or not mesh.triangles:
                add(ext, 1.0)
                continue
            tri = float(mesh.triangles)
            unpainted = max(0.0, tri - mesh.painted) + mesh.state_weight.get(0, 0.0)
            if unpainted > 0:
                add(ext, unpainted / tri)
            for st, w in mesh.state_weight.items():
                if st > 0:
                    add(st, w / tri)
            if mesh.unreadable_paint:
                add(ext, 0.01)
        return used

    def _compute_usage(self):
        ranges = self._layer_range_filaments()
        tool_changes = self._tool_change_filaments()
        cache = {}
        for p in self.plates:
            weights = {}
            for inst in p.instances:
                obj = inst.obj
                if obj.id not in cache:
                    w = dict(self.object_filaments(obj))
                    for f in ranges.get(obj.rank, set()):
                        w[f] = w.get(f, 0.0) + 0.3
                    cache[obj.id] = w
                for f, w in cache[obj.id].items():
                    weights[f] = weights.get(f, 0.0) + w
            for f in tool_changes.get(p.id, set()):
                weights[f] = weights.get(f, 0.0) + 0.3
            p.weights = {f: w for f, w in weights.items() if f >= 1}
            p.filaments = set(p.weights)
        self.object_usage = cache

    def _layer_range_filaments(self):
        res = {}
        if LAYER_RANGES not in self.nameset:
            return res
        try:
            root = ET.fromstring(self.raw(LAYER_RANGES))
        except ET.ParseError:
            return res
        for oe in root.findall("object"):
            rank = _int(oe.get("id"), 0)
            for opt in oe.iter("option"):
                key = opt.get("opt_key")
                if key == "extruder" or key in FILAMENT_KEYS_NEW or key in FILAMENT_KEYS_LEGACY:
                    v = _int(opt.text, 0)
                    if v > 1 or (v == 1 and key not in _LEGACY_ONE_IS_DEFAULT):
                        res.setdefault(rank, set()).add(v)
        return res

    def _tool_change_filaments(self):
        res = {}
        if CUSTOM_GCODE not in self.nameset:
            return res
        try:
            root = ET.fromstring(self.raw(CUSTOM_GCODE))
        except ET.ParseError:
            return res
        for pe in root.findall("plate"):
            info = pe.find("plate_info")
            pid = _int(info.get("id"), 1) if info is not None else 1
            for layer in pe.findall("layer"):
                ext = _int(layer.get("extruder"), 0)
                if ext >= 1:
                    res.setdefault(pid, set()).add(ext)
        return res


def _blend(a, b, t):
    if not a or not b:
        return a or b
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join("%02X" % int(round((x * (1 - t) + y * t) * 255)) for x, y in zip(ra, rb))


_RE_VERTEX_FAST = re.compile(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"')
_RE_VERTEX_ANY = re.compile(r"<vertex\b([^>]*)/?>")
_RE_PAINT_VALUE = re.compile(r'\s(?:paint_color|slic3rpe:mmu_segmentation)="([0-9A-Fa-f]+)"')


def _read_mesh(text, start, end):
    mesh = Mesh()
    v0 = text.find("<vertices", start, end)
    v1 = text.find("</vertices>", start, end)
    if v0 >= 0 and v1 > v0:
        seg = text[v0:v1]
        vals = _RE_VERTEX_FAST.findall(seg)
        if not vals and "<vertex" in seg:
            vals = []
            for m in _RE_VERTEX_ANY.finditer(seg):
                a = tag_attrs(m.group(1))
                vals.append((a.get("x", "0"), a.get("y", "0"), a.get("z", "0")))
        if vals:
            try:
                xs = [float(v[0]) for v in vals]
                ys = [float(v[1]) for v in vals]
                zs = [float(v[2]) for v in vals]
                mesh.bbox = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
            except ValueError:
                mesh.bbox = None
    t0 = text.find("<triangles", start, end)
    t1 = text.find("</triangles>", start, end)
    if t0 >= 0 and t1 > t0:
        seg = text[t0:t1]
        mesh.triangles = seg.count("<triangle ")
        paints = _RE_PAINT_VALUE.findall(seg)
        mesh.painted = len(paints)
        counts = {}
        for s in paints:
            counts[s] = counts.get(s, 0) + 1
        for s, c in counts.items():
            st = paint_leaf_states(s)
            if st is None:
                mesh.unreadable_paint = True
                continue
            mesh.states |= st
            share = float(c) / len(st)
            for x in st:
                mesh.state_weight[x] = mesh.state_weight.get(x, 0.0) + share
    return mesh


# --------------------------------------------------------------------------- reglages de l'utilisateur (modele)

# --------------------------------------------------------------------------- prereglages de filament d'Orca

# Reglages de filament qui sont des listes de textes (Orca les ecrit separes par « ; »).
STRING_VECTOR_KEYS = frozenset("""
filament_type filament_vendor default_filament_colour filament_settings_id filament_ids filament_start_gcode
filament_end_gcode filament_change_extrusion_role_gcode filament_notes compatible_printers compatible_prints
filament_ramming_parameters filament_extruder_variant filament_colour filament_multi_colour filament_colour_type
filament_plugin_config_overrides adaptive_pressure_advance_model volumetric_speed_coefficients
""".split())


def _unescape_cstyle(text):
    """Texte echappe par Orca (\\n, \\r, \\x -> x)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            nxt = text[i + 1]
            out.append("\n" if nxt == "n" else "\r" if nxt == "r" else nxt)
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def split_serialized(text, strings=False):
    """Valeur d'un reglage ecrite par Orca (opt_serialize) -> liste de textes, comme dans un projet.
    Textes : separes par « ; », entre guillemets si besoin (comme unescape_strings_cstyle d'Orca) ;
    nombres, booleens et listes de choix : separes par « , »."""
    t = text or ""
    if not t:
        return []
    if not (strings or '"' in t or ";" in t):
        return t.split(",")
    out, i, n = [], 0, len(t)
    while True:
        while i < n and t[i] in " \t":
            i += 1
        if i >= n:
            return out
        buf = []
        if t[i] == '"':
            i += 1
            while i < n and t[i] != '"':
                if t[i] == "\\" and i + 1 < n:
                    i += 1
                    buf.append("\n" if t[i] == "n" else "\r" if t[i] == "r" else t[i])
                else:
                    buf.append(t[i])
                i += 1
            i += 1
        else:
            while i < n and t[i] != ";":
                buf.append(t[i])
                i += 1
        out.append("".join(buf))
        while i < n and t[i] in " \t":
            i += 1
        if i >= n:
            return out
        if t[i] != ";":
            return out
        i += 1
        if i >= n:
            out.append("")
            return out


def strip_project_suffix(name):
    """« Anycubic PLA(un projet.3mf)(un autre (1V2).3mf) » -> « Anycubic PLA » : Orca ajoute le nom
    du projet aux profils d'un projet qui different des tiens."""
    name = (name or "").strip()
    while name.lower().endswith(".3mf)"):
        depth, i = 0, len(name) - 1
        while i >= 0:
            if name[i] == ")":
                depth += 1
            elif name[i] == "(":
                depth -= 1
                if depth == 0:
                    break
            i -= 1
        if i <= 0:
            break
        name = name[:i].rstrip()
    return name


class FilamentPreset:
    """Un prereglage de filament d'Orca : son nom et ses valeurs telles qu'Orca les ecrit."""
    SCALARS = ("inherits", "filament_id", "compatible_printers_condition", "compatible_prints_condition")

    def __init__(self, name, raw, other=False):
        self.name = name
        self.raw = dict(raw)
        self.other = other          # prevu pour une autre imprimante que celle des reglages
        self._cache = {}

    @classmethod
    def read(cls, preset, other=False):
        raw = {}
        for key in preset.config_keys():
            try:
                value = preset.config_value(key)
            except Exception:
                continue
            if value is not None:
                raw[key] = str(value)
        return cls(preset.name, raw, other)

    def values(self, key, strings=False):
        """Valeurs d'un reglage (une par variante de buse). strings : le reglage est un texte qui
        peut contenir des virgules (deduit des reglages du projet)."""
        if key in self.SCALARS or key not in self.raw:
            return None
        strings = strings or key in STRING_VECTOR_KEYS
        if (key, strings) not in self._cache:
            self._cache[(key, strings)] = split_serialized(self.raw[key], strings)
        return self._cache[(key, strings)]

    def first(self, key):
        v = self.values(key)
        return v[0] if v else None

    def scalar(self, key):
        v = self.raw.get(key)
        return _unescape_cstyle(v) if v is not None else None

    def variants(self):
        return self.values("filament_extruder_variant") or []

    @property
    def type(self):
        return self.first("filament_type") or ""

    @property
    def color(self):
        return norm_color(self.first("default_filament_colour") or "") or None


def read_filament_presets(template):
    """Prereglages utiles a la conversion, lus dans Orca (fil de l'interface) : ceux de
    l'utilisateur, et ceux des cases des reglages (par leur nom, sans le nom de projet ajoute par
    Orca). Retourne {"user": [FilamentPreset...], "slots": {case: FilamentPreset}}."""
    out = {"user": [], "slots": {}}
    try:
        bundle = orca.host.preset_bundle()
        coll = bundle.filaments
    except Exception:
        return out
    try:
        same_printer = bundle.current_printer_preset().name == _cfg_str(template.config, "printer_settings_id")
    except Exception:
        same_printer = False
    for s, name in enumerate(template.slot_names):
        clean = strip_project_suffix(name)
        try:
            p = coll.find_preset(clean) if clean else None
            if p is not None and not p.is_project_embedded and not p.is_default:
                out["slots"][s] = FilamentPreset.read(p)
        except Exception as e:
            log_error("prereglage %s : %s" % (clean, e))
    taken = {p.name for p in out["slots"].values()}
    for i in range(coll.size()):
        try:
            p = coll.preset(i)
            if p.is_default or p.is_project_embedded or not p.is_user() or p.name in taken:
                continue
            out["user"].append(FilamentPreset.read(p, other=bool(same_printer and not p.is_compatible)))
        except Exception as e:
            log_error("prereglage %d : %s" % (i, e))
    out["user"].sort(key=lambda p: (p.other, p.name.lower()))
    return out


class Template:
    """Reglages de l'utilisateur, pris dans un projet enregistre par son OrcaSlicer."""

    def __init__(self, config, application, orca_tag, captured_at=None, source="", bundle_3mf_names=None):
        self.config = config
        self.application = application
        self.orca_tag = orca_tag
        self.captured_at = captured_at or time.time()
        self.source = source
        self.presets = []           # prereglages de l'utilisateur proposes en plus des cases
        self.slot_presets = {}      # case -> prereglage d'Orca du meme nom (valeurs a jour)

    def attach(self, presets):
        """Prereglages lus dans Orca (read_filament_presets)."""
        presets = presets or {}
        self.presets = list(presets.get("user") or [])
        self.slot_presets = dict(presets.get("slots") or {})
        return self

    def profile(self, index):
        """Profil numero index de la liste proposee : (nom, matiere, prereglage d'Orca ou None,
        case de base des reglages)."""
        k = self.slot_count
        if index < k:
            p = self.slot_presets.get(index)
            name = p.name if p else strip_project_suffix(self.slot_names[index])
            return name, self.slot_types[index], p, index
        p = self.presets[index - k]
        return p.name, p.type, p, self.closest_slot(p)

    def closest_slot(self, preset):
        """Case des reglages la plus proche d'un prereglage (meme matiere, couleur proche)."""
        k = self.slot_count
        want = base_type(preset.type)
        return min(range(k), key=lambda t: (base_type(self.slot_types[t]) != want,
                                            color_distance(preset.color, self.slot_colors[t]) if preset.color else 0.0, t))

    @classmethod
    def from_3mf_bytes(cls, data, source=""):
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            cfg = json.loads(z.read(PROJECT_CFG).decode("utf-8"))
            main = z.read(MAIN_MODEL).decode("utf-8", "replace")
        except (KeyError, ValueError, zipfile.BadZipFile) as e:
            raise ConvertError(tr("err_ref_unreadable", e))
        meta = {m.group(1): xml_unescape(m.group(2)).strip()
                for m in re.finditer(r'<metadata\s+name="([^"]+)"\s*>(.*?)</metadata>', main[:200000], re.S)}
        app = meta.get("Application", "")
        tag = meta.get("OrcaSlicer") or ""
        if not is_orca_file(app, tag):
            raise ConvertError(tr("err_ref_not_orca", app or tr("unknown")))
        if not tag and app.startswith("OrcaSlicer-"):
            tag = app[len("OrcaSlicer-"):]      # anciennes versions : pas d'etiquette a part
        return cls(cfg, app, tag or None, source=source)

    def to_json(self):
        return {"config": self.config, "application": self.application, "orca_tag": self.orca_tag,
                "captured_at": self.captured_at, "source": self.source}

    @classmethod
    def from_json(cls, d):
        return cls(d["config"], d.get("application", ""), d.get("orca_tag"), d.get("captured_at"), d.get("source", ""))

    @property
    def filament_total(self):
        """Nombre de filaments du projet de reference, couleurs melangees comprises."""
        return len(_cfg_list(self.config, "filament_colour")) or len(_cfg_list(self.config, "filament_settings_id"))

    @property
    def slot_count(self):
        """Cases de vrais filaments (les couleurs melangees d'Orca sont a la fin et ne comptent pas)."""
        n = self.filament_total
        mixed = _cfg_list(self.config, "filament_mixed_components")
        flags = _cfg_list(self.config, "filament_is_mixed")
        k = 0
        while k < n and not (k < len(mixed) and mixed[k].strip()) and not (k < len(flags) and flags[k].strip() in ("1", "true")):
            k += 1
        return max(1, k)

    @property
    def head_count(self):
        """Tetes de l'imprimante (4 sur la U1) : Orca garde au moins un filament par tete."""
        return len(_cfg_list(self.config, "nozzle_diameter")) or 4

    @property
    def profiles(self):
        """Profils de filament proposes pour les couleurs du modele : les cases des reglages, puis les
        prereglages de l'utilisateur (avec leur couleur par defaut s'ils en ont une)."""
        out = []
        for i, (c, t) in enumerate(zip(self.slot_colors, self.slot_types)):
            out.append({"n": i + 1, "color": c, "cname": color_name(c), "type": t or "?", "base": base_type(t),
                        "name": self.profile(i)[0], "group": "slot"})
        for p in self.presets:
            c = p.color
            out.append({"n": None, "color": c, "cname": color_name(c) if c else "", "type": p.type or "?",
                        "base": base_type(p.type), "name": p.name, "group": "other" if p.other else "user"})
        return out

    @property
    def slot_colors(self):
        return [norm_color(c) or "#808080" for c in _cfg_list(self.config, "filament_colour")[:self.slot_count]]

    @property
    def slot_types(self):
        t = _cfg_list(self.config, "filament_type")
        return [t[i] if i < len(t) else "" for i in range(self.slot_count)]

    @property
    def slot_names(self):
        t = _cfg_list(self.config, "filament_settings_id")
        return [t[i] if i < len(t) else "" for i in range(self.slot_count)]

    def bed_rect(self):
        return area_rect(_cfg_list(self.config, "printable_area")) or (0.0, 0.0, 270.0, 270.0)

    def summary(self):
        cfg = self.config
        nozzles = _cfg_list(cfg, "nozzle_diameter")
        flows = _cfg_list(cfg, "nozzle_volume_type")
        return {
            "printer": _cfg_str(cfg, "printer_settings_id"),
            "printer_model": _cfg_str(cfg, "printer_model"),
            "process": _cfg_str(cfg, "print_settings_id"),
            "bed_type": _cfg_str(cfg, "curr_bed_type"),
            "nozzles": nozzles,
            "flows": flows,
            "slots": [{"color": c, "type": t, "name": strip_project_suffix(n)}
                      for c, t, n in zip(self.slot_colors, self.slot_types[:self.slot_count], self.slot_names[:self.slot_count])],
            "captured_at": self.captured_at,
            "app": self.application,
        }


# --------------------------------------------------------------------------- plan : couleurs -> filaments

def color_key(f):
    return "%s|%s" % (f["color"] or "?", f["base"])


def color_entries(src, plate_indices):
    """Couleurs utilisees par des plaques, dans l'ordre des filaments d'origine. Deux filaments
    identiques (meme couleur, meme matiere, meme profil) ne font qu'une couleur ; rien d'autre
    n'est regroupe."""
    used = set()
    for i in plate_indices:
        used |= src.plates[i].filaments
    entries, by_key = [], {}
    for idx in sorted(used):
        f = src.filament(idx)
        if f["color"]:
            key = (f["color"], (f["type"] or "").strip().upper(), (f["name"] or "").strip())
        else:
            key = ("?", idx)
        e = by_key.get(key)
        if e is None:
            e = {"src": [], "color": f["color"], "base": f["base"]}
            by_key[key] = e
            entries.append(e)
        e["src"].append(idx)
    return entries


def _slot_cost(entry, s, template):
    """Ecart entre une couleur du modele et la bobine actuelle de la case s."""
    cost = min(color_distance(entry["color"], template.slot_colors[s]), 60.0) if entry["color"] else 30.0
    if entry["base"] != "?" and base_type(template.slot_types[s]) not in (entry["base"], "?"):
        cost += 40.0
    return cost


def order_entries(entries, template):
    """Place les couleurs : celles qui ressemblent le plus aux bobines des tetes prennent leurs cases
    (1 a 4), les autres suivent dans l'ordre d'origine. Retourne une liste (une entree ou None
    pour une case qui ne sert pas) d'au moins une case par tete."""
    heads = max(1, template.head_count)
    reach = min(heads, template.slot_count)
    n = len(entries)
    layout = [None] * max(n, heads)
    if n == 0:
        return layout
    cost = [[_slot_cost(e, s, template) for s in range(reach)] for e in entries]
    best = None
    if n <= reach:
        # chaque couleur choisit sa case
        for perm in itertools.permutations(range(reach), n):
            c = sum(cost[i][s] for i, s in enumerate(perm)) + 0.001 * sum(perm)
            if best is None or c < best[0]:
                best = (c, {s: i for i, s in enumerate(perm)})
    elif math.perm(n, reach) <= 200000:
        # chaque case choisit sa couleur
        for perm in itertools.permutations(range(n), reach):
            c = sum(cost[i][s] for s, i in enumerate(perm)) + 0.001 * sum(perm)
            if best is None or c < best[0]:
                best = (c, {s: i for s, i in enumerate(perm)})
    else:
        taken = {}
        for s in range(reach):
            i = min((i for i in range(n) if i not in taken.values()), key=lambda i: (cost[i][s], i))
            taken[s] = i
        best = (0.0, taken)
    placed = best[1]
    for s, i in placed.items():
        layout[s] = entries[i]
    rest = [e for i, e in enumerate(entries) if i not in placed.values()]
    pos = reach
    for e in rest:
        while layout[pos] is not None:
            pos += 1
        layout[pos] = e
    return layout


def default_profile(entry, s, template):
    """Profil propose pour la couleur placee en case s : celui de la case s s'il est de la bonne
    matiere, sinon le plus proche parmi tes cases et tes prereglages : meme matiere d'abord, puis
    couleur la plus proche (un prereglage sans couleur passe apres ceux qui en ont une)."""
    k = template.slot_count
    types = [base_type(t) for t in template.slot_types]
    want = entry["base"] if entry else "?"
    if s < k and (want == "?" or types[s] in (want, "?")):
        return s
    cands = [(t, types[t], template.slot_colors[t]) for t in range(k)]
    cands += [(k + i, base_type(p.type), p.color) for i, p in enumerate(template.presets) if not p.other]
    color = entry["color"] if entry else None

    def cost(c):
        idx, typ, col = c
        mismatch = not (want == "?" or typ in (want, "?"))
        if color and col:
            d = color_distance(color, col)
        else:
            d = 0.0 if not color else 1000.0
        return (mismatch, d, idx >= k, idx)
    if s < k and not any(not cost(c)[0] for c in cands):
        return s
    return min(cands, key=cost)[0]


def plan_file(src, template, plate_indices):
    """Plan d'un fichier converti : une case par couleur utilisee (au moins une par tete)."""
    layout = order_entries(color_entries(src, plate_indices), template)
    k = template.slot_count
    slots = []
    for s, e in enumerate(layout):
        if e is None:
            slots.append({"src": [], "base": s if s < k else 0})
        else:
            slots.append({"src": list(e["src"]), "base": default_profile(e, s, template)})
    return {"plates": list(plate_indices), "slots": slots}


def make_plan(src, template, one_per_plate=False):
    """Fichiers a produire : un seul avec toutes les plaques, ou un par plaque."""
    plates = [p.index for p in src.plates if p.instances]
    groups = [[i] for i in plates] if one_per_plate else [plates]
    return [plan_file(src, template, g) for g in groups if g]


# --------------------------------------------------------------------------- construction du 3MF converti

def _plate_shift(src, template, plate, dest_index, dest_cols):
    """Decalage (x, y) a ajouter aux pieces d'une plaque d'origine pour la poser sur la plaque
    dest_index du projet converti. Retourne (dx, dy, alerte ou None)."""
    sminx, sminy, smaxx, smaxy = src.bed_rect()
    dminx, dminy, dmaxx, dmaxy = template.bed_rect()
    sw, sd = smaxx - sminx, smaxy - sminy
    dw, dd = dmaxx - dminx, dmaxy - dminy
    sox, soy = src.plate_origin(plate.index)
    dox, doy = plate_origin(dest_index, dest_cols, dw, dd)
    content = None
    for inst in plate.instances:
        content = merge_bbox(content, inst.bbox)
    # position dans le plateau d'origine (coin du plateau = 0, 0)
    if content is not None:
        lx0, ly0 = content[0] - sox - sminx, content[1] - soy - sminy
        lx1, ly1 = content[3] - sox - sminx, content[4] - soy - sminy
    else:
        lx0 = ly0 = lx1 = ly1 = 0.0
    if abs(sw - dw) <= 1.0 and abs(sd - dd) <= 1.0:
        sx, sy = 0.0, 0.0                       # meme plateau : on garde la position
    else:
        sx, sy = (dw - sw) / 2.0, (dd - sd) / 2.0   # on garde la position par rapport au centre
    warn = None
    margin = 0.5
    if content is not None:
        if (lx1 - lx0) > dw + 0.01 or (ly1 - ly0) > dd + 0.01:
            warn = tr("w_too_big", lx1 - lx0, ly1 - ly0)
            sx = (dw - (lx1 + lx0)) / 2.0
            sy = (dd - (ly1 + ly0)) / 2.0
        elif lx0 + sx < margin or ly0 + sy < margin or lx1 + sx > dw - margin or ly1 + sy > dd - margin:
            sx = (dw - (lx1 + lx0)) / 2.0         # deborde : on centre le contenu
            sy = (dd - (ly1 + ly0)) / 2.0
    dx = dox + dminx + sx - (sox + sminx)
    dy = doy + dminy + sy - (soy + sminy)
    return dx, dy, sx, sy, warn


def _remap_value(key, value, mapping):
    """Renumerote un reglage de filament. Retourne (cle, valeur) a ecrire."""
    v = _int(value, 0)
    if key in FILAMENT_KEYS_LEGACY:
        new_key = FILAMENT_KEYS_LEGACY[key]
        if v <= 0 or (v == 1 and key in _LEGACY_ONE_IS_DEFAULT):
            return new_key, "0"
        return new_key, str(mapping.get(v, 1))
    if v <= 0:
        return key, str(v)
    return key, str(mapping.get(v, 1))


def _remap_metadata_elems(parent, mapping, extruder_default_one=False):
    for md in parent.findall("metadata"):
        key = md.get("key")
        if key == "extruder":
            v = _int(md.get("value"), 0)
            if v >= 1:
                md.set("value", str(mapping.get(v, 1)))
        elif key in FILAMENT_KEYS_NEW or key in FILAMENT_KEYS_LEGACY:
            new_key, new_val = _remap_value(key, md.get("value"), mapping)
            md.set("key", new_key)
            md.set("value", new_val)


_PLATE_KEYS_DROP = {"filament_map_mode", "filament_maps", "filament_volume_maps", "thumbnail_file",
                    "thumbnail_no_light_file", "top_file", "pick_file", "pattern_file", "pattern_bbox_file",
                    "gcode_file", "bed_type", "nozzle_diameters", "printer_model_id", "limit_filament_maps",
                    "first_layer_print_sequence", "other_layers_print_sequence",
                    "other_layers_print_sequence_nums"}


def _xml_bytes(root):
    ET.indent(root, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


def _rewrite_main_model(src, text, drop_objs, keep_inst, shifts, template):
    """Fichier 3D/3dmodel.model : metadonnees, objets gardes, positions."""
    # metadonnees de l'application : celles de l'OrcaSlicer de l'utilisateur
    app_line = '<metadata name="Application">%s</metadata>' % xml_escape(template.application)
    pat_app = re.compile(r'<metadata\s+name="Application"\s*>.*?</metadata>', re.S)
    if pat_app.search(text):
        text = pat_app.sub(lambda m: app_line, text, count=1)
    else:
        text = re.sub(r"(<model\b[^>]*>)", lambda m: m.group(1) + "\n " + app_line, text, count=1)
    text = re.sub(r'[ \t]*<metadata\s+name="OrcaSlicer"\s*>.*?</metadata>[ \t]*\r?\n?', "", text, flags=re.S)
    if template.orca_tag:
        orca_line = '<metadata name="OrcaSlicer">%s</metadata>' % xml_escape(template.orca_tag)
        text = text.replace(app_line, app_line + "\n " + orca_line, 1)
    text = re.sub(r'[ \t]*<metadata\s+name="Thumbnail_(?:Middle|Small)"\s*>.*?</metadata>[ \t]*\r?\n?', "", text, flags=re.S)
    # objets de premier niveau dont aucune instance n'est gardee
    if drop_objs:
        def obj_sub(m):
            return "" if tag_attrs(m.group(1)).get("id") in drop_objs else m.group(0)
        text = re.sub(r"[ \t]*<object\b([^>]*)>.*?</object>[ \t]*\r?\n?", obj_sub, text, flags=re.S)
    # construction : instances gardees, deplacees sur leur nouvelle plaque
    b = text.find("<build")
    if b >= 0:
        e = text.find("</build>", b)
        end = e if e > 0 else len(text)
        section = text[b:end]
        counters = {}

        def item_sub(m):
            tag = m.group(1)
            a = tag_attrs(m.group(2))
            oid = a.get("objectid")
            obj = src.objects.get(oid)
            if obj is None:
                return m.group(0)
            i = counters.get(oid, 0)
            counters[oid] = i + 1
            if (oid, i) not in keep_inst or i >= len(obj.instances):
                return ""
            inst = obj.instances[i]
            dx, dy = shifts.get(inst.plate.index, (0.0, 0.0))
            t = list(inst.transform)
            t[9] += dx
            t[10] += dy
            new_tf = 'transform="%s"' % format_transform(t)
            if re.search(r'\btransform="[^"]*"', tag):
                new_tag = re.sub(r'\btransform="[^"]*"', lambda _: new_tf, tag, count=1)
            else:
                new_tag = tag.replace("<item", "<item " + new_tf, 1)
            return m.group(0).replace(tag, new_tag, 1)
        section = re.sub(r"[ \t]*(<item\b([^>]*?)(?:/>|>\s*</item>))[ \t]*\r?\n?", item_sub, section)
        text = text[:b] + section + text[end:]
    return text


def build_project_config(template, slots):
    """Reglages du projet converti, faits a partir de ceux de l'utilisateur. slots : une entree par
    filament du projet converti, {"base": case des reglages, "preset": prereglage d'Orca ou None,
    "color": couleur voulue ou None pour garder celle de la case}. Chaque reglage de filament vient
    du prereglage d'Orca s'il y en a un (avec ses variantes de buse, comme Orca l'ecrit dans un
    projet), sinon de la case de base (lignes de filament_self_index)."""
    cfg = json.loads(json.dumps(template.config))
    total = template.filament_total
    if not total or not slots:
        return cfg
    bases = [min(max(0, int(s["base"])), total - 1) for s in slots]
    presets = [s.get("preset") for s in slots]
    physical = template.slot_count
    self_index = [_int(x, 0) for x in _cfg_list(cfg, "filament_self_index")]
    rows_of = {}
    for r, fi in enumerate(self_index):
        rows_of.setdefault(fi - 1, []).append(r)
    n_rows = len(self_index) if self_index else total

    def rows(b):
        return rows_of.get(b) or [min(b, n_rows - 1)]

    # lignes de chaque filament : une par variante de buse du prereglage, sinon celles de la case
    counts = []
    for b, p in zip(bases, presets):
        pv = p.variants() if (p is not None and self_index) else []
        counts.append(len(pv) if pv else len(rows(b)))

    def is_text(values):
        return any(isinstance(x, str) and ("," in x or " " in x or "\n" in x) for x in values)

    def per_filament(key, values):
        out = []
        text = is_text(values)
        for b, p in zip(bases, presets):
            pv = p.values(key, text) if p is not None else None
            out.append(pv[0] if pv else values[b])
        return out

    def per_row(key, values):
        out = []
        text = is_text(values)
        for b, p, n in zip(bases, presets, counts):
            pv = p.values(key, text) if p is not None else None
            if pv:
                out.extend(pv[i] if i < len(pv) else pv[0] for i in range(n))
            else:
                rb = rows(b)
                out.extend(values[rb[min(i, len(rb) - 1)]] for i in range(n))
        return out

    special = set(FILAMENT_POSITION_KEYS) | set(FILAMENT_MIXED_DEFAULTS) | {
        "filament_self_index", "filament_colour", "filament_multi_colour", "filament_colour_type",
        "filament_settings_id", "filament_ids"}
    for key in list(cfg):
        v = cfg[key]
        if not isinstance(v, list) or key in special:
            continue
        if key not in FILAMENT_PRESET_KEYS and not key.startswith("filament_"):
            continue
        if self_index and len(v) == n_rows and (n_rows != total or key in FILAMENT_VARIANT_KEYS):
            cfg[key] = per_row(key, v)
        elif len(v) == total:
            cfg[key] = per_filament(key, v)
    # nom des profils (ceux d'Orca, sans nom de projet ajoute) et identifiant de filament
    names = _cfg_list(cfg, "filament_settings_id")
    if names:
        cfg["filament_settings_id"] = [
            p.name if p is not None else strip_project_suffix(names[b] if b < len(names) else "")
            for b, p in zip(bases, presets)]
    ids = cfg.get("filament_ids")
    if isinstance(ids, list) and len(ids) == total:
        cfg["filament_ids"] = [(p.scalar("filament_id") if p is not None and p.scalar("filament_id") is not None
                                else ids[b]) for b, p in zip(bases, presets)]
    if self_index:
        cfg["filament_self_index"] = [str(j + 1) for j, n in enumerate(counts) for _r in range(n)]
    # tete et buse prevues : celles de la case pour les premieres places, sinon celles du profil
    for key in FILAMENT_POSITION_KEYS:
        v = cfg.get(key)
        if isinstance(v, list) and len(v) == total:
            cfg[key] = [v[j] if j < physical else v[b] for j, b in enumerate(bases)]
    for key, default in FILAMENT_MIXED_DEFAULTS.items():
        if isinstance(cfg.get(key), list):
            cfg[key] = [default] * len(bases)
    # couleurs : celles du modele (format de l'utilisateur, avec ou sans transparence)
    colours = _cfg_list(template.config, "filament_colour")
    alpha = bool(colours) and all(len((c or "").strip().lstrip("#")) == 8 for c in colours)
    multi = _cfg_list(template.config, "filament_multi_colour")
    ctype = _cfg_list(template.config, "filament_colour_type")
    new_cols, new_multi, new_types = [], [], []
    for s, b in zip(slots, bases):
        col = s.get("color")
        if col:
            new_cols.append(col + ("FF" if alpha else ""))
            new_multi.append(col + ("FF" if alpha else ""))
            new_types.append("1")
        else:
            new_cols.append(colours[b] if b < len(colours) else "#FFFFFF")
            new_multi.append(multi[b] if b < len(multi) else new_cols[-1])
            new_types.append(ctype[b] if b < len(ctype) else "1")
    cfg["filament_colour"] = new_cols
    if isinstance(cfg.get("filament_multi_colour"), list):
        cfg["filament_multi_colour"] = new_multi
    if isinstance(cfg.get("filament_colour_type"), list):
        cfg["filament_colour_type"] = new_types
    # profils utilises : [traitement, filaments..., imprimante]. Pour un prereglage d'Orca : son
    # parent, ses conditions, et aucun ecart note (Orca reprend alors les valeurs du projet telles
    # quelles et reconnait ton prereglage a l'ouverture)
    from_preset = {"inherits_group": "inherits", "compatible_machine_expression_group": "compatible_printers_condition",
                   "compatible_process_expression_group": "compatible_prints_condition"}

    def group(key, values):
        out = []
        for b, p in zip(bases, presets):
            if p is None:
                out.append(values[b])
            elif key == "different_settings_to_system":
                out.append("")
            else:
                out.append(p.scalar(from_preset[key]) or "")
        return out
    for key in PRESET_GROUP_KEYS:
        v = cfg.get(key)
        if not isinstance(v, list):
            continue
        if len(v) == total + 2:
            cfg[key] = [v[0]] + group(key, v[1:-1]) + [v[-1]]
        elif len(v) == total + 1:
            cfg[key] = [v[0]] + group(key, v[1:])
        elif len(v) == total:
            cfg[key] = group(key, v)
    # purge entre filaments : celle des profils de base, calculee comme Orca entre deux couleurs
    # qui partagent le meme profil
    vec = cfg.get("flush_volumes_vector")
    new_vec = None
    if isinstance(vec, list) and len(vec) == 2 * total:
        new_vec = [vec[2 * b + k] for b in bases for k in (0, 1)]
        cfg["flush_volumes_vector"] = new_vec
    mat = cfg.get("flush_volumes_matrix")
    mult = cfg.get("flush_multiplier")
    nozzles = len(mult) if isinstance(mult, list) and mult else 1
    if isinstance(mat, list) and len(mat) == total * total * nozzles:
        out = []
        for z in range(nozzles):
            off = z * total * total
            for i, bi in enumerate(bases):
                for j, bj in enumerate(bases):
                    if i == j:
                        out.append("0")
                    elif bi != bj:
                        out.append(mat[off + bi * total + bj])
                    else:
                        try:
                            out.append(_fmt_num(float(new_vec[2 * i]) + float(new_vec[2 * j + 1])) if new_vec else mat[off + 1 if total > 1 else off])
                        except (ValueError, IndexError):
                            out.append("140")
        cfg["flush_volumes_matrix"] = out
    # reglages du traitement qui designent un filament : rien au-dela du dernier
    m = len(bases)
    for key in FILAMENT_KEYS_NEW:
        v = cfg.get(key)
        if isinstance(v, str) and _int(v, 0) > m:
            cfg[key] = "0"
    return cfg


def slot_mapping(slots):
    """Filament d'origine -> numero de filament du projet converti."""
    return {int(idx): j + 1 for j, s in enumerate(slots) for idx in s["src"]}


def build_output(src, template, group, slots, report):
    """Construit le 3MF converti pour un groupe de plaques. slots : filaments du projet converti
    (voir plan_file). Retourne les octets du fichier."""
    plates = [src.plates[i] for i in group]
    dest_cols = compute_column_count(len(plates))
    mapping = slot_mapping(slots)
    # instances et objets gardes
    keep_inst = set()
    for p in plates:
        for inst in p.instances:
            keep_inst.add((inst.obj.id, inst.index))
    keep_objs = {oid for oid, _ in keep_inst}
    drop_objs = {oid for oid in src.object_order if src.objects[oid].instances and oid not in keep_objs}
    remaining = [oid for oid in src.object_order if oid not in drop_objs]
    inst_new = {}
    for oid in remaining:
        k = 0
        for inst in src.objects[oid].instances:
            if (oid, inst.index) in keep_inst:
                inst_new[(oid, inst.index)] = k
                k += 1
    rank_new = {src.objects[oid].rank: r for r, oid in enumerate(remaining, 1)}
    # decalage de chaque plaque vers sa place dans le projet converti
    shifts, local_shift = {}, {}
    for j, p in enumerate(plates):
        dx, dy, sx, sy, warn = _plate_shift(src, template, p, j, dest_cols)
        shifts[p.index] = (dx, dy)
        local_shift[p.index] = (sx, sy)
        if warn:
            report["warnings"].append(tr("w_plate", p.id, p.name or tr("unnamed"), warn))

    out_files = {}
    # --- modele principal
    main_text = _rewrite_main_model(src, src.text(src.main), drop_objs, keep_inst, shifts, template)
    out_files[src.main] = remap_paint_in_xml(main_text, mapping).encode("utf-8")
    # --- sous-modeles encore references
    needed_files = set()
    for oid in remaining:
        for path, _sub, _tf in src.objects[oid].components:
            if path != src.main:
                needed_files.add(path)
    for name in src.names:
        if name == src.main or not name.lower().endswith(".model"):
            continue
        if name in needed_files:
            out_files[name] = remap_paint_in_xml(src.text(name), mapping).encode("utf-8")
        else:
            out_files[name] = None
    if MAIN_RELS in src.nameset:
        def rel_sub(m):
            target = (tag_attrs(m.group(1)).get("Target") or "").lstrip("/")
            return "" if target.lower().endswith(".model") and target not in needed_files else m.group(0)
        rels = re.sub(r"[ \t]*<Relationship\b([^>]*)/>[ \t]*\r?\n?", rel_sub, src.text(MAIN_RELS))
        out_files[MAIN_RELS] = rels.encode("utf-8")
    # --- reglages des objets et des plaques
    if src.model_cfg is not None:
        root = ET.fromstring(src.raw(MODEL_CFG))
        for oe in list(root.findall("object")):
            if oe.get("id") in drop_objs:
                root.remove(oe)
                continue
            _remap_metadata_elems(oe, mapping)
            for pe in oe.findall("part"):
                _remap_metadata_elems(pe, mapping)
        children = list(root)
        first_plate = next((i for i, c in enumerate(children) if c.tag == "plate"), None)
        for pe in root.findall("plate"):
            root.remove(pe)
        insert_at = first_plate if first_plate is not None else len([c for c in root if c.tag == "object"])
        for j, p in enumerate(plates):
            root.insert(insert_at + j, _new_plate_elem(src, p, j, inst_new))
        asm = root.find("assemble")
        if asm is not None:
            for it in list(asm.findall("assemble_item")):
                key = (it.get("object_id"), _int(it.get("instance_id"), 0))
                if key not in inst_new:
                    asm.remove(it)
                else:
                    it.set("instance_id", str(inst_new[key]))
        out_files[MODEL_CFG] = _xml_bytes(root)
    else:
        root = ET.Element("config")
        for oid in remaining:
            obj = src.objects[oid]
            if not obj.instances:
                continue
            oe = ET.SubElement(root, "object", id=oid)
            ET.SubElement(oe, "metadata", key="name", value=obj.name or ("objet %s" % oid))
            ET.SubElement(oe, "metadata", key="extruder", value=str(mapping.get(obj.extruder, 1)))
        for j, p in enumerate(plates):
            root.append(_new_plate_elem(src, p, j, inst_new))
        out_files[MODEL_CFG] = _xml_bytes(root)
    # --- reglages du projet : ceux de l'utilisateur, un filament par couleur du modele
    cfg_slots = []
    for s in slots:
        name, _t, preset, base = template.profile(s["base"])
        color = (s.get("pick") or src.filament(s["src"][0])["color"]) if s["src"] else None
        cfg_slots.append({"base": base, "preset": preset, "color": color})
    cfg = build_project_config(template, cfg_slots)
    # tour d'essuyage : a la place choisie par l'auteur, deplacee comme les pieces
    sx_list, sy_list = _cfg_list(src.config, "wipe_tower_x"), _cfg_list(src.config, "wipe_tower_y")
    tx_list, ty_list = _cfg_list(cfg, "wipe_tower_x") or ["15"], _cfg_list(cfg, "wipe_tower_y") or ["220"]
    dminx, dminy, dmaxx, dmaxy = template.bed_rect()
    new_x, new_y = [], []
    for p in plates:
        try:
            if p.index < len(sx_list) and p.index < len(sy_list):
                x = float(sx_list[p.index]) + local_shift[p.index][0] + (dminx - src.bed_rect()[0])
                y = float(sy_list[p.index]) + local_shift[p.index][1] + (dminy - src.bed_rect()[1])
            else:
                x, y = float(tx_list[0]), float(ty_list[0])
        except ValueError:
            x, y = 15.0, 220.0
        x = min(max(x, 1.0), max(1.0, (dmaxx - dminx) - 40.0))
        y = min(max(y, 1.0), max(1.0, (dmaxy - dminy) - 40.0))
        new_x.append(_fmt_num(round(x, 3)))
        new_y.append(_fmt_num(round(y, 3)))
    cfg["wipe_tower_x"] = new_x
    cfg["wipe_tower_y"] = new_y
    out_files[PROJECT_CFG] = json.dumps(cfg, indent=4, ensure_ascii=False).encode("utf-8")
    # --- fichiers annexes lies aux objets et aux plaques
    if LAYER_RANGES in src.nameset:
        out_files[LAYER_RANGES] = _rewrite_ranked_xml(src.raw(LAYER_RANGES), rank_new, mapping)
    if CUT_INFO in src.nameset:
        out_files[CUT_INFO] = _rewrite_ranked_xml(src.raw(CUT_INFO), rank_new, None)
    for name in (LAYER_HEIGHTS, BRIM_EARS):
        if name in src.nameset:
            out_files[name] = _rewrite_object_lines(src.raw(name), rank_new)
    if CUSTOM_GCODE in src.nameset:
        plate_new = {p.id: j + 1 for j, p in enumerate(plates)}
        out_files[CUSTOM_GCODE] = _rewrite_custom_gcode(src.raw(CUSTOM_GCODE), plate_new, mapping)
    return _pack(src, out_files)


def _pack(src, out_files):
    order = list(src.names)
    for extra in (PROJECT_CFG, MODEL_CFG):
        if extra not in src.nameset:
            order.append(extra)
    final = []
    seen = set()
    for name in order:
        if name in seen:
            continue
        seen.add(name)
        if name in out_files:
            if out_files[name] is not None:
                final.append(name)
        elif not _DROP.match(name):
            final.append(name)
    keep = set(final)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in final:
            if name == PKG_RELS and name not in out_files:
                data = _filter_pkg_rels(src.raw(name), keep)
            elif name in out_files:
                data = out_files[name]
            else:
                data = src.raw(name)
            z.writestr(name, data)
    return buf.getvalue()


def _new_plate_elem(src, p, j, inst_new):
    pe = ET.Element("plate")
    ET.SubElement(pe, "metadata", key="plater_id", value=str(j + 1))
    have = set()
    if p.elem is not None:
        for md in p.elem.findall("metadata"):
            key = md.get("key")
            if key in _PLATE_KEYS_DROP or key == "plater_id" or key is None:
                continue
            have.add(key)
            ET.SubElement(pe, "metadata", key=key, value=md.get("value", ""))
    if "plater_name" not in have:
        ET.SubElement(pe, "metadata", key="plater_name", value=p.name or "")
    if "locked" not in have:
        ET.SubElement(pe, "metadata", key="locked", value="false")
    for inst in p.instances:
        key = (inst.obj.id, inst.index)
        if key not in inst_new:
            continue
        mi = ET.SubElement(pe, "model_instance")
        ET.SubElement(mi, "metadata", key="object_id", value=inst.obj.id)
        ET.SubElement(mi, "metadata", key="instance_id", value=str(inst_new[key]))
        ident = src.identify.get(key)
        if ident:
            ET.SubElement(mi, "metadata", key="identify_id", value=ident)
    return pe


def _rewrite_ranked_xml(data, rank_new, mapping):
    """layer_config_ranges.xml / cut_information.xml : objets reperes par leur rang (1..)."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    for oe in list(root.findall("object")):
        old = _int(oe.get("id"), 0)
        if old not in rank_new:
            root.remove(oe)
            continue
        oe.set("id", str(rank_new[old]))
        if mapping is None:
            continue
        for opt in oe.iter("option"):
            key = opt.get("opt_key")
            if key == "extruder":
                v = _int(opt.text, 0)
                if v >= 1:
                    opt.text = str(mapping.get(v, 1))
            elif key in FILAMENT_KEYS_NEW or key in FILAMENT_KEYS_LEGACY:
                new_key, new_val = _remap_value(key, opt.text, mapping)
                opt.set("opt_key", new_key)
                opt.text = new_val
    return _xml_bytes(root)


def _rewrite_object_lines(data, rank_new):
    """layer_heights_profile.txt / brim_ear_points.txt : lignes 'object_id=N|...'."""
    out = []
    for line in data.decode("utf-8", "replace").splitlines():
        m = re.match(r"\s*object_id=(\d+)\|(.*)$", line)
        if not m:
            out.append(line)
            continue
        old = int(m.group(1))
        if old in rank_new:
            out.append("object_id=%d|%s" % (rank_new[old], m.group(2)))
    return ("\n".join(out) + ("\n" if out else "")).encode("utf-8")


def _rewrite_custom_gcode(data, plate_new, mapping):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    for pe in list(root.findall("plate")):
        info = pe.find("plate_info")
        pid = _int(info.get("id"), 1) if info is not None else 1
        if pid not in plate_new:
            root.remove(pe)
            continue
        if info is not None:
            info.set("id", str(plate_new[pid]))
        for layer in pe.findall("layer"):
            ext = _int(layer.get("extruder"), 0)
            if ext >= 1:
                layer.set("extruder", str(mapping.get(ext, 1)))
    return _xml_bytes(root)


def _filter_pkg_rels(data, keep):
    text = data.decode("utf-8", "replace")

    def sub(m):
        target = (tag_attrs(m.group(1)).get("Target") or "").lstrip("/")
        return m.group(0) if not target or target in keep else ""
    return re.sub(r"[ \t]*<Relationship\b([^>]*)/>[ \t]*\r?\n?", sub, text).encode("utf-8")


# --------------------------------------------------------------------------- analyse et conversion (API)

OUT_TAG = "U1-by-Dragg"   # signe les fichiers convertis : « modele - U1-by-Dragg.3mf »


def output_name(src, plates, multiple):
    base = os.path.splitext(os.path.basename(src.name or "projet.3mf"))[0]
    base = re.sub(r"\s*-\s*U1(?:-by-Dragg)?(\s*-\s*(?:plaques?|plates?) [\d\-]+)?$", "", base).strip() or "projet"
    if not multiple:
        return "%s - %s.3mf" % (base, OUT_TAG)
    ids = "-".join(str(p.id) for p in plates)
    return tr("out_plateN" if len(plates) > 1 else "out_plate1", base, ids, OUT_TAG)


def describe_source(src):
    minx, miny, maxx, maxy = src.bed_rect()
    nozzles = _cfg_list(src.config, "nozzle_diameter")
    plates = [p.index for p in src.plates if p.instances]
    return {
        "app": src.app_label(),
        "kind": src.kind,
        "printer": src.printer or "",
        "nozzle": nozzles[0] if nozzles else "",
        "bed": [round(maxx - minx), round(maxy - miny)],
        "plates": len(plates),
        "colors": len(color_entries(src, plates)),
        "title": src.meta.get("Title", ""),
        "designer": src.meta.get("Designer", ""),
    }


def plate_thumbnail(src, plate):
    for name in ("Metadata/plate_%d_small.png" % plate.id, "Metadata/plate_%d.png" % plate.id):
        if name in src.nameset:
            try:
                data = src.raw(name)
            except KeyError:
                continue
            if len(data) < 400000:
                return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    return ""


def _check_source(src):
    if src.kind == "prusa":
        raise ConvertError(tr("err_prusa"))
    if src.is_sliced_only:
        raise ConvertError(tr("err_sliced"))
    if not any(o.instances for o in src.objects.values()):
        raise ConvertError(tr("err_no_part"))


def analyze(src, template, one_per_plate=False, with_thumbs=True):
    """Resultat d'analyse pour l'interface : source, plaques, fichiers prevus, alertes."""
    _check_source(src)
    plan = make_plan(src, template, one_per_plate)
    filaments = []
    used = set()
    for p in src.plates:
        used |= p.filaments
    for idx in sorted(used):
        f = src.filament(idx)
        filaments.append({"index": idx, "color": f["color"] or "#808080", "known": bool(f["color"]),
                          "name": color_name(f["color"]), "type": f["type"] or "?", "base": f["base"],
                          "preset": f["name"], "mixed": f["mixed"],
                          "plates": [p.id for p in src.plates if idx in p.filaments]})
    plates = []
    for p in src.plates:
        if not p.instances:
            continue
        plates.append({"index": p.index, "id": p.id, "name": p.name, "objects": len(p.instances),
                       "filaments": sorted(p.filaments),
                       "thumb": plate_thumbnail(src, p) if with_thumbs else ""})
    files = []
    multiple = len(plan) > 1
    for f in plan:
        gplates = [src.plates[i] for i in f["plates"]]
        slots = []
        for j, s in enumerate(f["slots"]):
            if not s["src"]:
                slots.append({"n": j + 1, "src": [], "base": s["base"], "pad": True})
                continue
            fl = src.filament(s["src"][0])
            slots.append({"n": j + 1, "src": s["src"], "base": s["base"], "pad": False,
                          "color": fl["color"] or "#808080", "known": bool(fl["color"]),
                          "name": color_name(fl["color"]), "type": fl["type"] or "?", "ftype": fl["base"],
                          "preset": fl["name"], "mixed": any(src.filament(i)["mixed"] for i in s["src"]),
                          "same": len(s["src"]),
                          "plates": [p.id for p in gplates if any(i in p.filaments for i in s["src"])]})
        files.append({"plates": f["plates"], "plate_ids": [p.id for p in gplates],
                      "name": output_name(src, gplates, multiple), "slots": slots,
                      "colors": sum(1 for s in slots if not s["pad"])})
    warnings = list(src.warnings)
    if any(src.filament(i)["mixed"] for i in used if i not in src.virtual):
        warnings.append(tr("w_mixed_orca"))
    if src.virtual and any(i in src.virtual for i in used):
        warnings.append(tr("w_mixed_fs"))
    if any(m.unreadable_paint for m in src.meshes.values() if isinstance(m, Mesh)):
        warnings.append(tr("w_paint"))
    if any(len(f["slots"]) > MAX_PAINT_FILAMENTS for f in plan):
        warnings.append(tr("w_paint_max", MAX_PAINT_FILAMENTS))
    return {
        "source": describe_source(src),
        "filaments": filaments,
        "plates": plates,
        "files": files,
        "profiles": template.profiles,
        "heads": template.head_count,
        "warnings": warnings,
    }


def check_plan(src, template, files):
    """Verifie un plan envoye par l'interface : plaques, couleurs et profils de chaque filament."""
    k = template.slot_count
    heads = template.head_count
    seen = set()
    clean = []
    for f in files:
        plates = []
        for i in f.get("plates") or []:
            i = _int(i, -1)
            if 0 <= i < len(src.plates) and src.plates[i].instances and i not in seen and i not in plates:
                plates.append(i)
        seen.update(plates)
        if not plates:
            continue
        needed = set()
        for i in plates:
            needed |= src.plates[i].filaments
        slots, got = [], set()
        for s in f.get("slots") or []:
            srcs = []
            for x in s.get("src") or []:
                x = _int(x, 0)
                if x in needed and x not in got:
                    srcs.append(x)
                    got.add(x)
            base = _int(s.get("base"), -1)
            if not 0 <= base < k + len(template.presets):
                raise ConvertError(tr("err_profile", base + 1))
            pick = s.get("color")
            pick = pick.upper() if isinstance(pick, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", pick) else None
            slots.append({"src": srcs, "base": base, "pick": pick if srcs else None})
        missing = needed - got
        if missing:
            raise ConvertError(tr("err_no_slot", ", ".join(str(x) for x in sorted(missing))))
        while len(slots) > heads and not slots[-1]["src"]:
            slots.pop()
        while len(slots) < heads:
            slots.append({"src": [], "base": len(slots) if len(slots) < k else 0})
        clean.append({"plates": plates, "slots": slots})
    missing_plates = [p.id for p in src.plates if p.instances and p.index not in seen]
    if missing_plates:
        raise ConvertError(tr("err_plates_missing", ", ".join(map(str, missing_plates))))
    return clean


def convert(src, template, files, progress=None):
    """Produit les fichiers convertis : liste de dicts {name, data, plates, map, filaments, report}."""
    _check_source(src)
    files = check_plan(src, template, files)
    results = []
    multiple = len(files) > 1
    for fi, f in enumerate(files):
        if progress:
            progress(tr("p_file", fi + 1, len(files)) if multiple else tr("p_converting"))
        plates = [src.plates[i] for i in f["plates"]]
        report = {"warnings": []}
        for j, s in enumerate(f["slots"]):
            if not s["src"]:
                continue
            fl = src.filament(s["src"][0])
            name, ftype = template.profile(s["base"])[:2]
            want, have = fl["base"], base_type(ftype)
            if want != "?" and have != "?" and want != have:
                report["warnings"].append(tr("w_material", j + 1, color_name(fl["color"]), want, name or "?", have))
        data = build_output(src, template, f["plates"], f["slots"], report)
        results.append({"name": output_name(src, plates, multiple), "data": data,
                        "plates": [p.id for p in plates], "map": slot_mapping(f["slots"]),
                        "filaments": len(f["slots"]),
                        "colors": sum(1 for s in f["slots"] if s["src"]), "report": report})
    return results


# --------------------------------------------------------------------------- reglages actuels d'Orca

def _split_cfg_value(value):
    """Valeur de reglage serialisee par Orca -> liste ('"a";"b"', 'a;b', '0.4,0.4')."""
    v = (value or "").strip()
    if not v:
        return []
    if '"' in v:
        return [x.replace('\\"', '"') for x in re.findall(r'"((?:[^"\\]|\\.)*)"', v)]
    if ";" in v:
        return [x.strip() for x in v.split(";") if x.strip()]
    return [x.strip() for x in v.split(",") if x.strip()]


def current_settings():
    """Resume des reglages selectionnes dans Orca (sans rien exporter)."""
    bundle = orca.host.preset_bundle()

    def full(key):
        try:
            return bundle.full_config_value(key) or ""
        except Exception:
            return ""
    try:
        printer = bundle.current_printer_preset()
        printer_name = printer.name
        printer_model = printer.config_value("printer_model") or full("printer_model")
    except Exception:
        printer_name, printer_model = full("printer_settings_id"), full("printer_model")
    try:
        process_name = bundle.current_process_preset().name
    except Exception:
        process_name = full("print_settings_id")
    try:
        fil_names = list(bundle.current_filament_preset_names())
    except Exception:
        fil_names = _split_cfg_value(full("filament_settings_id"))
    cfg = {
        "printer_settings_id": printer_name,
        "printer_model": (printer_model or "").strip('"'),
        "print_settings_id": process_name,
        "filament_settings_id": fil_names,
        "filament_colour": _split_cfg_value(full("filament_colour")),
        "filament_type": _split_cfg_value(full("filament_type")),
        "printable_area": _split_cfg_value(full("printable_area")),
        "curr_bed_type": full("curr_bed_type").strip('"'),
        "nozzle_diameter": _split_cfg_value(full("nozzle_diameter")),
        "nozzle_volume_type": _split_cfg_value(full("nozzle_volume_type")),
        "filament_mixed_components": _split_cfg_value(full("filament_mixed_components")),
    }
    return Template(cfg, "OrcaSlicer", None, source="current")


def default_u1_template():
    cfg = {"printer_settings_id": "Snapmaker U1 (0.4 nozzle)", "printer_model": "Snapmaker U1",
           "print_settings_id": "", "filament_colour": ["#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFFFFF"],
           "filament_type": ["PLA"] * 4, "filament_settings_id": ["", "", "", ""],
           "printable_area": ["0.5x1", "270.5x1", "270.5x271", "0.5x271"]}
    return Template(cfg, "OrcaSlicer", None, source="default")


def is_u1(model_name):
    return "U1" in (model_name or "") and "snapmaker" in (model_name or "").lower()


# --------------------------------------------------------------------------- stockage du plugin

_STORAGE = [None]


def storage_dir():
    if _STORAGE[0] is None:
        path = orca.host.plugin.storage()
        if not path:
            raise RuntimeError(tr("err_storage"))
        os.makedirs(path, exist_ok=True)
        _STORAGE[0] = path
    return _STORAGE[0]


def downloads_dir():
    return os.path.join(os.path.expanduser("~"), "Downloads")


def _template_path():
    return os.path.join(storage_dir(), "reglages_memorises.json")


def load_saved_template():
    try:
        with open(_template_path(), "r", encoding="utf-8") as f:
            return Template.from_json(json.load(f))
    except (OSError, ValueError, KeyError, RuntimeError):
        return None


def save_template(template):
    path = _template_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(template.to_json(), f)
    os.replace(tmp, path)


def _options_path():
    return os.path.join(storage_dir(), "options.json")


def load_options():
    try:
        with open(_options_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_options(options):
    path = _options_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(options, f)
    os.replace(tmp, path)


OUT_MODES = ("beside", "downloads", "folder")


def output_choice(options=None):
    """Ou ecrire les fichiers convertis : (mode, dossier choisi)."""
    o = options if options is not None else load_options()
    mode = o.get("out") if o.get("out") in OUT_MODES else "beside"
    return mode, str(o.get("out_dir") or "")


def output_folder(source_path, options=None):
    """Dossier des fichiers convertis selon le choix de l'utilisateur."""
    mode, folder = output_choice(options)
    if mode == "downloads":
        return downloads_dir()
    if mode == "folder" and folder and os.path.isdir(folder):
        return folder
    return _output_folder(source_path) if source_path else downloads_dir()


def capture_current_template():
    """Exporte une copie du projet ouvert (fil de l'interface) et en garde les reglages."""
    path = os.path.join(storage_dir(), "capture_reglages.3mf")
    orca.host.plater().export_3mf_copy(path)
    try:
        with open(path, "rb") as f:
            data = f.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return Template.from_3mf_bytes(data, source="orca")


def log_error(text):
    try:
        with open(os.path.join(storage_dir(), "erreurs.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n")
    except Exception:
        pass


def app_label(app):
    """« BambuStudio-02.03.01.51 » -> « Bambu Studio 02.03.01.51 »."""
    m = re.match(r"([A-Za-z_ ]+?)[- ]?(\d[\w.\-]*)$", app or "")
    name, ver = (m.group(1), m.group(2)) if m else (app or "", "")
    name = {"BambuStudio": "Bambu Studio", "Snapmaker_Orca": "Snapmaker Orca", "OrcaSlicer": "OrcaSlicer"}.get(name, name.replace("_", " "))
    return (name + " " + ver).strip() or tr("unknown_app")


def is_orca_file(app, orca_tag):
    """Projet enregistre par OrcaSlicer : etiquette « OrcaSlicer » (Orca 2.3.2 et plus, qui signe
    l'application « BambuStudio-… ») ou application « OrcaSlicer-… » (anciennes versions)."""
    app = app or ""
    return not app.lower().startswith("snapmaker") and (bool(orca_tag) or app.startswith("OrcaSlicer"))


def sniff_3mf(path):
    """Lecture rapide : d'ou vient le 3MF, pour quelle imprimante, combien de couleurs."""
    info = {"path": path, "name": os.path.basename(path)}
    try:
        st = os.stat(path)
        info["size"] = st.st_size
        info["mtime"] = st.st_mtime
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            head = b""
            main = MAIN_MODEL if MAIN_MODEL in names else next((n for n in names if n.lower().endswith("3dmodel.model")), None)
            if main:
                with z.open(main) as f:
                    head = f.read(16384)
            m = re.search(rb'<metadata\s+name="Application"\s*>([^<]*)<', head)
            app = m.group(1).decode("utf-8", "replace") if m else ""
            info["app"] = app
            m = re.search(rb'<metadata\s+name="OrcaSlicer"\s*>([^<]*)<', head)
            info["orca_tag"] = m.group(1).decode("utf-8", "replace").strip() if m else ""
            cfg = {}
            if PROJECT_CFG in names:
                try:
                    cfg = json.loads(z.read(PROJECT_CFG).decode("utf-8", "replace"))
                except ValueError:
                    cfg = {}
            info["printer"] = _cfg_str(cfg, "printer_model") or _cfg_str(cfg, "printer_settings_id")
            cols = {norm_color(c) for c in _cfg_list(cfg, "filament_colour")}
            info["colors"] = len(cols - {None})
            info["sliced"] = not main or (any(n.lower().endswith(".gcode") for n in names) and b"<item" not in head and len(head) < 16384)
            info["prusa"] = PRUSA_CFG in names
            info["plain"] = not cfg
    except (OSError, zipfile.BadZipFile, KeyError) as e:
        info["error"] = str(e)
    return info


def needs_conversion(info):
    if info.get("error") or info.get("prusa"):
        return False
    if is_orca_file(info.get("app"), info.get("orca_tag")) and is_u1(info.get("printer")):
        return False
    return True


def source_label(info):
    if is_orca_file(info.get("app"), info.get("orca_tag")):
        return "OrcaSlicer"
    app = info.get("app") or ""
    m = re.match(r"([A-Za-z_ ]+?)[- ]?(\d[\w.\-]*)$", app)
    name = m.group(1) if m else app
    name = {"BambuStudio": "Bambu Studio", "Snapmaker_Orca": "Snapmaker Orca", "OrcaSlicer": "OrcaSlicer"}.get(name, name.replace("_", " "))
    return name or "3MF"


# --------------------------------------------------------------------------- onglet (page HTML)

PAGE = r"""<!doctype html><html lang="__LANG__"><head><meta charset="utf-8"><style>
:root{--fg:var(--orca-fg,#e9ecef);--muted:var(--orca-muted,#9aa3ad);--line:var(--orca-border,rgba(255,255,255,.13));
--bg:var(--orca-bg,#1f2226);--accent:#009688;--accent2:#4fd1c0;--bad:#e05a4f;--warn:#e0a030;--ok:#3fb27f;
color-scheme:dark;font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}body{margin:0;padding:14px 18px 40px;color:var(--fg);background:var(--bg)}
header{display:flex;align-items:baseline;gap:10px;margin-bottom:2px}header h1{font-size:18px;margin:0}
header .v{color:var(--muted);font-size:11px;margin-left:auto}.lead{color:var(--muted);margin:0 0 12px}
section{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:10px 0}
h2{font-size:11.5px;letter-spacing:.7px;text-transform:uppercase;color:var(--muted);margin:0 0 8px;display:flex;align-items:center;gap:8px}
h2 b{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;background:rgba(0,150,136,.25);color:var(--accent2);font-size:11px}
button{background:transparent;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px 10px;font:inherit;cursor:pointer;white-space:nowrap}
button:hover{border-color:rgba(0,150,136,.7)}button.go{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600;padding:6px 16px}
button:disabled{opacity:.4;cursor:default}
input[type=text]{flex:1;min-width:0;background:rgba(0,0,0,.25);color:inherit;border:1px solid var(--line);border-radius:6px;padding:5px 8px;font:inherit}
.row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.muted{color:var(--muted)}.small{font-size:11.5px}
.sw{display:inline-block;width:14px;height:14px;border-radius:50%;border:1px solid rgba(255,255,255,.3);vertical-align:-2px;flex:none}
.sw.big{width:20px;height:20px}
.choice{display:flex;gap:8px;align-items:flex-start;padding:6px 8px;border-radius:8px;cursor:pointer;border:1px solid transparent}
.choice.on{border-color:rgba(0,150,136,.6);background:rgba(0,150,136,.08)}.choice input{margin-top:3px}
.slots{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 2px}.slot{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--muted)}
.slot b{color:var(--fg)}
.files .f{display:flex;align-items:center;gap:10px;padding:6px 4px;border-top:1px solid var(--line)}.files .f:first-child{border-top:0}
.f .t{flex:1;min-width:0}.f .t div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.badge{font-size:10.5px;border-radius:4px;padding:1px 6px;background:rgba(255,255,255,.08);color:var(--muted)}
.badge.ok{background:rgba(63,178,127,.16);color:var(--ok)}.badge.todo{background:rgba(224,160,48,.16);color:var(--warn)}
.plates{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin:6px 0 10px}
.plate{border:1px solid var(--line);border-radius:8px;padding:6px;text-align:center}
.plate img{width:100%;height:96px;object-fit:contain;background:rgba(0,0,0,.2);border-radius:6px}
.plate .nm{font-size:11.5px;margin:3px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.group{border-top:1px dashed var(--line);padding-top:8px;margin-top:8px}.group h3{font-size:13px;margin:0 0 6px}
.map{width:100%;border-collapse:collapse}.map td{padding:4px 4px;border-top:1px solid rgba(255,255,255,.05);vertical-align:middle}
.pick{display:flex;gap:4px}.pick button{display:flex;align-items:center;gap:4px;padding:2px 7px;font-size:12px}
.pick button.on{border-color:var(--accent2);background:rgba(0,150,136,.18)}
.msg{margin:8px 0;padding:7px 10px;border-radius:7px;font-size:12.5px}.msg.err{background:rgba(224,90,79,.16)}
.msg.warn{background:rgba(224,160,48,.14)}.msg.info{background:rgba(0,150,136,.14)}.msg.ok{background:rgba(63,178,127,.14)}
ul.w{margin:4px 0 0 18px;padding:0}ul.w li{margin:2px 0}
.bar{height:4px;border-radius:2px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:6px}.bar i{display:block;height:100%;width:35%;background:var(--accent);animation:mv 1.1s infinite ease-in-out}
@keyframes mv{0%{margin-left:-35%}100%{margin-left:100%}}
.hidden{display:none!important}code{font-size:12px;word-break:break-all}
.wrap{max-width:1100px;margin:0 auto}td.num{width:22px;color:var(--muted);font-weight:600;text-align:right;padding-right:6px}
tr.pad td{opacity:.75}select{max-width:100%;background:rgba(0,0,0,.25);color:inherit;border:1px solid var(--line);border-radius:6px;padding:3px 6px;font:inherit}
.eatrow{display:flex;gap:16px;align-items:flex-start}.eatlist{flex:1;min-width:0}
.u1zone{flex:none;width:200px;border:2px dashed rgba(79,209,192,.4);border-radius:12px;padding:6px 8px 10px;text-align:center;cursor:pointer}
.u1zone:hover,.u1zone:focus-visible{border-color:var(--accent2);background:rgba(0,150,136,.08);outline:none}
.u1zone .u1{width:170px;margin:0 auto}.u1zone .small{text-wrap:balance}
@media (max-width:640px){.eatrow{flex-direction:column}.u1zone{width:100%}}
#eat{position:fixed;inset:0;z-index:50;display:grid;place-items:center;background:rgba(18,20,23,.8);pointer-events:none}
#eat.click{pointer-events:auto;cursor:pointer}#eat .u1{width:300px;max-width:70vw;margin:0 auto}#eatCap{font-size:18px;text-align:center;margin-top:2px}
.u1{display:block;height:auto}.u1 *{transform-box:fill-box}
.u1 .u-bd{animation:u-bob 3s ease-in-out infinite}.u1 .u-ey{transform-origin:50% 50%;animation:u-blink 4.2s infinite}
.u1 .u-ck{transform-origin:50% 50%;transition:transform .2s}.u1 .u-gl{transform-origin:50% 100%;transition:transform .18s}
.u1 .u-fg,.u1 .u-tg{opacity:0;transition:opacity .15s}.u1 .u-fl,.u1 .u-bb,.u1 .u-dp,.u1 .u-cr,.u1 .u-sb{opacity:0}
.u1 .u-fl{transform-origin:50% 50%}.u1 .u-pr{transform-origin:50% 100%;transform:scaleY(0)}.u1 .u-sb{transform-origin:0 50%}
@keyframes u-bob{50%{transform:translateY(-3px)}}@keyframes u-blink{0%,93%,100%{transform:scaleY(1)}96%{transform:scaleY(.1)}}
.u1.hungry .u-gl,.u1.spit .u-gl{transform:scaleY(0)}
.u1.hungry .u-fg,.u1.hungry .u-tg,.u1.spit .u-fg,.u1.spit .u-tg,.u1.burp .u-tg{opacity:1}
.u1.hungry .u-ey{animation:none;transform:scale(1.22)}.u1.hungry .u-ph{animation:u-hop .32s ease-in-out infinite alternate}
.u1.hungry .u-dp{animation:u-drip 1s infinite}.u1.hungry .u-op{animation:u-glow .7s infinite alternate}.u1.hungry .u-bd{animation-duration:.5s}
@keyframes u-hop{to{transform:translateY(-3px)}}@keyframes u-glow{to{fill:#17564e}}
@keyframes u-drip{0%{opacity:0;transform:translateY(0)}30%{opacity:1}100%{opacity:0;transform:translateY(14px)}}
.u1.chomp .u-gl{animation:u-shut 1s forwards}.u1.chomp .u-fg,.u1.chomp .u-tg{animation:u-hide 1s forwards}
.u1.chomp .u-fl{animation:u-fall 1s forwards}.u1.chomp .u-cr{animation:u-crumb 1s forwards}.u1.chomp .u-ey{animation:u-squeeze 1s forwards}
@keyframes u-shut{0%,50%{transform:scaleY(0)}62%,100%{transform:scaleY(1)}}@keyframes u-hide{0%,52%{opacity:1}64%,100%{opacity:0}}
@keyframes u-fall{0%{opacity:1;transform:translate(0,0)}50%{opacity:1;transform:translate(0,166px)}60%{opacity:1;transform:translate(0,168px) scale(1.15,.55)}72%,100%{opacity:0;transform:translate(0,170px) scale(.4,.2)}}
@keyframes u-crumb{0%,60%{opacity:0;transform:translate(0,0)}70%{opacity:1}100%{opacity:0;transform:translate(var(--x),var(--y))}}
@keyframes u-squeeze{0%,50%{transform:scale(1.22)}62%,100%{transform:scaleY(.15)}}
.u1.chew .u-gl{animation:u-chew .34s ease-in-out infinite alternate}.u1.chew .u-hd{animation:u-print .42s ease-in-out infinite alternate}
.u1.chew .u-pr{animation:u-grow 1.8s forwards}.u1.chew .u-ey{animation:none;transform:scaleY(.4)}.u1.chew .u-ck{transform:scale(1.35)}
.u1.chew .u-ss{opacity:0}.u1.chew .u-sb{opacity:1;animation:u-bar 1.2s linear infinite}
@keyframes u-chew{from{transform:scaleY(1)}to{transform:scaleY(.62)}}@keyframes u-print{from{transform:translateX(-44px)}to{transform:translateX(44px)}}
@keyframes u-grow{to{transform:scaleY(1)}}@keyframes u-bar{from{transform:scaleX(.05)}to{transform:scaleX(1)}}
.u1.burp .u-pr{transform:scaleY(1)}.u1.burp .u-gl{transform:scaleY(.6)}.u1.burp .u-bb{animation:u-up 1.8s forwards}
@keyframes u-up{0%{opacity:0;transform:translateY(14px)}20%,80%{opacity:1}100%{opacity:0;transform:translateY(-30px)}}
.u1.spit .u-tg{fill:#9bd36a}.u1.spit .u-ey{animation:none;transform:scaleY(.25)}.u1.spit .u-fl{animation:u-spit 1.1s forwards}
@keyframes u-spit{0%{opacity:1;transform:translate(0,150px)}100%{opacity:0;transform:translate(120px,-30px) rotate(80deg)}}
@media (prefers-reduced-motion:reduce){.u1 *{animation:none!important;transition:none!important}}
header select{font-size:11px;padding:1px 4px;margin-left:8px;color:var(--muted)}
.pick{width:24px;height:24px;padding:0;border:1px solid rgba(0,0,0,.45);border-radius:6px;background:none;cursor:pointer;vertical-align:middle}
.pick::-webkit-color-swatch-wrapper{padding:0}.pick::-webkit-color-swatch{border:none;border-radius:5px}
a.reset{color:var(--accent);cursor:pointer;text-decoration:underline}
.out{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin-top:10px}
.out label{display:flex;align-items:center;gap:5px}
.out input[type=text]{flex:1;min-width:260px}
.out .err{color:var(--warn)}
footer{margin:18px 0 0;text-align:center}footer button{padding:1px 8px;margin-left:8px;font-size:11.5px}
</style></head><body><div class="wrap">
<header><h1>Mange-3MF</h1><span class="muted" data-t="sub"></span><span class="v"><span id="ver"></span><select id="lang" data-tt="lang_title"></select></span></header>
<p class="lead" data-th="lead"></p>

<div id="status"></div>
<section id="s3" class="hidden"><h2 data-t="h_analysis"></h2><div id="analysis"></div></section>
<section id="s4" class="hidden"><h2 data-t="h_result"></h2><div id="result"></div></section>

<section id="s1"><h2 data-t="h_tpl"></h2>
<div id="tplChoices"></div>
<div class="row small" style="margin-top:6px"><button id="capture" data-t="capture"></button><span class="muted" id="capMsg"></span></div>
<div class="out small"><span data-t="out_title"></span>
<label><input type="radio" name="out" value="beside"><span data-t="out_beside"></span></label>
<label><input type="radio" name="out" value="downloads"><span data-t="out_downloads"></span></label>
<label><input type="radio" name="out" value="folder"><span data-t="out_folder"></span></label>
<input type="text" id="outDir" data-tp="out_ph"><button id="outOk" data-t="out_ok"></button><span id="outMsg" class="muted"></span></div>
</section>

<section id="s2"><h2 data-t="h_src"></h2>
<div class="eatrow"><div class="u1zone" id="u1zone" role="button" tabindex="0" data-tt="u1_title"><div id="u1small"></div><div class="small" data-t="drop_hint"></div><div class="muted small" data-t="u1_click"></div></div>
<div class="eatlist"><div id="opened"></div>
<div class="muted small" style="margin:4px 0 2px"><span data-t="recent_title"></span> <button id="refresh" class="small" style="padding:1px 7px;margin-left:6px" data-t="refresh"></button></div>
<div class="files" id="recent"><div class="muted small" data-t="searching"></div></div>
<div class="row" style="margin-top:8px"><input type="text" id="path" data-tp="path_ph">
<button id="go" data-t="analyse"></button><button id="browse" data-t="browse"></button><input type="file" id="file" accept=".3mf" class="hidden"></div>
</div></div>
</section>
<div id="eat" class="hidden"><div><div id="eatU"></div><div id="eatCap"></div></div></div>
<template id="u1t"><svg class="u1 idle" viewBox="0 -80 260 316" aria-hidden="true" focusable="false">
<ellipse cx="130" cy="227" rx="98" ry="6" fill="rgba(0,0,0,.35)"/>
<g class="u-bd">
<rect x="46" y="212" width="26" height="10" rx="3" fill="#3a3f46"/><rect x="188" y="212" width="26" height="10" rx="3" fill="#3a3f46"/>
<rect x="30" y="22" width="200" height="194" rx="18" fill="#dfe3e8" stroke="#2a2e34" stroke-width="2.5"/>
<polygon points="44,23 216,23 204,8 56,8" fill="#eef1f4" stroke="#2a2e34" stroke-width="2" stroke-linejoin="round"/>
<polygon class="u-op" points="60,21 200,21 192,11 68,11" fill="#1c1f23"/>
<g class="u-ph"><rect x="74" y="4" width="22" height="14" rx="3" fill="#59606a"/><rect x="74" y="4" width="22" height="5" rx="2" fill="#1b1d21"/></g>
<g class="u-ph" style="animation-delay:-.08s"><rect x="102" y="4" width="22" height="14" rx="3" fill="#59606a"/><rect x="102" y="4" width="22" height="5" rx="2" fill="#f2c230"/></g>
<g class="u-ph" style="animation-delay:-.16s"><rect x="136" y="4" width="22" height="14" rx="3" fill="#59606a"/><rect x="136" y="4" width="22" height="5" rx="2" fill="#e0453c"/></g>
<g class="u-ph" style="animation-delay:-.24s"><rect x="164" y="4" width="22" height="14" rx="3" fill="#59606a"/><rect x="164" y="4" width="22" height="5" rx="2" fill="#f4f4f4"/></g>
<rect x="44" y="66" width="172" height="106" rx="10" fill="#2b2225"/>
<path class="u-fg" d="M50 67l6 12 6-12zM198 67l6 12 6-12z" fill="#f4f4f4"/>
<rect x="48" y="82" width="164" height="5" rx="2" fill="#8a919a"/>
<g class="u-pr"><rect x="112" y="124" width="36" height="5" rx="2" fill="#f4f4f4"/><rect x="112" y="129" width="36" height="6" fill="#e0302b"/><rect x="112" y="135" width="36" height="6" fill="#5cc46a"/><rect x="112" y="141" width="36" height="7" fill="#8a6a50"/></g>
<rect x="58" y="148" width="144" height="8" rx="2" fill="#26292e"/><rect x="58" y="148" width="144" height="2" fill="#4a4f57"/>
<ellipse class="u-tg" cx="130" cy="164" rx="40" ry="8" fill="#e86f84"/>
<g class="u-hd"><rect x="118" y="84" width="24" height="22" rx="4" fill="#c9ced4" stroke="#2a2e34" stroke-width="1.5"/><rect x="122" y="88" width="16" height="3" rx="1.5" fill="#4fd1c0"/><path d="M126 106h8l-4 6z" fill="#c9a227"/><circle class="u-dp" cx="130" cy="116" r="2.6" fill="#4fd1c0"/></g>
<rect class="u-cr" x="100" y="140" width="5" height="5" fill="#f2c230" style="--x:-30px;--y:-16px"/><rect class="u-cr" x="150" y="140" width="5" height="5" fill="#e0453c" style="--x:30px;--y:-20px"/><rect class="u-cr" x="126" y="136" width="5" height="5" fill="#009688" style="--x:4px;--y:-34px"/><rect class="u-cr" x="112" y="142" width="4" height="4" fill="#fff" style="--x:-18px;--y:-28px"/>
<g class="u-fl"><g transform="translate(110 -66)"><path d="M0 4a4 4 0 0 1 4-4h22l14 14v30a4 4 0 0 1-4 4H4a4 4 0 0 1-4-4z" fill="#fff" stroke="#2a2e34" stroke-width="2"/><path d="M26 0v14h14" fill="none" stroke="#2a2e34" stroke-width="2"/><rect x="0" y="24" width="40" height="12" fill="#009688"/><text x="20" y="33.5" text-anchor="middle" font-size="10" font-family="system-ui,sans-serif" fill="#fff">3MF</text></g></g>
<g class="u-gl"><rect x="44" y="66" width="172" height="106" rx="10" fill="rgba(56,64,74,.6)" stroke="#aab1b9" stroke-width="1.5"/><path d="M64 76l-12 34M78 76l-7 20" stroke="rgba(255,255,255,.28)" stroke-width="2.5" stroke-linecap="round"/><rect x="204" y="104" width="4" height="26" rx="2" fill="#8a919a"/></g>
<path d="M48 23.3H212A16.7 16.7 0 0 1 228.7 40V64H31.3V40A16.7 16.7 0 0 1 48 23.3Z" fill="#dfe3e8"/>
<g class="u-ey"><circle cx="100" cy="44" r="13" fill="#fff" stroke="#2a2e34" stroke-width="2.2"/><circle cx="101.5" cy="46" r="5.5" fill="#1d2025"/><circle cx="103.5" cy="43.5" r="2" fill="#fff"/><circle cx="160" cy="44" r="13" fill="#fff" stroke="#2a2e34" stroke-width="2.2"/><circle cx="161.5" cy="46" r="5.5" fill="#1d2025"/><circle cx="163.5" cy="43.5" r="2" fill="#fff"/></g>
<ellipse class="u-ck" cx="72" cy="54" rx="9" ry="4.5" fill="#f29aa8" opacity=".55"/><ellipse class="u-ck" cx="188" cy="54" rx="9" ry="4.5" fill="#f29aa8" opacity=".55"/>
<line x1="31.5" y1="178" x2="228.5" y2="178" stroke="#aab1b9" stroke-width="1.5"/>
<circle cx="50" cy="197" r="2.5" fill="#4fd1c0"/>
<rect x="150" y="185" width="64" height="24" rx="4" fill="#111417" stroke="#2a2e34" stroke-width="2"/>
<path class="u-ss" d="M174 194q8 6 16 0" fill="none" stroke="#4fd1c0" stroke-width="2" stroke-linecap="round"/>
<rect class="u-sb" x="158" y="195" width="48" height="4" rx="2" fill="#4fd1c0"/>
</g>
<g class="u-bb"><circle cx="130" cy="-26" r="26" fill="rgba(79,209,192,.16)" stroke="#4fd1c0" stroke-width="2"/><g class="u-dots"></g></g>
</svg></template>
<footer class="muted small"><span data-t="support"></span> <code>ko-fi.com/dragg</code><button id="kofi" data-t="copy_link"></button></footer>
</div>
<script>
(function(){
var L=__TEXTS__;
var nav=(navigator.languages&&navigator.languages[0])||navigator.language||"";
var lang="__LANG__";if(!L[lang]){lang=nav.slice(0,2).toLowerCase();if(!L[lang])lang="en"}
function t(k){var a=arguments,s=L[lang]&&L[lang][k];if(s==null)s=L.en&&L.en[k];if(s==null)s=k;
 return String(s).replace(/\{(\d+)\}/g,function(_,i){var v=a[+i+1];return v==null?"":v})}
var S={tpl:null,cur:null,choice:"saved",an:null,res:null,rec:null,opened:null,token:null,busy:false,conv:false,onePer:false,langChoice:"auto"};
function $(id){return document.getElementById(id)}
function esc(x){var d=document.createElement("span");d.textContent=x==null?"":String(x);return d.innerHTML}
function send(m){orca.postMessage(m)}
function each(sel,fn){Array.prototype.forEach.call(document.querySelectorAll(sel),fn)}
function hidden(id){return $(id).classList.contains("hidden")}
function sw(c,big){return '<span class="sw'+(big?' big':'')+'" style="background:'+esc(c||'#808080')+'"></span>'}
function plural(n,one,many){return n>1?many:one}
function colors(n){return n+" "+plural(n,t("color1"),t("colorN"))}
function statics(){document.documentElement.lang=lang;
 each("[data-t]",function(e){e.textContent=t(e.getAttribute("data-t"))});
 each("[data-th]",function(e){e.innerHTML=t(e.getAttribute("data-th"))});
 each("[data-tp]",function(e){e.setAttribute("placeholder",t(e.getAttribute("data-tp")))});
 each("[data-tt]",function(e){e.setAttribute("title",t(e.getAttribute("data-tt")))});
 var h='<option value="auto">'+esc(t("lang_auto"))+'</option>';
 Object.keys(L).forEach(function(k){h+='<option value="'+esc(k)+'">'+esc(L[k].lang_name||k)+'</option>'});
 $("lang").innerHTML=h;$("lang").value=S.langChoice}
function status(kind,html,progress){var box=(S.conv&&$("cstatus"))||$("status");if(box!==$("status"))$("status").innerHTML="";box.innerHTML=html?'<div class="msg '+kind+'">'+html+(progress?'<div class="bar"><i></i></div>':'')+'</div>':''}
function ago(x){if(!x)return"";var s=(Date.now()/1000-x);if(s<90)return t("ago_now");if(s<3600)return t("ago_min",Math.round(s/60));if(s<86400)return t("ago_h",Math.round(s/3600));return t("ago_d",Math.round(s/86400))}
function size(b){return b>1048576?(b/1048576).toFixed(1)+" "+t("mb"):Math.max(1,Math.round(b/1024))+" "+t("kb")}
var BEDS={"Textured PEI Plate":"bed_tpei","Cool Plate":"bed_cool","Engineering Plate":"bed_eng","High Temp Plate":"bed_hot","Supertack Plate":"bed_tack","Textured Cool Plate":"bed_tcool"};
function flow(f){return f=="High Flow"?t("hf"):(f=="Standard"?t("std"):f)}
function nozzles(x){var n=x.nozzles||[],f=(x.flows||[]).map(flow);if(!n.length)return"";var same=n.every(function(y){return y==n[0]});
 var out=t("nozzles")+" "+(same?n[0]:n.join("/"));if(f.length){var cnt={};f.forEach(function(y){cnt[y]=(cnt[y]||0)+1});var main=Object.keys(cnt).sort(function(a,b){return cnt[b]-cnt[a]})[0];
 var ex=[];f.forEach(function(y,i){if(y!=main)ex.push("T"+(i+1)+" "+y)});out+=" "+(ex.length?"("+main+", "+t("except")+" "+ex.join(", ")+")":"("+main+")")}return out}
function tplLine(x){if(!x)return"";var n=nozzles(x);
 return esc(x.printer)+(n?" · "+esc(n):"")+(x.process?" · "+esc(x.process):"")+(x.bed_type?" · "+esc(BEDS[x.bed_type]?t(BEDS[x.bed_type]):x.bed_type):"")}
function slotsHtml(x){if(!x)return"";return '<div class="slots">'+x.slots.map(function(s,i){return '<span class="slot">'+sw(s.color)+'<b>'+(i+1)+'</b> '+esc(s.name||s.type)+'</span>'}).join("")+'</div>'}
function renderTpl(){var h="";
 if(S.tpl){h+='<label class="choice'+(S.choice=="saved"?" on":"")+'"><input type="radio" name="tc" value="saved"'+(S.choice=="saved"?" checked":"")+'><div><div><b>'+esc(t("tpl_saved"))+'</b> <span class="muted small">'+esc(S.tpl.when)+'</span></div><div class="small">'+tplLine(S.tpl)+'</div>'+slotsHtml(S.tpl)+'</div></label>'}
 if(S.cur){var bad=!S.cur.u1;h+='<label class="choice'+(S.choice=="current"?" on":"")+'"><input type="radio" name="tc" value="current"'+(S.choice=="current"?" checked":"")+'><div><div><b>'+esc(t("tpl_current"))+'</b>'+(bad?' <span class="badge todo">'+esc(t("badge_not_u1"))+'</span>':'')+(S.cur.foreign?' <span class="badge todo">'+esc(t("badge_foreign"))+'</span>':'')+'</div><div class="small">'+tplLine(S.cur)+'</div>'+slotsHtml(S.cur)+'</div></label>'}
 if(!S.tpl)h+='<div class="msg info small">'+esc(t("tpl_hint"))+'</div>';
 $("tplChoices").innerHTML=h;
 each('input[name=tc]',function(r){r.onchange=function(){S.choice=r.value;renderTpl();if(S.token)send({command:"replan",token:S.token,template:S.choice,one_per_plate:S.onePer})}})}
function fileRow(f,opened){var tag=f.error?'<span class="badge">'+esc(t("badge_unreadable"))+'</span>':f.prusa?'<span class="badge">PrusaSlicer</span>':f.sliced?'<span class="badge">'+esc(t("badge_sliced"))+'</span>':f.todo?'<span class="badge todo">'+esc(t("badge_todo"))+'</span>':'<span class="badge ok">'+esc(t("badge_ok"))+'</span>';
 var info=[f.label,f.printer,f.colors?colors(f.colors):""].filter(Boolean).join(" · ");
 return '<div class="f"><div class="t"><div><b>'+esc(f.name)+'</b> '+tag+'</div><div class="muted small">'+esc(info)+(f.size?" · "+size(f.size):"")+(f.mtime?" · "+ago(f.mtime):"")+(opened?" · "+esc(t("opened_in_orca")):"")+'</div></div><button data-p="'+esc(f.path)+'">'+esc(t("analyse"))+'</button></div>'}
function bindAnalyze(root){Array.prototype.forEach.call(root.querySelectorAll("button[data-p]"),function(b){b.onclick=function(){analyze({path:b.getAttribute("data-p")})}})}
function renderOpened(){$("opened").innerHTML=S.opened?'<div class="files">'+fileRow(S.opened,true)+'</div>':'';bindAnalyze($("opened"))}
function renderRecent(){var m=S.rec;if(!m)return;$("recent").innerHTML=m.files.length?m.files.map(function(f){return fileRow(f)}).join(""):'<div class="muted small">'+esc(t("no_3mf",m.folder))+'</div>';bindAnalyze($("recent"))}
function top(){try{window.scrollTo({top:0,behavior:"smooth"})}catch(e){window.scrollTo(0,0)}}
function analyze(src){if(S.busy)return;S.conv=false;src.command="analyze";src.template=S.choice;src.one_per_plate=S.onePer;S.busy=true;$("s3").classList.add("hidden");$("s4").classList.add("hidden");status("info",esc(t("analysing")),true);top();send(src)}
function profLabel(p){var c=p.cname?' ('+p.cname+')':'';return p.n?p.n+' · '+(p.name||p.type)+c:(p.name||p.type)+(p.type&&p.type!="?"?' · '+p.type:'')+c}
function profOpts(sel){var groups={slot:[],user:[],other:[]};
 S.an.profiles.forEach(function(p,i){(groups[p.group||"slot"]||groups.slot).push('<option value="'+i+'"'+(i==sel?' selected':'')+'>'+esc(profLabel(p))+'</option>')});
 return [["slot","grp_slots"],["user","grp_user"],["other","grp_other"]].map(function(g){return groups[g[0]].length?'<optgroup label="'+esc(t(g[1]))+'">'+groups[g[0]].join("")+'</optgroup>':''}).join("")}
function renderAnalysis(a,fresh){S.an=a;S.token=a.token;if(a.one_per_plate!=null)S.onePer=!!a.one_per_plate;var s=a.source,h="";
 h+='<div class="row"><div style="flex:1"><div><b>'+esc(a.file)+'</b>'+(s.title?' — '+esc(s.title):'')+(s.designer?' <span class="muted">'+esc(t("by"))+' '+esc(s.designer)+'</span>':'')+'</div><div class="muted small">'+esc(s.app)+(s.printer?' · '+esc(s.printer):'')+(s.nozzle?' · '+esc(t("nozzle"))+' '+esc(s.nozzle):'')+' · '+esc(t("bed"))+' '+s.bed[0]+'×'+s.bed[1]+' · '+s.plates+' '+plural(s.plates,t("plate1"),t("plateN"))+' · '+colors(s.colors)+'</div></div></div>';
 h+='<div class="plates">'+a.plates.map(function(p){return '<div class="plate">'+(p.thumb?'<img src="'+p.thumb+'">':'')+'<div class="nm">'+p.id+(p.name?' · '+esc(p.name):'')+'</div><div>'+p.filaments.map(function(i){return sw(fil(i).color)}).join(" ")+'</div></div>'}).join("")+'</div>';
 if(a.plates.length>1)h+='<label class="row small" style="margin-bottom:4px"><input type="checkbox" id="onePer"'+(S.onePer?" checked":"")+'> '+esc(t("one_per_plate"))+'</label>';
 a.files.forEach(function(f,fi){
  h+='<div class="group"><h3>'+(a.files.length>1?esc(t("file_n",fi+1)):'')+esc(f.name)+' <span class="muted small" style="font-weight:normal">· '+colors(f.colors)+' → '+esc(t("n_filaments",f.slots.length))+'</span></h3><table class="map">';
  h+='<tr class="muted small"><td></td><td></td><td>'+esc(t("th_color"))+'</td><td>'+esc(t("th_profile"))+'</td></tr>';
  var pads=[];
  f.slots.forEach(function(sl,si){var p=a.profiles[sl.base]||{};
   if(sl.pad){pads.push(sl.n);h+='<tr class="pad"><td class="num">'+sl.n+'</td><td style="width:26px">'+sw(p.color,1)+'</td><td colspan="2" class="muted small">'+esc(t("pad_row",p.name||p.type,p.cname))+'</td></tr>';return}
   var warn=(sl.ftype&&sl.ftype!="?"&&p.base&&p.base!="?"&&p.base!=sl.ftype)?'<div class="small" style="color:var(--warn);margin-top:2px">'+esc(t("warn_material",sl.ftype,p.base))+'</div>':'';
   var col=sl.pick||sl.color,changed=sl.pick?' · <span style="color:var(--accent)">'+esc(t("color_changed"))+'</span> (<a class="reset" data-rf="'+fi+'" data-rs="'+si+'">'+esc(t("color_reset"))+'</a>)':'';
   h+='<tr><td class="num">'+sl.n+'</td><td style="width:30px"><input type="color" class="pick" data-cf="'+fi+'" data-cs="'+si+'" value="'+esc(String(col).slice(0,7))+'" title="'+esc(t("pick_color"))+'"></td><td><b>'+esc(sl.name)+'</b> <span class="muted">· '+esc(sl.type)+(sl.preset?' · '+esc(sl.preset):'')+'</span><div class="muted small">'+plural(sl.plates.length,t("plate1"),t("plateN"))+' '+sl.plates.join(", ")+(sl.mixed?' · '+esc(t("mixed")):'')+(sl.same>1?' · '+esc(t("same_n",sl.same)):'')+changed+'</div></td><td><select data-f="'+fi+'" data-s="'+si+'">'+profOpts(sl.base)+'</select>'+warn+'</td></tr>'});
  h+='</table>';
  if(pads.length)h+='<div class="muted small" style="margin-top:4px">'+esc(pads.length>1?t("pads_many",pads.slice(0,-1).join(", "),pads[pads.length-1]):t("pads_one",pads[0]))+'</div>';
  h+='</div>'});
 if(a.warnings.length)h+='<div class="msg warn"><b>'+esc(t("to_know"))+'</b><ul class="w">'+a.warnings.map(function(w){return'<li>'+esc(w)+'</li>'}).join("")+'</ul></div>';
 if(a.not_ready)h+='<div class="msg err">'+esc(a.not_ready)+'</div>';
 h+='<div class="row" style="margin-top:10px"><button class="go" id="convert"'+(a.not_ready?' disabled':'')+'>'+esc(a.files.length>1?t("convert_n",a.files.length):t("convert"))+'</button><span class="muted small">'+esc(a.files.length>1?t("created_n",a.dest_hint):t("created_1",a.dest_hint))+'</span></div><div id="cstatus"></div>';
 $("analysis").innerHTML=h;$("s3").classList.remove("hidden");if(fresh)top();
 var op=$("onePer");if(op)op.onchange=function(){S.onePer=op.checked;send({command:"replan",token:S.token,template:S.choice,one_per_plate:S.onePer})};
 each("select[data-f]",function(sel){sel.onchange=function(){a.files[+sel.getAttribute("data-f")].slots[+sel.getAttribute("data-s")].base=+sel.value;renderAnalysis(a)}});
 each("input.pick",function(inp){inp.onchange=function(){var sl=a.files[+inp.getAttribute("data-cf")].slots[+inp.getAttribute("data-cs")],v=inp.value.toUpperCase();if(v==String(sl.color).slice(0,7).toUpperCase())delete sl.pick;else sl.pick=v;renderAnalysis(a)}});
 each("a.reset",function(x){x.onclick=function(){delete a.files[+x.getAttribute("data-rf")].slots[+x.getAttribute("data-rs")].pick;renderAnalysis(a)}});
 $("convert").onclick=function(){if(S.busy)return;S.busy=true;S.conv=true;status("info",esc(t("converting")),true);send({command:"convert",token:S.token,template:S.choice,files:a.files.map(function(f){return{plates:f.plates,slots:f.slots.map(function(sl){return{src:sl.src,base:sl.base,color:sl.pick||null}})}})})}}
function keepBases(old,a){if(old.files.length!=a.files.length)return;a.files.forEach(function(f,fi){var o=old.files[fi];if(o.slots.length!=f.slots.length)return;f.slots.forEach(function(sl,si){sl.base=o.slots[si].base;if(o.slots[si].pick)sl.pick=o.slots[si].pick})})}
function fil(i){var a=S.an;for(var j=0;j<a.filaments.length;j++)if(a.filaments[j].index==i)return a.filaments[j];return{color:"#808080",name:"?",type:"?",plates:[]}}
function renderResult(r,scroll){S.res=r;var h=r.files.map(function(f){return '<div class="f"><div class="t"><div>✅ <b>'+esc(f.name)+'</b> <span class="muted small">'+colors(f.colors)+' · '+esc(t("n_filaments",f.filaments))+' · '+plural(f.plates.length,t("plate1"),t("plateN"))+' '+f.plates.join(", ")+'</span></div><div class="muted small"><code>'+esc(f.path)+'</code></div>'+(f.warnings.length?'<ul class="w small">'+f.warnings.map(function(w){return'<li>'+esc(w)+'</li>'}).join("")+'</ul>':'')+'</div><button data-c="'+esc(f.path)+'">'+esc(t("copy_path"))+'</button></div>'}).join("");
 h+='<div class="msg info">'+t("open_hint")+'</div>';
 $("result").innerHTML='<div class="files">'+h+'</div>';$("s4").classList.remove("hidden");
 each("button[data-c]",function(b){b.onclick=function(){var p=b.getAttribute("data-c");copy(p);b.textContent=t("copied");setTimeout(function(){b.textContent=t("copy_path")},1500)}});
 if(scroll!==false)$("s4").scrollIntoView({behavior:"smooth"})}
function copy(x){try{navigator.clipboard.writeText(x)}catch(e){}var ta=document.createElement("textarea");ta.value=x;document.body.appendChild(ta);ta.select();try{document.execCommand("copy")}catch(e){}ta.remove()}
function renderOut(){var o=S.out||{mode:"beside",dir:"",msg:""};each('input[name=out]',function(r){r.checked=r.value==o.mode});
 if(document.activeElement!==$("outDir"))$("outDir").value=o.dir||"";$("outMsg").textContent=o.msg||"";$("outMsg").className=o.error?"err":"muted"}
function sendOut(mode){send({command:"outdir",mode:mode,dir:$("outDir").value.trim().replace(/^"|"$/g,"")})}
function relabel(full){statics();renderTpl();renderOpened();renderRecent();renderOut();
 if(full){if(S.an&&!hidden("s3"))renderAnalysis(S.an);if(S.res&&!hidden("s4"))renderResult(S.res,false)}}
orca.onMessage(function(m){if(!m||!m.command)return;
 if(m.command=="state"){$("ver").textContent="v"+m.version;S.tpl=m.saved;S.cur=m.current;if(!S.tpl)S.choice="current";else if(m.choice)S.choice=m.choice;
  if(m.lang_choice)S.langChoice=m.lang_choice;var nl=(m.lang&&L[m.lang])?m.lang:lang,changed=nl!=lang;lang=nl;
  S.opened=m.opened;if(m.cap!=null)$("capMsg").textContent=m.cap;if(m.out)S.out=m.out;relabel(changed)}
 else if(m.command=="recent"){S.rec=m;renderRecent()}
 else if(m.command=="analysis"){
  if(m.relabel){if(S.an&&S.an.token==m.token&&!hidden("s3")){keepBases(S.an,m);renderAnalysis(m,false)}return}
  S.busy=false;status();renderAnalysis(m,true);if(U.on)eatBurp(m)}
 else if(m.command=="built"){send({command:"write",token:m.token})}
 else if(m.command=="result"){
  if(m.relabel){if(S.res&&!hidden("s4"))renderResult(m,false);return}
  S.busy=false;status();S.conv=false;renderResult(m)}
 else if(m.command=="progress"){S.busy=true;status("info",esc(m.text),true)}
 else if(m.command=="error"){S.busy=false;status("err",esc(m.text));S.conv=false;if(U.on)eatSpit(t("u1_sick"))}});
$("go").onclick=function(){var p=$("path").value.trim().replace(/^"|"$/g,"");if(p)analyze({path:p})};
$("path").onkeydown=function(e){if(e.key=="Enter")$("go").click()};
$("refresh").onclick=function(){$("recent").innerHTML='<div class="muted small">'+esc(t("searching"))+'</div>';send({command:"recent"})};
$("capture").onclick=function(){$("capMsg").textContent="…";send({command:"capture"})};
$("browse").onclick=function(){$("file").click()};
each('input[name=out]',function(r){r.onchange=function(){if(r.value!="folder"||$("outDir").value.trim())sendOut(r.value);else $("outDir").focus()}});
$("outOk").onclick=function(){if($("outDir").value.trim())sendOut("folder")};
$("outDir").onkeydown=function(e){if(e.key=="Enter")$("outOk").click()};
$("kofi").onclick=function(){var b=$("kofi");copy("https://ko-fi.com/dragg");b.textContent=t("copied");setTimeout(function(){b.textContent=t("copy_link")},1500)};
$("lang").onchange=function(){var v=$("lang").value;S.langChoice=v;if(L[v]&&v!=lang){lang=v;relabel(true)}send({command:"lang",lang:v,nav:nav})};
var U={small:null,big:null,on:false,t0:0,tm:[]},RM=!!(window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches);
function u1New(box){var n=document.importNode($("u1t").content.firstElementChild,true);box.appendChild(n);return n}
function u1Set(svg,st){if(!svg)return;svg.setAttribute("class","u1");void svg.getBoundingClientRect();svg.setAttribute("class","u1 "+st)}
function eatClear(){U.tm.forEach(clearTimeout);U.tm=[]}
function eatLater(ms,f){U.tm.push(setTimeout(f,ms))}
function eatShow(st,cap){$("eat").classList.remove("hidden");u1Set(U.big,st);$("eatCap").textContent=cap}
function eatHide(){eatClear();U.on=false;$("eat").classList.add("hidden");$("eat").classList.remove("click")}
function eatStart(){eatClear();if(RM){eatHide();return}U.on=true;U.t0=Date.now();$("eat").classList.add("click");eatShow("chomp",t("u1_chomp"));
 eatLater(1000,function(){eatShow("chew",t("u1_chew"))});eatLater(90000,eatHide)}
function eatSpit(cap){eatClear();if(RM){eatHide();return}U.on=true;$("eat").classList.add("click");eatShow("spit",cap);eatLater(1700,eatHide)}
function eatBurp(m){if(!U.on)return;var cols=[];(m.filaments||[]).forEach(function(x){var c=String(x.color||"").slice(0,7);if(/^#[0-9a-fA-F]{6}$/.test(c)&&cols.indexOf(c)<0)cols.push(c)});
 eatClear();eatLater(Math.max(0,1000-(Date.now()-U.t0)),function(){var n=Math.min(cols.length,8),h="";
  for(var i=0;i<n;i++){var a=i/n*Math.PI*2-Math.PI/2,r=n>1?12:0;h+='<circle cx="'+(130+Math.cos(a)*r).toFixed(1)+'" cy="'+(-26+Math.sin(a)*r).toFixed(1)+'" r="'+(n>6?4.5:6)+'" fill="'+cols[i]+'" stroke="#15171a"/>'}
  U.big.querySelector(".u-dots").innerHTML=h;var ls=U.big.querySelectorAll(".u-pr rect");for(var j=0;j<ls.length&&cols.length;j++)ls[j].setAttribute("fill",cols[j%cols.length]);
  eatShow("burp",t("u1_burp",colors(cols.length)));eatLater(1800,eatHide)})}
function readFile(f){if(!/\.3mf$/i.test(f.name||"")){status("err",esc(t("not_3mf",f.name)));eatSpit(t("u1_spit"));return}
 if(f.size>80*1048576){status("err",esc(t("too_big",size(f.size))));eatSpit(t("u1_sick"));return}
 if(S.busy)return;
 var rd=new FileReader();status("info",esc(t("reading",f.name)),true);eatStart();rd.onload=function(){var b=String(rd.result);analyze({upload:b.slice(b.indexOf(",")+1),name:f.name})};rd.onerror=function(){eatSpit(t("u1_sick"))};rd.readAsDataURL(f)}
$("file").onchange=function(){var f=$("file").files[0];if(f)readFile(f);$("file").value=""};
U.small=u1New($("u1small"));U.small.setAttribute("viewBox","0 0 260 232");U.big=u1New($("eatU"));
$("u1zone").onclick=function(){$("file").click()};
$("u1zone").onkeydown=function(e){if(e.key=="Enter"||e.key==" "){e.preventDefault();$("file").click()}};
$("u1zone").onmouseenter=function(){u1Set(U.small,"hungry")};$("u1zone").onmouseleave=function(){u1Set(U.small,"idle")};
$("eat").onclick=function(){if(U.on)eatHide()};
var depth=0;
document.addEventListener("dragenter",function(e){e.preventDefault();depth++;if(!U.on&&!S.busy)eatShow("hungry",t("drop"))});
document.addEventListener("dragover",function(e){e.preventDefault();if(e.dataTransfer)e.dataTransfer.dropEffect="copy"});
document.addEventListener("dragleave",function(){depth=Math.max(0,depth-1);if(!depth&&!U.on)eatHide()});
document.addEventListener("drop",function(e){e.preventDefault();depth=0;if(!U.on)eatHide();var f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];if(f)readFile(f)});
statics();
send({command:"init",nav:nav});
})();
</script></body></html>"""


def page_html(lang=None):
    """Page de l'onglet, avec tous les textes et la langue de depart."""
    texts = json.dumps(TEXTS).replace("</", "<\\/")
    return PAGE.replace("__TEXTS__", texts).replace("__LANG__", lang or current_language())


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FEFEFE" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
<path d="M12 3 L15.6 5.05 A3.2 3.2 0 0 0 20 9.9 L20 16.5 L12 21 L4 16.5 L4 7.5 Z"/>
<path d="M4 7.5 L12 12 L15.4 10.1 M12 12 L12 21"/></svg>"""


class Converter:
    """Logique de l'onglet. Les fichiers sont lus et ecrits dans le fil de l'interface (pour que les
    demandes d'autorisation d'Orca puissent s'afficher) ; l'analyse et la conversion tournent dans
    un fil a part. Les derniers resultats sont gardes et renvoyes quand la page (re)demarre : Orca
    ne construit la page qu'a la premiere ouverture de l'onglet."""

    def __init__(self):
        self.page = None        # capacite « onglet » d'Orca (post_message)
        self.lock = threading.Lock()
        self.jobs = {}          # jeton -> {"src", "path", "dest", ...}
        self.built = {}         # jeton -> resultats a ecrire
        self.counter = 0
        self.opened = None      # projet ouvert dans Orca s'il vient d'ailleurs
        self.cap_key = ""       # dernier message de « Memoriser » (cle de TEXTS)
        self.replay = {}        # derniers messages "progress" / "analysis" / "result" (textes a traduire)
        self.lang_choice = None # "auto" ou une langue de TEXTS (options.json, lu a la demande)
        self.orca_lang = ""     # langue de l'interface d'Orca
        self.nav = ""           # langue du navigateur de la page (secours)
        self.out_key = ""       # dernier message du choix de dossier (cle de TEXTS)
        self.out_arg = ""

    def attach(self, page):
        if page is not None:
            self.page = page

    def post(self, data):
        cmd = data.get("command")
        with self.lock:
            if cmd == "analysis":
                self.replay = {"analysis": data}
            elif cmd == "result":
                self.replay.pop("progress", None)
                self.replay["result"] = data
            elif cmd == "progress":
                self.replay["progress"] = data
            elif cmd == "error":
                self.replay.pop("progress", None)
        self._send(data)

    def _send(self, data):
        """Envoie a la page, textes dans la langue courante."""
        p = self.page
        if p is not None:
            try:
                p.post_message(relocalize(data))
            except Exception:
                pass

    # ---- langue
    def language_choice(self):
        if self.lang_choice is None:
            choice = load_options().get("lang", "auto")
            self.lang_choice = choice if choice in TEXTS else "auto"
        return self.lang_choice

    def refresh_language(self):
        """Langue choisie dans l'onglet, sinon celle d'Orca (a appeler sur le fil de l'interface)."""
        code = orca_language()
        if code:
            self.orca_lang = code
        choice = self.language_choice()
        set_language(choice if choice in TEXTS else lang_of(self.orca_lang or self.nav or system_language()))
        return current_language()

    def template_for(self, choice):
        """Reglages pour le plan, avec les prereglages d'Orca (fil de l'interface)."""
        template = self.pick_template(choice)
        return template.attach(read_filament_presets(template))

    def dest_hint(self, path):
        return tr("dest_in", _short_folder(output_folder(path)))

    def choose_output(self, mode, folder):
        """Dossier des fichiers convertis choisi dans l'onglet."""
        mode = mode if mode in OUT_MODES else "beside"
        folder = os.path.expanduser((folder or "").strip().strip('"'))
        options = load_options()
        self.out_key, self.out_arg = "", ""
        if mode == "folder" and not os.path.isdir(folder):
            self.out_key, self.out_arg = "err_out_dir", folder
            options["out_dir"] = folder
        else:
            options["out"] = mode
            if mode == "folder":
                options["out_dir"] = os.path.abspath(folder)
                self.out_key = "out_saved"
        try:
            save_options(options)
        except Exception as e:
            log_error("options : %s" % e)
        self.send_state()
        with self.lock:
            again = []
            if "analysis" in self.replay:
                job = self.jobs.get(self.replay["analysis"].get("token")) or {}
                self.replay["analysis"]["dest_hint"] = self.dest_hint(job.get("path", ""))
                again.append(dict(self.replay["analysis"], relabel=True))
        for m in again:
            self._send(m)

    def choose_language(self, choice, nav=""):
        """Langue choisie dans l'onglet : memorisee, puis tout est renvoye dans cette langue."""
        choice = choice if choice in TEXTS else "auto"
        self.lang_choice = choice
        try:
            options = load_options()
            options["lang"] = choice
            save_options(options)
        except Exception as e:
            log_error("options : %s" % e)
        if nav:
            self.nav = nav
        self.refresh_language()
        self.send_state()
        with self.lock:
            again = [dict(self.replay[k], relabel=True) for k in ("analysis", "result") if k in self.replay]
            again += [self.replay[k] for k in ("progress",) if k in self.replay]
        for m in again:
            self._send(m)

    # ---- messages de la page (fil de l'interface)
    def on_message(self, msg):
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except ValueError:
                return
        if not isinstance(msg, dict):
            return
        cmd = msg.get("command")
        try:
            if cmd in ("init", "lang") and msg.get("nav"):
                self.nav = str(msg["nav"])
            self.refresh_language()
            if cmd == "init":
                self.send_state()
                self.list_recent()
                with self.lock:
                    replay = [self.replay[k] for k in ("analysis", "result", "progress") if k in self.replay]
                for m in replay:
                    self._send(m)
            elif cmd == "lang":
                self.choose_language(msg.get("lang"))
            elif cmd == "outdir":
                self.choose_output(msg.get("mode"), msg.get("dir"))
            elif cmd == "recent":
                self.list_recent()
            elif cmd == "capture":
                t = capture_current_template()
                save_template(t)
                self.cap_key = "cap_saved"
                self.send_state(choice="saved")
            elif cmd == "analyze":
                self.start_analyze(msg)
            elif cmd == "replan":
                self.start_replan(msg)
            elif cmd == "convert":
                self.start_convert(msg)
            elif cmd == "write":
                self.write_outputs(msg.get("token"))
        except PermissionError as e:
            self.post({"command": "error", "text": tr("err_denied", e)})
        except ConvertError as e:
            self.post({"command": "error", "text": message_of(e)})
        except Exception as e:
            import traceback
            log_error(traceback.format_exc())
            self.post({"command": "error", "text": tr("err_generic", e)})

    # ---- etat
    def template_summary(self, t):
        if t is None:
            return None
        s = t.summary()
        when = ""
        if t.source != "current":
            lt = time.localtime(t.captured_at)
            when = tr("when_saved", lt.tm_mday, lt.tm_mon, lt.tm_year, lt.tm_hour, lt.tm_min)
        s["when"] = when
        s["u1"] = is_u1(s.get("printer_model") or s.get("printer"))
        return s

    def send_state(self, choice=None):
        saved = self.template_summary(load_saved_template())
        try:
            cur = self.template_summary(current_settings())
            cur["foreign"] = bool(self.opened)
        except Exception as e:
            log_error("current_settings: %s" % e)
            cur = None
        opened = None
        if self.opened:
            o = dict(self.opened)
            o["label"] = source_label(o)
            o["todo"] = needs_conversion(o)
            opened = o
        mode, folder = output_choice()
        out_msg = (tr(self.out_key, self.out_arg) if self.out_arg else tr(self.out_key)) if self.out_key else ""
        self.post({"command": "state", "version": VERSION, "saved": saved, "current": cur, "opened": opened,
                   "choice": choice, "cap": tr(self.cap_key) if self.cap_key else "",
                   "lang": current_language(), "lang_choice": self.language_choice(),
                   "out": {"mode": mode, "dir": folder, "msg": out_msg, "error": self.out_key == "err_out_dir"}})

    def list_recent(self):
        folder = downloads_dir()

        def worker():
            files = []
            try:
                names = [n for n in os.listdir(folder) if n.lower().endswith(".3mf")]
                paths = sorted((os.path.join(folder, n) for n in names), key=lambda p: -os.path.getmtime(p))[:12]
                for p in paths:
                    info = sniff_3mf(p)
                    info["label"] = source_label(info)
                    info["todo"] = needs_conversion(info)
                    files.append(info)
            except OSError as e:
                log_error("liste Telechargements : %s" % e)
            self.post({"command": "recent", "files": files, "folder": folder})
        threading.Thread(target=worker, daemon=True).start()

    # ---- analyse
    def pick_template(self, choice):
        """Reglages pour le plan (les reglages actuels ne sont exportes qu'a la conversion)."""
        saved = load_saved_template()
        if choice == "saved" and saved is not None:
            return saved
        try:
            cur = current_settings()
        except Exception:
            cur = None
        if cur is not None and is_u1(cur.config.get("printer_model")):
            return cur
        return saved or default_u1_template()

    def ready_message(self, choice):
        """None si la conversion peut se faire, sinon ce qu'il manque."""
        if choice == "saved" and load_saved_template() is not None:
            return None
        try:
            cur = current_settings()
            model = cur.config.get("printer_model")
        except Exception:
            model = ""
        if is_u1(model):
            return None
        return tr("need_u1")

    def start_analyze(self, msg, on_done=None):
        if msg.get("upload"):
            data = base64.b64decode(msg["upload"])
            name = os.path.basename(msg.get("name") or "projet.3mf")
            path = ""
        else:
            path = os.path.abspath(os.path.expanduser((msg.get("path") or "").strip().strip('"')))
            if not path.lower().endswith(".3mf") or not os.path.isfile(path):
                raise ConvertError(tr("err_not_found", path))
            with open(path, "rb") as f:
                data = f.read()
            name = os.path.basename(path)
        template = self.template_for(msg.get("template"))
        ready = self.ready_message(msg.get("template"))
        one = bool(msg.get("one_per_plate"))
        with self.lock:
            self.counter += 1
            token = "a%d" % self.counter
            self.jobs = {token: {"path": path, "name": name,
                                 "presets": {"user": template.presets, "slots": template.slot_presets}}}
        self.post({"command": "progress", "text": tr("p_analysing", name)})

        def worker():
            ok = False
            try:
                src = Source3MF(data, name, path)
                res = analyze(src, template, one)
                with self.lock:
                    job = self.jobs.get(token)
                    if job is None:
                        return
                    job["src"] = src
                res.update({"command": "analysis", "token": token, "file": name, "one_per_plate": one,
                            "dest_hint": self.dest_hint(path), "not_ready": ready})
                self.post(res)
                ok = True
            except ConvertError as e:
                self.post({"command": "error", "text": tr("err_in_file", name, message_of(e))})
            except Exception as e:
                import traceback
                log_error(traceback.format_exc())
                self.post({"command": "error", "text": tr("err_analyse", name, e)})
            if on_done:
                on_done(name, ok)
        threading.Thread(target=worker, daemon=True).start()

    def _job(self, token):
        with self.lock:
            job = self.jobs.get(token)
        if not job or "src" not in job:
            raise ConvertError(tr("err_lost"))
        return job

    def start_replan(self, msg):
        job = self._job(msg.get("token"))
        template = self.template_for(msg.get("template"))
        job["presets"] = {"user": template.presets, "slots": template.slot_presets}
        one = bool(msg.get("one_per_plate"))
        res = analyze(job["src"], template, one)
        res.update({"command": "analysis", "token": msg.get("token"), "file": job["name"], "one_per_plate": one,
                    "dest_hint": self.dest_hint(job["path"]),
                    "not_ready": self.ready_message(msg.get("template"))})
        self.post(res)

    # ---- conversion
    def start_convert(self, msg):
        token = msg.get("token")
        job = self._job(token)
        if msg.get("template") == "current" or load_saved_template() is None:
            missing = self.ready_message("current")
            if missing:
                raise ConvertError(missing)
            template = capture_current_template()
            if not is_u1(template.config.get("printer_model")):
                raise ConvertError(tr("err_not_u1"))
            save_template(template)
            self.cap_key = "cap_current"
        else:
            template = load_saved_template()
        template.attach(job.get("presets"))
        files = msg.get("files") or []
        self.post({"command": "progress", "text": tr("p_converting")})

        def worker():
            try:
                results = convert(job["src"], template, files,
                                  progress=lambda t: self.post({"command": "progress", "text": t}))
                with self.lock:
                    self.built[token] = results
                self.post({"command": "built", "token": token})
            except ConvertError as e:
                self.post({"command": "error", "text": message_of(e)})
            except Exception as e:
                import traceback
                log_error(traceback.format_exc())
                self.post({"command": "error", "text": tr("err_convert", e)})
        threading.Thread(target=worker, daemon=True).start()

    def write_outputs(self, token):
        with self.lock:
            results = self.built.pop(token, None)
            job = self.jobs.get(token)
        if not results or not job:
            raise ConvertError(tr("err_nothing"))
        folder = output_folder(job["path"])
        files = []
        for r in results:
            path = _free_path(os.path.join(folder, r["name"]))
            with open(path, "wb") as f:
                f.write(r["data"])
            files.append({"name": os.path.basename(path), "path": path, "plates": r["plates"],
                          "filaments": r["filaments"], "colors": r["colors"],
                          "warnings": r["report"]["warnings"]})
        self.send_state()
        self.post({"command": "result", "files": files})

    # ---- evenements d'Orca
    def notify(self, text, hypertext="", callback=None, level="ImportantNotificationLevel"):
        try:
            ui = orca.host.ui
            lvl = getattr(ui.NotificationLevel, level, None) or getattr(ui.NotificationLevel, "ImportantNotificationLevel")
            if callback is None:
                ui.push_notification(lvl, str(text))
            else:
                ui.push_notification(lvl, str(text), str(hypertext), callback)
        except Exception as e:
            log_error("notification : %s" % e)

    def prepare(self, path):
        """Clic sur la notification : analyse du projet ouvert, prete dans l'onglet."""
        try:
            self.refresh_language()
            choice = "saved" if load_saved_template() is not None else "current"

            def done(name, ok):
                if ok:
                    self.notify(tr("n_ready", name), level="RegularNotificationLevel")
            self.start_analyze({"path": path, "template": choice}, on_done=done)
        except ConvertError as e:
            self.notify(tr("n_error", message_of(e)), level="WarningNotificationLevel")
        except Exception as e:
            log_error("preparation : %s" % e)
        return True

    def on_project_opened(self, path):
        self.opened = None
        if not path or not path.lower().endswith(".3mf"):
            return
        info = None
        if _inside(path, downloads_dir()):
            info = sniff_3mf(path)
            foreign = needs_conversion(info)
        else:
            try:
                foreign = not is_u1(current_settings().config.get("printer_model"))
            except Exception:
                foreign = False
            info = {"path": path, "name": os.path.basename(path), "app": "", "printer": ""}
        if not foreign:
            return
        self.opened = info
        what = source_label(info) if info.get("app") else tr("another_slicer")
        text = tr("n_foreign", info["name"], what, (" (%s)" % info["printer"]) if info.get("printer") else "")
        self.notify(text, tr("n_link"), lambda p=path: self.prepare(p))
        self.send_state()

    def on_new_project(self):
        self.opened = None
        self.send_state()


def _inside(path, folder):
    try:
        p = os.path.normcase(os.path.abspath(path))
        f = os.path.normcase(os.path.abspath(folder))
        return os.path.commonpath([p, f]) == f
    except ValueError:
        return False


def _output_folder(source_path):
    """Dossier du fichier d'origine, sauf dossiers temporaires / d'application -> Telechargements."""
    folder = os.path.dirname(source_path)
    low = os.path.normcase(folder)
    for bad in (os.environ.get("TEMP"), os.environ.get("TMP"), os.environ.get("APPDATA"),
                os.environ.get("LOCALAPPDATA"), "/tmp"):
        if bad and _inside(low, bad):
            return downloads_dir()
    return folder or downloads_dir()


def _short_folder(folder):
    home = os.path.expanduser("~")
    if _inside(folder, home):
        rel = os.path.relpath(folder, home)
        return tr("downloads") if rel in ("Downloads",) else rel
    return folder


def _free_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    for i in range(2, 100):
        cand = "%s (%d)%s" % (base, i, ext)
        if not os.path.exists(cand):
            return cand
    return "%s (%d)%s" % (base, int(time.time()), ext)


CONVERTER = Converter()


# --------------------------------------------------------------------------- enregistrement dans Orca

if orca is not None:

    class Mange3MFTab(orca.pages.PagesPluginCapabilityBase):
        """Onglet « Mange-3MF » de la fenetre principale d'Orca."""

        def get_name(self):
            return PLUGIN_NAME

        def get_icon(self):
            try:
                path = os.path.join(storage_dir(), "mange3mf_icon.svg")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(ICON_SVG)
                return path
            except Exception:
                return ""

        def get_default_config(self):
            return {}

        def get_ui(self):
            CONVERTER.attach(self)
            CONVERTER.refresh_language()
            return page_html()

        # Appele sur le fil de l'interface.
        def on_message(self, data):
            CONVERTER.attach(self)
            CONVERTER.on_message(data)

        def on_lifecycle_event(self, event, ctx):
            CONVERTER.attach(self)
            try:
                CONVERTER.refresh_language()
                if event == getattr(orca.LifecycleEvent, "ProjectOpened", object()):
                    CONVERTER.on_project_opened(getattr(ctx, "name", "") or "")
                elif event == getattr(orca.LifecycleEvent, "NewProject", object()):
                    CONVERTER.on_new_project()
            except Exception as e:
                log_error("evenement : %s" % e)

    @orca.plugin
    class Mange3MF(orca.base):
        def register_capabilities(self):
            dl = downloads_dir()
            try:
                orca.request_permissions(fs_read=[os.path.join(dl, "*")], fs_readwrite=[os.path.join(dl, "*")],
                                         threading=True)
            except Exception:
                orca.request_permissions(threading=True)
            orca.register_capability(Mange3MFTab)
