# Fonctionnement de Mange-3MF

Notes pour reprendre ou corriger le code de `mange_3mf_any.py` (version 0.2.1). Le comportement côté OrcaSlicer a été vérifié dans les sources d'**OrcaSlicer 2.5.1** (références en fin de document).

## 1. Organisation du fichier

Un seul fichier Python, sans dépendance hors bibliothèque standard, en sections :

| Section | Contenu |
|---|---|
| fichiers du 3MF | noms des fichiers internes, fichiers retirés (`_DROP`), réglages qui désignent un filament, listes des réglages de filament d'Orca 2.5.1 (`FILAMENT_PRESET_KEYS`, `FILAMENT_VARIANT_KEYS`) |
| couleurs | `norm_color`, écart de couleur ΔE CIE76 (`color_distance`), noms de couleurs, familles de matières (`base_type`) |
| peinture | lecture et renumérotation des chaînes `paint_color` |
| outils XML / géométrie | attributs, transformations 3MF, boîtes englobantes, grille des plaques |
| lecture d'un 3MF | `Source3MF` : objets, maillages, plaques, filaments utilisés |
| réglages de l'utilisateur | `Template` : les réglages mémorisés |
| plan | `make_plan` : une case par couleur, ordre des cases, profil proposé pour chaque couleur |
| construction | `build_project_config` (réglages du projet pour N filaments) et `build_output` (3MF converti) |
| API | `analyze`, `check_plan`, `convert` (utilisées par l'onglet et les tests) |
| onglet | page HTML (`PAGE` : analyse et fichiers prêts en haut, puis réglages et choix du 3MF), icône (`ICON_SVG`) et `Converter` |
| enregistrement | capacité « onglet » (`orca.pages.PagesPluginCapabilityBase`) et déclaration des droits |

Le cœur (jusqu'à l'API) n'utilise pas `orca` : il tourne et se teste hors d'OrcaSlicer.

## 2. Fils d'exécution et droits

- Les messages de la page arrivent dans le **fil de l'interface** (`on_message` de la capacité « onglet »). Les fichiers y sont **lus et écrits**, pour que les demandes d'autorisation d'Orca puissent s'afficher (hors du fil de l'interface, Orca refuse sans demander).
- L'analyse et la conversion tournent dans un **fil à part** ; elles travaillent en mémoire et renvoient leurs résultats par `post_message` (qu'Orca fait passer par le fil de l'interface).
- Orca ne construit la page d'un onglet qu'**à la première ouverture** de l'onglet (`LazyPage`), et un message envoyé avant est perdu. `Converter` garde donc les derniers messages `analysis`, `result` et `progress` et les renvoie quand la page envoie `init`.
- Écriture en deux temps : le fil de conversion envoie `built`, la page répond `write`, et l'écriture se fait dans le fil de l'interface.
- Droits déclarés au chargement : lecture / écriture de `~/Downloads/*` et fils d'exécution. Le dossier de stockage du plugin est toujours autorisé par Orca.
- Les noms de fichiers du plugin évitent les mots bloqués par Orca (`config`, `conf`, `secret`, `cert`…) : `reglages_memorises.json`, `capture_reglages.3mf`, `erreurs.log`.

## 3. Les réglages mémorisés (`Template`)

Orca ne donne pas aux plugins de quoi écrire un `project_settings.config` complet. Le plugin appelle donc `plater().export_3mf_copy()` (fil de l'interface) : Orca écrit une copie du projet ouvert, et le plugin en garde `Metadata/project_settings.config` et les étiquettes `Application` / `OrcaSlicer` du modèle.

Attention aux étiquettes : OrcaSlicer 2.3.2 et plus écrit `Application` = `BambuStudio-<SLIC3R_VERSION>` (`BambuStudio-02.08.01.55` pour Orca 2.5.1, par compatibilité avec Bambu Studio) **et** l'étiquette `OrcaSlicer` = sa vraie version (`2.5.1`). C'est cette étiquette qui fait d'un fichier un projet Orca (`is_orca_3mf`, `En3mfType::From_Orca`). Le plugin accepte donc un projet de référence qui a l'étiquette `OrcaSlicer`, ou une application `OrcaSlicer-…` (anciennes versions, l'étiquette est alors déduite) ; Snapmaker Orca est refusé (`is_orca_file`).

Le projet converti part de ce fichier, refait pour N filaments par `build_project_config` (voir § 7 bis), avec en plus `wipe_tower_x` / `wipe_tower_y` (une position par plaque).

Comme chaque valeur de filament est recopiée depuis un des profils de l'utilisateur, Orca resélectionne ses profils à l'ouverture sans les marquer « modifiés » (`PresetCollection::load_external_preset`, comparaison `profile_print_params_same`).

Pourquoi mémoriser plutôt que lire les réglages au moment de convertir : quand on ouvre dans Orca un 3MF d'un autre logiciel, Orca bascule sur les réglages de ce projet (ou sur ses valeurs par défaut). Les « réglages actuels » ne sont alors plus ceux de l'utilisateur.

Les profils proposés (`slot_count`, `profiles`) sont les vrais filaments : les couleurs mélangées d'Orca (`filament_is_mixed` ou `filament_mixed_components` non vide) sont rangées à la fin et ne comptent pas. `head_count` = nombre de buses (`nozzle_diameter`), 4 sur la U1.

## 4. Lecture du 3MF source (`Source3MF`)

Format Bambu Studio / OrcaSlicer (« BBS ») :

| Fichier | Lu pour |
|---|---|
| `_rels/.rels` | trouver le modèle principal |
| `3D/3dmodel.model` | étiquettes (`Application`, `OrcaSlicer`), objets de premier niveau, composants, éléments `<build><item>` (une instance par élément, dans l'ordre) |
| `3D/Objects/*.model` | maillages : boîte englobante, nombre de triangles, peinture |
| `Metadata/project_settings.config` | filaments (`filament_colour`, `filament_type`, `filament_settings_id`), plateau (`printable_area`), tour d'essuyage, couleurs mélangées |
| `Metadata/model_settings.config` | objets (filament, réglages), pièces (`<part>` : type, filament, réglages), plaques (`<plate>` : nom, instances), assemblage |
| `Metadata/layer_config_ranges.xml` | filaments des plages de couches |
| `Metadata/custom_gcode_per_layer.xml` | changements d'outil par couche |

Origine (`kind`), dans cet ordre : `prusa` (refusé), `plain` (pas de réglages), `snapmaker` (« Snapmaker_Orca-… »), `orca` (étiquette `OrcaSlicer`, ou « OrcaSlicer-… »), `bambu` (« BambuStudio-… » **sans** étiquette `OrcaSlicer`), `orca-fork` (autres). Un projet d'Orca 2.5.1 commence par « BambuStudio-02.08.01.55 » : l'étiquette doit être regardée avant l'application.

Pièces et maillages : une pièce de `model_settings` correspond au composant de même identifiant (sinon au composant de même rang). Les maillages peuvent être **partagés** entre objets (Bambu Studio 2.x écrit un maillage une fois et le référence plusieurs fois).

Instances hors de toute plaque : rangées sur la plaque dont la zone contient leur centre.

### Filaments utilisés et poids

Pour chaque objet (`object_filaments`) :

- pièce normale non peinte : filament de la pièce, sinon de l'objet (poids 1) ;
- pièce peinte : filament de la pièce pour la part non peinte, et chaque état de peinture au prorata des triangles ;
- pièce entièrement peinte : son filament n'est **pas** compté (il n'imprime rien) ;
- modificateur avec un filament : poids 0,3 ; pièce négative et bloqueurs / forceurs : ignorés ;
- filaments par fonction (objet ou pièce), plages de couches, changements d'outil : comptés.

Depuis la 0.2.0, aucune couleur n'est fusionnée : les poids sont calculés mais ne servent plus au plan.

## 5. La peinture (`paint_color`)

Format d'OrcaSlicer (`TriangleSelector::serialize`, `FacetsAnnotation::get_triangle_as_string`) :

- une chaîne hexadécimale par triangle, **lue de droite à gauche**, un chiffre = un quartet ;
- chaque nœud de l'arbre de découpe commence par un quartet : 2 bits bas = nombre de côtés coupés (0 = feuille), 2 bits hauts = état de la feuille ou côté spécial ;
- feuille d'état 0, 1 ou 2 : dans le quartet ; état 3 à 17 : bits hauts `11` puis un quartet (état − 3) ; état 18 et plus : `11`, quartet `1111`, puis un quartet (état − 18) ;
- un nœud coupé en N côtés a N + 1 enfants, à la suite dans le flux ;
- l'état d'une feuille est le **numéro du filament** (0 = filament de la pièce).

`remap_paint` parcourt l'arbre, renumérote les feuilles et réécrit la chaîne (une feuille peut changer de longueur). Une chaîne illisible est laissée telle quelle. Pour aller vite sur les gros fichiers (plus de 500 000 triangles), les remplacements se font par expression régulière avec un cache par chaîne distincte.

À savoir : à l'ouverture, Orca remet à « non peint » toute feuille dont l'état dépasse le nombre de filaments du projet. C'est ce qui efface la peinture des couleurs 5 à 7 quand un projet à 7 couleurs est ouvert tel quel (Orca lui donne ses 4 cases par défaut). Orca ne peint pas au-delà de 16 filaments (`EnforcerBlockerType::Extruder16`).

## 6. Le plan des couleurs (`make_plan`)

Un seul fichier avec toutes les plaques (ou un par plaque si demandé), et **une case par couleur** :

1. **Couleurs** (`color_entries`) : les filaments utilisés par les plaques du fichier, dans l'ordre d'origine. Deux filaments ne sont réunis que s'ils sont identiques (même couleur, même matière, même nom de profil) ; un filament sans couleur lisible reste seul.
2. **Ordre** (`order_entries`) : les cases 1 à 4 (une par tête, limitées au nombre de profils) vont aux couleurs qui ressemblent le plus aux bobines actuelles. Coût d'une couleur sur une case : ΔE avec la couleur de la case (plafonné à 60) + 40 si la matière du profil diffère. Recherche exhaustive (permutations) tant qu'il y a au plus 200 000 possibilités, sinon choix glouton. Les autres couleurs suivent, dans l'ordre d'origine. Moins de 4 couleurs : les cases restantes sont vides (`None`).
3. **Profil proposé** (`default_profile`) : celui de la case si sa matière est la bonne ; sinon un profil de la même matière (couleur la plus proche) ; sans profil de cette matière, celui de la case (avec une alerte à la conversion). Une case vide garde le profil et la couleur de la case du projet de référence.

Format d'un fichier du plan : `{"plates": [indices], "slots": [{"src": [filaments d'origine], "base": profil (0…)}]}`. L'onglet le renvoie, avec les profils changés à la main ; `check_plan` vérifie que chaque plaque est dans un fichier, que chaque filament utilisé a une case et que chaque profil existe, et complète à une case par tête.

## 7. Construction du 3MF converti (`build_output`)

- **Étiquettes** : `Application` = celle de l'OrcaSlicer de l'utilisateur (`BambuStudio-02.08.01.55` pour Orca 2.5.1), plus l'étiquette `OrcaSlicer` (sa version). Orca classe alors le fichier comme un de ses projets (`En3mfType::From_Orca`) : il lit les réglages et les plaques, et ne découpe ni ne « cuit » les instances comme il le fait pour les 3MF d'autres logiciels.
- **Objets** : les objets de premier niveau dont aucune instance n'est gardée sont retirés du modèle et de `model_settings` ; les instances sont renumérotées par objet.
- **Sous-modèles** : seuls ceux encore référencés sont gardés (et leurs relations), peinture renumérotée.
- **Filaments** : `extruder` des objets et des pièces renuméroté ; anciens noms de filaments par fonction convertis vers les nouveaux (`wall_filament` → `outer_wall_filament_id`, « 1 » = par défaut).
- **Plaques** : renumérotées 1…n, métadonnées gardées sauf vignettes, G-code, répartition filaments / buses, type de plaque et ordre des filaments.
- **Positions** : grille des plaques d'Orca (`PartPlateList`) : colonnes = ⌈√n⌉ (même calcul qu'Orca), pas = largeur × 1,2. Une instance garde sa position dans sa plaque ; si le plateau d'origine a une autre taille, on garde la position par rapport au centre ; si la plaque déborde, son contenu est centré ; s'il est plus grand que le plateau : alerte.
- **Fichiers annexes** : plages de couches, découpes, hauteurs de couches, oreilles de bordure repérés par le rang de l'objet (1…) → renumérotés ; changements par couche repérés par plaque → renumérotés.
- **Retirés** : vignettes et G-code de l'auteur, `slice_info.config`, profils embarqués, `filament_sequence.json`, relations vers des fichiers absents.

## 7 bis. Réglages du projet pour N filaments (`build_project_config`)

Orca écrit les réglages de filament d'un projet ainsi (`PresetBundle::full_fff_config`) : pour chaque filament, les valeurs de son profil sont mises bout à bout. La plupart des réglages ont **une valeur par filament** ; ceux de `filament_options_with_variant` (températures, débit, rétraction, pressure advance…) ont **une valeur par variante de buse** du profil (sur la U1 : « Direct Drive Standard » et « Direct Drive High Flow »), et `filament_self_index` dit à quel filament appartient chaque ligne.

Pour chaque filament du projet converti, avec `base` = case du projet de référence dont on reprend le profil :

| Réglages | Recopie |
|---|---|
| réglages de profil de filament (`Preset::filament_options()`, et tout réglage `filament_…` en liste) | valeur de la case `base` ; lignes de la case `base` pour les réglages à variantes, `filament_self_index` refait |
| `filament_colour`, `filament_multi_colour`, `filament_colour_type` | couleur du modèle, couleur pleine (`1`) ; case vide : ceux de la case |
| `filament_settings_id`, `filament_ids` | ceux de la case `base` |
| `filament_map`, `filament_volume_map`, `filament_nozzle_map` (tête et buse prévues) | ceux de la place dans le projet de référence pour les premières places, sinon ceux de la case `base` ; `filament_map_mode` inchangé |
| couleurs mélangées (`filament_is_mixed`, `filament_mixed_…`) | remises à zéro |
| `inherits_group`, `compatible_machine_expression_group`, `different_settings_to_system` ([traitement, filaments…, imprimante]), `compatible_process_expression_group` ([filaments…]) | valeurs des cases `base` |
| `flush_volumes_vector` (2 par filament) | celles de la case `base` |
| `flush_volumes_matrix` (N × N par buse) | 0 sur la diagonale ; entre deux profils différents, la valeur d'origine entre ces profils ; entre deux couleurs du même profil, purge de déchargement + chargement, comme Orca (`update_multi_material_filament_presets`) |
| filaments par fonction du traitement (`support_filament`…) | remis à « par défaut » s'ils dépassent le nombre de filaments |

Orca garde au moins un filament par tête (`PresetBundle::min_filament_count`) : 4 sur la U1, d'où les cases vides. Au-delà de 4 filaments, le G-code de changement d'outil du profil U1 écrit `T` + numéro du filament (`T4`, `T5`…) : c'est à l'imprimante (ou à multiACE) de les traiter.

## 8. Détection à l'ouverture

Capacité « onglet » avec `on_lifecycle_event` :

- `ProjectOpened` : si le fichier est dans Téléchargements, lecture rapide (`sniff_3mf`, qui lit aussi l'étiquette `OrcaSlicer`) : à convertir si ce n'est pas un projet OrcaSlicer pour une U1. Ailleurs, on ne lit pas le fichier (pas de demande d'autorisation à chaque ouverture) : à convertir si l'imprimante sélectionnée par Orca n'est pas une U1. Si oui, notification « Préparer la conversion dans l'onglet Mange-3MF » : le clic lance l'analyse (fil de l'interface pour la lecture), puis une notification « prête » est envoyée depuis le fil d'analyse (`push_notification` passe par le fil de l'interface). Un plugin ne peut pas afficher son onglet : l'utilisateur l'ouvre.
- `NewProject` : oubli du projet ouvert.

## 9. Messages entre la page et le plugin

| Page → plugin | Plugin → page |
|---|---|
| `init`, `recent` | `state` (réglages mémorisés / actuels, projet ouvert), `recent` (fichiers) ; à `init`, les derniers `analysis`, `result`, `progress` sont renvoyés |
| `capture` | `state` |
| `analyze {path \| upload, name, template, one_per_plate}` | `progress`, puis `analysis` (source, plaques, `files` avec les cases, `profiles`, `heads`) ou `error` |
| `replan {token, template, one_per_plate}` | `analysis` |
| `convert {token, template, files}` | `progress`, puis `built {token}` |
| `write {token}` | `result {files}` |

## 10. Références (OrcaSlicer 2.5.1)

- `src/libslic3r/Format/bbs_3mf.cpp` : lecture / écriture des 3MF, étiquettes `Application` (« BambuStudio- » + `SLIC3R_VERSION`) et `OrcaSlicer` (`SoftFever_VERSION`), `is_orca_3mf`, fichiers annexes ; `version.inc` : `SLIC3R_VERSION` 02.08.01.55 pour Orca 2.5.1.
- `src/slic3r/GUI/Plater.cpp` : chargement d'un projet, types de 3MF (`From_Orca`, `From_BBS`, `From_Other`), « chargement de la géométrie seulement ».
- `src/libslic3r/PresetBundle.cpp`, `src/libslic3r/Preset.cpp` : réglages d'un projet → profils.
- `src/libslic3r/TriangleSelector.cpp`, `src/libslic3r/Model.cpp` : format de la peinture.
- `src/slic3r/GUI/PartPlate.cpp` / `.hpp` : grille des plaques.
- `src/libslic3r/PrintConfig.cpp` : réglages de filament par fonction et anciens noms.
- `src/libslic3r/PresetBundle.cpp` : `full_fff_config` (réglages de filament bout à bout, `filament_self_index`), `load_config_file_config`, `update_multi_material_filament_presets` (purge), `min_filament_count`.
- `src/libslic3r/Preset.cpp` (`s_Preset_filament_options`) et `src/libslic3r/PrintConfig.cpp` (`filament_options_with_variant`, `filament_map`, `filament_colour_type`, couleurs mélangées).
- `resources/profiles/Snapmaker/machine/` : profils U1 (variantes de buse, G-code de changement d'outil).
- `src/slic3r/plugin/host/PluginPages.cpp`, `src/slic3r/plugin/pluginTypes/pages/` : onglets des plugins (page construite à la première ouverture, `post_message`, icône).
- `src/slic3r/plugin/host/PluginHostUi.cpp` : notifications (`push_notification`, niveaux).
- `src/slic3r/plugin/` et `docs/HLSD/plugin-permissions.md` : API des plugins et droits.
