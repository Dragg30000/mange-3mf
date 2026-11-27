# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Mange-3MF (Snapmaker U1)"
# description = "Tab that converts any 3MF (MakerWorld / Bambu Studio, PrusaSlicer / Printables, Snapmaker Orca, other Orca forks) into an OrcaSlicer project for the Snapmaker U1: exactly the model's colors, painting and plates kept, with your own settings. In English, French, German, Spanish or Italian."
# author = "Dragg avec son ami Claude"
# version = "0.6.1"
# ///
"""Mange-3MF - convertit un 3MF d'un autre logiciel en projet OrcaSlicer pour la Snapmaker U1.

Sources acceptees : projets Bambu Studio (MakerWorld), PrusaSlicer (Printables), Snapmaker Orca,
OrcaSlicer et ses variantes (Creality, Elegoo, Anycubic...), 3MF sans reglages (avec leurs couleurs,
s'ils en ont). Pas les fichiers deja tranches (.gcode.3mf, .bgcode).

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

L'interface est un onglet « Mange-3MF » d'Orca, en francais, anglais, allemand, espagnol ou italien
(langue d'Orca, ou au choix dans l'onglet ; tous les textes sont dans TEXTS). Quand Orca ouvre un 3MF pas regle pour la U1,
la U1 apparait aussi dans un panneau a cote du plateau (Preparer et Apercu) : elle le mange, propose
tes profils et le convertit (au choix dans les Reglages : panneau, notification seule ou rien). Le
fichier converti s'ouvre ensuite avec Fichier > Ouvrir (Ctrl+O) : un plugin ne peut pas ouvrir un
projet lui-meme.

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

VERSION = "0.6.1"
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
PRUSA_MODEL_CFG = "Metadata/Slic3r_PE_model.config"
PRUSA_GCODE = "Metadata/Prusa_Slicer_custom_gcode_per_print_z.xml"
PRUSA_RANGES = "Metadata/Prusa_Slicer_layer_config_ranges.xml"
PRUSA_HEIGHTS = "Metadata/Slic3r_PE_layer_heights_profile.txt"

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
UPLOAD_CHUNK = 16 * 1048576     # un fichier glisse arrive par morceaux de 16 Mo au plus (page : CHUNK)
UPLOAD_MAX = 500 * 1048576      # taille maxi d'un fichier glisse ou choisi avec « Parcourir » (page : MAXUP)
UPLOAD_PARTS_MAX = -(-UPLOAD_MAX // UPLOAD_CHUNK) + 1

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
        "lead": "MakerWorld / Bambu Studio, Printables / PrusaSlicer, Snapmaker Orca, autres Orca : "
                "exactement les couleurs du modèle (un filament par couleur), la peinture et les plaques, "
                "avec <b>tes</b> réglages.",
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
        "hf": "High flow",
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
        "th_profile": "Profil de filament",
        "pad_name": "case libre",
        "pad_sub": "pas de couleur du modèle",
        "extra_name": "couleur en plus",
        "extra_sub": "pas utilisée par le modèle",
        "extras_note": "Les couleurs en plus ne servent à aucune pièce : elles seront dans le projet, prêtes pour peindre ou changer la couleur d'une pièce dans Orca.",
        "add_color": "+ Ajouter une couleur",
        "remove_color": "Retirer cette couleur",
        "max_colors": "{0} filaments au plus",
        "color_reset_prof": "remettre celle du profil",
        "warn_material": "le modèle veut du {0}, ce profil est du {1}",
        "mixed": "couleur mélangée",
        "same_n": "{0} filaments identiques",
        "pads_one": "Orca garde au moins une case par tête de la U1 : la case {0} ne sert pas au modèle, sa couleur et son profil sont au choix.",
        "pads_many": "Orca garde au moins une case par tête de la U1 : les cases {0} et {1} ne servent pas au modèle, leur couleur et leur profil sont au choix.",
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
        "reading": "Lecture de {0} ({1}/{2})…",
        "err_upload": "Le fichier n'est pas arrivé en entier : glisse-le à nouveau.",
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
        "home_sub": "Glisse un fichier sur la U1, ou choisis-en un dans tes Téléchargements.",
        "say_idle": "J'ai faim.",
        "say_idle2": "Glisse un 3MF sur moi, ou clique pour en choisir un.",
        "busy2": "Quelques secondes, le temps de tout goûter.",
        "say_done": "C'était délicieux !",
        "say_done2": "Un autre 3MF ? Glisse-le sur moi.",
        "mini2": "Voici ce que j'ai trouvé dans le modèle.",
        "recent_sub": "Le plus récent en haut.",
        "edit": "Modifier",
        "settings": "Réglages",
        "rig_used": "Ils vont dans chaque projet converti.",
        "rig_sub": "Une colonne par tête : le filament qu'elle reçoit et sa buse.",
        "filament_n": "filament {0}",
        "filament_more": "filaments {0} à {1}",
        "via_ace": "via multiACE",
        "k_printer": "Imprimante",
        "k_process": "Profil",
        "h_plates": "Les plaques",
        "h_before": "Avant de convertir",
        "h_map": "Couleurs et filaments",
        "map_sub": "Chaque couleur du modèle devient un filament et garde sa couleur, quel que soit le profil. Un même profil peut servir pour plusieurs couleurs. Clique sur une pastille pour changer la couleur.",
        "map_busy": "La U1 lit les plaques, les couleurs et la peinture.",
        "th_plates": "Plaques",
        "need_ace": "{0} filaments pour 4 têtes : au-delà de 4, ta U1 a besoin de multiACE.",
        "need_ace2": "Pas de multiACE ? Coche « Un fichier par plaque » : chaque fichier n'a que les couleurs de sa plaque.",
        "all_good": "Rien de spécial : tout est prêt à convertir.",
        "one_per_hint": "{0} fichiers, un par plaque",
        "res_title": "Ton projet est prêt",
        "res_title_n": "Tes {0} projets sont prêts",
        "res_sub": "Tes réglages et les couleurs sont dedans.",
        "h_open": "L'ouvrir dans Orca : 3 gestes",
        "open_sub": "Orca ne laisse pas un plugin ouvrir un projet tout seul.",
        "step_copy": "Copie le chemin du projet",
        "step_open": "Dans Orca : Fichier › Ouvrir un projet",
        "step_paste": "Colle le chemin et valide",
        "key_enter": "Entrée",
        "orig_kept": "Ton fichier d'origine n'est pas modifié.",
        "back": "Revenir aux couleurs",
        "again": "Convertir un autre 3MF",
        "cancel": "Annuler",
        "dlg_sub": "Ces réglages vont dans chaque projet converti : imprimante, buses, profil, plaque et filaments.",
        "saved_desc": "Ils restent les mêmes tant que tu ne les remplaces pas.",
        "current_desc": "Ceux affichés maintenant dans Orca : ils changent avec Orca.",
        "out_h": "Fichiers convertis",
        "dlg_foot": "Tes choix sont gardés pour la prochaine fois.",
        "close": "Fermer",
        # --- panneau de Preparer
        "pn_rest2": "Glisse un 3MF sur moi, ou ouvre-le dans Orca : je te dis s'il faut le convertir.",
        "pn_rest2b": "Glisse un 3MF sur moi : je le prépare pour ta U1.",
        "pn_zone": "Dépose un 3MF ici",
        "pn_drag": "Lâche-le !",
        "pn_drag2": "Je le prends ici, pas besoin d'aller dans l'onglet.",
        "pn_zone_drag": "Lâche ton 3MF",
        "pn_offer": "Miam !",
        "pn_offer2": "Ce 3MF n'est pas réglé pour ta U1.",
        "pn_eat": "Le manger",
        "pn_later": "Pas maintenant",
        "pn_offer_hint": "Tu pourras changer les profils et ajouter des couleurs avant de convertir.",
        "pn_chew": "Je mâche…",
        "pn_an_hint": "Clique une pastille pour changer la couleur. Tout se règle aussi dans l'onglet Mange-3MF.",
        "pn_pads_edit": "Choisir le filament de ces cases",
        "pn_pads": "cases libres",
        "pn_keep_1": "ta bobine",
        "pn_keep_n": "tes bobines",
        "pn_conv": "Je prépare ton projet…",
        "pn_done": "C'est prêt !",
        "pn_done_hint": "Puis {0} (Ctrl+O), colle le chemin et valide.",
        "pn_menu": "Fichier › Ouvrir un projet",
        "pn_err": "Pouah !",
        "pn_ok": "OK",
        "pn_h": "Quand Orca ouvre un 3MF pas réglé pour ta U1",
        "pn_mode_panel": "la U1 apparaît à côté du plateau (Préparer et Aperçu)",
        "pn_mode_notif": "une notification seulement",
        "pn_mode_off": "rien",
        "pn_show": "Mettre la U1 dans Préparer",
        "pn_shown": "Elle t'attend dans Préparer et Aperçu.",
        "pn_mode_label": "Quand un 3MF n'est pas réglé :",
        "pn_opt_panel": "je viens ici",
        "pn_opt_notif": "une notification",
        "pn_opt_off": "rien",
        "pn_bye": "D'accord, je me cache.",
        "pn_bye2": "Pour me remettre : onglet Mange-3MF, Réglages.",
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
        "err_sliced": "c'est un fichier déjà tranché (.gcode.3mf) : il ne contient pas le modèle. Télécharge le "
                      "projet 3MF d'origine.",
        "err_no_part": "aucune pièce dans ce 3MF",
        "err_profile": "profil {0} inconnu : refais l'analyse",
        "err_no_slot": "filament {0} sans case : refais l'analyse",
        "err_too_many_extra": "trop de couleurs en plus : {0} filaments au plus par fichier",
        "err_gone": "plus de 3MF ouvert : rouvre-le dans Orca, ou glisse-le sur moi",
        "err_panel": "cet OrcaSlicer ne sait pas afficher le panneau (il faut la version 2.5.1 ou plus)",
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
        # 0.6.0
        "grp_system": "Préréglages système",
        "w_system": "Aucun de tes profils n'est du {0} : je propose « {1} », un profil d'Orca pour ta U1. "
                    "Vérifie-le avant d'imprimer.",
        "w_no_profile": "Aucun profil {0} pour ta U1, ni chez toi ni dans Orca : choisis-en un proche et "
                        "vérifie les températures.",
        "err_system_gone": "profil d'Orca « {0} » introuvable : refais l'analyse",
        "mem_used": "ton choix de la dernière fois",
        "mem_text": "Quand tu changes le profil d'une couleur, il est repris la fois suivante pour la même "
                    "couleur et la même matière.",
        "mem_count": "Couleurs retenues : {0}.",
        "mem_forget": "Oublier mes choix de profils",
        "mem_forgot": "C'est oublié.",
        "sup_keep": "Garder les supports de l'auteur",
        "sup_hint": "Sinon, les supports de tes réglages.",
        "sup_tree": "supports arborescents",
        "sup_normal": "supports normaux",
        "sup_objects": "supports sur certains objets",
        "sup_fil": "support en {1} {0}",
        "sup_iface": "interface en {1} {0}",
        "err_prusa_sla": "projet PrusaSlicer pour une imprimante résine (SLA) : rien à convertir pour la U1",
        "w_prusa_keys": "Réglages par objet de PrusaSlicer non repris : {0}.",
    },
    "en": {
        "lang_name": "English",
        "lang_auto": "Auto (Orca's language)",
        "lang_title": "Tab language",
        # --- tab
        "sub": "any 3MF → your Snapmaker U1",
        "lead": "MakerWorld / Bambu Studio, Printables / PrusaSlicer, Snapmaker Orca, other Orca forks: "
                "exactly the model's colors (one filament per color), the painting and the plates, with "
                "<b>your</b> settings.",
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
        "hf": "High flow",
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
        "th_profile": "Filament profile",
        "pad_name": "free slot",
        "pad_sub": "no model color",
        "extra_name": "extra color",
        "extra_sub": "not used by the model",
        "extras_note": "Extra colors are not used by any part: they will be in the project, ready to paint or to recolor a part in Orca.",
        "add_color": "+ Add a color",
        "remove_color": "Remove this color",
        "max_colors": "{0} filaments at most",
        "color_reset_prof": "back to the profile's color",
        "warn_material": "the model wants {0}, this profile is {1}",
        "mixed": "mixed color",
        "same_n": "{0} identical filaments",
        "pads_one": "Orca keeps at least one slot per U1 head: slot {0} is not used by the model, its color and profile are up to you.",
        "pads_many": "Orca keeps at least one slot per U1 head: slots {0} and {1} are not used by the model, their colors and profiles are up to you.",
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
        "reading": "Reading {0} ({1}/{2})…",
        "err_upload": "The file did not arrive in full: drop it again.",
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
        "home_sub": "Drop a file on the U1, or pick one from your Downloads.",
        "say_idle": "I'm hungry.",
        "say_idle2": "Drop a 3MF on me, or click to pick one.",
        "busy2": "A few seconds to taste everything.",
        "say_done": "That was delicious!",
        "say_done2": "Another 3MF? Drop it on me.",
        "mini2": "Here is what I found in the model.",
        "recent_sub": "Newest first.",
        "edit": "Change",
        "settings": "Settings",
        "rig_used": "They go into every converted project.",
        "rig_sub": "One column per head: its filament and its nozzle.",
        "filament_n": "filament {0}",
        "filament_more": "filaments {0} to {1}",
        "via_ace": "via multiACE",
        "k_printer": "Printer",
        "k_process": "Process",
        "h_plates": "Plates",
        "h_before": "Before converting",
        "h_map": "Colors and filaments",
        "map_sub": "Each model color becomes a filament and keeps its color, whatever the profile. One profile can be used for several colors. Click a swatch to change the color.",
        "map_busy": "The U1 is reading the plates, colors and painting.",
        "th_plates": "Plates",
        "need_ace": "{0} filaments for 4 heads: above 4, your U1 needs multiACE.",
        "need_ace2": "No multiACE? Tick “One file per plate”: each file only has the colors of its plate.",
        "all_good": "Nothing special: everything is ready to convert.",
        "one_per_hint": "{0} files, one per plate",
        "res_title": "Your project is ready",
        "res_title_n": "Your {0} projects are ready",
        "res_sub": "Your settings and the colors are inside.",
        "h_open": "Open it in Orca: 3 steps",
        "open_sub": "Orca doesn't let a plugin open a project by itself.",
        "step_copy": "Copy the project's path",
        "step_open": "In Orca: File › Open Project",
        "step_paste": "Paste the path and confirm",
        "key_enter": "Enter",
        "orig_kept": "Your original file is not changed.",
        "back": "Back to the colors",
        "again": "Convert another 3MF",
        "cancel": "Cancel",
        "dlg_sub": "These settings go into every converted project: printer, nozzles, process, plate and filaments.",
        "saved_desc": "They stay the same until you replace them.",
        "current_desc": "The ones shown in Orca right now: they change with Orca.",
        "out_h": "Converted files",
        "dlg_foot": "Your choices are kept for next time.",
        "close": "Close",
        # --- Prepare panel
        "pn_rest2": "Drop a 3MF on me, or open it in Orca: I'll tell you if it needs converting.",
        "pn_rest2b": "Drop a 3MF on me: I'll get it ready for your U1.",
        "pn_zone": "Drop a 3MF here",
        "pn_drag": "Drop it!",
        "pn_drag2": "I'll take it right here, no need for the tab.",
        "pn_zone_drag": "Let go of your 3MF",
        "pn_offer": "Yum!",
        "pn_offer2": "This 3MF isn't set up for your U1.",
        "pn_eat": "Eat it",
        "pn_later": "Not now",
        "pn_offer_hint": "You can change the profiles and add colors before converting.",
        "pn_chew": "Chewing…",
        "pn_an_hint": "Click a dot to change the color. Everything can also be set in the Mange-3MF tab.",
        "pn_pads_edit": "Choose the filament for these slots",
        "pn_pads": "free slots",
        "pn_keep_1": "your spool",
        "pn_keep_n": "your spools",
        "pn_conv": "Making your project…",
        "pn_done": "It's ready!",
        "pn_done_hint": "Then {0} (Ctrl+O), paste the path and confirm.",
        "pn_menu": "File › Open Project",
        "pn_err": "Yuck!",
        "pn_ok": "OK",
        "pn_h": "When Orca opens a 3MF not set up for your U1",
        "pn_mode_panel": "the U1 shows up beside the plate (Prepare and Preview)",
        "pn_mode_notif": "a notification only",
        "pn_mode_off": "nothing",
        "pn_show": "Put the U1 in Prepare",
        "pn_shown": "She's waiting in Prepare and Preview.",
        "pn_mode_label": "When a 3MF isn't set up:",
        "pn_opt_panel": "I show up here",
        "pn_opt_notif": "a notification",
        "pn_opt_off": "nothing",
        "pn_bye": "OK, I'll hide.",
        "pn_bye2": "To bring me back: Mange-3MF tab, Settings.",
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
        "err_sliced": "this is an already sliced file (.gcode.3mf): it does not contain the model. Download the "
                      "original 3MF project.",
        "err_no_part": "no part in this 3MF",
        "err_profile": "unknown profile {0}: analyze the file again",
        "err_no_slot": "filament {0} has no slot: analyze the file again",
        "err_too_many_extra": "too many extra colors: {0} filaments at most per file",
        "err_gone": "no 3MF open any more: open it again in Orca, or drop it on me",
        "err_panel": "this OrcaSlicer can't show the panel (version 2.5.1 or later needed)",
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
        # 0.6.0
        "grp_system": "System presets",
        "w_system": "None of your profiles is {0}: I suggest “{1}”, an Orca profile for your U1. Check it "
                    "before printing.",
        "w_no_profile": "No {0} profile for your U1, neither yours nor in Orca: pick a close one and check "
                        "the temperatures.",
        "err_system_gone": "Orca profile “{0}” not found: analyze the file again",
        "mem_used": "your choice from last time",
        "mem_text": "When you change a color's profile, it is picked again next time for the same color and material.",
        "mem_count": "Colors remembered: {0}.",
        "mem_forget": "Forget my profile choices",
        "mem_forgot": "Forgotten.",
        "sup_keep": "Keep the author's supports",
        "sup_hint": "Otherwise, your settings' supports.",
        "sup_tree": "tree supports",
        "sup_normal": "normal supports",
        "sup_objects": "supports on some objects",
        "sup_fil": "{0} {1} support",
        "sup_iface": "{0} {1} interface",
        "err_prusa_sla": "PrusaSlicer project for a resin (SLA) printer: nothing to convert for the U1",
        "w_prusa_keys": "PrusaSlicer per-object settings not carried over: {0}.",
    },
    "de": {
        "lang_name": "Deutsch",
        "lang_auto": "Auto (Sprache von Orca)",
        "lang_title": "Sprache des Tabs",
        "sub": "jedes 3MF → deine Snapmaker U1",
        "lead": "MakerWorld / Bambu Studio, Printables / PrusaSlicer, Snapmaker Orca, andere Orca-Varianten: "
                "genau die Farben des Modells (ein Filament pro Farbe), die Bemalung und die Platten, mit "
                "<b>deinen</b> Einstellungen.",
        "h_analysis": "Analyse",
        "h_result": "Dateien bereit",
        "h_tpl": "Deine Einstellungen für die Umwandlung",
        "h_src": "Das 3MF zum Fressen",
        "capture": "Aktuelle Einstellungen von Orca speichern",
        "recent_title": "Neueste 3MFs in deinen Downloads",
        "refresh": "Aktualisieren",
        "searching": "Suche…",
        "path_ph": "Oder füge den Pfad eines 3MF ein (Rechtsklick auf die Datei › Als Pfad kopieren)",
        "analyse": "Analysieren",
        "browse": "Durchsuchen…",
        "drop_hint": "Lass ein 3MF auf die U1 fallen: Sie hat Hunger.",
        "drop": "Mmmh! Lass es fallen…",
        "u1_click": "oder klick sie an, um eine Datei zu wählen",
        "u1_title": "Lass hier ein 3MF fallen oder klick, um eins zu wählen",
        "u1_chomp": "Knusper!",
        "u1_chew": "Kaue…",
        "u1_burp": "Rülps! {0}",
        "u1_spit": "Igitt! Das ist kein 3MF.",
        "u1_sick": "Igitt! Das bekomme ich nicht runter.",
        "tpl_saved": "Gespeicherte Einstellungen",
        "tpl_current": "Aktuelle Einstellungen von Orca",
        "badge_not_u1": "keine U1",
        "badge_foreign": "aus dem offenen Projekt",
        "tpl_hint": "Wähle in Orca deine üblichen Einstellungen (U1, Düsen, Prozess, Platte, Filamente) und "
                    "klick dann auf „Speichern“: Sie werden für jede Umwandlung verwendet.",
        "nozzles": "Düsen",
        "except": "außer",
        "hf": "High Flow",
        "std": "Standard",
        "bed_tpei": "Texturierte PEI-Platte",
        "bed_cool": "Cool-Platte",
        "bed_eng": "Engineering-Platte",
        "bed_hot": "Hochtemperatur-Platte",
        "bed_tack": "SuperTack-Platte",
        "bed_tcool": "Texturierte Cool-Platte",
        "badge_unreadable": "unlesbar",
        "badge_sliced": "bereits gesliced",
        "badge_todo": "umzuwandeln",
        "badge_ok": "schon für die U1",
        "color1": "Farbe",
        "colorN": "Farben",
        "mb": "MB",
        "kb": "KB",
        "ago_now": "gerade eben",
        "ago_min": "vor {0} Min.",
        "ago_h": "vor {0} Std.",
        "ago_d": "vor {0} Tag(en)",
        "opened_in_orca": "in Orca geöffnet",
        "no_3mf": "Kein 3MF in {0}.",
        "analysing": "Analysiere…",
        "by": "von",
        "nozzle": "Düse",
        "bed": "Druckbett",
        "plate1": "Platte",
        "plateN": "Platten",
        "one_per_plate": "Eine Datei pro Platte",
        "file_n": "Datei {0}: ",
        "n_filaments": "{0} Filamente",
        "th_color": "Farbe im Modell",
        "th_profile": "Filamentprofil",
        "pad_name": "freier Slot",
        "pad_sub": "keine Farbe des Modells",
        "extra_name": "zusätzliche Farbe",
        "extra_sub": "vom Modell nicht verwendet",
        "extras_note": "Zusätzliche Farben werden von keinem Teil verwendet: Sie sind im Projekt, bereit zum "
                       "Bemalen oder um ein Teil in Orca umzufärben.",
        "add_color": "+ Farbe hinzufügen",
        "remove_color": "Diese Farbe entfernen",
        "max_colors": "höchstens {0} Filamente",
        "color_reset_prof": "zurück zur Farbe des Profils",
        "warn_material": "das Modell will {0}, dieses Profil ist {1}",
        "mixed": "Mischfarbe",
        "same_n": "{0} gleiche Filamente",
        "pads_one": "Orca behält mindestens einen Slot pro Kopf der U1: Slot {0} wird vom Modell nicht "
                    "verwendet, Farbe und Profil kannst du frei wählen.",
        "pads_many": "Orca behält mindestens einen Slot pro Kopf der U1: Die Slots {0} und {1} werden vom "
                     "Modell nicht verwendet, Farben und Profile kannst du frei wählen.",
        "to_know": "Gut zu wissen",
        "convert": "Umwandeln",
        "convert_n": "In {0} Dateien umwandeln",
        "created_1": "Die Datei wird {0} erstellt. Ein Filament pro Farbe des Modells, mit dem gewählten Profil.",
        "created_n": "Die Dateien werden {0} erstellt. Ein Filament pro Farbe des Modells, mit dem gewählten Profil.",
        "converting": "Umwandlung…",
        "copy_path": "Pfad kopieren",
        "copied": "Kopiert ✓",
        "open_hint": "In Orca: <b>Datei › Projekt öffnen</b> (Strg+O), Pfad einfügen und bestätigen. Deine "
                     "Einstellungen und die Farben sind schon drin.",
        "not_3mf": "Das ist keine 3MF-Datei: {0}",
        "too_big": "Datei zu groß, um hier gelesen zu werden ({0}): Leg sie in Downloads oder füge ihren Pfad ein.",
        "reading": "Lese {0} ({1}/{2})…",
        "err_upload": "Die Datei ist nicht vollständig angekommen: Lass sie noch einmal fallen.",
        "grp_slots": "In deinen Einstellungen",
        "grp_user": "Deine Voreinstellungen",
        "grp_other": "Für einen anderen Drucker",
        "pick_color": "Farbe dieses Filaments ändern",
        "color_changed": "Farbe geändert",
        "color_reset": "zurück zur Farbe des Modells",
        "out_title": "Umgewandelte Dateien:",
        "out_beside": "neben dem Original-3MF",
        "out_downloads": "in Downloads",
        "out_folder": "in diesem Ordner",
        "out_ph": "Ordnerpfad (Rechtsklick auf den Ordner › Als Pfad kopieren)",
        "out_ok": "OK",
        "support": "Gefällt dir das Plugin? Spendier Dragg einen Kaffee ☕",
        "copy_link": "Link kopieren",
        "home_sub": "Lass eine Datei auf die U1 fallen oder wähle eine aus deinen Downloads.",
        "say_idle": "Ich hab Hunger.",
        "say_idle2": "Lass ein 3MF auf mich fallen oder klick, um eins zu wählen.",
        "busy2": "Ein paar Sekunden, um alles zu kosten.",
        "say_done": "Das war lecker!",
        "say_done2": "Noch ein 3MF? Lass es auf mich fallen.",
        "mini2": "Das habe ich im Modell gefunden.",
        "recent_sub": "Neueste zuerst.",
        "edit": "Ändern",
        "settings": "Einstellungen",
        "rig_used": "Sie kommen in jedes umgewandelte Projekt.",
        "rig_sub": "Eine Spalte pro Kopf: sein Filament und seine Düse.",
        "filament_n": "Filament {0}",
        "filament_more": "Filamente {0} bis {1}",
        "via_ace": "via multiACE",
        "k_printer": "Drucker",
        "k_process": "Prozess",
        "h_plates": "Platten",
        "h_before": "Vor dem Umwandeln",
        "h_map": "Farben und Filamente",
        "map_sub": "Jede Farbe des Modells wird ein Filament und behält ihre Farbe, egal welches Profil. Ein "
                   "Profil kann für mehrere Farben dienen. Klick auf einen Farbpunkt, um die Farbe zu ändern.",
        "map_busy": "Die U1 liest die Platten, die Farben und die Bemalung.",
        "th_plates": "Platten",
        "need_ace": "{0} Filamente für 4 Köpfe: Über 4 braucht deine U1 multiACE.",
        "need_ace2": "Kein multiACE? Hak „Eine Datei pro Platte“ an: Jede Datei hat nur die Farben ihrer Platte.",
        "all_good": "Nichts Besonderes: Alles ist bereit zum Umwandeln.",
        "one_per_hint": "{0} Dateien, eine pro Platte",
        "res_title": "Dein Projekt ist fertig",
        "res_title_n": "Deine {0} Projekte sind fertig",
        "res_sub": "Deine Einstellungen und die Farben sind drin.",
        "h_open": "In Orca öffnen: 3 Schritte",
        "open_sub": "Orca lässt ein Plugin kein Projekt selbst öffnen.",
        "step_copy": "Pfad des Projekts kopieren",
        "step_open": "In Orca: Datei › Projekt öffnen",
        "step_paste": "Pfad einfügen und bestätigen",
        "key_enter": "Eingabe",
        "orig_kept": "Deine Originaldatei bleibt unverändert.",
        "back": "Zurück zu den Farben",
        "again": "Ein weiteres 3MF umwandeln",
        "cancel": "Abbrechen",
        "dlg_sub": "Diese Einstellungen kommen in jedes umgewandelte Projekt: Drucker, Düsen, Prozess, "
                   "Platte und Filamente.",
        "saved_desc": "Sie bleiben gleich, bis du sie ersetzt.",
        "current_desc": "Die gerade in Orca angezeigten: Sie ändern sich mit Orca.",
        "out_h": "Umgewandelte Dateien",
        "dlg_foot": "Deine Auswahl bleibt für das nächste Mal gespeichert.",
        "close": "Schließen",
        "pn_rest2": "Lass ein 3MF auf mich fallen oder öffne es in Orca: Ich sage dir, ob es umgewandelt werden muss.",
        "pn_rest2b": "Lass ein 3MF auf mich fallen: Ich mache es für deine U1 bereit.",
        "pn_zone": "3MF hier ablegen",
        "pn_drag": "Lass los!",
        "pn_drag2": "Ich nehme es direkt hier, ganz ohne den Tab.",
        "pn_zone_drag": "Lass dein 3MF los",
        "pn_offer": "Mmmh!",
        "pn_offer2": "Dieses 3MF ist nicht für deine U1 eingerichtet.",
        "pn_eat": "Fressen",
        "pn_later": "Nicht jetzt",
        "pn_offer_hint": "Du kannst die Profile ändern und Farben hinzufügen, bevor du umwandelst.",
        "pn_chew": "Kaue…",
        "pn_an_hint": "Klick auf einen Punkt, um die Farbe zu ändern. Alles lässt sich auch im Tab Mange-3MF "
                      "einstellen.",
        "pn_pads_edit": "Filament für diese Slots wählen",
        "pn_pads": "freie Slots",
        "pn_keep_1": "deine Spule",
        "pn_keep_n": "deine Spulen",
        "pn_conv": "Ich mache dein Projekt…",
        "pn_done": "Fertig!",
        "pn_done_hint": "Dann {0} (Strg+O), Pfad einfügen und bestätigen.",
        "pn_menu": "Datei › Projekt öffnen",
        "pn_err": "Igitt!",
        "pn_ok": "OK",
        "pn_h": "Wenn Orca ein 3MF öffnet, das nicht für deine U1 eingerichtet ist",
        "pn_mode_panel": "erscheint die U1 neben der Platte (Vorbereiten und Vorschau)",
        "pn_mode_notif": "nur eine Benachrichtigung",
        "pn_mode_off": "nichts",
        "pn_show": "Die U1 in Vorbereiten zeigen",
        "pn_shown": "Sie wartet in Vorbereiten und Vorschau.",
        "pn_mode_label": "Wenn ein 3MF nicht eingerichtet ist:",
        "pn_opt_panel": "ich erscheine hier",
        "pn_opt_notif": "eine Benachrichtigung",
        "pn_opt_off": "nichts",
        "pn_bye": "Okay, ich verstecke mich.",
        "pn_bye2": "Um mich zurückzuholen: Tab Mange-3MF, Einstellungen.",
        "when_saved": "gespeichert am {0:02d}.{1:02d}. um {3:02d}:{4:02d}",
        "cap_saved": "Einstellungen gespeichert.",
        "cap_current": "Aktuelle Einstellungen für die Umwandlung gespeichert.",
        "out_saved": "Ordner gespeichert.",
        "err_out_dir": "Ordner nicht gefunden: {0}",
        "dest_in": "in {0}",
        "downloads": "Downloads",
        "out_plate1": "{0} - {2} - Platte {1}.3mf",
        "out_plateN": "{0} - {2} - Platten {1}.3mf",
        "unknown_app": "unbekannte Software",
        "another_slicer": "anderes Programm",
        "unknown": "unbekannt",
        "unnamed": "ohne Namen",
        "mix": "Mischung {0}+{1}",
        "p_analysing": "Analysiere {0}…",
        "p_converting": "Umwandlung…",
        "p_file": "Datei {0} von {1}…",
        "need_u1": "Ich brauche deine U1-Einstellungen: Wähle in Orca deine Snapmaker U1 und deine Profile "
                   "(oder öffne eins deiner U1-Projekte) und klick dann auf „Aktuelle Einstellungen von Orca "
                   "speichern“.",
        "w_cfg_unreadable": "Die Einstellungen des Originalprojekts sind unlesbar: Sie werden ignoriert.",
        "w_obj_unreadable": "Die Objekteinstellungen sind unlesbar: Die Farben der Objekte werden ignoriert.",
        "w_mixed_orca": "Das Projekt nutzt Mischfarben (gemischte Filamente von Orca): Jede wird eine "
                        "Vollfarbe mit eigenem Filament.",
        "w_mixed_fs": "Das Projekt nutzt Mischfarben (Snapmaker Orca Full Spectrum): Jede wird eine "
                      "Vollfarbe mit eigenem Filament.",
        "w_paint": "Ein Teil der Bemalung ist unlesbar: Er bleibt, wie er ist.",
        "w_paint_max": "Mehr als {0} Farben: Orca kann nur mit den ersten {0} Filamenten malen.",
        "w_plate": "Platte {0} „{1}“: {2}.",
        "w_too_big": "zu groß für das Druckbett der U1 ({0:.0f} x {1:.0f} mm)",
        "w_material": "Filament {0} ({1}): Das Modell will {2}, das gewählte Profil „{3}“ ist {4}. Ändere es "
                      "bei Bedarf in Orca.",
        "err_not_3mf": "diese Datei ist kein 3MF (unlesbares Archiv)",
        "err_no_model": "dieses 3MF enthält kein 3D-Modell",
        "err_ref_unreadable": "Referenzprojekt unlesbar ({0})",
        "err_ref_not_orca": "das Referenzprojekt muss von OrcaSlicer stammen (gefunden: {0})",
        "err_sliced": "das ist eine bereits geslicte Datei (.gcode.3mf): Sie enthält das Modell nicht. Lade "
                      "das originale 3MF-Projekt herunter.",
        "err_no_part": "kein Teil in diesem 3MF",
        "err_profile": "unbekanntes Profil {0}: analysiere die Datei erneut",
        "err_no_slot": "Filament {0} hat keinen Slot: analysiere die Datei erneut",
        "err_too_many_extra": "zu viele zusätzliche Farben: höchstens {0} Filamente pro Datei",
        "err_gone": "kein 3MF mehr offen: Öffne es erneut in Orca oder lass es auf mich fallen",
        "err_panel": "dieses OrcaSlicer kann das Panel nicht anzeigen (Version 2.5.1 oder neuer nötig)",
        "err_plates_missing": "Platte(n) {0} fehlen im Plan",
        "err_not_found": "Datei nicht gefunden: {0}",
        "err_lost": "Analyse verloren: analysiere die Datei erneut",
        "err_not_u1": "das offene Projekt ist nicht für eine Snapmaker U1 eingerichtet",
        "err_nothing": "nichts zu schreiben: starte die Umwandlung erneut",
        "err_denied": "Zugriff von Orca verweigert: {0}",
        "err_generic": "Fehler: {0}",
        "err_in_file": "{0}: {1}",
        "err_analyse": "{0} konnte nicht analysiert werden: {1}",
        "err_convert": "Umwandlung fehlgeschlagen: {0}",
        "err_storage": "Speicherordner des Plugins nicht verfügbar",
        "n_foreign": "„{0}“ – {1}{2}: Farben und Einstellungen passen nicht zu deiner U1.",
        "n_link": "Umwandlung im Tab Mange-3MF vorbereiten",
        "n_ready": "Die Umwandlung von „{0}“ ist bereit: Öffne den Tab Mange-3MF.",
        "n_error": "Mange-3MF: {0}",
        "col_black": "Schwarz",
        "col_white": "Weiß",
        "col_lightgrey": "Hellgrau",
        "col_grey": "Grau",
        "col_darkgrey": "Dunkelgrau",
        "col_brown": "Braun",
        "col_beige": "Beige",
        "col_red": "Rot",
        "col_orange": "Orange",
        "col_yellow": "Gelb",
        "col_green": "Grün",
        "col_turquoise": "Türkis",
        "col_blue": "Blau",
        "col_purple": "Lila",
        "col_pink": "Rosa",
        "col_lightpink": "Hellrosa",
        "grp_system": "Systemvoreinstellungen",
        "w_system": "Keines deiner Profile ist {0}: Ich schlage „{1}“ vor, ein Profil von Orca für deine U1. "
                    "Prüfe es vor dem Drucken.",
        "w_no_profile": "Kein {0}-Profil für deine U1, weder bei dir noch in Orca: Wähle ein ähnliches und "
                        "prüfe die Temperaturen.",
        "err_system_gone": "Profil von Orca „{0}“ nicht gefunden: analysiere die Datei erneut",
        "mem_used": "deine Wahl vom letzten Mal",
        "mem_text": "Wenn du das Profil einer Farbe änderst, wird es beim nächsten Mal für dieselbe Farbe "
                    "und dasselbe Material wieder genommen.",
        "mem_count": "Gemerkte Farben: {0}.",
        "mem_forget": "Meine Profilwahl vergessen",
        "mem_forgot": "Vergessen.",
        "sup_keep": "Stützen des Autors behalten",
        "sup_hint": "Sonst die Stützen deiner Einstellungen.",
        "sup_tree": "Baumstützen",
        "sup_normal": "normale Stützen",
        "sup_objects": "Stützen an einigen Objekten",
        "sup_fil": "Stützen in {0} ({1})",
        "sup_iface": "Schnittstelle in {0} ({1})",
        "err_prusa_sla": "PrusaSlicer-Projekt für einen Harzdrucker (SLA): nichts für die U1 umzuwandeln",
        "w_prusa_keys": "Objekteinstellungen von PrusaSlicer nicht übernommen: {0}.",
    },
    "es": {
        "lang_name": "Español",
        "lang_auto": "Auto (idioma de Orca)",
        "lang_title": "Idioma de la pestaña",
        "sub": "cualquier 3MF → tu Snapmaker U1",
        "lead": "MakerWorld / Bambu Studio, Printables / PrusaSlicer, Snapmaker Orca, otras variantes de "
                "Orca: exactamente los colores del modelo (un filamento por color), la pintura y las placas, "
                "con <b>tus</b> ajustes.",
        "h_analysis": "Análisis",
        "h_result": "Archivos listos",
        "h_tpl": "Tus ajustes para la conversión",
        "h_src": "El 3MF que comer",
        "capture": "Guardar los ajustes actuales de Orca",
        "recent_title": "Últimos 3MF en tus Descargas",
        "refresh": "Actualizar",
        "searching": "Buscando…",
        "path_ph": "O pega la ruta de un 3MF (clic derecho en el archivo › Copiar como ruta de acceso)",
        "analyse": "Analizar",
        "browse": "Examinar…",
        "drop_hint": "Suelta un 3MF sobre la U1: tiene hambre.",
        "drop": "¡Ñam! Suéltalo…",
        "u1_click": "o haz clic en ella para elegir un archivo",
        "u1_title": "Suelta aquí un 3MF o haz clic para elegir uno",
        "u1_chomp": "¡Crunch!",
        "u1_chew": "Masticando…",
        "u1_burp": "¡Burp! {0}",
        "u1_spit": "¡Puaj! Eso no es un 3MF.",
        "u1_sick": "¡Puaj! Esto no hay quien se lo trague.",
        "tpl_saved": "Ajustes guardados",
        "tpl_current": "Ajustes actuales de Orca",
        "badge_not_u1": "no es una U1",
        "badge_foreign": "del proyecto abierto",
        "tpl_hint": "Elige tus ajustes habituales en Orca (U1, boquillas, proceso, placa, filamentos) y haz "
                    "clic en “Guardar”: se usarán en cada conversión.",
        "nozzles": "boquillas",
        "except": "excepto",
        "hf": "High flow",
        "std": "Estándar",
        "bed_tpei": "placa PEI texturizada",
        "bed_cool": "placa Cool",
        "bed_eng": "placa Engineering",
        "bed_hot": "placa de alta temperatura",
        "bed_tack": "placa SuperTack",
        "bed_tcool": "placa Cool texturizada",
        "badge_unreadable": "ilegible",
        "badge_sliced": "ya laminado",
        "badge_todo": "por convertir",
        "badge_ok": "ya para la U1",
        "color1": "color",
        "colorN": "colores",
        "mb": "MB",
        "kb": "KB",
        "ago_now": "ahora mismo",
        "ago_min": "hace {0} min",
        "ago_h": "hace {0} h",
        "ago_d": "hace {0} d",
        "opened_in_orca": "abierto en Orca",
        "no_3mf": "Ningún 3MF en {0}.",
        "analysing": "Analizando…",
        "by": "de",
        "nozzle": "boquilla",
        "bed": "cama",
        "plate1": "placa",
        "plateN": "placas",
        "one_per_plate": "Un archivo por placa",
        "file_n": "Archivo {0}: ",
        "n_filaments": "{0} filamentos",
        "th_color": "Color del modelo",
        "th_profile": "Perfil de filamento",
        "pad_name": "ranura libre",
        "pad_sub": "sin color del modelo",
        "extra_name": "color extra",
        "extra_sub": "no lo usa el modelo",
        "extras_note": "Ninguna pieza usa los colores extra: estarán en el proyecto, listos para pintar o "
                       "para cambiar el color de una pieza en Orca.",
        "add_color": "+ Añadir un color",
        "remove_color": "Quitar este color",
        "max_colors": "{0} filamentos como máximo",
        "color_reset_prof": "volver al color del perfil",
        "warn_material": "el modelo pide {0}, este perfil es {1}",
        "mixed": "color mezclado",
        "same_n": "{0} filamentos idénticos",
        "pads_one": "Orca mantiene al menos una ranura por cabezal de la U1: el modelo no usa la ranura {0}, "
                    "su color y su perfil los eliges tú.",
        "pads_many": "Orca mantiene al menos una ranura por cabezal de la U1: el modelo no usa las ranuras "
                     "{0} y {1}, sus colores y perfiles los eliges tú.",
        "to_know": "Conviene saber",
        "convert": "Convertir",
        "convert_n": "Convertir en {0} archivos",
        "created_1": "El archivo se crea {0}. Un filamento por color del modelo, con el perfil elegido.",
        "created_n": "Los archivos se crean {0}. Un filamento por color del modelo, con el perfil elegido.",
        "converting": "Convirtiendo…",
        "copy_path": "Copiar ruta",
        "copied": "Copiado ✓",
        "open_hint": "En Orca: <b>Archivo › Abrir proyecto</b> (Ctrl+O), pega la ruta y confirma. Tus "
                     "ajustes y los colores ya están dentro.",
        "not_3mf": "Esto no es un archivo 3MF: {0}",
        "too_big": "Archivo demasiado grande para leerlo aquí ({0}): ponlo en Descargas o pega su ruta.",
        "reading": "Leyendo {0} ({1}/{2})…",
        "err_upload": "El archivo no llegó completo: suéltalo otra vez.",
        "grp_slots": "En tus ajustes",
        "grp_user": "Tus preajustes",
        "grp_other": "Para otra impresora",
        "pick_color": "Cambiar el color de este filamento",
        "color_changed": "color cambiado",
        "color_reset": "volver al color del modelo",
        "out_title": "Archivos convertidos:",
        "out_beside": "junto al 3MF original",
        "out_downloads": "en Descargas",
        "out_folder": "en esta carpeta",
        "out_ph": "Ruta de la carpeta (clic derecho en la carpeta › Copiar como ruta de acceso)",
        "out_ok": "OK",
        "support": "¿Te gusta el plugin? Invita a Dragg a un café ☕",
        "copy_link": "Copiar enlace",
        "home_sub": "Suelta un archivo sobre la U1 o elige uno de tus Descargas.",
        "say_idle": "Tengo hambre.",
        "say_idle2": "Suéltame un 3MF encima o haz clic para elegir uno.",
        "busy2": "Unos segundos para probarlo todo.",
        "say_done": "¡Estaba delicioso!",
        "say_done2": "¿Otro 3MF? Suéltamelo encima.",
        "mini2": "Esto es lo que encontré en el modelo.",
        "recent_sub": "Los más recientes primero.",
        "edit": "Cambiar",
        "settings": "Ajustes",
        "rig_used": "Van en cada proyecto convertido.",
        "rig_sub": "Una columna por cabezal: su filamento y su boquilla.",
        "filament_n": "filamento {0}",
        "filament_more": "filamentos {0} a {1}",
        "via_ace": "vía multiACE",
        "k_printer": "Impresora",
        "k_process": "Proceso",
        "h_plates": "Placas",
        "h_before": "Antes de convertir",
        "h_map": "Colores y filamentos",
        "map_sub": "Cada color del modelo se convierte en un filamento y conserva su color, sea cual sea el "
                   "perfil. Un mismo perfil puede servir para varios colores. Haz clic en una muestra para "
                   "cambiar el color.",
        "map_busy": "La U1 está leyendo las placas, los colores y la pintura.",
        "th_plates": "Placas",
        "need_ace": "{0} filamentos para 4 cabezales: por encima de 4, tu U1 necesita multiACE.",
        "need_ace2": "¿Sin multiACE? Marca “Un archivo por placa”: cada archivo solo tiene los colores de su placa.",
        "all_good": "Nada especial: todo está listo para convertir.",
        "one_per_hint": "{0} archivos, uno por placa",
        "res_title": "Tu proyecto está listo",
        "res_title_n": "Tus {0} proyectos están listos",
        "res_sub": "Tus ajustes y los colores están dentro.",
        "h_open": "Ábrelo en Orca: 3 pasos",
        "open_sub": "Orca no deja que un plugin abra un proyecto por sí solo.",
        "step_copy": "Copia la ruta del proyecto",
        "step_open": "En Orca: Archivo › Abrir proyecto",
        "step_paste": "Pega la ruta y confirma",
        "key_enter": "Intro",
        "orig_kept": "Tu archivo original no se modifica.",
        "back": "Volver a los colores",
        "again": "Convertir otro 3MF",
        "cancel": "Cancelar",
        "dlg_sub": "Estos ajustes van en cada proyecto convertido: impresora, boquillas, proceso, placa y filamentos.",
        "saved_desc": "Se mantienen hasta que los sustituyas.",
        "current_desc": "Los que muestra Orca ahora mismo: cambian con Orca.",
        "out_h": "Archivos convertidos",
        "dlg_foot": "Tus elecciones se guardan para la próxima vez.",
        "close": "Cerrar",
        "pn_rest2": "Suéltame un 3MF encima o ábrelo en Orca: te diré si hay que convertirlo.",
        "pn_rest2b": "Suéltame un 3MF encima: lo prepararé para tu U1.",
        "pn_zone": "Suelta aquí un 3MF",
        "pn_drag": "¡Suéltalo!",
        "pn_drag2": "Lo tomo aquí mismo, sin la pestaña.",
        "pn_zone_drag": "Suelta tu 3MF",
        "pn_offer": "¡Ñam!",
        "pn_offer2": "Este 3MF no está preparado para tu U1.",
        "pn_eat": "Cómetelo",
        "pn_later": "Ahora no",
        "pn_offer_hint": "Puedes cambiar los perfiles y añadir colores antes de convertir.",
        "pn_chew": "Masticando…",
        "pn_an_hint": "Haz clic en un punto para cambiar el color. Todo se puede ajustar también en la "
                      "pestaña Mange-3MF.",
        "pn_pads_edit": "Elige el filamento de estas ranuras",
        "pn_pads": "ranuras libres",
        "pn_keep_1": "tu bobina",
        "pn_keep_n": "tus bobinas",
        "pn_conv": "Preparando tu proyecto…",
        "pn_done": "¡Listo!",
        "pn_done_hint": "Luego {0} (Ctrl+O), pega la ruta y confirma.",
        "pn_menu": "Archivo › Abrir proyecto",
        "pn_err": "¡Puaj!",
        "pn_ok": "OK",
        "pn_h": "Cuando Orca abre un 3MF no preparado para tu U1",
        "pn_mode_panel": "la U1 aparece junto a la placa (Preparar y Previsualizar)",
        "pn_mode_notif": "solo una notificación",
        "pn_mode_off": "nada",
        "pn_show": "Poner la U1 en Preparar",
        "pn_shown": "Te espera en Preparar y Previsualizar.",
        "pn_mode_label": "Cuando un 3MF no está preparado:",
        "pn_opt_panel": "aparezco aquí",
        "pn_opt_notif": "una notificación",
        "pn_opt_off": "nada",
        "pn_bye": "Vale, me escondo.",
        "pn_bye2": "Para traerme de vuelta: pestaña Mange-3MF, Ajustes.",
        "when_saved": "guardados el {0:02d}/{1:02d} a las {3:02d}:{4:02d}",
        "cap_saved": "Ajustes guardados.",
        "cap_current": "Ajustes actuales guardados para la conversión.",
        "out_saved": "Carpeta guardada.",
        "err_out_dir": "Carpeta no encontrada: {0}",
        "dest_in": "en {0}",
        "downloads": "Descargas",
        "out_plate1": "{0} - {2} - placa {1}.3mf",
        "out_plateN": "{0} - {2} - placas {1}.3mf",
        "unknown_app": "programa desconocido",
        "another_slicer": "otro programa",
        "unknown": "desconocido",
        "unnamed": "sin nombre",
        "mix": "mezcla {0}+{1}",
        "p_analysing": "Analizando {0}…",
        "p_converting": "Convirtiendo…",
        "p_file": "Archivo {0} de {1}…",
        "need_u1": "Necesito tus ajustes de la U1: elige tu Snapmaker U1 y tus perfiles en Orca (o abre uno "
                   "de tus proyectos U1) y haz clic en “Guardar los ajustes actuales de Orca”.",
        "w_cfg_unreadable": "Los ajustes del proyecto original son ilegibles: se ignoran.",
        "w_obj_unreadable": "Los ajustes de los objetos son ilegibles: se ignoran los colores de los objetos.",
        "w_mixed_orca": "El proyecto usa colores mezclados (filamentos mezclados de Orca): cada uno pasa a "
                        "ser un color sólido con su propio filamento.",
        "w_mixed_fs": "El proyecto usa colores mezclados (Snapmaker Orca Full Spectrum): cada uno pasa a ser "
                      "un color sólido con su propio filamento.",
        "w_paint": "Parte de la pintura es ilegible: se conserva tal cual.",
        "w_paint_max": "Más de {0} colores: Orca solo puede pintar con los {0} primeros filamentos.",
        "w_plate": "Placa {0} “{1}”: {2}.",
        "w_too_big": "demasiado grande para la cama de la U1 ({0:.0f} x {1:.0f} mm)",
        "w_material": "Filamento {0} ({1}): el modelo pide {2}, el perfil elegido “{3}” es {4}. Cámbialo en "
                      "Orca si hace falta.",
        "err_not_3mf": "este archivo no es un 3MF (archivo comprimido ilegible)",
        "err_no_model": "este 3MF no contiene ningún modelo 3D",
        "err_ref_unreadable": "proyecto de referencia ilegible ({0})",
        "err_ref_not_orca": "el proyecto de referencia debe venir de OrcaSlicer (encontrado: {0})",
        "err_sliced": "es un archivo ya laminado (.gcode.3mf): no contiene el modelo. Descarga el proyecto "
                      "3MF original.",
        "err_no_part": "ninguna pieza en este 3MF",
        "err_profile": "perfil {0} desconocido: vuelve a analizar el archivo",
        "err_no_slot": "el filamento {0} no tiene ranura: vuelve a analizar el archivo",
        "err_too_many_extra": "demasiados colores extra: {0} filamentos como máximo por archivo",
        "err_gone": "ya no hay ningún 3MF abierto: vuelve a abrirlo en Orca o suéltamelo encima",
        "err_panel": "este OrcaSlicer no puede mostrar el panel (hace falta la versión 2.5.1 o posterior)",
        "err_plates_missing": "placa(s) {0} fuera del plan",
        "err_not_found": "archivo no encontrado: {0}",
        "err_lost": "análisis perdido: vuelve a analizar el archivo",
        "err_not_u1": "el proyecto abierto no está preparado para una Snapmaker U1",
        "err_nothing": "nada que escribir: vuelve a lanzar la conversión",
        "err_denied": "Acceso denegado por Orca: {0}",
        "err_generic": "Error: {0}",
        "err_in_file": "{0}: {1}",
        "err_analyse": "No se pudo analizar {0}: {1}",
        "err_convert": "La conversión falló: {0}",
        "err_storage": "carpeta de datos del plugin no disponible",
        "n_foreign": "“{0}” viene de {1}{2}: colores y ajustes no adaptados a tu U1.",
        "n_link": "Preparar la conversión en la pestaña Mange-3MF",
        "n_ready": "La conversión de “{0}” está lista: abre la pestaña Mange-3MF.",
        "n_error": "Mange-3MF: {0}",
        "col_black": "negro",
        "col_white": "blanco",
        "col_lightgrey": "gris claro",
        "col_grey": "gris",
        "col_darkgrey": "gris oscuro",
        "col_brown": "marrón",
        "col_beige": "beige",
        "col_red": "rojo",
        "col_orange": "naranja",
        "col_yellow": "amarillo",
        "col_green": "verde",
        "col_turquoise": "turquesa",
        "col_blue": "azul",
        "col_purple": "morado",
        "col_pink": "rosa",
        "col_lightpink": "rosa claro",
        "grp_system": "Preajustes del sistema",
        "w_system": "Ninguno de tus perfiles es {0}: propongo “{1}”, un perfil de Orca para tu U1. Revísalo "
                    "antes de imprimir.",
        "w_no_profile": "No hay ningún perfil {0} para tu U1, ni tuyo ni en Orca: elige uno parecido y "
                        "revisa las temperaturas.",
        "err_system_gone": "perfil de Orca “{0}” no encontrado: vuelve a analizar el archivo",
        "mem_used": "tu elección de la última vez",
        "mem_text": "Cuando cambias el perfil de un color, se vuelve a usar la próxima vez para el mismo "
                    "color y el mismo material.",
        "mem_count": "Colores recordados: {0}.",
        "mem_forget": "Olvidar mis perfiles elegidos",
        "mem_forgot": "Olvidado.",
        "sup_keep": "Conservar los soportes del autor",
        "sup_hint": "Si no, los soportes de tus ajustes.",
        "sup_tree": "soportes en árbol",
        "sup_normal": "soportes normales",
        "sup_objects": "soportes en algunos objetos",
        "sup_fil": "soporte en {1} {0}",
        "sup_iface": "interfaz en {1} {0}",
        "err_prusa_sla": "proyecto de PrusaSlicer para una impresora de resina (SLA): nada que convertir para la U1",
        "w_prusa_keys": "Ajustes por objeto de PrusaSlicer no conservados: {0}.",
    },
    "it": {
        "lang_name": "Italiano",
        "lang_auto": "Auto (lingua di Orca)",
        "lang_title": "Lingua della scheda",
        "sub": "qualsiasi 3MF → la tua Snapmaker U1",
        "lead": "MakerWorld / Bambu Studio, Printables / PrusaSlicer, Snapmaker Orca, altre varianti di "
                "Orca: esattamente i colori del modello (un filamento per colore), la pittura e i piatti, "
                "con le <b>tue</b> impostazioni.",
        "h_analysis": "Analisi",
        "h_result": "File pronti",
        "h_tpl": "Le tue impostazioni per la conversione",
        "h_src": "Il 3MF da mangiare",
        "capture": "Salva le impostazioni attuali di Orca",
        "recent_title": "Ultimi 3MF nei tuoi Download",
        "refresh": "Aggiorna",
        "searching": "Ricerca…",
        "path_ph": "Oppure incolla il percorso di un 3MF (clic destro sul file › Copia come percorso)",
        "analyse": "Analizza",
        "browse": "Sfoglia…",
        "drop_hint": "Lascia cadere un 3MF sulla U1: ha fame.",
        "drop": "Gnam! Lascialo…",
        "u1_click": "o cliccala per scegliere un file",
        "u1_title": "Lascia qui un 3MF o clicca per sceglierne uno",
        "u1_chomp": "Crunch!",
        "u1_chew": "Mastico…",
        "u1_burp": "Burp! {0}",
        "u1_spit": "Bleah! Questo non è un 3MF.",
        "u1_sick": "Bleah! Questo non va giù.",
        "tpl_saved": "Impostazioni salvate",
        "tpl_current": "Impostazioni attuali di Orca",
        "badge_not_u1": "non è una U1",
        "badge_foreign": "dal progetto aperto",
        "tpl_hint": "Scegli in Orca le tue impostazioni abituali (U1, ugelli, processo, piatto, filamenti), "
                    "poi clicca “Salva”: verranno usate per ogni conversione.",
        "nozzles": "ugelli",
        "except": "tranne",
        "hf": "High flow",
        "std": "Standard",
        "bed_tpei": "piatto PEI testurizzato",
        "bed_cool": "piatto Cool",
        "bed_eng": "piatto Engineering",
        "bed_hot": "piatto alta temperatura",
        "bed_tack": "piatto SuperTack",
        "bed_tcool": "piatto Cool testurizzato",
        "badge_unreadable": "illeggibile",
        "badge_sliced": "già slicato",
        "badge_todo": "da convertire",
        "badge_ok": "già per la U1",
        "color1": "colore",
        "colorN": "colori",
        "mb": "MB",
        "kb": "KB",
        "ago_now": "proprio ora",
        "ago_min": "{0} min fa",
        "ago_h": "{0} h fa",
        "ago_d": "{0} g fa",
        "opened_in_orca": "aperto in Orca",
        "no_3mf": "Nessun 3MF in {0}.",
        "analysing": "Analisi in corso…",
        "by": "di",
        "nozzle": "ugello",
        "bed": "piano",
        "plate1": "piatto",
        "plateN": "piatti",
        "one_per_plate": "Un file per piatto",
        "file_n": "File {0}: ",
        "n_filaments": "{0} filamenti",
        "th_color": "Colore del modello",
        "th_profile": "Profilo filamento",
        "pad_name": "slot libero",
        "pad_sub": "nessun colore del modello",
        "extra_name": "colore extra",
        "extra_sub": "non usato dal modello",
        "extras_note": "I colori extra non sono usati da nessuna parte: saranno nel progetto, pronti per "
                       "dipingere o ricolorare una parte in Orca.",
        "add_color": "+ Aggiungi un colore",
        "remove_color": "Rimuovi questo colore",
        "max_colors": "{0} filamenti al massimo",
        "color_reset_prof": "torna al colore del profilo",
        "warn_material": "il modello vuole {0}, questo profilo è {1}",
        "mixed": "colore misto",
        "same_n": "{0} filamenti identici",
        "pads_one": "Orca tiene almeno uno slot per testina della U1: lo slot {0} non è usato dal modello, "
                    "colore e profilo sono a tua scelta.",
        "pads_many": "Orca tiene almeno uno slot per testina della U1: gli slot {0} e {1} non sono usati dal "
                     "modello, colori e profili sono a tua scelta.",
        "to_know": "Buono a sapersi",
        "convert": "Converti",
        "convert_n": "Converti in {0} file",
        "created_1": "Il file viene creato {0}. Un filamento per colore del modello, con il profilo scelto.",
        "created_n": "I file vengono creati {0}. Un filamento per colore del modello, con il profilo scelto.",
        "converting": "Conversione…",
        "copy_path": "Copia percorso",
        "copied": "Copiato ✓",
        "open_hint": "In Orca: <b>File › Apri progetto</b> (Ctrl+O), incolla il percorso e conferma. Le tue "
                     "impostazioni e i colori sono già dentro.",
        "not_3mf": "Questo non è un file 3MF: {0}",
        "too_big": "File troppo grande per essere letto qui ({0}): mettilo in Download o incolla il suo percorso.",
        "reading": "Lettura di {0} ({1}/{2})…",
        "err_upload": "Il file non è arrivato per intero: lascialo cadere di nuovo.",
        "grp_slots": "Nelle tue impostazioni",
        "grp_user": "I tuoi preset",
        "grp_other": "Per un'altra stampante",
        "pick_color": "Cambia il colore di questo filamento",
        "color_changed": "colore cambiato",
        "color_reset": "torna al colore del modello",
        "out_title": "File convertiti:",
        "out_beside": "accanto al 3MF originale",
        "out_downloads": "in Download",
        "out_folder": "in questa cartella",
        "out_ph": "Percorso della cartella (clic destro sulla cartella › Copia come percorso)",
        "out_ok": "OK",
        "support": "Ti piace il plugin? Offri un caffè a Dragg ☕",
        "copy_link": "Copia link",
        "home_sub": "Lascia cadere un file sulla U1 o scegline uno dai tuoi Download.",
        "say_idle": "Ho fame.",
        "say_idle2": "Lasciami cadere addosso un 3MF o clicca per sceglierne uno.",
        "busy2": "Qualche secondo per assaggiare tutto.",
        "say_done": "Era delizioso!",
        "say_done2": "Un altro 3MF? Lasciamelo cadere addosso.",
        "mini2": "Ecco cosa ho trovato nel modello.",
        "recent_sub": "Prima i più recenti.",
        "edit": "Cambia",
        "settings": "Impostazioni",
        "rig_used": "Finiscono in ogni progetto convertito.",
        "rig_sub": "Una colonna per testina: il suo filamento e il suo ugello.",
        "filament_n": "filamento {0}",
        "filament_more": "filamenti da {0} a {1}",
        "via_ace": "via multiACE",
        "k_printer": "Stampante",
        "k_process": "Processo",
        "h_plates": "Piatti",
        "h_before": "Prima di convertire",
        "h_map": "Colori e filamenti",
        "map_sub": "Ogni colore del modello diventa un filamento e mantiene il suo colore, qualunque sia il "
                   "profilo. Uno stesso profilo può servire per più colori. Clicca su un campione per "
                   "cambiare il colore.",
        "map_busy": "La U1 sta leggendo i piatti, i colori e la pittura.",
        "th_plates": "Piatti",
        "need_ace": "{0} filamenti per 4 testine: oltre 4, la tua U1 ha bisogno di multiACE.",
        "need_ace2": "Niente multiACE? Spunta “Un file per piatto”: ogni file ha solo i colori del suo piatto.",
        "all_good": "Niente di particolare: tutto è pronto per la conversione.",
        "one_per_hint": "{0} file, uno per piatto",
        "res_title": "Il tuo progetto è pronto",
        "res_title_n": "I tuoi {0} progetti sono pronti",
        "res_sub": "Le tue impostazioni e i colori sono dentro.",
        "h_open": "Aprilo in Orca: 3 passi",
        "open_sub": "Orca non permette a un plugin di aprire un progetto da solo.",
        "step_copy": "Copia il percorso del progetto",
        "step_open": "In Orca: File › Apri progetto",
        "step_paste": "Incolla il percorso e conferma",
        "key_enter": "Invio",
        "orig_kept": "Il tuo file originale non viene modificato.",
        "back": "Torna ai colori",
        "again": "Converti un altro 3MF",
        "cancel": "Annulla",
        "dlg_sub": "Queste impostazioni finiscono in ogni progetto convertito: stampante, ugelli, processo, "
                   "piatto e filamenti.",
        "saved_desc": "Restano uguali finché non le sostituisci.",
        "current_desc": "Quelle mostrate ora in Orca: cambiano con Orca.",
        "out_h": "File convertiti",
        "dlg_foot": "Le tue scelte restano salvate per la prossima volta.",
        "close": "Chiudi",
        "pn_rest2": "Lasciami cadere addosso un 3MF o aprilo in Orca: ti dirò se va convertito.",
        "pn_rest2b": "Lasciami cadere addosso un 3MF: lo preparo per la tua U1.",
        "pn_zone": "Lascia qui un 3MF",
        "pn_drag": "Lascialo!",
        "pn_drag2": "Lo prendo qui, senza la scheda.",
        "pn_zone_drag": "Molla il tuo 3MF",
        "pn_offer": "Gnam!",
        "pn_offer2": "Questo 3MF non è impostato per la tua U1.",
        "pn_eat": "Mangialo",
        "pn_later": "Non ora",
        "pn_offer_hint": "Puoi cambiare i profili e aggiungere colori prima di convertire.",
        "pn_chew": "Mastico…",
        "pn_an_hint": "Clicca su un punto per cambiare il colore. Tutto si può impostare anche nella scheda Mange-3MF.",
        "pn_pads_edit": "Scegli il filamento per questi slot",
        "pn_pads": "slot liberi",
        "pn_keep_1": "la tua bobina",
        "pn_keep_n": "le tue bobine",
        "pn_conv": "Preparo il tuo progetto…",
        "pn_done": "È pronto!",
        "pn_done_hint": "Poi {0} (Ctrl+O), incolla il percorso e conferma.",
        "pn_menu": "File › Apri progetto",
        "pn_err": "Bleah!",
        "pn_ok": "OK",
        "pn_h": "Quando Orca apre un 3MF non impostato per la tua U1",
        "pn_mode_panel": "la U1 appare accanto al piatto (Prepara e Anteprima)",
        "pn_mode_notif": "solo una notifica",
        "pn_mode_off": "niente",
        "pn_show": "Metti la U1 in Prepara",
        "pn_shown": "Ti aspetta in Prepara e Anteprima.",
        "pn_mode_label": "Quando un 3MF non è impostato:",
        "pn_opt_panel": "appaio qui",
        "pn_opt_notif": "una notifica",
        "pn_opt_off": "niente",
        "pn_bye": "Ok, mi nascondo.",
        "pn_bye2": "Per riportarmi: scheda Mange-3MF, Impostazioni.",
        "when_saved": "salvate il {0:02d}/{1:02d} alle {3:02d}:{4:02d}",
        "cap_saved": "Impostazioni salvate.",
        "cap_current": "Impostazioni attuali salvate per la conversione.",
        "out_saved": "Cartella salvata.",
        "err_out_dir": "Cartella non trovata: {0}",
        "dest_in": "in {0}",
        "downloads": "Download",
        "out_plate1": "{0} - {2} - piatto {1}.3mf",
        "out_plateN": "{0} - {2} - piatti {1}.3mf",
        "unknown_app": "programma sconosciuto",
        "another_slicer": "un altro programma",
        "unknown": "sconosciuto",
        "unnamed": "senza nome",
        "mix": "miscela {0}+{1}",
        "p_analysing": "Analisi di {0}…",
        "p_converting": "Conversione…",
        "p_file": "File {0} di {1}…",
        "need_u1": "Mi servono le tue impostazioni U1: scegli la tua Snapmaker U1 e i tuoi profili in Orca "
                   "(o apri uno dei tuoi progetti U1), poi clicca “Salva le impostazioni attuali di Orca”.",
        "w_cfg_unreadable": "Le impostazioni del progetto originale sono illeggibili: vengono ignorate.",
        "w_obj_unreadable": "Le impostazioni degli oggetti sono illeggibili: i colori degli oggetti vengono ignorati.",
        "w_mixed_orca": "Il progetto usa colori misti (filamenti misti di Orca): ognuno diventa un colore "
                        "pieno con il suo filamento.",
        "w_mixed_fs": "Il progetto usa colori misti (Snapmaker Orca Full Spectrum): ognuno diventa un colore "
                      "pieno con il suo filamento.",
        "w_paint": "Parte della pittura è illeggibile: resta così com'è.",
        "w_paint_max": "Più di {0} colori: Orca può dipingere solo con i primi {0} filamenti.",
        "w_plate": "Piatto {0} “{1}”: {2}.",
        "w_too_big": "troppo grande per il piano della U1 ({0:.0f} x {1:.0f} mm)",
        "w_material": "Filamento {0} ({1}): il modello vuole {2}, il profilo scelto “{3}” è {4}. Cambialo in "
                      "Orca se serve.",
        "err_not_3mf": "questo file non è un 3MF (archivio illeggibile)",
        "err_no_model": "questo 3MF non contiene alcun modello 3D",
        "err_ref_unreadable": "progetto di riferimento illeggibile ({0})",
        "err_ref_not_orca": "il progetto di riferimento deve venire da OrcaSlicer (trovato: {0})",
        "err_sliced": "è un file già slicato (.gcode.3mf): non contiene il modello. Scarica il progetto 3MF originale.",
        "err_no_part": "nessuna parte in questo 3MF",
        "err_profile": "profilo {0} sconosciuto: analizza di nuovo il file",
        "err_no_slot": "il filamento {0} non ha uno slot: analizza di nuovo il file",
        "err_too_many_extra": "troppi colori extra: {0} filamenti al massimo per file",
        "err_gone": "nessun 3MF più aperto: riaprilo in Orca o lasciamelo cadere addosso",
        "err_panel": "questo OrcaSlicer non può mostrare il pannello (serve la versione 2.5.1 o successiva)",
        "err_plates_missing": "piatto/i {0} esclusi dal piano",
        "err_not_found": "file non trovato: {0}",
        "err_lost": "analisi persa: analizza di nuovo il file",
        "err_not_u1": "il progetto aperto non è impostato per una Snapmaker U1",
        "err_nothing": "niente da scrivere: rilancia la conversione",
        "err_denied": "Accesso negato da Orca: {0}",
        "err_generic": "Errore: {0}",
        "err_in_file": "{0}: {1}",
        "err_analyse": "Impossibile analizzare {0}: {1}",
        "err_convert": "Conversione non riuscita: {0}",
        "err_storage": "cartella dati del plugin non disponibile",
        "n_foreign": "“{0}” viene da {1}{2}: colori e impostazioni non adatti alla tua U1.",
        "n_link": "Prepara la conversione nella scheda Mange-3MF",
        "n_ready": "La conversione di “{0}” è pronta: apri la scheda Mange-3MF.",
        "n_error": "Mange-3MF: {0}",
        "col_black": "nero",
        "col_white": "bianco",
        "col_lightgrey": "grigio chiaro",
        "col_grey": "grigio",
        "col_darkgrey": "grigio scuro",
        "col_brown": "marrone",
        "col_beige": "beige",
        "col_red": "rosso",
        "col_orange": "arancione",
        "col_yellow": "giallo",
        "col_green": "verde",
        "col_turquoise": "turchese",
        "col_blue": "blu",
        "col_purple": "viola",
        "col_pink": "rosa",
        "col_lightpink": "rosa chiaro",
        "grp_system": "Preset di sistema",
        "w_system": "Nessuno dei tuoi profili è {0}: propongo “{1}”, un profilo di Orca per la tua U1. "
                    "Controllalo prima di stampare.",
        "w_no_profile": "Nessun profilo {0} per la tua U1, né tuo né in Orca: scegline uno simile e "
                        "controlla le temperature.",
        "err_system_gone": "profilo di Orca “{0}” non trovato: analizza di nuovo il file",
        "mem_used": "la tua scelta dell'ultima volta",
        "mem_text": "Quando cambi il profilo di un colore, viene ripreso la volta successiva per lo stesso "
                    "colore e lo stesso materiale.",
        "mem_count": "Colori ricordati: {0}.",
        "mem_forget": "Dimentica i profili scelti",
        "mem_forgot": "Dimenticato.",
        "sup_keep": "Mantieni i supporti dell'autore",
        "sup_hint": "Altrimenti, i supporti delle tue impostazioni.",
        "sup_tree": "supporti ad albero",
        "sup_normal": "supporti normali",
        "sup_objects": "supporti su alcuni oggetti",
        "sup_fil": "supporto in {1} {0}",
        "sup_iface": "interfaccia in {1} {0}",
        "err_prusa_sla": "progetto PrusaSlicer per una stampante a resina (SLA): niente da convertire per la U1",
        "w_prusa_keys": "Impostazioni per oggetto di PrusaSlicer non riprese: {0}.",
    },
}
DEFAULT_LANG = "en"
_LANG_WORDS = {"french": "fr", "english": "en", "german": "de", "deutsch": "de", "spanish": "es",
               "italian": "it", "italiano": "it"}  # noms de langue de Windows (« French_France »)
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


def human_size(n):
    """Taille lisible pour les messages (même forme que la page : « 112.3 Mo »)."""
    if n >= 1048576:
        return "%.1f %s" % (n / 1048576.0, tr("mb"))
    return "%d %s" % (max(1, round(n / 1024.0)), tr("kb"))


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


def paint_leaf(state):
    """Chaine paint_color d'un triangle peint tout entier avec le filament state (0 = celui de la piece)."""
    if state < 3:
        return _HEXC[state << 2]
    if state <= 17:
        return _HEXC[state - 3] + "C"
    return _HEXC[state - 18] + "FC"


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
        self.origin = None          # "prusa" ou "plain" : projet relu comme un projet Orca (voir plus bas)
        self.keep_supports = False  # garder les supports de l'auteur (ses filaments comptent alors)
        pre = []
        if PRUSA_CFG in self.nameset:
            data, pre = prusa_to_orca(self.zip, self.names)
            self._reopen(data, "prusa")
        elif PROJECT_CFG not in self.nameset:
            data = plain_colors_to_orca(self.zip, self.names)
            if data is not None:
                self._reopen(data, "plain")
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
        self.warnings.extend(pre)
        self._parse()

    def _reopen(self, data, origin):
        """Projet d'un autre format reecrit en memoire comme un projet Orca : on lit celui-la."""
        self.zip = zipfile.ZipFile(io.BytesIO(data))
        self.data = data
        self.names = [i.filename for i in self.zip.infolist() if not i.filename.endswith("/")]
        self.nameset = set(self.names)
        self.origin = origin

    def set_supports(self, keep):
        """Garder les supports de l'auteur : ses filaments de support et d'interface comptent alors comme
        utilises sur chaque plaque (ils sont dans le projet converti)."""
        keep = bool(keep) and author_supports(self) is not None
        if keep != self.keep_supports:
            self.keep_supports = keep
            self._compute_usage()

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
        if self.origin:
            return self.origin
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
            if self.keep_supports and p.instances:
                sup = author_supports(self) or {}
                for f in (sup.get("filament", 0), sup.get("interface", 0)):
                    if f >= 1:
                        weights[f] = weights.get(f, 0.0) + 0.2
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
        self.user = False           # prereglage de l'utilisateur (pas un prereglage systeme)
        self.system = False         # prereglage systeme d'Orca (propose pour une matiere qui te manque)
        self.light = False          # lu en bref (nom, matiere, couleur) : relu en entier s'il sert
        self.visible = True         # montre dans les listes d'Orca
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

    @classmethod
    def light_read(cls, preset):
        """Prereglage systeme lu en bref : nom, matiere, couleur, marque. Relu en entier a la conversion s'il
        sert."""
        raw = {}
        for key in ("filament_type", "default_filament_colour", "filament_vendor"):
            try:
                value = preset.config_value(key)
            except Exception:
                value = None
            if value is not None:
                raw[key] = str(value)
        fp = cls(preset.name, raw)
        fp.system = fp.light = True
        fp.visible = bool(getattr(preset, "is_visible", True))
        return fp

    @property
    def vendor(self):
        """Marque du filament (Generic, Polymaker...), pour ranger les prereglages systeme comme Orca."""
        v = self.values("filament_vendor", True)
        return (v[0] if v else "").strip()

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
                out["slots"][s].user = bool(p.is_user())
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
    out["system"] = _system_presets(coll, template, same_printer)
    return out


_NOZZLE_IN_NAME = re.compile(r"(\d+(?:\.\d+)?)\s*nozzle", re.I)


def _printer_names(template):
    """Imprimante des reglages et son profil systeme (pour reconnaitre les prereglages qui vont avec)."""
    cfg = template.config
    names = {_cfg_str(cfg, "printer_settings_id")}
    inh = _cfg_list(cfg, "inherits_group")
    if inh:
        names.add(inh[-1])
    return {strip_project_suffix(n) for n in names if n}


def _system_presets(coll, template, same_printer):
    """Prereglages systeme d'Orca pour l'imprimante des reglages, lus en bref. Ils ne sont proposes que
    pour une matiere du modele qu'aucun de tes profils n'a (PETG, TPU...)."""
    out = []
    printers = _printer_names(template)
    try:
        nozzle = float((_cfg_list(template.config, "nozzle_diameter") or ["0"])[0])
        count = coll.size()
    except Exception:
        return out
    for i in range(count):
        try:
            p = coll.preset(i)
            if not getattr(p, "is_system", False) or p.is_default or p.is_project_embedded:
                continue
            if same_printer:
                if not p.is_compatible:
                    continue
            else:
                listed = split_serialized(p.config_value("compatible_printers") or "", True)
                if listed:
                    if not printers & set(listed):
                        continue
                elif (p.config_value("compatible_printers_condition") or "").strip() in ("", '""'):
                    pass                    # pour toutes les imprimantes (bibliotheque de filaments d'Orca)
                else:
                    m = _NOZZLE_IN_NAME.search(p.name)
                    if "@U1" not in p.name or (m and nozzle and abs(float(m.group(1)) - nozzle) > 1e-6):
                        continue
            out.append(FilamentPreset.light_read(p))
        except Exception as e:
            log_error("prereglage systeme %d : %s" % (i, e))
    return out


def hydrate_presets(template, files):
    """Prereglages systeme d'Orca choisis dans un plan : lus en entier (fil de l'interface)."""
    k = template.slot_count
    used = {_int(s.get("base"), -1) for f in files or [] for s in f.get("slots") or []}
    coll = None
    for j, p in enumerate(template.presets):
        if not p.light or (k + j) not in used:
            continue
        if coll is None:
            coll = orca.host.preset_bundle().filaments
        q = coll.find_preset(p.name)
        if q is None:
            raise ConvertError(tr("err_system_gone", p.name))
        full = FilamentPreset.read(q)
        full.system = True
        template.presets[j] = full


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
        self.system = []            # prereglages systeme d'Orca pour cette imprimante (lus en bref)
        self.missing = set()        # matieres du modele qu'aucun de tes profils n'a
        self.system_rank = {}       # prereglage systeme -> rang parmi ceux proposes pour une matiere manquante

    def attach(self, presets):
        """Prereglages lus dans Orca (read_filament_presets)."""
        presets = presets or {}
        self.presets = list(presets.get("user") or [])
        self.slot_presets = dict(presets.get("slots") or {})
        self.system = list(presets.get("system") or [])
        return self

    def add_system(self, missing, per_type=6):
        """Ajoute a la liste, apres tes profils, les prereglages systeme d'Orca : ceux qu'Orca montre pour ton
        imprimante (coches dans sa fenetre de choix des filaments), ranges par marque, et, pour une matiere du
        modele qu'aucun de tes profils n'a (missing), les meilleurs meme caches. Seuls ces derniers peuvent
        etre choisis d'office. Retourne ceux proposes pour les matieres manquantes, le meilleur d'abord."""
        have = {p.name for p in self.presets} | {self.profile(i)[0] for i in range(self.slot_count)}
        self.missing = {m for m in missing if m and m != "?"}
        picked = []
        for want in sorted(self.missing):
            cands = [p for p in self.system if base_type(p.type) == want and p.name not in have]
            cands.sort(key=lambda p: ((p.type or "").strip().upper() != want, not p.visible, "@u1" not in p.name.lower(),
                                      "generic" not in p.name.lower(), len(p.name), p.name.lower()))
            picked += cands[:per_type]
        self.system_rank = {p.name: i for i, p in enumerate(picked)}
        shown, seen = [], set()
        for p in [p for p in self.system if p.visible] + picked:
            if p.name not in have and p.name not in seen:
                seen.add(p.name)
                shown.append(p)
        shown.sort(key=lambda p: (p.vendor.lower() != "generic", p.vendor.lower() or "~", p.name.lower()))
        if shown:
            self.presets = list(self.presets) + shown
        return picked

    def profile_index(self, name, want=None):
        """Numero dans la liste proposee du profil nomme name (une case de tes reglages d'abord), de la
        matiere want si elle est donnee ; None s'il n'y est plus."""
        if not name:
            return None

        def fits(t):
            return want in (None, "?") or base_type(t) in (want, "?")
        for i in range(self.slot_count):
            if self.profile(i)[0] == name and fits(self.slot_types[i]):
                return i
        for j, p in enumerate(self.presets):
            if p.name == name and fits(p.type):
                return self.slot_count + j
        return None

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
            out.append({"n": i + 1, "color": c, "fill": c, "cname": color_name(c), "type": t or "?", "base": base_type(t),
                        "name": self.profile(i)[0], "group": "slot",
                        "user": bool(getattr(self.slot_presets.get(i), "user", False))})
        for p in self.presets:
            c = p.color
            out.append({"n": None, "color": c, "fill": c or self.slot_colors[self.closest_slot(p)],
                        "cname": color_name(c) if c else "", "type": p.type or "?",
                        "base": base_type(p.type), "name": p.name,
                        "group": "other" if p.other else ("system" if p.system else "user"),
                        "vendor": p.vendor if p.system else ""})
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
            "slots": [{"color": c, "cname": color_name(c) if c else "", "type": t, "name": strip_project_suffix(n)}
                      for c, t, n in zip(self.slot_colors, self.slot_types[:self.slot_count], self.slot_names[:self.slot_count])],
            "captured_at": self.captured_at,
            "app": self.application,
        }



# --------------------------------------------------------------------------- projets PrusaSlicer (Printables)
# Un projet PrusaSlicer est relu en memoire comme un projet Orca : chaque objet devient des
# sous-objets (un par volume, dans 3D/Objects/), ses reglages par objet et par volume vont dans
# model_settings.config, les couleurs des extrudeurs dans project_settings.config, la peinture
# (slic3rpe:mmu_segmentation, meme codage) devient paint_color. Ensuite, meme chemin que les autres.

_PRUSA_VOLUME_TYPES = {"ModelPart": "normal_part", "ParameterModifier": "modifier_part",
                       "NegativeVolume": "negative_part", "SupportBlocker": "support_blocker",
                       "SupportEnforcer": "support_enforcer"}
# reglages par objet ou par volume de PrusaSlicer repris (nom dans Orca) ; les anciens noms de
# filament par fonction (perimeter_extruder...) sont gardes, la conversion les renomme
_PRUSA_KEYS = {"layer_height": "layer_height", "perimeters": "wall_loops", "top_solid_layers": "top_shell_layers",
               "bottom_solid_layers": "bottom_shell_layers", "fill_density": "sparse_infill_density",
               "support_material": "enable_support", "brim_width": "brim_width",
               "wipe_into_infill": "flush_into_infill", "wipe_into_objects": "flush_into_objects"}
# types de code par hauteur : PrusaSlicer (0 couleur, 1 pause, 2 perso, 3 modele, 4 outil) -> Orca
_PRUSA_GCODE_TYPES = {0: 0, 1: 1, 2: 4, 3: 3, 4: 2}
_MODEL_HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
               'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
               'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
               'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">\n')
_RELS_3DMODEL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
_IDENTITY_3MF = "1 0 0 0 1 0 0 0 1 0 0 0"
_IDENTITY_MATRIX = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"


def parse_prusa_config(text):
    """Metadata/Slic3r_PE.config (lignes « ; cle = valeur ») -> {cle: valeur ecrite}."""
    cfg = {}
    for line in text.splitlines():
        m = re.match(r";\s*([A-Za-z0-9_]+)\s*=\s?(.*)$", line)
        if m:
            cfg[m.group(1)] = m.group(2).rstrip("\r")
    return cfg


def prusa_list(value):
    """Valeur de liste de PrusaSlicer -> textes : « a;b », « "a b";c » ou « 0.4,0.4 »."""
    v = (value or "").strip()
    if not v:
        return []
    if ";" not in v and '"' not in v:
        return [x.strip() for x in v.split(",")]
    out, cur, quoted, i = [], [], False, 0
    while i < len(v):
        c = v[i]
        if quoted:
            if c == "\\" and i + 1 < len(v):
                cur.append(v[i + 1])
                i += 2
                continue
            if c == '"':
                quoted = False
            else:
                cur.append(c)
        elif c == '"':
            quoted = True
        elif c == ";":
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append("".join(cur).strip())
    return out


def prusa_colours(pcfg):
    """Couleur de chaque extrudeur telle que PrusaSlicer la montre : celle de l'extrudeur si elle est
    donnee, sinon celle du filament."""
    ecol, fcol = prusa_list(pcfg.get("extruder_colour")), prusa_list(pcfg.get("filament_colour"))
    n = max(len(ecol), len(fcol), len(prusa_list(pcfg.get("nozzle_diameter"))), 1)
    out = []
    for i in range(n):
        c = norm_color(ecol[i]) if i < len(ecol) else None
        out.append(c or (norm_color(fcol[i]) if i < len(fcol) else None) or "#808080")
    return out


def _prusa_project_config(pcfg):
    """Reglages du projet PrusaSlicer, avec les noms d'Orca, pour l'analyse (couleurs, matieres,
    plateau, tour d'essuyage, supports de l'auteur)."""
    colours = prusa_colours(pcfg)
    n = len(colours)

    def per_ext(key, default=""):
        vals = prusa_list(pcfg.get(key))
        return [vals[i] if i < len(vals) else (vals[-1] if vals else default) for i in range(n)]
    printer = prusa_list(pcfg.get("printer_settings_id"))
    cfg = {"filament_colour": colours, "filament_type": per_ext("filament_type", "PLA"),
           "filament_settings_id": per_ext("filament_settings_id"), "filament_vendor": per_ext("filament_vendor"),
           "nozzle_diameter": per_ext("nozzle_diameter", "0.4"),
           "printable_area": prusa_list(pcfg.get("bed_shape")) or ["0x0", "250x0", "250x210", "0x210"],
           "printer_model": pcfg.get("printer_model", ""), "printer_settings_id": printer[0] if printer else "",
           "wipe_tower_x": [pcfg.get("wipe_tower_x") or "170"], "wipe_tower_y": [pcfg.get("wipe_tower_y") or "140"]}
    if "support_material" in pcfg:
        cfg["enable_support"] = "1" if pcfg["support_material"] in ("1", "true") else "0"
        style = pcfg.get("support_material_style", "")
        auto = pcfg.get("support_material_auto", "1") in ("1", "true")
        cfg["support_type"] = ("tree" if style == "organic" else "normal") + ("(auto)" if auto else "(manual)")
        for a, b in (("support_material_extruder", "support_filament"),
                     ("support_material_interface_extruder", "support_interface_filament"),
                     ("support_material_contact_distance", "support_top_z_distance"),
                     ("support_material_interface_layers", "support_interface_top_layers"),
                     ("support_material_buildplate_only", "support_on_build_plate_only"),
                     ("raft_layers", "raft_layers")):
            if pcfg.get(a) not in (None, ""):
                cfg[b] = pcfg[a]
    return cfg


def _compose_tf(c, t):
    """Transformation c (composant) puis t (instance), au format du 3MF (vecteurs lignes)."""
    r = [[sum(c[3 * i + k] * t[3 * k + j] for k in range(3)) for j in range(3)] for i in range(3)]
    tr_ = [sum(c[9 + k] * t[3 * k + j] for k in range(3)) + t[9 + j] for j in range(3)]
    return tuple(r[0] + r[1] + r[2] + tr_)


def _prusa_meta(elem):
    return {md.get("key"): md.get("value", "") for md in elem.findall("metadata") if md.get("key")}


def _settings_elems(parent, meta, dropped, is_object):
    """Metadonnees d'un objet ou d'un volume de PrusaSlicer -> celles d'Orca (model_settings.config)."""
    if meta.get("name"):
        ET.SubElement(parent, "metadata", key="name", value=meta["name"])
    ext = _int(meta.get("extruder"), 0)
    if is_object or ext >= 1:
        ET.SubElement(parent, "metadata", key="extruder", value=str(max(1, ext)))
    for key, value in meta.items():
        if key in ("name", "extruder", "volume_type", "modifier", "matrix") or key.startswith("source_"):
            continue
        if key in FILAMENT_KEYS_LEGACY or key in FILAMENT_KEYS_NEW:
            ET.SubElement(parent, "metadata", key=key, value=value)
        elif key in _PRUSA_KEYS:
            ET.SubElement(parent, "metadata", key=_PRUSA_KEYS[key], value=value)
        else:
            dropped.add(key)


def _split_mesh(block, ranges):
    """Maillage d'un objet PrusaSlicer (tous ses volumes) -> un maillage par volume (first, last : rang
    des triangles), les sommets renumerotes. Retourne les textes <mesh>...</mesh>."""
    v0, v1 = block.find("<vertices"), block.find("</vertices>")
    t0, t1 = block.find("<triangles"), block.find("</triangles>")
    verts = re.findall(r"<vertex\b[^>]*/>", block[v0:v1])
    tris = re.findall(r"<triangle\b[^>]*/>", block[t0:t1])
    out = []
    for first, last in ranges:
        part = tris[first:last + 1]
        idx = [tuple(int(x) for x in re.findall(r'\bv[123]="(\d+)"', t)) for t in part]
        lo = min(min(i) for i in idx) if idx else 0
        hi = max(max(i) for i in idx) if idx else -1
        lines = ['<mesh>\n<vertices>\n', "\n".join(verts[lo:hi + 1]), '\n</vertices>\n<triangles>\n']
        new = []
        for t, (a, b, c) in zip(part, idx):
            rest = re.sub(r'\s*\bv[123]="\d+"', "", t[len("<triangle"):])
            new.append('<triangle v1="%d" v2="%d" v3="%d"%s' % (a - lo, b - lo, c - lo, rest))
        lines += ["\n".join(new), "\n</triangles>\n</mesh>"]
        out.append("".join(lines))
    return out


def _rename_paint(text):
    return (text.replace(" slic3rpe:mmu_segmentation=", " paint_color=")
            .replace(" slic3rpe:custom_supports=", " paint_supports=")
            .replace(" slic3rpe:custom_seam=", " paint_seam="))


def _prusa_gcodes(data):
    """Prusa_Slicer_custom_gcode_per_print_z.xml -> custom_gcode_per_layer.xml d'Orca (plaque 1)."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    out = ET.Element("custom_gcodes_per_layer")
    plate = ET.SubElement(out, "plate")
    ET.SubElement(plate, "plate_info", id="1")
    for code in root.findall("code"):
        gcode = code.get("gcode", "")
        if code.get("type") is not None:
            kind = _PRUSA_GCODE_TYPES.get(_int(code.get("type"), 2), 4)
        else:
            kind = 0 if gcode == "M600" else 1 if gcode == "M601" else 2 if gcode == "tool_change" else 4
        ET.SubElement(plate, "layer", top_z=code.get("print_z", "0"), type=str(kind),
                      extruder=code.get("extruder", "1"), color=code.get("color", ""), extra=code.get("extra", ""),
                      gcode=gcode)
    mode = root.find("mode")
    ET.SubElement(plate, "mode", value=mode.get("value", "MultiAsSingle") if mode is not None else "MultiAsSingle")
    return _xml_bytes(out)


def _prusa_ranges(data):
    """Prusa_Slicer_layer_config_ranges.xml -> layer_config_ranges.xml d'Orca (extrudeur, hauteur)."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    for rng in root.iter("range"):
        for opt in list(rng.findall("option")):
            if opt.get("opt_key") not in ("extruder", "layer_height"):
                rng.remove(opt)
    return _xml_bytes(root)


def prusa_to_orca(zf, names):
    """Projet PrusaSlicer -> le meme projet ecrit comme un projet Orca (octets d'un zip), et les
    alertes. ConvertError s'il n'est pas lisible (ou pour une imprimante resine)."""
    nameset = set(names)
    pcfg = parse_prusa_config(zf.read(PRUSA_CFG).decode("utf-8", "replace"))
    if pcfg.get("printer_technology", "FFF").upper() == "SLA":
        raise ConvertError(tr("err_prusa_sla"))
    main_name = MAIN_MODEL if MAIN_MODEL in nameset else next(
        (n for n in names if n.lower().endswith(".model") and n.lower().startswith("3d/")), None)
    if not main_name:
        raise ConvertError(tr("err_no_model"))
    main = zf.read(main_name).decode("utf-8", "replace")
    pobjs = {}
    if PRUSA_MODEL_CFG in nameset:
        try:
            for oe in ET.fromstring(zf.read(PRUSA_MODEL_CFG)).findall("object"):
                pobjs[oe.get("id")] = oe
        except ET.ParseError:
            pobjs = {}
    warnings, dropped = [], set()
    files, tops, rels = {}, [], []
    mcfg = ET.Element("config")
    res0 = main.find("<resources")
    # objets : ceux qui ont un maillage, et les alias (instances suivantes d'un objet : un composant
    # vers le premier, que PrusaSlicer ecrit pour chaque instance en plus)
    found, alias = [], {}
    rx_obj, pos = re.compile(r"<object\b([^>]*)>"), max(res0, 0)
    while True:
        m = rx_obj.search(main, pos)
        if m is None:
            break
        end = main.find("</object>", m.end())
        if end < 0:
            break
        pos = end + len("</object>")
        a = tag_attrs(m.group(1))
        if a.get("id") is None:
            continue
        if main.find("<mesh", m.end(), end) >= 0:
            found.append((a, m.end(), end))
            continue
        c = re.search(r"<component\b([^>]*)/?>", main[m.end():end])
        if c:
            ca = tag_attrs(c.group(1))
            alias[a["id"]] = (ca.get("objectid"), parse_transform(ca.get("transform")))
    # numeros des sous-objets : uniques dans tout le projet (Orca partage le maillage de deux
    # sous-objets de meme numero)
    next_id = max([_int(a.get("id"), 0) for a, _b, _e in found] + [_int(k, 0) for k in alias] + [0]) + 1
    for a, b0, b1 in found:
        oid = a["id"]
        body = main[b0:b1]
        mb0, mb1 = body.find("<mesh"), body.rfind("</mesh>")
        if mb0 < 0 or mb1 < 0:
            continue
        block = body[mb0:mb1 + len("</mesh>")]
        po = pobjs.get(oid)
        vols = []
        if po is not None:
            for ve in po.findall("volume"):
                vols.append((_int(ve.get("firstid"), 0), _int(ve.get("lastid"), -1), _prusa_meta(ve)))
        vols.sort(key=lambda v: v[0])
        n_tri = block.count("<triangle ")
        if not vols or len(vols) == 1 and vols[0][0] == 0 and vols[0][1] in (-1, n_tri - 1):
            meshes = [block]
            vols = [(0, n_tri - 1, vols[0][2] if vols else {})]
        else:
            meshes = _split_mesh(block, [(v[0], v[1]) for v in vols])
        sub = "3D/Objects/object_%s.model" % oid
        ids = list(range(next_id, next_id + len(meshes)))
        next_id += len(meshes)
        objs_text = [' <object id="%d" type="model">\n%s\n </object>' % (i, mesh) for i, mesh in zip(ids, meshes)]
        files[sub] = (_MODEL_HEAD + ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
                      + _rename_paint("\n".join(objs_text)) + '\n </resources>\n <build/>\n</model>\n').encode("utf-8")
        rels.append(sub)
        comps = "".join('    <component p:path="/%s" objectid="%d" transform="%s"/>\n' % (sub, i, _IDENTITY_3MF)
                        for i in ids)
        tops.append('  <object id="%s" type="model">\n   <components>\n%s   </components>\n  </object>' % (oid, comps))
        oe = ET.SubElement(mcfg, "object", id=oid)
        ometa = _prusa_meta(po) if po is not None else {}
        if not ometa.get("name"):
            ometa["name"] = a.get("name") or "Object %s" % oid
        _settings_elems(oe, ometa, dropped, True)
        for i, (_f, _l, vm) in zip(ids, vols):
            subtype = _PRUSA_VOLUME_TYPES.get(vm.get("volume_type"), "modifier_part" if vm.get("modifier") == "1" else "normal_part")
            pe = ET.SubElement(oe, "part", id=str(i), subtype=subtype)
            _settings_elems(pe, vm, dropped, False)
            ET.SubElement(pe, "metadata", key="matrix", value=_IDENTITY_MATRIX)
    if not tops:
        raise ConvertError(tr("err_no_part"))
    # modele principal : metadonnees de PrusaSlicer (sauf les siennes), objets a composants, construction
    head = main[:res0 if res0 > 0 else 0]
    meta = "".join(" %s\n" % x for x in re.findall(r'<metadata\s+name="[^"]+"[^>]*>.*?</metadata>', head, re.S)
                   if 'name="slic3rpe:' not in x)
    b0, b1 = main.find("<build"), main.find("</build>")
    build = main[b0:b1 + len("</build>")] if b0 >= 0 and b1 > b0 else "<build/>"
    if alias:
        def item(mi):
            ia = tag_attrs(mi.group(1))
            target = alias.get(ia.get("objectid"))
            if target is None:
                return mi.group(0)
            tf = _compose_tf(target[1], parse_transform(ia.get("transform")))
            return '<item objectid="%s" transform="%s" printable="%s"/>' % (
                target[0], format_transform(tf), ia.get("printable", "1"))
        build = re.sub(r"<item\b([^>]*?)/?>(?:\s*</item>)?", item, build)
    files[MAIN_MODEL] = (_MODEL_HEAD + meta + ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
                         + "\n".join(tops) + '\n </resources>\n ' + build + '\n</model>\n').encode("utf-8")
    files[MAIN_RELS] = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                        + "".join(' <Relationship Target="/%s" Id="rel-%d" Type="%s"/>\n' % (r, i + 1, _RELS_3DMODEL)
                                  for i, r in enumerate(rels))
                        + '</Relationships>\n').encode("utf-8")
    files[PROJECT_CFG] = json.dumps(_prusa_project_config(pcfg), indent=1).encode("utf-8")
    files[MODEL_CFG] = _xml_bytes(mcfg)
    if PRUSA_GCODE in nameset:
        g = _prusa_gcodes(zf.read(PRUSA_GCODE))
        if g:
            files[CUSTOM_GCODE] = g
    if PRUSA_RANGES in nameset:
        r = _prusa_ranges(zf.read(PRUSA_RANGES))
        if r:
            files[LAYER_RANGES] = r
    if PRUSA_HEIGHTS in nameset:
        files[LAYER_HEIGHTS] = zf.read(PRUSA_HEIGHTS)
    if dropped:
        warnings.append(tr("w_prusa_keys", ", ".join(sorted(dropped)[:6]) + ("…" if len(dropped) > 6 else "")))
    keep = [n for n in names if n not in files and n != main_name and not n.startswith("Metadata/Slic3r_PE")
            and not n.startswith("Metadata/Prusa_Slicer")]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as out:
        for n in keep:
            out.writestr(n, zf.read(n))
        for n, d in files.items():
            out.writestr(n, d)
    return buf.getvalue(), warnings


# --------------------------------------------------------------------------- 3MF bruts en couleurs (CAO)
# Un 3MF sans reglages (Fusion, Onshape, 3D Builder...) peut avoir des couleurs (extension Materials
# du 3MF : <m:colorgroup>, <basematerials>), par objet (pid / pindex) ou par triangle (pid / p1).
# Chaque couleur devient un filament ; la couleur d'un objet, son filament ; un triangle d'une autre
# couleur, de la peinture.

_RE_GROUP = re.compile(r"<((?:\w+:)?colorgroup|basematerials)\b([^>]*)>(.*?)</\1>", re.S)
_RE_GROUP_ITEM = re.compile(r"<(?:\w+:)?(?:color|base)\b([^>]*)/?>")


def _tri_color(palette, ta, opid, opidx):
    """Couleur d'un triangle : la sienne (pid, p1), sinon celle de son objet (pid, pindex)."""
    pid = ta.get("pid") or opid
    if pid is None:
        return None
    idx = _int(ta["p1"], 0) if "p1" in ta else (0 if ta.get("pid") else opidx)
    return palette.get((pid, idx))


def plain_colors_to_orca(zf, names):
    """3MF sans reglages : octets d'un zip ou ses couleurs sont des filaments (project_settings,
    model_settings, peinture), ou None s'il n'a pas de couleurs."""
    main_name = MAIN_MODEL if MAIN_MODEL in names else next(
        (n for n in names if n.lower().endswith(".model") and n.lower().startswith("3d/")), None)
    if not main_name:
        return None
    try:
        main = zf.read(main_name).decode("utf-8", "replace")
    except KeyError:
        return None
    palette = {}
    for m in _RE_GROUP.finditer(main):
        gid = tag_attrs(m.group(2)).get("id")
        for k, it in enumerate(_RE_GROUP_ITEM.finditer(m.group(3))):
            a = tag_attrs(it.group(1))
            c = norm_color(a.get("color") or a.get("displaycolor") or "")
            if gid is not None and c:
                palette[(gid, k)] = c
    if not palette:
        return None
    order = []                                  # couleurs dans l'ordre ou elles servent

    def num(color):
        if color not in order:
            order.append(color)
        return order.index(color) + 1
    b0 = main.find("<build")
    built = [tag_attrs(x).get("objectid") for x in re.findall(r"<item\b([^>]*?)/?>", main[b0:] if b0 >= 0 else "")]
    rx_obj, rx_tri = re.compile(r"<object\b([^>]*)>"), re.compile(r"<triangle\b([^>]*)/>")
    objects, pieces, pos = {}, [], 0
    while True:
        m = rx_obj.search(main, pos)
        if m is None:
            break
        end = main.find("</object>", m.end())
        if end < 0:
            break
        pos = end + len("</object>")
        a = tag_attrs(m.group(1))
        oid, opid, opidx = a.get("id"), a.get("pid"), _int(a.get("pindex"), 0)
        if oid is None:
            continue

        default = palette.get((opid, opidx)) if opid else None
        body = main[m.end():end]
        t0, t1 = body.find("<triangles"), body.find("</triangles>")
        colors = []
        if t0 >= 0 and t1 > t0:
            colors = [_tri_color(palette, tag_attrs(t.group(1)), opid, opidx) for t in rx_tri.finditer(body, t0, t1)]
        if default is None:
            seen = [c for c in colors if c]
            default = max(set(seen), key=seen.count) if seen else None
        comps = [tag_attrs(c.group(1)) for c in re.finditer(r"<component\b([^>]*)/?>", body)]
        objects[oid] = {"name": a.get("name") or "", "color": default,
                        "comps": [c.get("objectid") for c in comps if not (c.get("p:path") or c.get("path"))]}
        if default is not None and any(c and c != default for c in colors):
            pieces.append((m.end() + t0, m.end() + t1, default, opid, opidx))
    used = [oid for oid in dict.fromkeys(built) if oid in objects]
    for oid in used:                            # numeros des filaments : dans l'ordre des objets
        o = objects[oid]
        for c in [o["color"]] + [objects[x]["color"] for x in o["comps"] if x in objects]:
            if c:
                num(c)
    if not order:
        return None
    # peinture des triangles d'une autre couleur que leur objet (attributs de couleur retires)
    out, last = [], 0
    for t0, t1, default, opid, opidx in pieces:
        ext = num(default)
        seg = main[t0:t1]
        parts, k = [], 0
        for mt in rx_tri.finditer(seg):
            parts.append(seg[k:mt.start()])
            ta = tag_attrs(mt.group(1))
            col = _tri_color(palette, ta, opid, opidx)
            rest = re.sub(r'\s*\b(?:pid|p1|p2|p3)="[^"]*"', "", mt.group(1))
            state = num(col) if col else ext
            parts.append("<triangle%s%s/>" % (rest, ' paint_color="%s"' % paint_leaf(state) if state != ext else ""))
            k = mt.end()
        parts.append(seg[k:])
        out.append(main[last:t0])
        out.append("".join(parts))
        last = t1
    out.append(main[last:])
    new_main = "".join(out)
    mcfg = ET.Element("config")
    for oid in used:
        o = objects[oid]
        oe = ET.SubElement(mcfg, "object", id=oid)
        ET.SubElement(oe, "metadata", key="name", value=o["name"] or "Object %s" % oid)
        first = o["color"] or next((objects[x]["color"] for x in o["comps"] if x in objects and objects[x]["color"]), None)
        ET.SubElement(oe, "metadata", key="extruder", value=str(num(first) if first else 1))
        for x in o["comps"]:
            c = objects.get(x, {}).get("color")
            pe = ET.SubElement(oe, "part", id=x, subtype="normal_part")
            ET.SubElement(pe, "metadata", key="name", value=objects.get(x, {}).get("name") or "Part %s" % x)
            if c:
                ET.SubElement(pe, "metadata", key="extruder", value=str(num(c)))
    cfg = {"filament_colour": list(order), "filament_type": [""] * len(order),
           "filament_settings_id": [""] * len(order)}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for n in names:
            if n != main_name:
                z.writestr(n, zf.read(n))
        z.writestr(main_name, new_main.encode("utf-8"))
        z.writestr(PROJECT_CFG, json.dumps(cfg).encode("utf-8"))
        z.writestr(MODEL_CFG, _xml_bytes(mcfg))
    return buf.getvalue()

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
    # un prereglage systeme d'Orca n'est choisi d'office que pour une matiere qu'aucun de tes profils n'a
    cands += [(k + i, base_type(p.type), p.color) for i, p in enumerate(template.presets)
              if not p.other and (not p.system or base_type(p.type) in template.missing)]
    color = entry["color"] if entry else None

    def cost(c):
        idx, typ, col = c
        mismatch = not (want == "?" or typ in (want, "?"))
        p = template.presets[idx - k] if idx >= k else None
        if p is not None and p.system:          # le meilleur pour la matiere, sa couleur ne compte pas
            return (mismatch, 1000.0, True, 10 ** 6 + template.system_rank.get(p.name, 10 ** 5))
        if color and col:
            d = color_distance(color, col)
        else:
            d = 0.0 if not color else 1000.0
        return (mismatch, d, idx >= k, idx)
    if s < k and not any(not cost(c)[0] for c in cands):
        return s
    return min(cands, key=cost)[0]


def plan_file(src, template, plate_indices, choices=None):
    """Plan d'un fichier converti : une case par couleur utilisee (au moins une par tete). Le profil
    propose d'office (auto) laisse la place a celui que tu avais choisi pour cette couleur (mem)."""
    layout = order_entries(color_entries(src, plate_indices), template)
    k = template.slot_count
    slots = []
    for s, e in enumerate(layout):
        if e is None:
            slots.append({"src": [], "base": s if s < k else 0})
            continue
        auto = default_profile(e, s, template)
        slot = {"src": list(e["src"]), "base": auto, "auto": auto}
        mem = template.profile_index(remembered(choices, e), e["base"]) if choices else None
        if mem is not None:
            slot["base"] = slot["mem"] = mem
        slots.append(slot)
    return {"plates": list(plate_indices), "slots": slots}


def make_plan(src, template, one_per_plate=False, choices=None):
    """Fichiers a produire : un seul avec toutes les plaques, ou un par plaque."""
    plates = [p.index for p in src.plates if p.instances]
    groups = [[i] for i in plates] if one_per_plate else [plates]
    return [plan_file(src, template, g, choices) for g in groups if g]


# --------------------------------------------------------------------------- memoire des choix

CHOICES_MAX = 300           # couleurs retenues au plus (les plus anciennes partent)
CHOICE_NEAR = 6.0           # ecart (Delta E) pour reconnaitre une couleur presque identique


def choice_key(f):
    """Cle de la memoire des choix : matiere et couleur d'un filament du modele (None sans couleur)."""
    if not f or not f.get("color"):
        return None
    return "%s|%s" % (f.get("base") or "?", str(f["color"]).upper())


def remembered(choices, entry):
    """Profil choisi la derniere fois pour cette couleur : meme matiere, couleur identique, sinon tres
    proche. None s'il n'y en a pas."""
    key = choice_key(entry)
    if not key or not choices:
        return None
    hit = choices.get(key)
    if isinstance(hit, dict) and hit.get("name"):
        return hit["name"]
    base, color = key.split("|", 1)
    best = None
    for k, v in choices.items():
        b, _, c = k.partition("|")
        if b != base or not isinstance(v, dict) or not v.get("name") or not norm_color(c):
            continue
        d = color_distance(color, c)
        if d <= CHOICE_NEAR and (best is None or d < best[0]):
            best = (d, v["name"])
    return best[1] if best else None


def learn_choices(choices, src, template, files, analysed):
    """Memoire des choix apres une conversion : un profil change a la main pour une couleur du modele est
    retenu ; revenir au profil propose d'office l'oublie. Retourne True si elle a change."""
    changed = False
    for fi, f in enumerate(files or []):
        if fi >= len(analysed or []):
            break
        auto = {tuple(s.get("src") or []): s.get("auto") for s in analysed[fi].get("slots") or [] if s.get("src")}
        for s in f.get("slots") or []:
            srcs = tuple(_int(x, 0) for x in s.get("src") or [])
            if not srcs or auto.get(srcs) is None:
                continue
            key = choice_key(src.filament(srcs[0]))
            if key is None:
                continue
            base = _int(s.get("base"), -1)
            if base == auto[srcs]:
                if key in choices:
                    del choices[key]
                    changed = True
            elif 0 <= base < template.slot_count + len(template.presets):
                name = template.profile(base)[0]
                if name and (choices.get(key) or {}).get("name") != name:
                    choices[key] = {"name": name, "t": time.time()}
                    changed = True
    return changed


def carry_choices(old_files, old_profiles, profiles, files):
    """Choix faits a la main (profils, couleurs choisies, couleurs en plus) reportes sur une nouvelle
    analyse du meme 3MF : garder ou non les supports de l'auteur change les filaments, pas tes choix.
    old_profiles : (nom, groupe) de chaque profil de l'analyse d'avant."""
    names = [(p["name"], p["group"]) for p in profiles]

    def base_of(b):
        b = _int(b, -1)
        if not 0 <= b < len(old_profiles or []):
            return None
        key = tuple(old_profiles[b])
        return names.index(key) if key in names else None

    def pick_of(o, base, model):
        c = norm_color(o.get("color") or "")
        if not c or model:
            return c
        p = profiles[base] if 0 <= base < len(profiles) else {}
        own = norm_color(p.get("color") or "") if p.get("group") != "slot" else None
        return None if own == c else c              # couleur du profil : pas un choix
    by_src = {}
    for f in old_files or []:
        for s in f.get("slots") or []:
            src = tuple(_int(x, 0) for x in s.get("src") or [])
            if src:
                by_src.setdefault(src, s)
    for fi, f in enumerate(files):
        old = (old_files[fi].get("slots") or []) if fi < len(old_files or []) else []
        for si, s in enumerate(f["slots"]):
            if s["src"]:
                o = by_src.get(tuple(s["src"]))
            else:
                o = old[si] if si < len(old) and not old[si].get("src") and not old[si].get("extra") else None
            if not o:
                continue
            b = base_of(o.get("base"))
            if b is not None:
                s["base"] = b
            c = pick_of(o, s["base"], bool(s["src"]))
            if c:
                s["pick"] = c
        for o in old:
            if o.get("extra") and len(f["slots"]) < MAX_PAINT_FILAMENTS:
                b = base_of(o.get("base"))
                b = 0 if b is None else b
                f["slots"].append({"n": len(f["slots"]) + 1, "src": [], "base": b, "pad": False, "extra": True,
                                   "pick": pick_of(o, b, False)})


def missing_materials(src, template):
    """Matieres du modele qu'aucun de tes profils n'a (ni tes cases, ni tes prereglages)."""
    plates = [p.index for p in src.plates if p.instances]
    need = {e["base"] for e in color_entries(src, plates)} - {"?"}
    have = {base_type(t) for t in template.slot_types}
    have |= {base_type(p.type) for p in template.presets if not p.other and not p.system}
    if "?" in have:
        return set()
    return need - have


# --------------------------------------------------------------------------- supports de l'auteur

# Reglages de supports de l'auteur qu'on ne reprend pas : ils dependent de l'imprimante (largeur de
# ligne, vitesses, ventilation, filtration).
_SUPPORT_SKIP = {"support_line_width", "support_speed", "support_interface_speed", "support_air_filtration",
                 "support_chamber_temp_control", "support_material_interface_fan_speed", "support_multi_bed_types"}


def author_supports(src):
    """Supports du projet de l'auteur, s'il en a : {"on", "objects", "type", "filament", "interface"}."""
    cfg = src.config or {}
    on = _cfg_str(cfg, "enable_support") in ("1", "true")
    objs = any(str((o.keys or {}).get("enable_support", "")) in ("1", "true")
               for o in src.objects.values() if o.instances)
    if not on and not objs:
        return None
    return {"on": on, "objects": objs, "type": _cfg_str(cfg, "support_type"),
            "filament": _int(_cfg_str(cfg, "support_filament"), 0),
            "interface": _int(_cfg_str(cfg, "support_interface_filament"), 0)}


def supports_info(src, keep):
    """Ce que l'onglet et le panneau montrent des supports de l'auteur (None s'il n'en a pas)."""
    sup = author_supports(src)
    if not sup:
        return None
    desc = [tr("sup_tree" if (sup["type"] or "").lower().startswith("tree") else "sup_normal")] if sup["on"] else [tr("sup_objects")]
    for key, label in (("filament", "sup_fil"), ("interface", "sup_iface")):
        i = sup.get(key) or 0
        if i >= 1:
            f = src.filament(i)
            desc.append(tr(label, color_name(f["color"]), f["type"] or "?"))
    return {"keep": bool(keep), "desc": desc}


def copy_author_supports(src_cfg, cfg, mapping):
    """Reglages de supports de l'auteur dans les reglages du projet converti (filaments renumerotes)."""
    for key, value in (src_cfg or {}).items():
        if not isinstance(value, str) or key in _SUPPORT_SKIP or key not in cfg:
            continue
        if not (key in ("enable_support", "independent_support_layer_height")
                or key.startswith(("support_", "tree_support_", "raft_"))):
            continue
        if key in ("support_filament", "support_interface_filament"):
            v = _int(value, 0)
            value = str(mapping.get(v, 0)) if v >= 1 else "0"
        cfg[key] = value


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
            elif key == "different_settings_to_system" or (key == "inherits_group" and p.system):
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


def build_output(src, template, group, slots, report, keep_supports=False):
    """Construit le 3MF converti pour un groupe de plaques. slots : filaments du projet converti
    (voir plan_file) ; keep_supports : reglages de supports de l'auteur. Retourne les octets du fichier."""
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
        color = s.get("pick") or (src.filament(s["src"][0])["color"] if s["src"] else None)
        cfg_slots.append({"base": base, "preset": preset, "color": color})
    cfg = build_project_config(template, cfg_slots)
    if keep_supports:
        copy_author_supports(src.config, cfg, mapping)
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
    base = re.sub(r"\s*-\s*U1(?:-by-Dragg)?(\s*-\s*(?:plaques?|plates?|platten?|placas?|piatt[oi]) [\d\-]+)?$", "",
                  base, flags=re.I).strip() or "projet"
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
    if src.is_sliced_only:
        raise ConvertError(tr("err_sliced"))
    if not any(o.instances for o in src.objects.values()):
        raise ConvertError(tr("err_no_part"))


def analyze(src, template, one_per_plate=False, with_thumbs=True, choices=None, supports=False):
    """Resultat d'analyse pour l'interface : source, plaques, fichiers prevus, alertes. choices : memoire
    des choix ; supports : garder les supports de l'auteur. Les profils d'Orca d'une matiere qui te
    manque sont ajoutes a template.presets."""
    _check_source(src)
    src.set_supports(supports)
    missing = missing_materials(src, template)
    added = template.add_system(missing)
    plan = make_plan(src, template, one_per_plate, choices)
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
                          "auto": s.get("auto"), "mem": s.get("mem"),
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
    for want in sorted(missing):
        best = next((p.name for p in added if base_type(p.type) == want), None)
        warnings.append(tr("w_system", want, best) if best else tr("w_no_profile", want))
    return {
        "source": describe_source(src),
        "filaments": filaments,
        "plates": plates,
        "files": files,
        "profiles": template.profiles,
        "heads": template.head_count,
        "max_filaments": MAX_PAINT_FILAMENTS,
        "warnings": warnings,
        "supports": supports_info(src, src.keep_supports),
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
            # sans couleur du modele : case libre de la U1, ou couleur en plus ajoutee dans l'onglet
            # (pas utilisee par le modele, prete pour peindre ou reattribuer une piece dans Orca)
            slots.append({"src": srcs, "base": base, "pick": pick, "extra": bool(s.get("extra")) and not srcs})
        missing = needed - got
        if missing:
            raise ConvertError(tr("err_no_slot", ", ".join(str(x) for x in sorted(missing))))
        extras = sum(1 for s in slots if s["extra"])
        if extras and len(slots) > max(MAX_PAINT_FILAMENTS, len(slots) - extras):
            raise ConvertError(tr("err_too_many_extra", MAX_PAINT_FILAMENTS))
        while len(slots) > heads and not slots[-1]["src"] and not slots[-1]["extra"]:
            slots.pop()
        while len(slots) < heads:
            slots.append({"src": [], "base": len(slots) if len(slots) < k else 0, "pick": None, "extra": False})
        clean.append({"plates": plates, "slots": slots})
    missing_plates = [p.id for p in src.plates if p.instances and p.index not in seen]
    if missing_plates:
        raise ConvertError(tr("err_plates_missing", ", ".join(map(str, missing_plates))))
    return clean


def convert(src, template, files, progress=None):
    """Produit les fichiers convertis : liste de dicts {name, data, plates, map, filaments, report}."""
    _check_source(src)
    sup = [bool(f.get("supports")) for f in files or [] if isinstance(f, dict) and "supports" in f]
    if sup:                     # sinon : le choix de la derniere analyse
        src.set_supports(any(sup))
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
        data = build_output(src, template, f["plates"], f["slots"], report, keep_supports=src.keep_supports)
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


def _choices_path():
    return os.path.join(storage_dir(), "choix.json")


def load_choices():
    """Memoire des choix : {"PLA|#F5547C": {"name": profil, "t": date}}."""
    try:
        with open(_choices_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        items = d.get("items") if isinstance(d, dict) else None
        if not isinstance(items, dict):
            return {}
        return {k: v for k, v in items.items() if isinstance(v, dict) and v.get("name")}
    except Exception:
        return {}


def save_choices(items):
    if len(items) > CHOICES_MAX:
        items = dict(sorted(items.items(), key=lambda kv: -float(kv[1].get("t") or 0))[:CHOICES_MAX])
    path = _choices_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "items": items}, f, ensure_ascii=False)
    os.replace(tmp, path)


OUT_MODES = ("beside", "downloads", "folder")
PANEL_MODES = ("panel", "notif", "off")     # 3MF pas regle pour la U1 : panneau, notification, rien


def panel_mode(options=None):
    """Quand Orca ouvre un 3MF pas regle pour la U1 : la U1 dans le panneau de Preparer (par defaut),
    une notification seulement, ou rien."""
    o = options if options is not None else load_options()
    return o.get("panel") if o.get("panel") in PANEL_MODES else "panel"


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
            if PRUSA_CFG in names and not cfg:
                pc = parse_prusa_config(z.read(PRUSA_CFG).decode("utf-8", "replace"))
                cfg = {"printer_model": pc.get("printer_model", ""),
                       "printer_settings_id": (prusa_list(pc.get("printer_settings_id")) or [""])[0],
                       "filament_colour": prusa_colours(pc)}
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
    if info.get("error"):
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
/* Titres : Inter Display ExtraBold, Copyright 2016 The Inter Project Authors (github.com/rsms/inter), SIL Open Font License 1.1 (openfontlicense.org) ; seulement les caracteres de l'onglet. */
@font-face{font-family:"M3D";src:url(data:font/woff2;base64,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) format("woff2");font-weight:800;font-display:block}
:root{--ground:#1C1D20;--bar:#18191C;--card:#222428;--raise:#26282C;--edge:#2E3035;--edge2:#3A3D43;
--fg:#E9EAEC;--muted:#9C9DA0;--teal:#22B3A5;--teal-ink:#0C2E2A;--teal-card:#1F2A29;--amber:#F0A73C;--grey:#6A6E76;--coral:#EC6A5E;--coral-card:#2C2122;
color-scheme:dark;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;flex-direction:column;color:var(--fg);background:var(--ground)}
.h,h1,h2,h3{font-family:"M3D",system-ui,sans-serif;font-weight:800;letter-spacing:-.015em}
button{display:inline-flex;align-items:center;justify-content:center;gap:6px;font:inherit;color:var(--fg);background:transparent;border:1px solid var(--edge2);border-radius:8px;height:34px;padding:0 13px;font-weight:600;cursor:pointer;white-space:nowrap}
button:hover{border-color:#5a5e66}button:disabled{opacity:.4;cursor:default}
button.go{background:var(--teal);border-color:var(--teal);color:var(--teal-ink);height:42px;padding:0 22px;font-size:15px}
button.go:hover{background:#2bc4b5}
button:focus-visible,input:focus-visible,select:focus-visible,.zone:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
input[type=text]{flex:1;min-width:0;height:36px;background:rgba(0,0,0,.18);color:var(--fg);border:1px solid var(--edge2);border-radius:8px;padding:0 11px;font:inherit}
select{background:#1f2023;color:var(--fg);border:1px solid var(--edge2);border-radius:8px;height:36px;padding:0 8px;font:inherit;min-width:0}
.muted{color:var(--muted)}.small{font-size:12.5px}.hidden{display:none!important}
.row{display:flex;align-items:center;gap:8px}
/* top bar */
.bar{display:flex;align-items:center;gap:10px;height:46px;padding:0 18px;background:var(--bar);border-bottom:1px solid var(--edge)}
.bar b{font-size:14.5px;white-space:nowrap}.bar .muted{font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar .r{margin-left:auto;display:flex;align-items:center;gap:10px;flex:none}
.bar .r .muted{font-size:12.5px}
@media (max-width:1100px){.bar .r>.muted:first-child{display:none}}.bar button,.bar select{height:30px;font-size:12.5px}
/* head */
.head{display:flex;align-items:center;gap:18px;padding:20px 26px 18px;border-bottom:1px solid var(--edge)}
.head h1{margin:0;font-size:28px;line-height:1.12;word-break:break-word}
.head p{margin:4px 0 0;color:var(--muted);font-size:14.5px}.head p b{color:var(--fg);font-weight:600}
.thumb{width:62px;height:62px;border-radius:10px;background:var(--card);border:1px solid var(--edge);flex:none;display:grid;place-items:center;overflow:hidden}
.thumb img{width:100%;height:100%;object-fit:contain}
.legend{margin-left:auto;display:grid;grid-template-columns:repeat(4,auto);gap:4px 16px;flex:none}
.legend span{display:inline-flex;align-items:center;gap:6px;font-size:13.5px;white-space:nowrap}
.legend em{font-style:normal;color:var(--muted);font-weight:600;font-size:12px}
#status:empty{display:none}#status{padding:12px 26px 0}
.msg{display:flex;gap:10px;align-items:flex-start;border-radius:10px;padding:10px 14px;font-size:13.5px;background:var(--card);border:1px solid var(--edge)}
.msg>i{margin-top:5px}.msg.err{background:var(--coral-card);border-color:rgba(236,106,94,.5)}.msg.info{background:var(--teal-card);border-color:rgba(34,179,165,.45)}
.msg .grow{flex:1;min-width:0}
.bar2{height:5px;border-radius:3px;background:#2E3035;overflow:hidden;margin-top:7px}.bar2 i{display:block;height:100%;width:35%;background:var(--teal);border-radius:3px;animation:mv 1.1s infinite ease-in-out}
@keyframes mv{0%{margin-left:-35%}100%{margin-left:100%}}
/* body */
main{flex:1;display:grid;grid-template-columns:minmax(300px,420px) minmax(0,1fr)}
.col{padding:20px 26px;display:flex;flex-direction:column;gap:16px;min-width:0}
.col+.col{border-left:1px solid var(--edge)}
.sec{display:flex;align-items:flex-end;gap:10px}.sec h2{margin:0;font-size:19px;line-height:1.2}
.sec p{margin:2px 0 0;color:var(--muted);font-size:13.5px}.sec>button{margin-left:auto}
@media (max-width:860px){main{grid-template-columns:1fr}.col+.col{border-left:0;border-top:1px solid var(--edge)}.legend{display:none}}
/* round = filament, square = number / state */
.dot{display:inline-block;width:12px;height:12px;border-radius:50%;flex:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.2)}
.dot.dk{box-shadow:inset 0 0 0 1.5px #8D9096}
.num{display:inline-grid;place-items:center;min-width:24px;height:24px;padding:0 5px;border-radius:5px;background:#E9EAEC;color:#16171A;font-weight:700;font-size:13px;flex:none}
.num.gr{background:#3A3D43;color:var(--fg)}.num.teal{background:var(--teal);color:var(--teal-ink)}
.mk{display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--amber);flex:none}
.mk.grey{background:var(--grey)}.mk.teal{background:var(--teal)}.mk.coral{background:var(--coral)}
/* the U1 */
.zone{flex:1;min-height:300px;border:2px dashed var(--edge2);border-radius:14px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:12px 16px 16px;text-align:center;cursor:pointer}
.zone:hover{border-color:rgba(34,179,165,.7);background:rgba(34,179,165,.04)}
.zone .u1{width:230px;max-width:100%}
.say{font-family:"M3D",system-ui;font-weight:800;font-size:24px;letter-spacing:-.015em;line-height:1.15;margin-top:2px}
.say2{color:var(--muted);font-size:13.5px;margin-top:3px}
#zbar{width:220px}
.mini{display:flex;align-items:center;gap:14px}.mini .u1{width:104px;flex:none}.mini .say{font-size:21px}
/* lists */
.list{display:flex;flex-direction:column}
.li{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--edge)}
.li:first-child{border-top:0}
.li .nm{font-weight:650;font-size:14.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.li .mt{color:var(--muted);font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.li .st{display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--muted);white-space:nowrap}
.li .st b{color:var(--fg);font-weight:600}.li.off .nm{color:#8E9196}
/* heads, same cards as multiACE Bridge */
.rig{background:var(--card);border:1px solid var(--edge);border-radius:12px;padding:14px 14px 12px}
.rg{display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) minmax(0,.85fr);gap:10px}
.sp{display:flex;flex-direction:column;align-items:center;text-align:center;min-width:0}
.sp .n1{font-weight:650;font-size:12.5px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.sp .n2{color:var(--muted);font-size:11.5px}
.spool{display:block;width:38px;height:38px;margin-top:6px;flex:none}
.wire{width:4px;height:12px;margin:0 auto;border-radius:1px}
.tc{background:var(--raise);border:1px solid var(--edge2);border-radius:9px;padding:8px 10px}
.tc .t{font-family:"M3D",system-ui;font-weight:800;font-size:20px;line-height:1.1}
.tc .z{color:var(--muted);font-size:12.5px}.tc .f{display:flex;align-items:center;gap:6px;font-size:12.5px;margin-top:4px;white-space:nowrap;overflow:hidden}
.tc.ex{background:transparent;border-style:dashed;display:grid;place-items:center;text-align:center;color:var(--muted);font-size:12.5px;height:calc(100% - 12px)}
.kv{display:flex;flex-wrap:wrap;gap:4px 18px;margin-top:10px;font-size:13px;color:var(--muted)}.kv b{color:var(--fg);font-weight:600}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);margin-left:8px}
/* analysis */
.plates{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:8px}
.plate{background:var(--card);border:1px solid var(--edge);border-radius:9px;padding:6px 6px 7px}
.plate .pv{height:66px;border-radius:6px;background:var(--bar);display:flex;align-items:center;justify-content:center;gap:4px;flex-wrap:wrap;overflow:hidden}
.plate .pv img{width:100%;height:100%;object-fit:contain}
.plate .pl{display:flex;align-items:center;gap:6px;margin-top:6px;font-size:12.5px;min-width:0}
.plate .pl span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plate .ds{display:flex;gap:3px;margin-left:auto;flex:none}
.notes{display:flex;flex-direction:column;gap:8px}
.notes div{display:flex;gap:10px;align-items:flex-start;font-size:13.5px;line-height:1.45}.notes .mk{margin-top:5px}
.check{display:flex;gap:10px;align-items:flex-start;font-size:14px;cursor:pointer}
.check input{width:18px;height:18px;margin:1px 0 0;accent-color:var(--teal)}.check small{display:block;color:var(--muted);font-size:12.5px}
.grp h3{margin:0 0 6px;font-size:16px}.grp h3 span{font-family:system-ui;font-weight:400;font-size:13px;color:var(--muted);letter-spacing:0}
.th,.tr{display:grid;grid-template-columns:28px minmax(0,1fr) 70px minmax(0,1fr);gap:12px;align-items:center}
.th{color:var(--muted);font-size:12.5px;padding-bottom:6px;border-bottom:1px solid var(--edge)}
.tr{padding:7px 0;border-bottom:1px solid var(--edge)}
.tr .cn{display:flex;align-items:center;gap:9px;min-width:0}
.tr .cn .tx{min-width:0}.tr .cn b{font-weight:650}
.tr .cn .tx div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tr .cn .sub{color:var(--muted);font-size:12.5px}
.tr .pl{color:var(--muted);font-size:13px}
.tr.pad .tx,.tr.ex .tx{color:var(--muted)}
.addrow{display:flex;align-items:center;gap:10px;margin-top:10px}
button.rmc{width:34px;padding:0;flex:none;font-size:18px;font-weight:500;color:var(--muted)}button.rmc:hover{color:var(--coral);border-color:var(--coral)}
input.pick{-webkit-appearance:none;appearance:none;width:22px;height:22px;padding:0;border:0;border-radius:50%;background:none;cursor:pointer;flex:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.22);transition:box-shadow .15s}
input.pick:hover{box-shadow:inset 0 0 0 1px rgba(255,255,255,.22),0 0 0 3px var(--edge2)}input.pick:focus-visible{outline:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.22),0 0 0 3px var(--teal)}
input.pick::-webkit-color-swatch-wrapper{padding:0}input.pick::-webkit-color-swatch{border:none;border-radius:50%}
.prof{display:flex;align-items:center;gap:8px;min-width:0}.prof select{flex:1}
.warn{display:flex;gap:7px;align-items:center;color:#F3C98A;font-size:12px;margin-top:3px}
a.reset{color:var(--teal);cursor:pointer;text-decoration:underline}
.changed{color:var(--teal)}
/* result: 3 steps */
.gest{display:flex;flex-direction:column;gap:8px}
.g{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--edge);border-radius:11px;padding:12px 14px;font-size:14px}
.g.on{background:var(--teal-card);border:1.5px solid var(--teal);flex-direction:column;align-items:stretch;gap:10px;padding:14px 16px}
.g.done{opacity:.75}
.g .hd{display:flex;align-items:center;gap:10px;flex:1;min-width:0}.g .hd .h{font-size:17px}
.g .k{margin-left:auto;display:flex;gap:5px;align-items:center;color:var(--muted)}
.g .file{display:flex;gap:8px;align-items:center}
.g code{flex:1;min-width:0;font:12.5px ui-monospace,Consolas,monospace;background:rgba(0,0,0,.2);border:1px solid var(--edge2);border-radius:8px;padding:8px 10px;word-break:break-all}
kbd{font:600 12px system-ui;background:#2F3237;border:1px solid #474B52;border-bottom-width:3px;border-radius:5px;padding:1px 7px;color:var(--fg)}
.segs{display:flex;gap:5px}.segs i{width:34px;height:5px;border-radius:2px;background:#3A3D43}.segs i.on{background:var(--teal)}.segs i.done{background:#E9EAEC}
/* skeleton */
.sk{background:#2A2C31;border-radius:6px}
/* footer */
footer{position:sticky;bottom:0;display:flex;align-items:center;gap:12px;min-height:60px;padding:10px 18px 10px 26px;background:var(--ground);border-top:1px solid var(--edge);color:var(--muted);font-size:13.5px}
footer b{color:var(--fg);font-weight:600}footer .r{margin-left:auto;display:flex;gap:8px;align-items:center;flex:none}
#cstatus:empty{display:none}#cstatus{min-width:220px}#cstatus .msg{padding:6px 12px}
/* views */
.v{display:none!important}
body[data-v=home] .vh,body[data-v=busy] .vb,body[data-v=an] .va,body[data-v=res] .vr{display:flex!important}
body[data-v=home] .vh.blk,body[data-v=busy] .vb.blk,body[data-v=an] .va.blk,body[data-v=res] .vr.blk{display:block!important}
body[data-v=home] .vh.grd,body[data-v=busy] .vb.grd,body[data-v=an] .va.grd,body[data-v=res] .vr.grd{display:grid!important}
/* settings window */
#dlg{position:fixed;inset:0;z-index:40;background:rgba(12,13,15,.72);display:grid;place-items:center;padding:20px}
#dlg>div{width:min(1080px,100%);max-height:100%;overflow:auto;background:var(--ground);border:1px solid var(--edge2);border-radius:14px;box-shadow:0 30px 80px rgba(0,0,0,.6)}
#dlg .bar{border-radius:14px 14px 0 0}
#dlg .dbody{display:grid;grid-template-columns:minmax(0,380px) minmax(0,1fr)}
@media (max-width:860px){#dlg .dbody{grid-template-columns:1fr}}
.choice{display:flex;gap:11px;align-items:flex-start;border:1px solid var(--edge);border-radius:11px;padding:12px 14px;cursor:pointer}
.choice.on{background:var(--teal-card);border:1.5px solid var(--teal)}
.choice input{margin:3px 0 0;accent-color:var(--teal);width:16px;height:16px}
.choice b{font-family:"M3D",system-ui;font-weight:800;font-size:17px;letter-spacing:-.01em}
.choice p{margin:2px 0 0;color:var(--muted);font-size:13px}
.out{display:flex;flex-direction:column;gap:8px}.out label{display:flex;gap:9px;align-items:center;cursor:pointer}
.out label span{display:inline-block}.out label span::first-letter{text-transform:uppercase}
.out input[type=radio]{accent-color:var(--teal);width:16px;height:16px;margin:0}
.out .err{color:var(--amber)}
/* big U1 when a file is dragged on the tab */
#eat{position:fixed;inset:0;z-index:50;display:grid;place-items:center;background:rgba(14,15,17,.86);pointer-events:none}
#eat.click{pointer-events:auto;cursor:pointer}
#eat .ring{border:2.5px dashed var(--teal);border-radius:26px;padding:14px 46px 24px;background:rgba(34,179,165,.05);text-align:center}
#eat .u1{width:320px;max-width:70vw;margin:0 auto}
#eatCap{font-family:"M3D",system-ui;font-weight:800;font-size:34px;letter-spacing:-.015em;margin-top:-2px}
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
.u1.full .u-pr{transform:scaleY(1)}
.u1.spit .u-tg{fill:#9bd36a}.u1.spit .u-ey{animation:none;transform:scaleY(.25)}.u1.spit .u-fl{animation:u-spit 1.1s forwards}
@keyframes u-spit{0%{opacity:1;transform:translate(0,150px)}100%{opacity:0;transform:translate(120px,-30px) rotate(80deg)}}
@media (prefers-reduced-motion:reduce){.u1 *,.bar2 i{animation:none!important;transition:none!important}}
</style></head><body data-v="home">
<header class="bar"><span id="logo"></span><b>Mange-3MF</b><span class="muted" data-t="sub"></span>
<div class="r"><span class="muted" data-t="support"></span><button id="kofi" data-t="copy_link"></button><button id="openSet" data-t="settings"></button><select id="lang" data-tt="lang_title"></select><span class="muted" id="ver"></span></div></header>

<div class="head"><div class="thumb hidden" id="thumb"></div><div style="min-width:0"><h1 id="hTitle"></h1><p id="hSub"></p></div><div class="legend" id="legend"></div></div>
<div id="status"></div>

<main>
<div class="col">
 <div class="zone v vh vb vr" id="u1zone" role="button" tabindex="0" data-tt="u1_title"><div id="u1small"></div><div class="say" id="say"></div><div class="say2" id="say2"></div><div class="bar2 v vb" id="zbar"><i></i></div></div>
 <div class="row v vh" id="pathRow" style="flex-wrap:wrap"><input type="text" id="path" data-tp="path_ph" style="flex:1 1 100%"><button id="go" data-t="analyse"></button><button id="browse" data-t="browse"></button><input type="file" id="file" accept=".3mf" class="hidden"></div>
 <div class="v va mini" id="miniWrap"><div id="mini"></div><div><div class="say" id="miniSay"></div><div class="say2" data-t="mini2"></div></div></div>
 <div class="v va blk" id="platesWrap"><div class="sec" style="margin-bottom:8px"><h2 data-t="h_plates"></h2></div><div class="plates" id="plates"></div></div>
 <div class="v va blk" id="notesWrap"><div class="sec" style="margin-bottom:8px"><h2 data-t="h_before"></h2></div><div class="notes" id="notes"></div></div>
 <div class="v va" id="opWrap" style="flex-direction:column;gap:14px"></div>
</div>
<div class="col">
 <div class="v vh blk" id="homeRight">
  <div id="opened"></div>
  <div class="sec"><div><h2 data-t="recent_title"></h2><p data-t="recent_sub"></p></div><button id="refresh" data-t="refresh"></button></div>
  <div class="list" id="recent"><div class="muted small" data-t="searching"></div></div>
  <div class="sec" style="margin-top:18px"><div><h2 data-t="h_tpl"></h2><p id="rigSub"></p></div><button id="editSet" data-t="edit"></button></div>
  <div id="rig" style="margin-top:10px"></div>
 </div>
 <div class="v vb blk" id="busyRight"><div class="sec"><div><h2 data-t="h_map"></h2><p data-t="map_busy"></p></div></div><div id="skel" style="margin-top:12px"></div></div>
 <div class="v va blk" id="s3"><div class="sec"><div><h2 data-t="h_map"></h2><p data-t="map_sub"></p></div></div><div id="analysis" style="margin-top:12px"></div></div>
 <div class="v vr blk" id="s4"><div class="sec"><div><h2 data-t="h_open"></h2><p data-t="open_sub"></p></div><div class="segs" id="segs" style="margin-left:auto"></div></div><div id="result" style="margin-top:12px"></div></div>
</div>
</main>

<footer>
 <span class="v vh blk" id="fHome"></span>
 <span class="v vb" data-t="orig_kept"></span>
 <span class="v va blk" id="dest" style="flex:1;min-width:0"></span>
 <span class="v vr" data-t="orig_kept"></span>
 <div class="r"><div id="cstatus" class="v va blk"></div><button class="v va vb" id="cancel" data-t="cancel"></button><button class="go v va" id="convert"></button><button class="v vr" id="back" data-t="back"></button><button class="v vr" id="again" data-t="again"></button></div>
</footer>

<div id="dlg" class="hidden" role="dialog" aria-modal="true"><div>
 <header class="bar"><span id="logo2"></span><b>Mange-3MF</b><span class="muted" data-t="h_tpl"></span><div class="r"><button id="dlgX" aria-label="×">✕</button></div></header>
 <div class="head"><div><h1 data-t="h_tpl" style="font-size:25px"></h1><p data-t="dlg_sub"></p></div></div>
 <div class="dbody">
  <div class="col">
   <div id="tplChoices" style="display:flex;flex-direction:column;gap:10px"></div>
   <div class="row" style="flex-wrap:wrap"><button id="capture" data-t="capture"></button><span class="muted small" id="capMsg"></span></div>
   <div class="sec" style="margin-top:6px"><h2 data-t="out_h" style="font-size:17px"></h2></div>
   <div class="out">
    <label><input type="radio" name="out" value="beside"><span data-t="out_beside"></span></label>
    <label><input type="radio" name="out" value="downloads"><span data-t="out_downloads"></span></label>
    <label><input type="radio" name="out" value="folder"><span data-t="out_folder"></span></label>
    <div class="row"><input type="text" id="outDir" data-tp="out_ph"><button id="outOk" data-t="out_ok"></button></div>
    <span id="outMsg" class="muted small"></span></div>
  </div>
  <div class="col"><div class="sec"><div><h2 id="dlgRigTitle" style="font-size:17px"></h2><p data-t="rig_sub"></p></div></div><div id="dlgRig"></div>
   <div class="sec" style="margin-top:8px"><h2 data-t="pn_h" style="font-size:17px"></h2></div>
   <div class="out">
    <label><input type="radio" name="pmode" value="panel"><span data-t="pn_mode_panel"></span></label>
    <label><input type="radio" name="pmode" value="notif"><span data-t="pn_mode_notif"></span></label>
    <label><input type="radio" name="pmode" value="off"><span data-t="pn_mode_off"></span></label>
    <div class="row" style="flex-wrap:wrap;margin-top:2px"><button id="pshow" data-t="pn_show"></button><span class="muted small" id="pshowMsg"></span></div></div>
  </div>
 </div>
 <footer style="position:static"><span data-t="dlg_foot"></span><div class="r"><span class="muted small" id="memMsg"></span><button id="forget" data-t="mem_forget" data-tt="mem_text"></button><button class="go" id="dlgClose" data-t="close"></button></div></footer>
</div></div>

<div id="eat" class="hidden"><div class="ring"><div id="eatU"></div><div id="eatCap"></div></div></div>
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
<template id="icon"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="24" height="24" aria-hidden="true">
  <rect width="512" height="512" rx="112" fill="#1FA89B"/>
  <ellipse cx="256" cy="452" rx="168" ry="20" fill="#178A7F"/>
  <g stroke="#141920" stroke-width="12" stroke-linejoin="round">
    <rect x="124" y="84" width="56" height="58" rx="14" fill="#1b1d21"/>
    <rect x="190" y="84" width="56" height="58" rx="14" fill="#FFC83A"/>
    <rect x="266" y="84" width="56" height="58" rx="14" fill="#E5483F"/>
    <rect x="332" y="84" width="56" height="58" rx="14" fill="#F4F4F4"/>
    <rect x="80" y="124" width="352" height="324" rx="64" fill="#E3E7EC" stroke-width="16"/>
  </g>
  <g stroke="#141920" stroke-width="12">
    <circle cx="198" cy="196" r="42" fill="#fff"/>
    <circle cx="314" cy="196" r="42" fill="#fff"/>
  </g>
  <circle cx="207" cy="208" r="19" fill="#141920"/><circle cx="305" cy="208" r="19" fill="#141920"/>
  <circle cx="214" cy="199" r="7" fill="#fff"/><circle cx="312" cy="199" r="7" fill="#fff"/>
  <ellipse cx="130" cy="248" rx="22" ry="12" fill="#F29AA8"/><ellipse cx="382" cy="248" rx="22" ry="12" fill="#F29AA8"/>
  <rect x="116" y="266" width="280" height="150" rx="34" fill="#2B1D22" stroke="#141920" stroke-width="12"/>
  <clipPath id="lgm"><rect x="122" y="272" width="268" height="138" rx="28"/></clipPath>
  <g clip-path="url(#lgm)">
    <ellipse cx="256" cy="414" rx="96" ry="32" fill="#F07A8E"/>
    <path d="M136 272l14 34 14-34zM348 272l14 34 14-34z" fill="#fff"/>
  </g>
  <g transform="rotate(-12 256 300)">
    <path d="M206 236h66l34 34v96a10 10 0 0 1-10 10h-90a10 10 0 0 1-10-10V246a10 10 0 0 1 10-10z" fill="#fff" stroke="#141920" stroke-width="10" stroke-linejoin="round"/>
    <path d="M272 236v34h34" fill="none" stroke="#141920" stroke-width="10" stroke-linejoin="round"/>
    <rect x="196" y="318" width="110" height="30" fill="#22B3A5"/>
    <path d="M232.38 341.34Q230.77 341.34 229.58 341.02Q228.39 340.71 227.6 340.12Q226.8 339.53 226.37 338.66Q225.93 337.78 225.83 336.68L229.34 335.65Q229.37 336.28 229.59 336.79Q229.81 337.29 230.21 337.65Q230.61 338.01 231.18 338.19Q231.76 338.37 232.48 338.37Q233.31 338.37 233.94 338.12Q234.57 337.87 234.93 337.37Q235.28 336.86 235.28 336.1Q235.28 335.14 234.6 334.51Q233.91 333.88 232.51 333.64Q231.1 333.41 228.91 333.65V331.49L234.1 328.39V328.19L226.67 328.25V325.14H238.09V328.6L233.12 331.76V331.99Q235.39 331.83 236.7 332.41Q238.01 332.99 238.58 334.03Q239.15 335.07 239.15 336.27Q239.15 337.84 238.41 338.97Q237.68 340.09 236.18 340.72Q234.68 341.34 232.38 341.34ZM241.5 341V325.16H247.29L251.31 336.54H251.42L255.35 325.16H260.87V341H257.21L257.42 329.09H257.16L252.7 341H249.52L245.15 329.09H244.9L245.1 341H241.5ZM264.04 341V325.16H267.9V341H264.04ZM265.94 335.36V332.21H275.07V335.36H265.94ZM265.94 328.44V325.16H275.93V328.44H265.94Z" fill="#fff"/>
    <polygon points="251,256 274,269 251,282 228,269" fill="#1E88E5"/>
    <polygon points="228,269 251,282 251,306 228,293" fill="#E53935"/>
    <polygon points="251,282 274,269 274,293 251,306" fill="#FFC107"/>
  </g>
  <path d="M184 266l10 24 10-24zM308 266l10 24 10-24z" fill="#fff" stroke="#141920" stroke-width="6" stroke-linejoin="round"/>
</svg></template>
<script>
(function(){
var L=__TEXTS__;
var nav=(navigator.languages&&navigator.languages[0])||navigator.language||"";
var lang="__LANG__";if(!L[lang]){lang=nav.slice(0,2).toLowerCase();if(!L[lang])lang="en"}
function t(k){var a=arguments,s=L[lang]&&L[lang][k];if(s==null)s=L.en&&L.en[k];if(s==null)s=k;
 return String(s).replace(/\{(\d+)\}/g,function(_,i){var v=a[+i+1];return v==null?"":v})}
var S={tpl:null,cur:null,choice:"saved",an:null,res:null,rec:null,opened:null,token:null,busy:false,conv:false,onePer:false,langChoice:"auto",copied:false,busyName:"",busyText:"",skip:0,upId:null,pmode:"panel",runTok:null,dead:{}};
function $(id){return document.getElementById(id)}
function esc(x){var d=document.createElement("span");d.textContent=x==null?"":String(x);return d.innerHTML}
function send(m){orca.postMessage(m)}
function each(sel,fn){Array.prototype.forEach.call(document.querySelectorAll(sel),fn)}
function plural(n,one,many){return n>1?many:one}
function colors(n){return n+" "+plural(n,t("color1"),t("colorN"))}
function dark(c){c=String(c||"").replace("#","");if(c.length<6)return false;var r=parseInt(c.substr(0,2),16),g=parseInt(c.substr(2,2),16),b=parseInt(c.substr(4,2),16);return (r*299+g*587+b*114)/1000<45}
function dot(c,size){c=String(c||"#808080").slice(0,7);return '<i class="dot'+(dark(c)?' dk':'')+'" style="background:'+esc(c)+(size?';width:'+size+'px;height:'+size+'px':'')+'"></i>'}
/* bobine vue de face, en SVG (cercles lisses ; un degrade CSS en anneaux fins s'affichait en escalier dans Orca) :
   disque de la couleur du filament, spires a peine marquees, moyeu noir */
function spool(c){c=String(c||"#808080").slice(0,7);var d=dark(c),h='<svg class="spool" viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="19" fill="'+(d?'#2B2D32':esc(c))+'"/><g fill="none" stroke="'+(d?'rgba(255,255,255,.09)':'rgba(0,0,0,.12)')+'" stroke-width="1">';
 [15.8,12.9,10.2].forEach(function(r){h+='<circle cx="20" cy="20" r="'+r+'"/>'});
 return h+'</g><circle cx="20" cy="20" r="7.4" fill="#141518"/><circle cx="20" cy="20" r="2.5" fill="#3D4046"/>'
  +(d?'<circle cx="20" cy="20" r="18.5" fill="none" stroke="rgba(255,255,255,.2)" stroke-width="1"/>':'')+'</svg>'}
function cap1(s){s=String(s||"");return s.charAt(0).toUpperCase()+s.slice(1)}
function view(v){document.body.setAttribute("data-v",v);renderHead()}
function V(){return document.body.getAttribute("data-v")}
function statics(){document.documentElement.lang=lang;
 each("[data-t]",function(e){e.textContent=t(e.getAttribute("data-t"))});
 each("[data-th]",function(e){e.innerHTML=t(e.getAttribute("data-th"))});
 each("[data-tp]",function(e){e.setAttribute("placeholder",t(e.getAttribute("data-tp")))});
 each("[data-tt]",function(e){e.setAttribute("title",t(e.getAttribute("data-tt")))});
 var h='<option value="auto">'+esc(t("lang_auto"))+'</option>';
 Object.keys(L).forEach(function(k){h+='<option value="'+esc(k)+'">'+esc(L[k].lang_name||k)+'</option>'});
 $("lang").innerHTML=h;$("lang").value=S.langChoice;$("dlgX").setAttribute("aria-label",t("close"))}
function status(kind,html,progress){var box=(S.conv&&$("cstatus"))||$("status");if(box!==$("status"))$("status").innerHTML="";
 box.innerHTML=html?'<div class="msg '+kind+'"><i class="mk '+(kind=="err"?"coral":kind=="warn"?"":"teal")+'"></i><div class="grow">'+html+(progress?'<div class="bar2"><i></i></div>':'')+'</div></div>':''}
function ago(x){if(!x)return"";var s=(Date.now()/1000-x);if(s<90)return t("ago_now");if(s<3600)return t("ago_min",Math.round(s/60));if(s<86400)return t("ago_h",Math.round(s/3600));return t("ago_d",Math.round(s/86400))}
function size(b){return b>1048576?(b/1048576).toFixed(1)+" "+t("mb"):Math.max(1,Math.round(b/1024))+" "+t("kb")}
var BEDS={"Textured PEI Plate":"bed_tpei","Cool Plate":"bed_cool","Engineering Plate":"bed_eng","High Temp Plate":"bed_hot","Supertack Plate":"bed_tack","Textured Cool Plate":"bed_tcool"};
function flow(f){return f=="High Flow"?t("hf"):(f=="Standard"?t("std"):f)}
function bed(x){return x.bed_type?(BEDS[x.bed_type]?t(BEDS[x.bed_type]):x.bed_type):""}
function docIcon(band,label){return '<svg width="30" height="35" viewBox="0 0 40 46" aria-hidden="true"><path d="M3 4a3 3 0 0 1 3-3h20l11 11v29a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3z" fill="#E9EAEC"/><path d="M26 1v11h11" fill="#C9CBCF"/><rect x="3" y="26" width="34" height="11" fill="'+band+'"/><text x="20" y="34.6" text-anchor="middle" font-family="system-ui,sans-serif" font-weight="800" font-size="'+(label.length>3?7:9)+'" fill="#fff">'+label+'</text><path d="M20 8l6 3.4-6 3.4-6-3.4z" fill="#2B7BE4"/><path d="M14 11.4l6 3.4v6.6l-6-3.4z" fill="#E53935"/><path d="M26 11.4l-6 3.4v6.6l6-3.4z" fill="#F2C230"/></svg>'}
/* ---- head ---- */
function legendHtml(){var a=S.an;if(!a||!a.files.length)return"";var seen={},h="";
 a.files[0].slots.forEach(function(sl){if(sl.pad||sl.extra||seen[sl.n])return;   /* les couleurs du modele seulement */seen[sl.n]=1;h+='<span><em>'+sl.n+'</em>'+dot(sl.pick||sl.color)+esc(cap1(sl.name))+'</span>'});return h}
function thumbHtml(){var a=S.an;if(!a)return"";var p=a.plates.length==1&&a.plates[0].thumb?a.plates[0]:null;
 if(p)return '<img src="'+p.thumb+'" alt="">';return '<div style="display:flex;flex-wrap:wrap;gap:3px;width:46px;justify-content:center">'+a.filaments.slice(0,9).map(function(f){return dot(f.color,12)}).join("")+'</div>'}
function renderHead(){var v=V(),title="",sub="",leg="",th="";
 if(v=="home"){title=t("h_src");sub=esc(t("home_sub"))}
 else if(v=="busy"){title=S.busyName||t("h_src");sub=esc(S.busyText||t("analysing"))}
 else if(v=="an"&&S.an){var a=S.an,s=a.source;title=a.file+(s.title?" — "+s.title:"");
  sub='<b>'+esc(colors(s.colors))+', '+s.plates+' '+esc(plural(s.plates,t("plate1"),t("plateN")))+'.</b> '+esc([s.app,s.printer,s.nozzle?t("nozzle")+" "+s.nozzle:"",t("bed")+" "+s.bed[0]+"×"+s.bed[1]].filter(Boolean).join(", "))+(s.designer?' '+esc(t("by"))+' '+esc(s.designer):'');leg=legendHtml();th=thumbHtml()}
 else if(v=="res"&&S.res){var r=S.res;title=r.files.length>1?t("res_title_n",r.files.length):t("res_title");
  sub=(r.files.length==1?'<b>'+esc(r.files[0].name)+'</b>. ':'')+esc(t("res_sub"));leg=legendHtml();th=thumbHtml()}
 $("hTitle").textContent=title;$("hSub").innerHTML=sub;$("legend").innerHTML=leg;$("thumb").innerHTML=th;$("thumb").classList.toggle("hidden",!th);
 var z=v=="busy"?["u1_chew","busy2"]:v=="res"?["say_done","say_done2"]:["say_idle","say_idle2"];$("say").textContent=t(z[0]);$("say2").textContent=t(z[1]);
 var want=v=="busy"?"chew":v=="res"?"idle full":"idle";if(U.small&&!U.smallLock&&U.small.getAttribute("class")!="u1 "+want)u1Set(U.small,want)}
/* ---- settings ---- */
function tplOf(){return S.choice=="saved"&&S.tpl?S.tpl:(S.cur||S.tpl)}
function rigHtml(x){if(!x)return '<div class="msg info"><i class="mk teal"></i><div class="grow">'+esc(t("tpl_hint"))+'</div></div>';
 var sl=x.slots||[],fl=x.flows||[],heads=sl.slice(0,4),extra=sl.slice(4),h='<div class="rig">';
 h+='<div class="rg">'+heads.map(function(s,i){return '<div class="sp"><div class="n1">'+esc(s.name||s.type)+'</div><div class="n2">'+esc(t("filament_n",i+1))+'</div>'+spool(s.color)+'</div>'}).join("");
 h+=extra.length?'<div class="sp"><div class="n1">'+esc(extra[0].name||extra[0].type)+'</div><div class="n2">'+esc(extra.length>1?t("filament_more",5,4+extra.length):t("filament_n",5))+'</div>'+spool(extra[0].color)+'</div>':'<div></div>';
 h+='</div><div class="rg">'+heads.map(function(s,i){var c=String(s.color||"#808080").slice(0,7);return '<div><div class="wire" style="background:'+(dark(c)?'#43464c':esc(c))+'"></div><div class="tc"><div class="t">T'+(i+1)+'</div><div class="z">'+esc(fl[i]?flow(fl[i]):(x.nozzles&&x.nozzles[i]?t("nozzle")+" "+x.nozzles[i]:""))+'</div><div class="f">'+dot(c)+esc(cap1(s.cname||s.type||""))+'</div></div></div>'}).join("");
 h+=extra.length?'<div><div class="wire" style="background:repeating-linear-gradient(#7d8088 0 3px,transparent 3px 6px)"></div><div class="tc ex">'+esc(t("via_ace"))+'</div></div>':'<div></div>';
 h+='</div><div class="kv"><span>'+esc(t("k_printer"))+' <b>'+esc(x.printer||"")+'</b></span>'+(x.process?'<span>'+esc(t("k_process"))+' <b>'+esc(x.process)+'</b></span>':'')+(bed(x)?'<span><b>'+esc(cap1(bed(x)))+'</b></span>':'')+'</div></div>';return h}
function badges(x){return (x&&!x.u1?'<span class="badge"><i class="mk"></i>'+esc(t("badge_not_u1"))+'</span>':'')+(x&&x.foreign?'<span class="badge"><i class="mk"></i>'+esc(t("badge_foreign"))+'</span>':'')}
function renderTpl(){var x=tplOf(),h="";
 $("rig").innerHTML=rigHtml(x);$("rigSub").innerHTML=x?(x===S.tpl?esc(cap1(S.tpl.when))+'. ':esc(t("tpl_current"))+'. ')+esc(t("rig_used"))+badges(x===S.cur?x:null):'';
 if(S.tpl)h+='<label class="choice'+(S.choice=="saved"?" on":"")+'"><input type="radio" name="tc" value="saved"'+(S.choice=="saved"?" checked":"")+'><div><b>'+esc(t("tpl_saved"))+'</b><p>'+esc(cap1(S.tpl.when))+'. '+esc(t("saved_desc"))+'</p></div></label>';
 if(S.cur)h+='<label class="choice'+(S.choice=="current"?" on":"")+'"><input type="radio" name="tc" value="current"'+(S.choice=="current"?" checked":"")+'><div><b>'+esc(t("tpl_current"))+'</b>'+badges(S.cur)+'<p>'+esc(t("current_desc"))+'</p></div></label>';
 if(!S.tpl)h+='<div class="msg info"><i class="mk teal"></i><div class="grow">'+esc(t("tpl_hint"))+'</div></div>';
 $("tplChoices").innerHTML=h;$("dlgRig").innerHTML=rigHtml(x);$("dlgRigTitle").textContent=x===S.tpl?t("tpl_saved"):t("tpl_current");
 each('input[name=tc]',function(r){r.onchange=function(){S.choice=r.value;renderTpl();if(S.token)send({command:"replan",token:S.token,template:S.choice,one_per_plate:S.onePer})}})}
/* ---- 3MF lists ---- */
function fileRow(f,opened){var st=f.error?['grey',t("badge_unreadable")]:f.sliced?['grey',t("badge_sliced")]:f.todo?['',t("badge_todo")]:['grey',t("badge_ok")];
 var off=f.error||f.sliced,info=[f.label,f.printer,f.colors?colors(f.colors):"",f.size?size(f.size):""].filter(Boolean).join(", ");
 var when=opened?t("opened_in_orca"):ago(f.mtime);
 return '<div class="li'+(off?' off':'')+'">'+docIcon(off?'#6A6E76':'#22B3A5',f.sliced?'G-CODE':'3MF')+'<div style="min-width:0"><div class="nm">'+esc(f.name)+'</div><div class="mt">'+esc(info)+'</div></div><div class="st"><i class="mk '+st[0]+'"></i><span><b>'+esc(st[1])+'</b>'+(when?', '+esc(when):'')+'</span></div><button data-p="'+esc(f.path)+'">'+esc(t("analyse"))+'</button></div>'}
function bindAnalyze(root){Array.prototype.forEach.call(root.querySelectorAll("button[data-p]"),function(b){b.onclick=function(){analyze({path:b.getAttribute("data-p")})}})}
function renderOpened(){$("opened").innerHTML=S.opened?'<div class="list" style="margin-bottom:6px">'+fileRow(S.opened,true)+'</div>':'';bindAnalyze($("opened"))}
function renderRecent(){var m=S.rec;if(!m)return;$("recent").innerHTML=m.files.length?m.files.map(function(f){return fileRow(f)}).join(""):'<div class="muted small">'+esc(t("no_3mf",m.folder))+'</div>';bindAnalyze($("recent"))}
function top(){try{window.scrollTo({top:0,behavior:"smooth"})}catch(e){window.scrollTo(0,0)}}
function skeleton(){var h='<div class="th"><span></span><span>'+esc(t("th_color"))+'</span><span>'+esc(t("th_plates"))+'</span><span>'+esc(t("th_profile"))+'</span></div>';
 for(var i=0;i<5;i++)h+='<div class="tr"><span class="sk" style="width:24px;height:24px"></span><div class="cn"><span class="sk" style="width:22px;height:22px;border-radius:50%"></span><span class="sk" style="width:55%;height:12px"></span></div><span class="sk" style="width:34px;height:11px"></span><span class="sk" style="height:36px"></span></div>';
 $("skel").innerHTML=h}
function busyStart(name,text){S.conv=false;S.busy=true;S.busyName=name;S.busyText=text;status();skeleton();view("busy");top()}
function analyze(src,cont){if(S.busy&&!cont)return;src.command="analyze";src.template=S.choice;src.one_per_plate=S.onePer;
 var name=src.name||String(src.path||"").split(/[\\\/]/).pop();if(cont){S.busyText=t("analysing");renderHead()}else busyStart(name,t("analysing"));send(src)}
/* ---- analysis ---- */
function profLabel(p){var ty=p.type&&p.type!="?"&&p.type!=p.name?' · '+p.type:'';return (p.n?p.n+' · ':'')+(p.name||p.type)+ty}
function profOpts(sel){var groups={slot:[],user:[],system:[],other:[]};
 /* tes preregl. : tous, comme dans Orca ; ceux deja dans tes reglages y sont aussi (meme profil, meme numero) */
 S.an.profiles.forEach(function(p,i){var g=groups[p.group||"slot"]||groups.slot;g.push({p:p,i:i,on:i==sel});if(p.group=="slot"&&p.user)groups.user.push({p:{name:p.name,type:p.type},i:i})});
 groups.user.sort(function(a,b){return String(a.p.name).toLowerCase()<String(b.p.name).toLowerCase()?-1:1});
 return groupList(groups).map(function(g){return '<optgroup label="'+esc(g[0])+'">'+g[1].map(function(o){return '<option value="'+o.i+'"'+(o.on?' selected':'')+'>'+esc(profLabel(o.p))+'</option>'}).join("")+'</optgroup>'}).join("")}
/* groupes de la liste des profils : les prereglages systeme d'Orca, un groupe par marque (comme dans Orca) */
function groupList(groups){var out=[];[["slot","grp_slots"],["user","grp_user"],["system","grp_system"],["other","grp_other"]].forEach(function(g){var l=groups[g[0]];if(!l.length)return;
  if(g[0]!="system"){out.push([t(g[1]),l]);return}
  var by={},order=[];l.forEach(function(o){var v=o.p.vendor||"";if(!by[v]){by[v]=[];order.push(v)}by[v].push(o)});
  order.forEach(function(v){out.push([t("grp_system")+(v?" · "+v:""),by[v]])})});return out}
function fil(i){var a=S.an;for(var j=0;j<a.filaments.length;j++)if(a.filaments[j].index==i)return a.filaments[j];return{color:"#808080",name:"?",type:"?",plates:[]}}
function renderAnalysis(a,fresh){S.an=a;S.token=a.token;if(a.one_per_plate!=null)S.onePer=!!a.one_per_plate;var h="";
 a.files.forEach(function(f,fi){
  h+='<div class="grp"'+(fi?' style="margin-top:18px"':'')+'>'+(a.files.length>1?'<h3>'+esc(t("file_n",fi+1))+esc(f.name)+' <span>'+esc(colors(f.colors))+' → '+esc(t("n_filaments",f.slots.length))+'</span></h3>':'');
  h+='<div class="th"><span></span><span>'+esc(t("th_color"))+'</span><span>'+esc(t("th_plates"))+'</span><span>'+esc(t("th_profile"))+'</span></div>';
  var pads=[],nex=0,maxF=a.max_filaments||16;
  /* une ligne par filament du projet : couleur du modele, case libre de la U1 (pad) ou couleur en plus (extra) */
  f.slots.forEach(function(sl,si){var p=a.profiles[sl.base]||{},free=sl.pad||sl.extra;
   var warn=(!free&&sl.ftype&&sl.ftype!="?"&&p.base&&p.base!="?"&&p.base!=sl.ftype)?'<div class="warn"><i class="mk"></i>'+esc(t("warn_material",sl.ftype,p.base))+'</div>':'';
   var col=slotCol(a,sl),extra=[];if(sl.pad)pads.push(sl.n);if(sl.extra)nex++;
   if(!free){if(sl.mixed)extra.push(esc(t("mixed")));if(sl.same>1)extra.push(esc(t("same_n",sl.same)));if(sl.mem!=null&&sl.base==sl.mem)extra.push(esc(t("mem_used")))}
   if(sl.pick)extra.push('<span class="changed">'+esc(t("color_changed"))+'</span> (<a class="reset" data-rf="'+fi+'" data-rs="'+si+'">'+esc(t(free?"color_reset_prof":"color_reset"))+'</a>)');
   var nm=free?t(sl.pad?"pad_name":"extra_name"):sl.name,sub=free?t(sl.pad?"pad_sub":"extra_sub"):[sl.type,sl.preset].filter(Boolean).join(", ");
   h+='<div class="tr'+(sl.pad?' pad':'')+(sl.extra?' ex':'')+'"><span class="num'+(free?' gr':'')+'">'+sl.n+'</span><div class="cn"><input type="color" class="pick" data-cf="'+fi+'" data-cs="'+si+'" value="'+esc(String(col).slice(0,7))+'" title="'+esc(t("pick_color"))+'"><div class="tx"><div><b>'+esc(nm)+'</b> <span class="sub">'+esc(sub)+'</span></div>'+(extra.length?'<div class="sub">'+extra.join(", ")+'</div>':'')+'</div></div>'
    +'<span class="pl">'+(free?'—':esc(sl.plates.join(", ")))+'</span><div><div class="prof"><select data-f="'+fi+'" data-s="'+si+'" aria-label="'+esc(t("th_profile"))+'">'+profOpts(sl.base)+'</select>'
    +(sl.extra?'<button class="rmc" data-rf="'+fi+'" data-rs="'+si+'" title="'+esc(t("remove_color"))+'" aria-label="'+esc(t("remove_color"))+'">×</button>':'')+'</div>'+warn+'</div></div>'});
  if(pads.length)h+='<div class="muted small" style="margin-top:6px">'+esc(pads.length>1?t("pads_many",pads.slice(0,-1).join(", "),pads[pads.length-1]):t("pads_one",pads[0]))+'</div>';
  if(nex)h+='<div class="muted small" style="margin-top:6px">'+esc(t("extras_note"))+'</div>';
  var full=f.slots.length>=maxF;
  h+='<div class="addrow"><button class="addc" data-af="'+fi+'"'+(full?' disabled':'')+'>'+esc(t("add_color"))+'</button>'+(full?'<span class="muted small">'+esc(t("max_colors",maxF))+'</span>':'')+'</div>';
  h+='</div>'});
 $("analysis").innerHTML=h;
 /* left column: the U1 burps, the plates, what to know, one file per plate */
 var ncol=a.filaments.length;$("miniSay").textContent=t("u1_burp",colors(ncol));
 $("plates").innerHTML=a.plates.map(function(p){return '<div class="plate"><div class="pv">'+(p.thumb?'<img src="'+p.thumb+'" alt="">':p.filaments.map(function(i){return dot(fil(i).color,20)}).join(""))+'</div><div class="pl"><span class="num gr">'+p.id+'</span><span>'+esc(/^(plaque|plate)\s*\d+$/i.test(p.name||"")?"":p.name||"")+'</span><span class="ds">'+(p.thumb?p.filaments.map(function(i){return dot(fil(i).color,10)}).join(""):'')+'</span></div></div>'}).join("");
 var nn="",maxf=0;a.files.forEach(function(f){maxf=Math.max(maxf,f.slots.filter(function(s){return!s.pad&&!s.extra}).length)});
 if(maxf>4)nn+='<div><i class="mk"></i><span>'+esc(t("need_ace",maxf))+'</span></div>'+(a.plates.length>1&&!S.onePer?'<div><i class="mk grey"></i><span>'+esc(t("need_ace2"))+'</span></div>':'');
 a.warnings.forEach(function(w){nn+='<div><i class="mk"></i><span>'+esc(w)+'</span></div>'});
 if(a.not_ready)nn+='<div><i class="mk coral"></i><span>'+esc(a.not_ready)+'</span></div>';
 if(!nn)nn='<div><i class="mk grey"></i><span>'+esc(t("all_good"))+'</span></div>';
 $("notes").innerHTML=nn;
 var sup=a.supports;
 $("opWrap").innerHTML=(a.plates.length>1?'<label class="check"><input type="checkbox" id="onePer"'+(S.onePer?" checked":"")+'><span>'+esc(t("one_per_plate"))+'<small>'+esc(t("one_per_hint",a.plates.length))+'</small></span></label>':'')
  +(sup?'<label class="check"><input type="checkbox" id="keepSup"'+(sup.keep?" checked":"")+'><span>'+esc(t("sup_keep"))+'<small>'+esc(cap1(sup.desc.join(", "))+". "+t("sup_hint"))+'</small></span></label>':'');
 $("dest").innerHTML=esc(a.files.length>1?t("created_n",a.dest_hint):t("created_1",a.dest_hint));
 var cv=$("convert");cv.textContent=a.files.length>1?t("convert_n",a.files.length):t("convert");cv.disabled=!!a.not_ready;
 if(V()=="an")renderHead();if(fresh)top();
 var op=$("onePer");if(op)op.onchange=function(){S.onePer=op.checked;send({command:"replan",token:S.token,template:S.choice,one_per_plate:S.onePer})};
 /* supports de l'auteur : nouvelle analyse, tes choix restent (le plugin les reporte, « kept ») */
 var ks=$("keepSup");if(ks)ks.onchange=function(){ks.disabled=true;send({command:"replan",token:S.token,template:S.choice,one_per_plate:S.onePer,supports:ks.checked})};
 each("select[data-f]",function(sel){sel.onchange=function(){a.files[+sel.getAttribute("data-f")].slots[+sel.getAttribute("data-s")].base=+sel.value;renderAnalysis(a)}});
 each("input.pick",function(inp){inp.onchange=function(){var sl=a.files[+inp.getAttribute("data-cf")].slots[+inp.getAttribute("data-cs")],v=inp.value.toUpperCase(),was=sl.pick;delete sl.pick;if(v!=String(slotCol(a,sl)).slice(0,7).toUpperCase())sl.pick=v;else if(!was)return;renderAnalysis(a)}});
 each("button.addc",function(b){b.onclick=function(){var f=a.files[+b.getAttribute("data-af")];if(f.slots.length>=(a.max_filaments||16))return;
  f.slots.push({n:f.slots.length+1,src:[],extra:true,base:nextBase(a,f),pick:null});renderAnalysis(a)}});
 each("button.rmc",function(b){b.onclick=function(){var f=a.files[+b.getAttribute("data-rf")];f.slots.splice(+b.getAttribute("data-rs"),1);f.slots.forEach(function(s,i){s.n=i+1});renderAnalysis(a)}});
 each("a.reset",function(x){x.onclick=function(){delete a.files[+x.getAttribute("data-rf")].slots[+x.getAttribute("data-rs")].pick;renderAnalysis(a)}});planSync(a)}
/* couleur d'une ligne : choisie, sinon celle du modele, sinon (case libre, couleur en plus) celle que donne le profil */
function slotCol(a,sl){return sl.pick||(sl.pad||sl.extra?((a.profiles[sl.base]||{}).fill||"#808080"):sl.color)}
/* couleur envoyee au plugin : rien pour garder celle du modele ou de la case des reglages */
function sendCol(a,sl){if(sl.pick)return sl.pick;if(!(sl.pad||sl.extra))return null;var p=a.profiles[sl.base]||{};return p.group!="slot"&&p.color?String(p.color).slice(0,7):null}
/* plan envoye au plugin : a la conversion, et a chaque changement (le panneau de Preparer montre et convertit le meme) */
function planOf(a){return a.files.map(function(f){return{plates:f.plates,slots:f.slots.map(function(sl){return{src:sl.src,base:sl.base,color:sendCol(a,sl),extra:!!sl.extra}})}})}
var lastPlan="";
/* plan venu du panneau de Preparer : profils, couleurs choisies, couleurs en plus. false s'il ne va pas avec cette analyse. */
function applyPlan(a,files){if(!files||files.length!=a.files.length)return false;
 var next=files.map(function(pf,fi){var model={};a.files[fi].slots.forEach(function(s){if(!s.pad&&!s.extra&&s.src&&s.src.length)model[s.src[0]]=s});
  return (pf.slots||[]).map(function(ps,i){var src=ps.src||[],c=ps.color?String(ps.color).slice(0,7).toUpperCase():null,p=a.profiles[ps.base]||{};
   if(src.length){var sl=model[src[0]];if(!sl)return null;return{sl:sl,base:+ps.base,pick:c}}
   var pc=p.group!="slot"&&p.color?String(p.color).slice(0,7).toUpperCase():null,o={n:i+1,src:[],base:+ps.base,pick:c&&c!=pc?c:null};
   if(ps.extra)o.extra=true;else o.pad=true;return{sl:o,base:+ps.base,pick:o.pick}})});
 if(next.some(function(f){return f.some(function(x){return!x})}))return false;
 a.files.forEach(function(f,fi){f.slots=next[fi].map(function(x,i){var sl=x.sl;sl.base=x.base;if(x.pick)sl.pick=x.pick;else delete sl.pick;if(sl.extra&&sl.pick===undefined)sl.pick=null;sl.n=i+1;return sl})});
 return true}
function planSync(a){if(!a||!a.token)return;var p=planOf(a),k=a.token+"|"+JSON.stringify(p);if(k==lastPlan)return;lastPlan=k;send({command:"plan",token:a.token,files:p})}
/* couleur en plus : prend la premiere case de tes reglages pas encore dans le fichier */
function nextBase(a,f){var used={};f.slots.forEach(function(s){used[s.base]=1});for(var i=0;i<a.profiles.length;i++)if(a.profiles[i].group=="slot"&&!used[i])return i;return f.slots.length?f.slots[f.slots.length-1].base:0}
/* nouveau plan ou nouvelle langue pour le meme fichier : les couleurs en plus restent (profil retrouve par son nom) */
function carryExtras(old,a){var ex=[];
 old.files.forEach(function(f,fi){f.slots.forEach(function(s){if(!s.extra)return;var p=old.profiles[s.base]||{},e={name:p.name,group:p.group,pick:s.pick||null};
  if(fi&&ex.some(function(x){return x.name==e.name&&x.group==e.group&&x.pick==e.pick}))return;ex.push(e)})});
 a.files.forEach(function(f){ex.forEach(function(e){if(f.slots.length>=(a.max_filaments||16))return;var b=-1;
  a.profiles.forEach(function(p,i){if(b<0&&p.name==e.name&&p.group==e.group)b=i});
  f.slots.push({n:f.slots.length+1,src:[],extra:true,base:b<0?nextBase(a,f):b,pick:e.pick})})})}
function keepBases(old,a){if(old.files.length==a.files.length)a.files.forEach(function(f,fi){var o=old.files[fi].slots.filter(function(s){return!s.extra});if(o.length!=f.slots.length)return;
 f.slots.forEach(function(sl,si){sl.base=o[si].base;if(o[si].pick)sl.pick=o[si].pick})});carryExtras(old,a)}
$("convert").onclick=function(){var a=S.an;if(S.busy||!a)return;S.busy=true;S.conv=true;$("cancel").disabled=true;status("info",esc(t("converting")),true);
 send({command:"convert",token:S.token,template:S.choice,files:planOf(a)})};
/* ---- result: open it in Orca in 3 steps ---- */
function renderResult(r){S.res=r;var c=S.copied,h='<div class="gest">';
 h+='<div class="g'+(c?' done':' on')+'"><div class="hd"><span class="num'+(c?' gr':' teal')+'">'+(c?'✓':'1')+'</span><span class="h">'+esc(t("step_copy"))+'</span></div>';
 r.files.forEach(function(f){h+='<div class="file"><code>'+esc(f.path)+'</code><button class="'+(c?'':'go')+'" data-c="'+esc(f.path)+'">'+esc(t("copy_path"))+'</button></div>'+(f.warnings.length?'<div class="notes">'+f.warnings.map(function(w){return '<div><i class="mk"></i><span>'+esc(w)+'</span></div>'}).join("")+'</div>':'')});
 h+='</div><div class="g'+(c?' on':'')+'"><div class="hd"><span class="num'+(c?' teal':' gr')+'">2</span><b>'+esc(t("step_open"))+'</b><span class="k"><kbd>Ctrl</kbd>+<kbd>O</kbd></span></div></div>';
 h+='<div class="g"><div class="hd"><span class="num gr">3</span><b>'+esc(t("step_paste"))+'</b><span class="k"><kbd>Ctrl</kbd>+<kbd>V</kbd> <kbd>'+esc(t("key_enter"))+'</kbd></span></div></div></div>';
 h+='<div class="notes" style="margin-top:16px">'+r.files.map(function(f){return '<div><i class="mk grey"></i><span><b>'+esc(f.name)+'</b> : '+esc(colors(f.colors))+', '+esc(t("n_filaments",f.filaments))+', '+esc(plural(f.plates.length,t("plate1"),t("plateN")))+' '+esc(f.plates.join(", "))+'</span></div>'}).join("")+'</div>';
 $("result").innerHTML=h;$("segs").innerHTML='<i class="'+(c?'done':'on')+'"></i><i class="'+(c?'on':'')+'"></i><i></i>';
 each("button[data-c]",function(b){b.onclick=function(){copy(b.getAttribute("data-c"));S.copied=true;renderResult(r);var nb=document.querySelector('button[data-c="'+CSS.escape(b.getAttribute("data-c"))+'"]');if(nb){nb.textContent=t("copied");setTimeout(function(){nb.textContent=t("copy_path")},1500)}}})}
function copy(x){try{navigator.clipboard.writeText(x)}catch(e){}var ta=document.createElement("textarea");ta.value=x;document.body.appendChild(ta);ta.select();try{document.execCommand("copy")}catch(e){}ta.remove()}
$("back").onclick=function(){if(S.an)view("an")};
$("again").onclick=function(){S.res=null;view("home");top()};
/* Annuler : retour a l'accueil sans convertir ; une analyse en cours est ignoree a son arrivee (reconnue a son
   jeton, donne par sa progression ; sinon la prochaine qui arrive) */
$("cancel").onclick=function(){if(S.conv)return;if(S.upId){send({command:"upload_drop",id:S.upId});S.upId=null;S.busy=false;eatHide()}else if(V()=="busy"&&S.busy){if(S.runTok)S.dead[S.runTok]=1;else S.skip++;S.runTok=null;S.busy=false;eatHide()}S.an=null;S.token=null;S.res=null;status();view("home");top()};
/* ---- converted files folder ---- */
function renderOut(){var o=S.out||{mode:"beside",dir:"",msg:""};each('input[name=out]',function(r){r.checked=r.value==o.mode});
 if(document.activeElement!==$("outDir"))$("outDir").value=o.dir||"";$("outMsg").textContent=o.msg||"";$("outMsg").className=o.error?"err small":"muted small";
 var w=o.mode=="folder"&&o.dir?o.dir:o.mode=="downloads"?t("out_downloads"):t("out_beside");$("fHome").innerHTML=esc(t("out_title"))+' <b>'+esc(w)+'</b>'}
function sendOut(mode){send({command:"outdir",mode:mode,dir:$("outDir").value.trim().replace(/^"|"$/g,"")})}
/* ---- settings window ---- */
function openSet(){S.memForgot=false;renderMem();$("dlg").classList.remove("hidden");var r=document.querySelector('#tplChoices input:checked')||$("capture");if(r)r.focus()}
function closeSet(){$("dlg").classList.add("hidden")}
$("openSet").onclick=openSet;$("editSet").onclick=openSet;$("dlgClose").onclick=closeSet;$("dlgX").onclick=closeSet;
$("dlg").onclick=function(e){if(e.target===$("dlg"))closeSet()};
document.addEventListener("keydown",function(e){if(e.key=="Escape"&&!$("dlg").classList.contains("hidden"))closeSet()});
function renderPmode(){each('input[name=pmode]',function(r){r.checked=r.value==S.pmode})}
/* memoire des choix : profils changes a la main, repris la fois suivante pour la meme couleur */
function renderMem(){var n=S.choices||0;$("memMsg").textContent=S.memForgot&&!n?t("mem_forgot"):(n?t("mem_count",n):"");$("forget").disabled=!n}
function relabel(){statics();renderTpl();renderOpened();renderRecent();renderOut();renderPmode();renderMem();
 if(S.an)renderAnalysis(S.an);if(S.res)renderResult(S.res);if(V()=="busy")skeleton();renderHead()}
orca.onMessage(function(m){if(!m||!m.command)return;if(m.token&&S.dead[m.token])return;
 if(m.command=="state"){$("ver").textContent="v"+m.version;S.tpl=m.saved;S.cur=m.current;if(!S.tpl)S.choice="current";else if(m.choice)S.choice=m.choice;
  if(m.lang_choice)S.langChoice=m.lang_choice;var nl=(m.lang&&L[m.lang])?m.lang:lang;lang=nl;
  S.opened=m.opened;if(m.cap!=null)$("capMsg").textContent=m.cap;if(m.out)S.out=m.out;if(m.panel)S.pmode=m.panel;if(m.choices!=null)S.choices=m.choices;relabel()}
 else if(m.command=="recent"){S.rec=m;renderRecent()}
 else if(m.command=="choices"){S.choices=m.n;renderMem()}
 else if(m.command=="analysis"){
  if(m.relabel){if(S.an&&S.an.token==m.token){keepBases(S.an,m);renderAnalysis(m,false)}return}
  if(S.skip>0){S.skip--;return}
  S.runTok=null;
  if(S.an&&S.an.token==m.token&&!m.kept)carryExtras(S.an,m);   /* nouveau plan du meme fichier (kept : tes choix y sont deja) */
  S.busy=false;S.copied=false;S.res=null;status();renderAnalysis(m,!m.kept);view("an");burpDots(U.mini,modelCols(m));
  if(U.on){u1Set(U.mini,"idle full");eatBurp(m)}else u1Flash(U.mini,"burp",1800)}
 else if(m.command=="plan"){if(S.an&&m.token==S.an.token&&!S.conv&&applyPlan(S.an,m.files)){lastPlan=S.an.token+"|"+JSON.stringify(planOf(S.an));renderAnalysis(S.an)}}
 else if(m.command=="built"){send({command:"write",token:m.token})}
 else if(m.command=="result"){
  if(m.relabel){if(S.res)renderResult(m);return}
  S.busy=false;status();S.conv=false;$("cancel").disabled=false;S.copied=false;renderResult(m);view("res");top()}
 else if(m.command=="progress"){if(S.skip>0&&!S.conv)return;if(m.token&&V()=="busy"&&!S.conv)S.runTok=m.token;S.busy=true;if(V()=="busy"&&!S.conv){S.busyText=m.text;renderHead()}else status("info",esc(m.text),true)}
 else if(m.command=="error"){if(S.skip>0&&!S.conv&&!S.upId){S.skip--;return}S.upId=null;S.runTok=null;var wasConv=S.conv;S.busy=false;S.conv=false;$("cancel").disabled=false;if(V()=="busy")view(S.an&&S.token?"an":"home");status("err",esc(m.text));if(U.on)eatSpit(t("u1_sick"));else u1Flash(U.small,"spit",1700)}});
$("go").onclick=function(){var p=$("path").value.trim().replace(/^"|"$/g,"");if(p)analyze({path:p})};
$("path").onkeydown=function(e){if(e.key=="Enter")$("go").click()};
$("refresh").onclick=function(){$("recent").innerHTML='<div class="muted small">'+esc(t("searching"))+'</div>';send({command:"recent"})};
$("capture").onclick=function(){$("capMsg").textContent="…";send({command:"capture"})};
$("browse").onclick=function(){$("file").click()};
each('input[name=out]',function(r){r.onchange=function(){if(r.value!="folder"||$("outDir").value.trim())sendOut(r.value);else $("outDir").focus()}});
$("outOk").onclick=function(){if($("outDir").value.trim())sendOut("folder")};
each('input[name=pmode]',function(r){r.onchange=function(){S.pmode=r.value;send({command:"panel_mode",mode:r.value})}});
$("forget").onclick=function(){S.memForgot=true;send({command:"forget_choices"})};
$("pshow").onclick=function(){send({command:"panel_show"});$("pshowMsg").textContent=t("pn_shown")};
$("outDir").onkeydown=function(e){if(e.key=="Enter")$("outOk").click()};
$("kofi").onclick=function(){var b=$("kofi");copy("https://ko-fi.com/dragg");b.textContent=t("copied");setTimeout(function(){b.textContent=t("copy_link")},1500)};
$("lang").onchange=function(){var v=$("lang").value;S.langChoice=v;if(L[v]&&v!=lang){lang=v;relabel()}send({command:"lang",lang:v,nav:nav})};
/* ---- the hungry U1 ---- */
var U={small:null,big:null,mini:null,on:false,t0:0,tm:[],smallLock:false},RM=!!(window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches);
function u1New(box){var n=document.importNode($("u1t").content.firstElementChild,true);box.appendChild(n);return n}
function u1Set(svg,st){if(!svg)return;svg.setAttribute("class","u1");void svg.getBoundingClientRect();svg.setAttribute("class","u1 "+st)}
function u1Flash(svg,st,ms){if(!svg||RM)return;if(svg===U.small)U.smallLock=true;u1Set(svg,st);setTimeout(function(){if(svg===U.small)U.smallLock=false;renderHead();if(svg===U.mini)u1Set(U.mini,"idle full")},ms)}
function burpDots(svg,cols){var n=Math.min(cols.length,8),h="";
 for(var i=0;i<n;i++){var a=i/n*Math.PI*2-Math.PI/2,r=n>1?12:0;h+='<circle cx="'+(130+Math.cos(a)*r).toFixed(1)+'" cy="'+(-26+Math.sin(a)*r).toFixed(1)+'" r="'+(n>6?4.5:6)+'" fill="'+cols[i]+'" stroke="#15171a"/>'}
 svg.querySelector(".u-dots").innerHTML=h;var ls=svg.querySelectorAll(".u-pr rect");for(var j=0;j<ls.length&&cols.length;j++)ls[j].setAttribute("fill",cols[j%cols.length])}
function modelCols(m){var cols=[];(m.filaments||[]).forEach(function(x){var c=String(x.color||"").slice(0,7);if(/^#[0-9a-fA-F]{6}$/.test(c)&&cols.indexOf(c)<0)cols.push(c)});return cols}
function eatClear(){U.tm.forEach(clearTimeout);U.tm=[]}
function eatLater(ms,f){U.tm.push(setTimeout(f,ms))}
function eatShow(st,cap){$("eat").classList.remove("hidden");u1Set(U.big,st);$("eatCap").textContent=cap}
function eatHide(){eatClear();U.on=false;$("eat").classList.add("hidden");$("eat").classList.remove("click")}
function eatStart(){eatClear();if(RM){eatHide();return}U.on=true;U.t0=Date.now();$("eat").classList.add("click");eatShow("chomp",t("u1_chomp"));
 eatLater(1000,function(){eatShow("chew",t("u1_chew"))});eatLater(90000,eatHide)}
function eatSpit(cap){eatClear();if(RM){eatHide();return}U.on=true;$("eat").classList.add("click");eatShow("spit",cap);eatLater(1700,eatHide)}
function eatBurp(m){if(!U.on)return;var cols=modelCols(m);
 eatClear();eatLater(Math.max(0,1000-(Date.now()-U.t0)),function(){burpDots(U.big,cols);eatShow("burp",t("u1_burp",colors(cols.length)));eatLater(1800,eatHide)})}
/* Fichier glisse ou choisi : la page ne connait pas son chemin, elle envoie son contenu.
   Par morceaux de CHUNK (16 Mo) pour ne pas figer Orca avec un seul enorme message ; le plugin les recolle. */
var UP=window.M3D_UP={CHUNK:16*1048576,MAXUP:500*1048576};   /* aussi reglable par les tests */
function readFile(f){if(!/\.3mf$/i.test(f.name||"")){status("err",esc(t("not_3mf",f.name)));eatSpit(t("u1_spit"));return}
 if(f.size>UP.MAXUP){status("err",esc(t("too_big",size(f.size))));eatSpit(t("u1_sick"));return}
 if(S.busy)return;
 var n=Math.max(1,Math.ceil(f.size/UP.CHUNK)),id="u"+Date.now().toString(36)+Math.random().toString(36).slice(2,6),i=0;
 eatStart();S.upId=id;busyStart(f.name,n>1?t("reading",f.name,0,n):t("analysing"));
 function fail(){if(S.upId!==id)return;S.upId=null;S.busy=false;send({command:"upload_drop",id:id});view("home");status("err",esc(t("err_upload")));eatSpit(t("u1_sick"))}
 (function next(){if(S.upId!==id)return;
  if(i>=n){S.upId=null;analyze({upload_id:id,name:f.name},true);return}
  var rd=new FileReader();rd.onerror=fail;
  rd.onload=function(){if(S.upId!==id)return;var b=String(rd.result);send({command:"upload_part",id:id,i:i,n:n,data:b.slice(b.indexOf(",")+1)});i++;
   if(n>1){S.busyText=t("reading",f.name,i,n);renderHead()}setTimeout(next,0)};
  rd.readAsDataURL(f.slice(i*UP.CHUNK,Math.min(f.size,(i+1)*UP.CHUNK)))})()}
$("file").onchange=function(){var f=$("file").files[0];if(f)readFile(f);$("file").value=""};
U.small=u1New($("u1small"));U.small.setAttribute("viewBox","0 -50 260 286");U.big=u1New($("eatU"));U.mini=u1New($("mini"));U.mini.setAttribute("viewBox","0 -60 260 296");
$("logo").innerHTML=$("icon").innerHTML;$("logo2").innerHTML=$("icon").innerHTML;
$("u1zone").onclick=function(){if(V()!="busy")$("file").click()};
$("u1zone").onkeydown=function(e){if((e.key=="Enter"||e.key==" ")&&V()!="busy"){e.preventDefault();$("file").click()}};
$("u1zone").onmouseenter=function(){if(V()!="busy"&&!U.smallLock)u1Set(U.small,"hungry")};$("u1zone").onmouseleave=function(){if(!U.smallLock)renderHead()};
$("eat").onclick=function(){if(U.on)eatHide()};
var depth=0;
document.addEventListener("dragenter",function(e){e.preventDefault();depth++;if(!U.on&&!S.busy)eatShow("hungry",t("drop"))});
document.addEventListener("dragover",function(e){e.preventDefault();if(e.dataTransfer)e.dataTransfer.dropEffect="copy"});
document.addEventListener("dragleave",function(){depth=Math.max(0,depth-1);if(!depth&&!U.on)eatHide()});
document.addEventListener("drop",function(e){e.preventDefault();depth=0;if(!U.on)eatHide();var f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];if(f)readFile(f)});
statics();renderHead();renderOut();
send({command:"init",nav:nav});
})();
</script></body></html>
"""


PANEL_PAGE = r"""<!doctype html><html lang="__LANG__"><head><meta charset="utf-8"><style>
/* Panneau de Mange-3MF dans Preparer et Apercu. La U1 (dessin, animations) et la police des titres viennent de l'onglet. */
__FONT__
:root{--ground:#1C1D20;--card:#222428;--edge:#2E3035;--edge2:#3A3D43;--fg:#E9EAEC;--muted:#9C9DA0;--teal:#22B3A5;--teal-ink:#0C2E2A;--teal-card:#1F2A29;--amber:#F0A73C;--coral:#EC6A5E;
color-scheme:dark;font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;color:var(--fg);background:var(--ground)}
.hidden{display:none!important}
#pn{min-height:100%;display:flex;flex-direction:column;align-items:center;text-align:center;padding:14px 16px 16px;gap:10px}
#u{width:min(200px,74%);margin-bottom:-6px}
#u .u1{width:100%}
body[data-v=an] #u,body[data-v=done] #u{width:min(150px,56%)}
.say{font-family:"M3D",system-ui,sans-serif;font-weight:800;font-size:25px;letter-spacing:-.015em;line-height:1.12;word-break:break-word}
.say2{margin:0;color:var(--muted);font-size:13.5px;line-height:1.4;word-break:break-word}
.hint{margin:0;color:var(--muted);font-size:12.5px;line-height:1.4}.hint b{color:var(--fg);font-weight:600}
button{display:inline-flex;align-items:center;justify-content:center;gap:6px;width:100%;font:inherit;font-weight:600;color:var(--fg);background:transparent;border:1px solid var(--edge2);border-radius:8px;height:36px;padding:0 14px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
button:hover{border-color:#5a5e66}button:disabled{opacity:.4;cursor:default}
button.go{background:var(--teal);border-color:var(--teal);color:var(--teal-ink);height:42px;font-size:15px}
button.go:hover{background:#2bc4b5}button.go:disabled:hover{background:var(--teal)}
button:focus-visible,.zone:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
.card{width:100%;display:flex;align-items:center;gap:11px;text-align:left;background:var(--card);border:1px solid var(--edge);border-radius:10px;padding:10px 12px}
.card svg{flex:none}.card b{display:block;font-size:13.5px;font-weight:650;word-break:break-all}
.card small{display:block;color:var(--muted);font-size:12px;line-height:1.35;margin-top:2px}
.zone{width:100%;margin-top:auto;border:2px dashed var(--edge2);border-radius:12px;padding:20px 10px;color:var(--muted);font-size:13.5px;cursor:pointer}
.zone:hover{border-color:rgba(34,179,165,.7);background:rgba(34,179,165,.04)}
body[data-v=drag] .zone{border-color:var(--teal);color:var(--fg);background:var(--teal-card)}
.bar2{width:100%;height:5px;border-radius:3px;background:var(--edge);overflow:hidden;margin-top:auto;flex:none}
.bar2 i{display:block;height:100%;width:35%;background:var(--teal);border-radius:3px;animation:mv 1.1s infinite ease-in-out}
@keyframes mv{0%{margin-left:-35%}100%{margin-left:100%}}
.map{width:100%;display:flex;flex-direction:column;gap:6px;text-align:left;font-size:13.5px}
.map .fh{margin-top:4px;color:var(--muted);font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.map .r{display:flex;flex-wrap:wrap;align-items:center;gap:5px 7px;min-width:0;background:var(--card);border:1px solid var(--edge);border-radius:8px;padding:5px 6px 5px 8px}
.map .nm{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:0 1 auto;min-width:2.6em;max-width:46%}
.map select{flex:1 1 0;min-width:78px;margin-left:auto;height:28px;background:#1f2023;color:var(--fg);border:1px solid var(--edge2);border-radius:7px;padding:0 4px;font:inherit;font-size:12.5px}
.map select:focus-visible{outline:2px solid var(--teal);outline-offset:1px}
.pick{-webkit-appearance:none;appearance:none;width:17px;height:17px;padding:0;margin:0;border:0;border-radius:50%;background:none;cursor:pointer;flex:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.22);transition:box-shadow .15s}
.pick:hover{box-shadow:inset 0 0 0 1px rgba(255,255,255,.22),0 0 0 3px var(--edge2)}
.pick:focus-visible{outline:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.22),0 0 0 3px var(--teal)}
.pick::-webkit-color-swatch-wrapper{padding:0}.pick::-webkit-color-swatch{border:none;border-radius:50%}
.map button.rmc,.map button.rst{width:26px;height:26px;padding:0;flex:none;border-radius:6px;font-size:16px;font-weight:500;color:var(--muted)}
.map button.rmc:hover{color:var(--coral);border-color:var(--coral)}.map button.rst{border-color:transparent;font-size:15px}.map button.rst:hover{color:var(--fg);border-color:var(--edge2)}
.map button.padg{height:auto;font-weight:400;justify-content:flex-start;text-align:left;background:var(--card);border-color:var(--edge);padding:6px 9px 6px 8px}
.map button.padg:hover{border-color:#5a5e66}.map button.padg .chev{margin-left:6px;font-style:normal;color:var(--muted);font-size:16px;line-height:1}
.map button.addc{height:34px;border-style:dashed;color:var(--muted);font-size:13.5px}.map button.addc:hover:not(:disabled){color:var(--fg);border-color:var(--teal)}
.map .full{color:var(--muted);font-size:12px;text-align:center;margin-top:-2px}
.map em{margin-left:auto;padding-left:6px;font-style:normal;color:var(--muted);font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;text-align:right}
.map .free .nm{color:var(--muted)}
.map .m{color:var(--muted);font-size:12px;line-height:1.35;margin:-2px 2px 2px}
.map .sup{display:flex;gap:8px;align-items:flex-start;margin-top:6px;font-size:13px;line-height:1.35;cursor:pointer}
.map .sup input{width:16px;height:16px;margin:1px 0 0;flex:none;accent-color:var(--teal)}
.map .sup small{display:block;color:var(--muted);font-size:12px}
.map .w{display:flex;gap:7px;align-items:flex-start;color:#F3C98A;font-size:12px;line-height:1.35;margin:-2px 2px 2px}.map .w .mk{margin-top:3px}
.num{display:inline-grid;place-items:center;min-width:24px;height:24px;padding:0 5px;border-radius:5px;background:#E9EAEC;color:#16171A;font-weight:700;font-size:13px;flex:none}
.num.gr{background:#3A3D43;color:var(--fg)}
.dot{display:inline-block;width:13px;height:13px;border-radius:50%;flex:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.22)}
.dot.dk{box-shadow:inset 0 0 0 1.5px #8D9096}
.ar{font-style:normal;color:var(--muted);font-size:12px;margin:0 -3px}
.mk{display:inline-block;width:9px;height:9px;border-radius:2px;background:var(--amber);flex:none}.mk.coral{background:var(--coral)}.mk.grey{background:#5A5E66}
.notes{width:100%;display:flex;flex-direction:column;gap:6px;text-align:left}
.notes div{display:flex;gap:8px;align-items:flex-start;font-size:12.5px;line-height:1.4}.notes .mk{margin-top:4px}
body[data-v=done] #notes{order:1}
.paths{width:100%;display:flex;flex-direction:column;gap:8px}
code{display:block;width:100%;background:var(--card);border:1px solid var(--edge);border-radius:8px;padding:9px 10px;font:12px/1.4 ui-monospace,Consolas,monospace;word-break:break-all;text-align:left;color:var(--fg)}
.foot{width:100%;display:flex;flex-direction:column;gap:8px}
.pmode{width:100%;display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:4px 8px;margin-top:auto;padding-top:8px;color:var(--muted);font-size:12px}
body[data-v=rest] .pmode{margin-top:0}
.pmode select{height:26px;max-width:100%;background:#1f2023;color:var(--fg);border:1px solid var(--edge2);border-radius:6px;padding:0 4px;font:inherit;font-size:12px}
.pmode select:focus-visible{outline:2px solid var(--teal);outline-offset:1px}
__U1CSS__
</style></head><body data-v="rest"><div id="pn">
<div id="u"></div>
<div class="say" id="say"></div>
<p class="say2" id="say2"></p>
<div class="card hidden" id="card"></div>
<div class="map hidden" id="map"></div>
<div class="notes hidden" id="notes"></div>
<div class="paths hidden" id="paths"></div>
<div class="zone hidden" id="zone" role="button" tabindex="0"></div>
<div class="bar2 hidden" id="bar"><i></i></div>
<div class="foot" id="foot">
 <button class="go hidden" id="eat" data-t="pn_eat"></button>
 <button class="hidden" id="later" data-t="pn_later"></button>
 <button class="go hidden" id="convert"></button>
 <button class="go hidden" id="copy" data-t="copy_path"></button>
 <button class="hidden" id="cancel" data-t="cancel"></button>
 <button class="hidden" id="ok" data-t="pn_ok"></button>
</div>
<p class="hint hidden" id="hint"></p>
<label class="pmode hidden" id="pmode"><span data-t="pn_mode_label"></span><select id="pmodeSel"><option value="panel" data-t="pn_opt_panel"></option><option value="notif" data-t="pn_opt_notif"></option><option value="off" data-t="pn_opt_off"></option></select></label>
<input type="file" id="file" accept=".3mf" class="hidden">
</div>
__U1SVG__
<script>
(function(){
var L=__TEXTS__;
var nav=(navigator.languages&&navigator.languages[0])||navigator.language||"";
var lang="__LANG__";if(!L[lang])lang="en";
function t(k){var a=arguments,s=L[lang]&&L[lang][k];if(s==null)s=L.en&&L.en[k];if(s==null)s=k;
 return String(s).replace(/\{(\d+)\}/g,function(_,i){var v=a[+i+1];return v==null?"":v})}
/* v : ecran du panneau. rest (j'ai faim), drag (un fichier passe dessus), offer (Miam : projet ouvert pas regle pour la U1),
   busy (analyse), an (Burp : couleurs et profils), conv (conversion), done (c'est pret), err (pouah). */
var P={v:"rest",back:"rest",mode:"panel",offer:null,an:null,files:[],padsOpen:{},res:null,text:"",err:"",upId:null,tok:null,dead:{}};
var UP=window.M3D_UP={CHUNK:16*1048576,MAXUP:500*1048576};   /* comme l'onglet : morceaux de 16 Mo, 500 Mo au plus */
var PARTS={rest:["zone","pmode"],drag:["zone"],offer:["card","eat","later","hint","pmode"],busy:["bar","cancel"],an:["map","notes","convert","hint"],
 conv:["bar"],done:["paths","copy","notes","hint"],err:["ok"],bye:[]};
var ALL=["card","map","notes","paths","zone","bar","eat","later","convert","copy","cancel","ok","hint","pmode"];
function $(id){return document.getElementById(id)}
function esc(x){var d=document.createElement("span");d.textContent=x==null?"":String(x);return d.innerHTML}
function send(m){orca.postMessage(m)}
function show(id,on){$(id).classList.toggle("hidden",!on)}
function cap1(s){s=String(s||"");return s.charAt(0).toUpperCase()+s.slice(1)}
function colors(n){return n+" "+(n>1?t("colorN"):t("color1"))}
function size(b){return b>1048576?(b/1048576).toFixed(1)+" "+t("mb"):Math.max(1,Math.round(b/1024))+" "+t("kb")}
function dark(c){c=String(c||"").replace("#","");if(c.length<6)return false;var r=parseInt(c.substr(0,2),16),g=parseInt(c.substr(2,2),16),b=parseInt(c.substr(4,2),16);return (r*299+g*587+b*114)/1000<45}
function dot(c){c=String(c||"#808080").slice(0,7);return '<i class="dot'+(dark(c)?' dk':'')+'" style="background:'+esc(c)+'"></i>'}
function note(kind,x){return '<div><i class="mk'+(kind?' '+kind:'')+'"></i><span>'+esc(x)+'</span></div>'}
function docIcon(){return '<svg width="30" height="35" viewBox="0 0 40 46" aria-hidden="true"><path d="M3 4a3 3 0 0 1 3-3h20l11 11v29a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3z" fill="#E9EAEC"/><path d="M26 1v11h11" fill="#C9CBCF"/><rect x="3" y="26" width="34" height="11" fill="#22B3A5"/><text x="20" y="34.6" text-anchor="middle" font-family="system-ui,sans-serif" font-weight="800" font-size="9" fill="#fff">3MF</text><path d="M20 8l6 3.4-6 3.4-6-3.4z" fill="#2B7BE4"/><path d="M14 11.4l6 3.4v6.6l-6-3.4z" fill="#E53935"/><path d="M26 11.4l-6 3.4v6.6l6-3.4z" fill="#F2C230"/></svg>'}
function copy(x){try{navigator.clipboard.writeText(x)}catch(e){}var ta=document.createElement("textarea");ta.value=x;document.body.appendChild(ta);ta.select();try{document.execCommand("copy")}catch(e){}ta.remove()}
function flash(b){b.textContent=t("copied");setTimeout(function(){b.textContent=t("copy_path")},1500)}
function statics(){document.documentElement.lang=lang;
 Array.prototype.forEach.call(document.querySelectorAll("[data-t]"),function(e){e.textContent=t(e.getAttribute("data-t"))});$("zone").setAttribute("title",t("u1_title"))}
/* ---- la U1 ---- */
var U=document.importNode($("u1t").content.firstElementChild,true);$("u").appendChild(U);U.setAttribute("viewBox","0 -60 260 296");
var RM=!!(window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches);
function u1Set(st){U.setAttribute("class","u1");void U.getBoundingClientRect();U.setAttribute("class","u1 "+st)}
function modelCols(a){var cols=[];((a&&a.filaments)||[]).forEach(function(x){var c=String(x.color||"").slice(0,7);if(/^#[0-9a-fA-F]{6}$/.test(c)&&cols.indexOf(c)<0)cols.push(c)});return cols}
function burpDots(cols){var n=Math.min(cols.length,8),h="";
 for(var i=0;i<n;i++){var a=i/n*Math.PI*2-Math.PI/2,r=n>1?12:0;h+='<circle cx="'+(130+Math.cos(a)*r).toFixed(1)+'" cy="'+(-26+Math.sin(a)*r).toFixed(1)+'" r="'+(n>6?4.5:6)+'" fill="'+cols[i]+'" stroke="#15171a"/>'}
 U.querySelector(".u-dots").innerHTML=h;var ls=U.querySelectorAll(".u-pr rect");for(var j=0;j<ls.length&&cols.length;j++)ls[j].setAttribute("fill",cols[j%cols.length])}
function u1For(v,quiet){
 if(v=="an"||v=="done")burpDots(modelCols(P.an));
 if(v=="an"&&!quiet&&!RM){u1Set("burp");setTimeout(function(){if(P.v=="an")u1Set("idle full")},1800);return}
 if(v=="err"&&!quiet&&!RM){u1Set("spit");setTimeout(function(){if(P.v=="err")u1Set("idle")},1700);return}
 var want=v=="drag"||v=="offer"?"hungry":v=="busy"||v=="conv"?"chew":v=="an"||v=="done"?"idle full":"idle";
 if(U.getAttribute("class")!="u1 "+want)u1Set(want)}
/* ---- ce que montre chaque ecran ---- */
function fil(a,i){for(var j=0;j<a.filaments.length;j++)if(a.filaments[j].index==i)return a.filaments[j];return{color:"#808080",name:"?",base:"?"}}
/* Couleurs et profils, memes regles que l'onglet : pick = couleur choisie ; pad = case libre de la U1 ; extra = couleur en plus.
   Chaque changement part au plugin (« plan »), qui le donne a l'onglet ; ce que l'onglet change revient ici. */
function fromAnalysis(a){return a.files.map(function(f){return{plates:f.plates,slots:f.slots.map(function(s){return{src:s.src||[],base:s.base,pick:s.pick||null,pad:!!s.pad,extra:!!s.extra}})}})}
function presetCol(p){return p&&p.group!="slot"&&p.color?String(p.color).slice(0,7):null}
/* plan de l'onglet -> lignes du panneau (null s'il ne va pas avec cette analyse) */
function fromPlan(a,files){if(!a||!files||files.length!=a.files.length)return null;var ok=true;
 var out=files.map(function(pf,fi){var known={};a.files[fi].slots.forEach(function(s){if(s.src&&s.src.length)known[s.src[0]]=1});
  return{plates:pf.plates||a.files[fi].plates,slots:(pf.slots||[]).map(function(ps){var src=ps.src||[],c=ps.color?String(ps.color).slice(0,7).toUpperCase():null;
   if(src.length){if(!known[src[0]])ok=false;return{src:src,base:+ps.base,pick:c,pad:false,extra:false}}
   var pc=presetCol(a.profiles[ps.base]);return{src:[],base:+ps.base,pick:c&&c!=String(pc).toUpperCase()?c:null,pad:!ps.extra,extra:!!ps.extra}})}});
 return ok?out:null}
/* couleur d'une ligne : choisie, sinon celle du modele, sinon (case libre, couleur en plus) celle que donne le profil */
function slotCol(a,s){if(s.pick)return s.pick;if(s.pad||s.extra)return (a.profiles[s.base]||{}).fill||"#808080";return fil(a,s.src[0]).color}
/* plan envoye au plugin : exactement celui que l'onglet enverrait */
function planOf(){var a=P.an;return P.files.map(function(f){return{plates:f.plates,slots:f.slots.map(function(s){
 return{src:s.src,base:s.base,color:s.pick?s.pick:(s.pad||s.extra)?presetCol(a.profiles[s.base]):null,extra:!!s.extra}})}})}
/* couleur en plus : la premiere case de tes reglages pas encore dans le fichier */
function nextBase(a,f){var used={};f.slots.forEach(function(s){used[s.base]=1});for(var i=0;i<a.profiles.length;i++)if(a.profiles[i].group=="slot"&&!used[i])return i;return f.slots.length?f.slots[f.slots.length-1].base:0}
/* liste des profils : tes reglages, tes prereglages (tous, comme dans Orca), ceux d'une autre imprimante */
function profOpts(sel){var a=P.an,groups={slot:[],user:[],system:[],other:[]};
 a.profiles.forEach(function(p,i){var g=groups[p.group||"slot"]||groups.slot;g.push({p:p,i:i,on:i==sel});if(p.group=="slot"&&p.user)groups.user.push({p:p,i:i})});
 groups.user.sort(function(x,y){return String(x.p.name).toLowerCase()<String(y.p.name).toLowerCase()?-1:1});
 return groupList(groups).map(function(g){return '<optgroup label="'+esc(g[0])+'">'
  +g[1].map(function(o){return '<option value="'+o.i+'"'+(o.on?' selected':'')+'>'+esc(o.p.name||o.p.type||"?")+'</option>'}).join("")+'</optgroup>'}).join("")}
/* groupes de la liste des profils : les prereglages systeme d'Orca, un groupe par marque (comme dans Orca) */
function groupList(groups){var out=[];[["slot","grp_slots"],["user","grp_user"],["system","grp_system"],["other","grp_other"]].forEach(function(g){var l=groups[g[0]];if(!l.length)return;
  if(g[0]!="system"){out.push([t(g[1]),l]);return}
  var by={},order=[];l.forEach(function(o){var v=o.p.vendor||"";if(!by[v]){by[v]=[];order.push(v)}by[v].push(o)});
  order.forEach(function(v){out.push([t("grp_system")+(v?" · "+v:""),by[v]])})});return out}
function range(ns){var seq=ns.every(function(n,i){return!i||n==ns[i-1]+1});return seq&&ns.length>1?ns[0]+"–"+ns[ns.length-1]:ns.join(", ")}
function rowsHtml(){var a=P.an,maxF=a.max_filaments||16,many=P.files.length>1,h="";
 P.files.forEach(function(f,fi){var af=a.files[fi]||{},pads=[],at='data-f="'+fi+'" data-s="';
  if(many)h+='<div class="fh">'+esc(t("file_n",fi+1)+(af.name||""))+'</div>';
  f.slots.forEach(function(s,si){var n=si+1,p=a.profiles[s.base]||{},free=s.pad||s.extra;
   /* cases libres gardees telles quelles : une seule ligne « tes bobines », a ouvrir pour les changer */
   if(s.pad&&!s.pick&&s.base==si&&p.group=="slot"&&!P.padsOpen[fi]){pads.push(n);return}
   var m=free?null:fil(a,s.src[0]),mc=m?String(m.color||"#808080").slice(0,7):"",col=String(slotCol(a,s)).slice(0,7);
   var warn=m&&m.base&&m.base!="?"&&p.base&&p.base!="?"&&p.base!=m.base,mem=!free&&memOf(af,s);
   h+='<div class="r'+(free?' free':'')+'"><span class="num'+(free?' gr':'')+'">'+n+'</span>'
    +(s.pick&&!free?dot(mc)+'<i class="ar">→</i>':'')
    +'<input type="color" class="pick" '+at+si+'" value="'+esc(col)+'" title="'+esc(t("pick_color"))+'" aria-label="'+esc(t("pick_color"))+' '+n+'">'
    +'<span class="nm">'+esc(free?t(s.pad?"pad_name":"extra_name"):cap1(m.name))+'</span>'
    +(s.pick?'<button class="rst" '+at+si+'" title="'+esc(t(free?"color_reset_prof":"color_reset"))+'" aria-label="'+esc(t(free?"color_reset_prof":"color_reset"))+'">↺</button>':'')
    +'<select '+at+si+'" aria-label="'+esc(t("th_profile"))+' '+n+'">'+profOpts(s.base)+'</select>'
    +(s.extra?'<button class="rmc" '+at+si+'" title="'+esc(t("remove_color"))+'" aria-label="'+esc(t("remove_color"))+'">×</button>':'')+'</div>'
    +(warn?'<div class="w"><i class="mk"></i><span>'+esc(t("warn_material",m.base,p.base))+'</span></div>':'')
    +(mem?'<div class="m">'+esc(t("mem_used"))+'</div>':'')});
  if(pads.length)h+='<button class="r free padg" data-f="'+fi+'" title="'+esc(t("pn_pads_edit"))+'"><span class="num gr">'+esc(range(pads))+'</span><span class="nm">'
   +esc(pads.length>1?t("pn_pads"):t("pad_name"))+'</span><em>'+esc(pads.length>1?t("pn_keep_n"):t("pn_keep_1"))+'</em><i class="chev">›</i></button>';
  var full=f.slots.length>=maxF;
  h+='<button class="addc" data-f="'+fi+'"'+(full?' disabled':'')+'>'+esc(t("add_color"))+'</button>'+(full?'<div class="full">'+esc(t("max_colors",maxF))+'</div>':'')});
 var sup=a.supports;if(sup)h+='<label class="sup"><input type="checkbox" id="keepSup"'+(sup.keep?' checked':'')+'><span>'+esc(t("sup_keep"))+'<small>'+esc(cap1(sup.desc.join(", "))+". "+t("sup_hint"))+'</small></span></label>';
 return h}
/* profil repris de la memoire des choix (meme couleur, meme matiere que la derniere fois) */
function memOf(af,s){var r=null;(af.slots||[]).forEach(function(x){if(x.src&&x.src.length&&s.src.length&&x.src[0]==s.src[0])r=x});return!!(r&&r.mem!=null&&r.mem==s.base)}
function notesHtml(){var a=P.an,h="",maxf=0,ex=0;
 P.files.forEach(function(f){maxf=Math.max(maxf,f.slots.filter(function(s){return!s.pad&&!s.extra}).length);ex+=f.slots.filter(function(s){return s.extra}).length});
 if(maxf>4)h+=note("",t("need_ace",maxf));
 if(ex)h+=note("grey",t("extras_note"));
 (a.warnings||[]).forEach(function(w){h+=note("",w)});
 if(a.not_ready)h+=note("coral",a.not_ready);
 return h}
function pathsHtml(){var r=P.res,many=r.files.length>1,h="";
 r.files.forEach(function(f,i){h+='<code>'+esc(f.path)+'</code>'+(many?'<button data-c="'+i+'">'+esc(t("copy_path"))+'</button>':'')});return h}
function offerInfo(o){return [o.label||cap1(t("another_slicer")),o.printer].filter(Boolean).join(", ")}
function render(quiet){var v=P.v,a=P.an,say="",say2="",hint="";
 ALL.forEach(function(id){show(id,PARTS[v].indexOf(id)>=0)});
 if(v=="rest"){say=t("say_idle");say2=t(P.mode=="panel"?"pn_rest2":"pn_rest2b");$("zone").textContent=t("pn_zone")}
 else if(v=="drag"){say=t("pn_drag");say2=t("pn_drag2");$("zone").textContent=t("pn_zone_drag")}
 else if(v=="offer"){var o=P.offer||{};say=t("pn_offer");say2=t("pn_offer2");hint=esc(t("pn_offer_hint"));
  $("card").innerHTML=docIcon()+'<div style="min-width:0"><b>'+esc(o.name)+'</b><small>'+esc(offerInfo(o))+'</small></div>'}
 else if(v=="busy"){say=t("pn_chew");say2=P.text||t("analysing")}
 else if(v=="an"&&a){say=t("u1_burp",colors(a.filaments.length));$("map").innerHTML=rowsHtml();
  var nh=notesHtml();$("notes").innerHTML=nh;show("notes",!!nh);
  var c=$("convert");c.textContent=a.files.length>1?t("convert_n",a.files.length):t("convert");c.disabled=!!a.not_ready;hint=esc(t("pn_an_hint"))}
 else if(v=="conv"){say=t("pn_conv");say2=P.text||t("p_converting")}
 else if(v=="done"&&P.res){var r=P.res,w=[];say=t("pn_done");$("paths").innerHTML=pathsHtml();show("copy",r.files.length==1);
  r.files.forEach(function(f){(f.warnings||[]).forEach(function(x){w.push(note("",x))})});$("notes").innerHTML=w.join("");show("notes",w.length>0);
  var hp=t("pn_done_hint","\u0001").split("\u0001");hint=esc(hp[0])+'<b>'+esc(t("pn_menu"))+'</b>'+esc(hp[1]||"")}
 else if(v=="err"){say=t("pn_err");say2=P.err}
 else if(v=="bye"){say=t("pn_bye");say2=t("pn_bye2")}
 $("pmodeSel").value=P.mode;
 $("say").textContent=say;$("say2").textContent=say2;show("say2",!!say2);$("hint").innerHTML=hint;if(!hint)show("hint",false);
 show("foot",["eat","later","convert","copy","cancel","ok"].some(function(id){return!$(id).classList.contains("hidden")}));
 u1For(v,quiet)}
function view(v,quiet){var was=P.v;P.v=v;document.body.setAttribute("data-v",v);render(quiet);if(was!=v&&v!="drag")send({command:"view",v:v})}
/* ---- messages du plugin ---- */
orca.onMessage(function(m){if(!m||!m.command)return;var c=m.command,v=P.v,mine=!!(m.token&&P.an&&m.token==P.an.token);
 if(m.token&&P.dead[m.token])return;                 /* travail annule */
 if(c=="hello"){if(m.lang&&L[m.lang])lang=m.lang;if(m.mode)P.mode=m.mode;statics();render(true)}
 else if(c=="offer"){P.offer=m.file;if(v!="busy"&&v!="conv"&&!P.upId)view("offer",!!m.replay)}
 else if(c=="rest"){P.offer=null;if(v!="busy"&&v!="conv"&&!P.upId){P.an=null;P.plan=null;P.res=null;view("rest",true)}}
 else if(c=="progress"){if(m.token&&(v=="busy"||m.replay))P.tok=m.token;
  if(m.replay){P.text=m.text;view(P.an?"conv":"busy",true)}
  else if(v=="busy"||v=="conv"){P.text=m.text;render(true)}
  else if(mine&&(v=="an"||v=="done")){P.text=m.text;view("conv")}}   /* l'onglet convertit ce que montre le panneau */
 else if(c=="analysis"){
  if(m.relabel){if(mine){P.an=m;if(v=="an")render(true)}return}
  if(m.replay||v=="busy"||mine){P.an=m;P.files=fromAnalysis(m);P.padsOpen={};P.res=null;P.text="";P.tok=m.token;view("an",!!m.replay||(mine&&v=="an"))}}
 else if(c=="plan"){if(mine){var pf=fromPlan(P.an,m.files);if(pf){P.files=pf;if(v=="an")render(true)}}}
 else if(c=="built"){send({command:"write",token:m.token})}
 else if(c=="result"){
  if(m.relabel){if(P.res){P.res=m;if(v=="done")render(true)}return}
  if(m.replay||v=="conv"||mine){P.res=m;P.text="";view("done",!!m.replay)}}
 else if(c=="error"){if(v=="busy"||v=="conv"||P.upId){P.upId=null;P.back=v=="conv"&&P.an?"an":"rest";P.err=m.text;view("err")}}});
/* ---- gestes ---- */
$("eat").onclick=function(){P.text=t("analysing");P.tok=null;view("busy");send({command:"eat"})};
$("later").onclick=function(){P.offer=null;view("rest",true);send({command:"later"})};
$("cancel").onclick=function(){if(P.upId){send({command:"upload_drop",id:P.upId});P.upId=null}if(P.tok)P.dead[P.tok]=1;P.tok=null;view("rest",true);send({command:"cancel"})};
$("convert").onclick=function(){var a=P.an;if(!a||a.not_ready||P.v!="an")return;P.text=t("p_converting");view("conv");send({command:"convert",token:a.token,files:planOf()})};
function slotAt(el){var f=P.files[+el.getAttribute("data-f")];return f&&f.slots[+el.getAttribute("data-s")]}
function edited(){render(true);send({command:"plan",token:P.an.token,files:planOf()})}
$("map").addEventListener("change",function(e){var el=e.target;
 if(el.id=="keepSup"){if(P.v=="an"&&P.an){el.disabled=true;send({command:"replan",token:P.an.token,supports:el.checked})}return}
 var s=slotAt(el);if(!s||P.v!="an")return;
 if(el.tagName=="SELECT"){s.base=+el.value;edited()}
 else if(el.classList.contains("pick")){var v=String(el.value).toUpperCase(),was=s.pick;s.pick=null;
  if(v!=String(slotCol(P.an,s)).slice(0,7).toUpperCase())s.pick=v;else if(!was)return;edited()}});
$("map").addEventListener("click",function(e){var b=e.target.closest&&e.target.closest("button");if(!b||P.v!="an")return;var fi=+b.getAttribute("data-f"),f=P.files[fi];if(!f)return;
 if(b.classList.contains("addc")){if(f.slots.length>=(P.an.max_filaments||16))return;f.slots.push({src:[],base:nextBase(P.an,f),pick:null,pad:false,extra:true});edited()}
 else if(b.classList.contains("rmc")){f.slots.splice(+b.getAttribute("data-s"),1);edited()}
 else if(b.classList.contains("rst")){var s=slotAt(b);if(s){s.pick=null;edited()}}
 else if(b.classList.contains("padg")){P.padsOpen[fi]=1;render(true)}});
$("copy").onclick=function(){var f=P.res&&P.res.files[0];if(f){copy(f.path);flash($("copy"))}};
$("paths").onclick=function(e){var b=e.target.closest&&e.target.closest("button[data-c]");if(b&&P.res){copy(P.res.files[+b.getAttribute("data-c")].path);flash(b)}};
$("ok").onclick=function(){P.err="";view(P.back=="an"&&P.an?"an":"rest",true)};
/* Reglage, aussi dans l'onglet (Reglages) : la U1 ici, une notification seulement, ou rien. Sans le panneau, il se range. */
$("pmodeSel").onchange=function(){var v=$("pmodeSel").value;P.mode=v;send({command:"panel_mode",mode:v});
 if(v!="panel"){view("bye");setTimeout(function(){if(P.v=="bye"&&P.mode!="panel")orca.close()},2600)}};
$("zone").onclick=function(){if(P.v=="rest")$("file").click()};
$("zone").onkeydown=function(e){if((e.key=="Enter"||e.key==" ")&&P.v=="rest"){e.preventDefault();$("file").click()}};
$("zone").onmouseenter=function(){if(P.v=="rest")u1Set("hungry")};$("zone").onmouseleave=function(){if(P.v=="rest")u1Set("idle")};
$("file").onchange=function(){var f=$("file").files[0];if(f)readFile(f);$("file").value=""};
/* Fichier glisse ou choisi : la page ne connait pas son chemin, elle l'envoie par morceaux (comme l'onglet, numeros « p… »). */
function canEat(){return P.v!="busy"&&P.v!="conv"&&!P.upId}
function readFile(f){if(!/\.3mf$/i.test(f.name||"")){P.err=t("not_3mf",f.name);P.back="rest";view("err");return}
 if(f.size>UP.MAXUP){P.err=t("too_big",size(f.size));P.back="rest";view("err");return}
 var n=Math.max(1,Math.ceil(f.size/UP.CHUNK)),id="p"+Date.now().toString(36)+Math.random().toString(36).slice(2,6),i=0;
 P.upId=id;P.tok=null;P.offer=null;P.text=n>1?t("reading",f.name,0,n):t("analysing");view("busy");
 function fail(){if(P.upId!==id)return;P.upId=null;send({command:"upload_drop",id:id});P.err=t("err_upload");P.back="rest";view("err")}
 (function next(){if(P.upId!==id)return;
  if(i>=n){P.upId=null;send({command:"analyze",upload_id:id,name:f.name});return}
  var rd=new FileReader();rd.onerror=fail;
  rd.onload=function(){if(P.upId!==id)return;var b=String(rd.result);send({command:"upload_part",id:id,i:i,n:n,data:b.slice(b.indexOf(",")+1)});i++;
   if(n>1){P.text=t("reading",f.name,i,n);if(P.v=="busy")render(true)}setTimeout(next,0)};
  rd.readAsDataURL(f.slice(i*UP.CHUNK,Math.min(f.size,(i+1)*UP.CHUNK)))})()}
var depth=0;
document.addEventListener("dragenter",function(e){e.preventDefault();depth++;if(canEat()&&P.v!="drag"){P.back=P.v;view("drag",true)}});
document.addEventListener("dragover",function(e){e.preventDefault();if(e.dataTransfer)e.dataTransfer.dropEffect=canEat()?"copy":"none"});
document.addEventListener("dragleave",function(){depth=Math.max(0,depth-1);if(!depth&&P.v=="drag")view(P.back,true)});
document.addEventListener("drop",function(e){e.preventDefault();depth=0;if(P.v=="drag")view(P.back,true);
 var f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];if(f&&canEat())readFile(f)});
statics();render(true);
send({command:"init",nav:nav});
})();
</script></body></html>
"""


def page_html(lang=None):
    """Page de l'onglet, avec tous les textes et la langue de depart."""
    texts = json.dumps(TEXTS).replace("</", "<\\/")
    return PAGE.replace("__TEXTS__", texts).replace("__LANG__", lang or current_language())


def _page_part(start, end, keep_end=False):
    """Morceau de la page de l'onglet repris tel quel par le panneau (la U1, ses animations, la police)."""
    a = PAGE.index(start)
    b = PAGE.index(end, a + len(start))
    return PAGE[a:b + (len(end) if keep_end else 0)]


def panel_html(lang=None):
    """Page du panneau de Preparer : ses textes dans chaque langue, la U1 et la police de l'onglet."""
    keys = set(re.findall(r'"(\w+)"', PANEL_PAGE)) & set(TEXTS[DEFAULT_LANG])
    texts = json.dumps({code: {k: v for k, v in t.items() if k in keys} for code, t in TEXTS.items()})
    return (PANEL_PAGE.replace("__TEXTS__", texts.replace("</", "<\\/"))
            .replace("__LANG__", lang or current_language())
            .replace("__FONT__", _page_part("@font-face{", "}", True))
            .replace("__U1CSS__", _page_part(".u1{display:block;height:auto}", "</style>"))
            .replace("__U1SVG__", _page_part('<template id="u1t">', "</template>", True)))


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FEFEFE" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
<path d="M5.4 6V4.1h2.2V6M9 6V4.1h2.2V6M12.6 6V4.1h2.2V6M16.2 6V4.1h2.2V6"/>
<rect x="3.5" y="6" width="17" height="15" rx="3.5"/>
<circle cx="9" cy="10.4" r="2"/><circle cx="15" cy="10.4" r="2"/>
<rect x="6.5" y="13.6" width="11" height="4.9" rx="1.5"/>
<path d="M8.2 13.6l.8 1.5.8-1.5M14.2 13.6l.8 1.5.8-1.5"/>
<circle cx="9.5" cy="10.8" r=".55" fill="#FEFEFE" stroke="none"/><circle cx="14.5" cy="10.8" r=".55" fill="#FEFEFE" stroke="none"/></svg>"""


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
        self.uploads = {}       # fichier glisse envoye par morceaux : id -> {"n", "parts", "size"}
        self.opened = None      # projet ouvert dans Orca s'il vient d'ailleurs
        self.cap_key = ""       # dernier message de « Memoriser » (cle de TEXTS)
        self.replay = {}        # derniers messages "progress" / "analysis" / "result" (textes a traduire)
        self.lang_choice = None # "auto" ou une langue de TEXTS (options.json, lu a la demande)
        self.orca_lang = ""     # langue de l'interface d'Orca
        self.nav = ""           # langue du navigateur de la page (secours)
        self.out_key = ""       # dernier message du choix de dossier (cle de TEXTS)
        self.out_arg = ""
        self.panel = None       # la U1 dans le panneau de Preparer (Panel, plus bas)

    def attach(self, page):
        if page is not None:
            self.page = page

    def post(self, data):
        """Envoie a l'onglet et, pour le travail qu'il suit, au panneau de Preparer. data["_origin"] : qui
        a lance l'action (« panel » : le panneau). L'onglet recoit aussi les analyses et les resultats du
        panneau (pour y changer un profil ou revoir le resultat), mais pas sa progression, ses erreurs
        ni « built » : c'est le panneau qui ecrit ce qu'il a converti (l'onglet s'il est ferme)."""
        data = dict(data)
        origin = data.pop("_origin", None)
        cmd = data.get("command")
        to_panel = self.panel is not None and self.panel.relay(data, origin)
        if origin == "panel" and (cmd in ("progress", "error") or (cmd == "built" and to_panel)):
            return
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
        if self.panel is not None:
            self.panel.relabel()

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
                    replay = [self.replay[k] for k in ("analysis", "plan", "result", "progress") if k in self.replay]
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
            elif cmd == "upload_part":
                self.upload_part(msg)
            elif cmd == "upload_drop":
                self.drop_upload(msg.get("id"))
            elif cmd == "analyze":
                self.start_analyze(msg)
            elif cmd == "plan":
                self.set_plan(msg)
            elif cmd == "panel_mode":
                self.choose_panel_mode(msg.get("mode"))
            elif cmd == "panel_show":
                if self.panel is None or not self.panel.open():
                    raise ConvertError(tr("err_panel"))
            elif cmd == "replan":
                self.start_replan(msg)
            elif cmd == "forget_choices":
                self.forget_choices()
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
                   "lang": current_language(), "lang_choice": self.language_choice(), "panel": panel_mode(),
                   "choices": len(load_choices()),
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

    def upload_part(self, msg):
        """Un morceau d'un fichier glisse ou choisi dans la page (la page ne connait pas son chemin).
        Un gros fichier arrive en plusieurs messages de 16 Mo au plus, pour ne pas figer Orca ; un
        envoi a la fois par page (ceux du panneau sont numerotes « p… ») : un nouveau remplace l'ancien."""
        uid = str(msg.get("id") or "")
        i, n = int(msg.get("i", -1)), int(msg.get("n", 0))
        if not uid or not 0 <= i < n <= UPLOAD_PARTS_MAX:
            return
        part = base64.b64decode(msg.get("data") or "")
        with self.lock:
            up = self.uploads.get(uid)
            if up is None or up["n"] != n:
                self.uploads = {k: v for k, v in self.uploads.items() if k[:1] != uid[:1]}
                up = self.uploads[uid] = {"n": n, "parts": {}, "size": 0}
            up["size"] += len(part) - len(up["parts"].get(i, b""))
            up["parts"][i] = part
            if up["size"] > UPLOAD_MAX:
                self.uploads.pop(uid, None)
                raise ConvertError(tr("too_big", human_size(up["size"])))

    def drop_upload(self, uid):
        with self.lock:
            self.uploads.pop(str(uid), None)

    def start_analyze(self, msg, on_done=None, origin="tab"):
        """Analyse un 3MF (chemin, ou fichier envoye par la page) dans un fil a part ; renvoie son jeton.
        Un travail par origine : une analyse de l'onglet n'efface pas celle du panneau, et l'inverse."""
        if msg.get("upload_id"):
            with self.lock:
                up = self.uploads.pop(str(msg["upload_id"]), None)
            if not up or len(up["parts"]) != up["n"]:
                raise ConvertError(tr("err_upload"))
            data = b"".join(up["parts"][i] for i in range(up["n"]))
            name = os.path.basename(msg.get("name") or "projet.3mf")
            path = ""
        elif msg.get("upload"):
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
        choices = load_choices()
        keep = load_options().get("supports") == "model"
        with self.lock:
            self.counter += 1
            token = "a%d" % self.counter
            for k in [k for k, j in self.jobs.items() if j.get("origin") == origin]:
                del self.jobs[k]
                self.built.pop(k, None)
            self.jobs[token] = {"path": path, "name": name, "origin": origin, "template": msg.get("template"),
                                "one": one, "presets": {"user": template.presets, "slots": template.slot_presets}}
        if origin == "panel" and self.panel is not None:
            self.panel.follow(token)
        self.post({"command": "progress", "text": tr("p_analysing", name), "token": token, "_origin": origin})

        def failed(text):
            # une analyse annulee depuis le panneau se tait ; l'onglet ignore lui-meme ce qu'il a annule
            if origin != "panel" or self.alive(token):
                self.post({"command": "error", "text": text, "token": token, "_origin": origin})

        def worker():
            ok = False
            try:
                src = Source3MF(data, name, path)
                res = analyze(src, template, one, choices=choices, supports=keep)
                with self.lock:
                    job = self.jobs.get(token)
                    if job is None:         # annulee, ou remplacee par un autre 3MF
                        return
                    job["src"] = src
                    job["files"] = res["files"]
                    job["presets"] = {"user": template.presets, "slots": template.slot_presets}
                    job["profiles"] = [(p["name"], p["group"]) for p in res["profiles"]]
                res.update({"command": "analysis", "token": token, "file": name, "one_per_plate": one,
                            "dest_hint": self.dest_hint(path), "not_ready": ready, "_origin": origin})
                self.post(res)
                ok = True
            except ConvertError as e:
                failed(tr("err_in_file", name, message_of(e)))
            except Exception as e:
                import traceback
                log_error(traceback.format_exc())
                failed(tr("err_analyse", name, e))
            if on_done:
                on_done(name, ok)
        threading.Thread(target=worker, daemon=True).start()
        return token

    def alive(self, token):
        with self.lock:
            return token in self.jobs

    def drop_job(self, token):
        """Analyse annulee depuis le panneau : son resultat ne sera pas envoye. Une analyse deja
        terminee reste (l'onglet l'a peut-etre deja)."""
        with self.lock:
            job = self.jobs.get(token)
            if job is not None and "src" not in job:
                del self.jobs[token]

    def set_plan(self, msg, origin="tab"):
        """Plan (profils, couleurs choisies, couleurs en plus) envoye a chaque changement par l'onglet ou le
        panneau : l'autre le montre et convertit la meme chose."""
        token, files = msg.get("token"), msg.get("files")
        if not isinstance(files, list):
            return
        plan = {"command": "plan", "token": token, "files": files}
        with self.lock:
            job = self.jobs.get(token)
            if job is None:
                return
            job["plan"] = files
            if self.replay.get("analysis", {}).get("token") == token:
                self.replay["plan"] = plan      # l'onglet le retrouve s'il redemarre
        if origin == "panel":
            self._send(plan)
            if self.panel is not None:
                self.panel.keep(plan)
        elif self.panel is not None:
            self.panel.relay(plan, "tab")

    def choose_panel_mode(self, mode):
        """Reglage : panneau, notification seule ou rien quand Orca ouvre un 3MF pas regle pour la U1."""
        options = load_options()
        options["panel"] = mode if mode in PANEL_MODES else "panel"
        try:
            save_options(options)
        except Exception as e:
            log_error("options : %s" % e)
        self.send_state()
        if self.panel is not None:
            self.panel.hello()

    def _job(self, token):
        with self.lock:
            job = self.jobs.get(token)
        if not job or "src" not in job:
            raise ConvertError(tr("err_lost"))
        return job

    def start_replan(self, msg):
        """Nouvelle analyse du meme 3MF : autres reglages, un fichier par plaque, supports de l'auteur
        (gardes ou non ; ce choix est retenu pour les fois suivantes)."""
        job = self._job(msg.get("token"))
        choice = msg.get("template") if "template" in msg else job.get("template")
        template = self.template_for(choice)
        one = bool(msg.get("one_per_plate")) if "one_per_plate" in msg else bool(job.get("one"))
        options = load_options()
        if "supports" in msg:
            keep = bool(msg.get("supports"))
            options["supports"] = "model" if keep else "mine"
            try:
                save_options(options)
            except Exception as e:
                log_error("options : %s" % e)
        else:
            keep = options.get("supports") == "model"
        # supports gardes ou non : tes choix (profils, couleurs, couleurs en plus) restent
        old = None
        if "supports" in msg and one == bool(job.get("one")) and choice == job.get("template") and job.get("profiles"):
            old = job.get("plan") or [{"plates": f["plates"], "slots": [{"src": s["src"], "base": s["base"]} for s in f["slots"]]}
                                      for f in job.get("files") or []]
        res = analyze(job["src"], template, one, choices=load_choices(), supports=keep)
        if old:
            carry_choices(old, job["profiles"], res["profiles"], res["files"])
            res["kept"] = True
        with self.lock:
            job["template"] = choice
            job["one"] = one
            job["files"] = res["files"]
            job["presets"] = {"user": template.presets, "slots": template.slot_presets}
            job["profiles"] = [(p["name"], p["group"]) for p in res["profiles"]]
            job.pop("plan", None)
        res.update({"command": "analysis", "token": msg.get("token"), "file": job["name"], "one_per_plate": one,
                    "dest_hint": self.dest_hint(job["path"]),
                    "not_ready": self.ready_message(choice)})
        self.post(res)

    # ---- conversion
    def start_convert(self, msg, origin="tab"):
        token = msg.get("token")
        job = self._job(token)
        choice = msg.get("template") or job.get("template")
        if choice == "current" or load_saved_template() is None:
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
        # plan envoye par la page, sinon le dernier de l'onglet, sinon les profils proposes d'office
        files = msg.get("files") or job.get("plan") or [
            {"plates": f["plates"], "slots": [{"src": s["src"], "base": s["base"]} for s in f["slots"]],
             "supports": job["src"].keep_supports}
            for f in job.get("files") or []]
        hydrate_presets(template, files)
        self.remember(job, template, files)
        tag = {"token": token, "_origin": origin}
        self.post(dict(tag, command="progress", text=tr("p_converting")))

        def worker():
            try:
                results = convert(job["src"], template, files,
                                  progress=lambda t: self.post(dict(tag, command="progress", text=t)))
                with self.lock:
                    self.built[token] = results
                self.post(dict(tag, command="built"))
            except ConvertError as e:
                self.post(dict(tag, command="error", text=message_of(e)))
            except Exception as e:
                import traceback
                log_error(traceback.format_exc())
                self.post(dict(tag, command="error", text=tr("err_convert", e)))
        threading.Thread(target=worker, daemon=True).start()

    def remember(self, job, template, files):
        """Memoire des choix : profils changes a la main pour les couleurs du modele (fil de l'interface)."""
        try:
            choices = load_choices()
            if learn_choices(choices, job["src"], template, files, job.get("files")):
                save_choices(choices)
                self.post({"command": "choices", "n": len(choices)})
        except Exception as e:
            log_error("choix : %s" % e)

    def forget_choices(self):
        save_choices({})
        self.send_state()

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
        self.post({"command": "result", "files": files, "token": token})

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
        """Projet ouvert dans Orca. S'il n'est pas regle pour la U1 : la U1 le reclame dans le panneau
        de Preparer, ou une notification (selon le reglage, ou si le panneau ne peut pas)."""
        self.opened = None
        foreign = False
        if path and path.lower().endswith(".3mf"):
            if _inside(path, downloads_dir()):
                info = sniff_3mf(path)
                foreign = needs_conversion(info)
            else:
                try:
                    model = current_settings().config.get("printer_model") or ""
                    foreign = not is_u1(model)
                except Exception:
                    model, foreign = "", False
                info = {"path": path, "name": os.path.basename(path), "app": "", "printer": model}
        if not foreign:
            if self.panel is not None:
                self.panel.project_changed()
            return
        self.opened = info
        mode = panel_mode()
        shown = mode == "panel" and self.panel is not None and self.panel.offer_file(info)
        if not shown and mode != "off":
            what = source_label(info) if info.get("app") else tr("another_slicer")
            text = tr("n_foreign", info["name"], what, (" (%s)" % info["printer"]) if info.get("printer") else "")
            self.notify(text, tr("n_link"), lambda p=path: self.prepare(p))
        self.send_state()

    def on_new_project(self):
        self.opened = None
        if self.panel is not None:
            self.panel.project_changed()
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


class Panel:
    """La U1 dans un panneau a cote du plateau (onglets Preparer et Apercu ; create_dock_panel
    d'OrcaSlicer 2.5.1). Elle se montre quand Orca ouvre un 3MF pas regle pour la U1, le mange,
    propose tes profils et le convertit ; un 3MF glisse sur elle suit le meme chemin. C'est le travail
    de l'onglet (meme Converter) : l'onglet recoit l'analyse du panneau (pour changer un profil ou
    ajouter une couleur) et ce qui y change revient ici (« plan »)."""

    WIDTH, HEIGHT = 340, 620    # en DIP ; ensuite, Orca garde la place et la taille choisies

    def __init__(self, conv):
        self.conv = conv
        conv.panel = self
        self.handle = None      # orca.host.ui.UiDockPanel
        self.lock = threading.Lock()
        self.token = None       # analyse que suit le panneau
        self.offer = None       # projet ouvert pas regle pour la U1 : ce que la U1 propose de manger
        self.eaten = None       # proposition mangee (elle revient si l'analyse est annulee)
        self.view = "rest"      # ecran de la page (elle le dit a chaque changement)
        self.last = {}          # derniers messages du travail suivi (renvoyes si la page redemarre)

    # ---- le panneau d'Orca
    def is_open(self):
        h = self.handle
        try:
            return h is not None and bool(h.is_open())
        except Exception:
            return False

    def open(self):
        """Montre le panneau, cree au besoin (il revient ou l'utilisateur l'avait range). False si cet
        Orca ne sait pas faire de panneau."""
        if self.is_open():
            try:
                self.handle.show()
                return True
            except Exception as e:
                log_error("panneau : %s" % e)
                return False
        try:
            self.handle = orca.host.ui.create_dock_panel(
                html=panel_html(), title=PLUGIN_NAME, width=self.WIDTH, height=self.HEIGHT,
                on_message=self.on_message, on_close=self.on_close, dock="right")
            return True
        except Exception as e:
            log_error("panneau : %s" % e)
            self.handle = None
            return False

    def hide(self):
        if self.is_open():
            try:
                self.handle.hide()
            except Exception as e:
                log_error("panneau : %s" % e)

    def on_close(self):
        """Croix du panneau : Orca le detruit. Il revient au prochain 3MF pas regle pour la U1, ou avec
        le bouton des Reglages de l'onglet."""
        with self.lock:
            self.handle = None
            self.token, self.offer, self.eaten, self.last, self.view = None, None, None, {}, "rest"

    def send(self, data):
        h = self.handle
        if h is None:
            return False
        try:
            h.post(relocalize(data))
            return True
        except Exception as e:
            log_error("panneau : %s" % e)
            return False

    # ---- la page
    def hello(self):
        self.send({"command": "hello", "lang": current_language(), "mode": panel_mode(), "version": VERSION})

    def push(self):
        """Tout ce que montre le panneau, pour une page qui (re)demarre."""
        self.hello()
        with self.lock:
            offer, last = self.offer, dict(self.last)
        if offer is not None:
            self.send({"command": "offer", "file": offer, "replay": True})
        elif "analysis" in last:
            self.send(dict(last["analysis"], replay=True))
            if "plan" in last:
                self.send(last["plan"])
            if "result" in last:
                self.send(dict(last["result"], replay=True))
            elif "progress" in last:
                self.send(dict(last["progress"], replay=True))
        elif "progress" in last:
            self.send(dict(last["progress"], replay=True))
        else:
            self.send({"command": "rest"})

    def relabel(self):
        """Nouvelle langue : textes du panneau, et derniers messages retraduits."""
        if not self.is_open():
            return
        self.hello()
        with self.lock:
            last = dict(self.last)
        for k in ("analysis", "result"):
            if k in last:
                self.send(dict(last[k], relabel=True))
        if "progress" in last:
            self.send(last["progress"])

    def keep(self, plan):
        """Plan change dans le panneau : renvoye si la page du panneau redemarre."""
        with self.lock:
            if plan.get("token") == self.token:
                self.last["plan"] = plan

    def relay(self, data, origin):
        """Message d'un travail (lance par l'onglet ou le panneau) : au panneau s'il suit ce travail.
        « built » d'une conversion lancee dans l'onglet reste a l'onglet (c'est lui qui ecrit)."""
        token, cmd = data.get("token"), data.get("command")
        if token is None or token != self.token or (cmd == "built" and origin != "panel"):
            return False
        with self.lock:
            if cmd == "analysis":
                self.last = {"analysis": data}
            elif cmd == "plan":
                self.last["plan"] = data
            elif cmd == "progress":
                self.last["progress"] = data
            elif cmd == "result":
                self.last.pop("progress", None)
                self.last["result"] = data
            elif cmd == "error":
                self.last.pop("progress", None)
        return self.send(data)

    # Appele sur le fil de l'interface quand la page ecrit.
    def on_message(self, msg):
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except ValueError:
                return
        if not isinstance(msg, dict):
            return
        cmd = msg.get("command")
        conv = self.conv
        try:
            if cmd == "init" and msg.get("nav"):
                conv.nav = str(msg["nav"])
            conv.refresh_language()
            if cmd == "init":
                self.push()
            elif cmd == "view":
                self.view = str(msg.get("v") or "rest")
            elif cmd == "eat":
                with self.lock:
                    offer = self.offer
                path = (offer or {}).get("path") or (conv.opened or {}).get("path")
                if not path:
                    raise ConvertError(tr("err_gone"))
                self.start({"path": path}, eaten=offer)
            elif cmd == "later":
                with self.lock:
                    self.offer, self.eaten, self.view = None, None, "rest"
                self.hide()
            elif cmd == "upload_part":
                conv.upload_part(msg)
            elif cmd == "upload_drop":
                conv.drop_upload(msg.get("id"))
            elif cmd == "analyze":
                self.start({"upload_id": msg.get("upload_id"), "name": msg.get("name")})
            elif cmd == "cancel":
                self.cancel()
            elif cmd == "plan":
                conv.set_plan(msg, origin="panel")
            elif cmd == "replan":
                conv.start_replan({"token": msg.get("token"), "supports": bool(msg.get("supports"))})
            elif cmd == "panel_mode":
                conv.choose_panel_mode(msg.get("mode"))
            elif cmd == "convert":
                conv.start_convert({"token": msg.get("token"), "files": msg.get("files")}, origin="panel")
            elif cmd == "write":
                conv.write_outputs(msg.get("token"))
        except PermissionError as e:
            self.send({"command": "error", "text": tr("err_denied", e)})
        except ConvertError as e:
            self.send({"command": "error", "text": message_of(e)})
        except Exception as e:
            import traceback
            log_error(traceback.format_exc())
            self.send({"command": "error", "text": tr("err_generic", e)})

    # ---- le travail du panneau
    def start(self, msg, eaten=None):
        """Analyse demandee dans le panneau, avec tes reglages memorises (sinon ceux d'Orca)."""
        choice = "saved" if load_saved_template() is not None else "current"
        with self.lock:
            self.offer, self.eaten = None, eaten
        self.conv.start_analyze(dict(msg, template=choice), origin="panel")

    def follow(self, token):
        with self.lock:
            self.token, self.last, self.offer, self.view = token, {}, None, "busy"

    def cancel(self):
        """Annuler pendant l'analyse : rien n'arrivera ; le 3MF propose (s'il y en avait un) revient."""
        with self.lock:
            token, self.token, self.last = self.token, None, {}
            eaten, self.eaten = self.eaten, None
            self.offer, self.view = eaten, "offer" if eaten else "rest"
        if token:
            self.conv.drop_job(token)
        if eaten is not None:
            self.send({"command": "offer", "file": eaten})

    # ---- projets ouverts dans Orca
    def offer_file(self, info):
        """Projet ouvert dans Orca, pas regle pour la U1 : la U1 le reclame. False si elle ne peut pas
        (elle mache deja un 3MF, ou cet Orca n'a pas de panneaux) : notification a la place."""
        if self.is_open() and self.view in ("busy", "conv"):
            return False
        card = {"path": info.get("path") or "", "name": info.get("name") or "",
                "label": source_label(info) if info.get("app") else "",
                "printer": info.get("printer") or "", "colors": info.get("colors") or 0}
        was_open = self.is_open()
        with self.lock:
            self.offer, self.eaten, self.token, self.last, self.view = card, None, None, {}, "offer"
        if not self.open():
            with self.lock:
                self.offer, self.view = None, "rest"
            return False
        if was_open:
            self.send({"command": "offer", "file": card})
        return True

    def project_changed(self):
        """Projet regle pour la U1, ou nouveau projet : une proposition ou un travail termine n'a plus
        lieu d'etre, le panneau se range (il revient au prochain 3MF pas regle pour la U1)."""
        with self.lock:
            if self.handle is None or self.view not in ("offer", "done"):
                return
            if self.view == "done":
                self.token, self.last = None, {}
            self.offer, self.eaten, self.view = None, None, "rest"
        self.send({"command": "rest"})
        self.hide()


PANEL = Panel(CONVERTER)


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
