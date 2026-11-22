# Fonctionnement de Mange-3MF

Notes pour reprendre ou corriger le code de `mange_3mf_any.py` (version 0.4.2). Le comportement côté OrcaSlicer a été vérifié dans les sources d'**OrcaSlicer 2.5.1** (références en fin de document).

## 1. Organisation du fichier

Un seul fichier Python, sans dépendance hors bibliothèque standard, en sections :

| Section | Contenu |
|---|---|
| langues | `TEXTS` (tous les textes, une table par langue : messages du plugin et textes de l'onglet), `tr`, `Msg`, `relocalize`, choix de la langue (`lang_of`, `orca_language`, `system_language`) — voir § 9 bis |
| fichiers du 3MF | noms des fichiers internes, fichiers retirés (`_DROP`), réglages qui désignent un filament, listes des réglages de filament d'Orca 2.5.1 (`FILAMENT_PRESET_KEYS`, `FILAMENT_VARIANT_KEYS`) |
| couleurs | `norm_color`, écart de couleur ΔE CIE76 (`color_distance`), noms de couleurs, familles de matières (`base_type`) |
| peinture | lecture et renumérotation des chaînes `paint_color` |
| outils XML / géométrie | attributs, transformations 3MF, boîtes englobantes, grille des plaques |
| lecture d'un 3MF | `Source3MF` : objets, maillages, plaques, filaments utilisés |
| réglages de l'utilisateur | `Template` : les réglages mémorisés |
| plan | `make_plan` : une case par couleur, ordre des cases, profil proposé pour chaque couleur |
| construction | `build_project_config` (réglages du projet pour N filaments) et `build_output` (3MF converti) |
| API | `analyze`, `check_plan`, `convert` (utilisées par l'onglet et les tests) |
| onglet | page HTML (`PAGE` : 4 vues, accueil, analyse en cours, analyse, fichier prêt, et la fenêtre Réglages, voir § 9 quinquies ; `page_html` y met `TEXTS` et la langue), icône de l'onglet (`ICON_SVG` : la U1 au trait, 24 × 24, une seule couleur `#FEFEFE` ; même dessin que `docs/visuals/logo/mange3mf_tab_icon.svg`) et `Converter` |
| enregistrement | capacité « onglet » (`orca.pages.PagesPluginCapabilityBase`) et déclaration des droits |

Le cœur (jusqu'à l'API) n'utilise pas `orca` : il tourne et se teste hors d'OrcaSlicer.

**Numéro de version** : il est écrit deux fois. L'en-tête du fichier (bloc `[tool.orcaslicer.plugin]`, ligne `# version = …`) est ce qu'Orca lit, sans lancer le code, pour la fenêtre Plugins et les mises à jour d'Orca Cloud ; `VERSION` est ce qu'affiche l'onglet. Les deux doivent être identiques : `test_plugin.py` le vérifie (la 0.4.1 avait oublié l'en-tête).

## 2. Fils d'exécution et droits

- Les messages de la page arrivent dans le **fil de l'interface** (`on_message` de la capacité « onglet »). Les fichiers y sont **lus et écrits**, pour que les demandes d'autorisation d'Orca puissent s'afficher (hors du fil de l'interface, Orca refuse sans demander).
- L'analyse et la conversion tournent dans un **fil à part** ; elles travaillent en mémoire et renvoient leurs résultats par `post_message` (qu'Orca fait passer par le fil de l'interface).
- Orca ne construit la page d'un onglet qu'**à la première ouverture** de l'onglet (`LazyPage`), et un message envoyé avant est perdu. `Converter` garde donc les derniers messages `analysis`, `result` et `progress` et les renvoie quand la page envoie `init`.
- Écriture en deux temps : le fil de conversion envoie `built`, la page répond `write`, et l'écriture se fait dans le fil de l'interface.
- Droits déclarés au chargement : lecture / écriture de `~/Downloads/*` et fils d'exécution. Le dossier de stockage du plugin est toujours autorisé par Orca.
- Les noms de fichiers du plugin évitent les mots bloqués par Orca (`config`, `conf`, `secret`, `cert`…) : `reglages_memorises.json`, `capture_reglages.3mf`, `options.json` (langue choisie), `erreurs.log`.

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
| `init {nav}`, `recent` | `state` (réglages mémorisés / actuels, projet ouvert, `lang`, `lang_choice`), `recent` (fichiers) ; à `init`, les derniers `analysis`, `result`, `progress` sont renvoyés |
| `outdir {mode: "beside" \| "downloads" \| "folder", dir}` | `state` (`out` : mode, dossier, message), puis la dernière `analysis` avec `relabel: true` et le nouveau dossier |
| `lang {lang: "auto" \| "fr" \| "en"…, nav}` | `state`, puis les derniers `analysis` et `result` avec `relabel: true` (mêmes données, textes refaits dans la nouvelle langue) et `progress` |
| `capture` | `state` |
| `upload_part {id, i, n, data}` | rien (`error` si plus de 500 Mo) : un morceau (16 Mo au plus, base64) d'un fichier glissé ou choisi ; un seul envoi gardé à la fois |
| `upload_drop {id}` | rien : Annuler pendant l'envoi, les morceaux reçus sont oubliés |
| `analyze {path \| upload_id \| upload, name, template, one_per_plate}` | `progress`, puis `analysis` (source, plaques, `files` avec les cases, `profiles`, `heads`) ou `error` ; avec `upload_id`, les morceaux sont recollés dans l'ordre (`err_upload` s'il en manque) |
| `replan {token, template, one_per_plate}` | `analysis` |
| `convert {token, template, files}` | `progress`, puis `built {token}` |
| `write {token}` | `result {files}` |

## 9 bis. Langues

- **Une seule table** : `TEXTS = {"fr": {...}, "en": {...}}` contient tous les textes montrés à l'utilisateur, ceux du plugin (erreurs, alertes, notifications, noms de couleurs, noms des fichiers par plaque) comme ceux de la page. `page_html()` met toute la table dans la page (JSON, `</` échappé) avec la langue de départ ; la page traduit avec `t(clé, …)` et les attributs `data-t` (texte), `data-th` (HTML), `data-tp` (placeholder), `data-tt` (bulle). Les valeurs s'insèrent par `{0}`, `{1}`… (`str.format` côté Python, avec format éventuel comme `{0:.0f}`) : une langue peut les placer dans l'ordre qu'elle veut. Un texte absent est pris en anglais.
- **Ajouter une langue** : copier le bloc `"en"` de `TEXTS`, traduire en gardant les `{n}` et le HTML, ajouter son nom anglais dans `_LANG_WORDS` (pour les noms de langue de Windows). La liste de la page se remplit seule (`lang_name`). `tests/test_lang.py` vérifie que chaque langue a tous les textes et les mêmes `{n}`.
- **Textes retraduisibles** : `tr(clé, …)` rend un `Msg`, une `str` qui garde sa clé et ses valeurs (elles-mêmes des `Msg` au besoin). Les messages envoyés à la page sont gardés tels quels par `Converter` ; `_send` les passe par `relocalize`, qui refait chaque `Msg` dans la langue courante. Changer de langue renvoie donc l'analyse et les fichiers prêts dans la nouvelle langue, sans refaire l'analyse ; la page garde les profils choisis à la main (`relabel`).
- **Choix de la langue** (`Converter.refresh_language`, appelé dans le fil de l'interface : `get_ui`, chaque message de la page, événements d'Orca) : le choix de l'onglet (`options.json` : `auto`, `fr`, `en`…), sinon la langue de l'interface d'Orca (`orca.host.app_info()["language"]`, par exemple `fr_FR`, lisible seulement dans le fil de l'interface), sinon celle du navigateur de la page, sinon celle du système. Langue inconnue → anglais.
- Les fichiers convertis sont signés `OUT_TAG` (« U1-by-Dragg ») : `modèle - U1-by-Dragg.3mf`, et par plaque dans la langue courante (`… - U1-by-Dragg - plaque 2.3mf`, `… - U1-by-Dragg - plate 2.3mf`) ; l'ancien suffixe (`- U1` ou `- U1-by-Dragg`, plaques comprises, dans l'une ou l'autre langue) est retiré du nom d'origine.
- Lien Ko-fi dans la barre du haut de la page : texte et bouton « Copier le lien ». Pas de lien cliquable : une page d'onglet ouvre les liens dans l'onglet lui-même (`PluginPage::on_new_window` → `LoadURL`), sans retour possible.

## 9 ter. Préréglages de filament d'Orca (0.4.0)

- **Lecture** (`read_filament_presets`, fil de l'interface, à chaque analyse) : `orca.host.preset_bundle().filaments` ; pour chaque préréglage, `config_keys()` et `config_value(clé)` (valeur écrite par `opt_serialize`). Sont gardés : les préréglages utilisateur (`is_user()`, ni copie de projet `is_project_embedded`, ni `is_default`), et, pour chaque case des réglages, le préréglage du même nom (utilisateur ou système) trouvé par `find_preset` après avoir retiré les noms de projet ajoutés par Orca (`strip_project_suffix` : « X(projet.3mf)(autre (1V2).3mf) » → « X », parenthèses imbriquées comprises). Quand l'imprimante sélectionnée dans Orca est celle des réglages, `is_compatible` met à part les préréglages prévus pour une autre imprimante. Les préréglages lus sont gardés avec l'analyse (`job["presets"]`) et réutilisés à la conversion, pour que les numéros de profil restent les mêmes.
- **Valeurs** (`split_serialized`, comme `unescape_strings_cstyle` d'Orca) : textes séparés par « ; », entre guillemets si besoin (`\n`, `\r`, `\"` échappés), une chaîne vide seule s'écrit `""`, un « ; » final ajoute une chaîne vide ; nombres, booléens, pourcentages, `nil` et listes de choix séparés par « , ». Un réglage est traité comme du texte s'il est dans `STRING_VECTOR_KEYS` ou si ses valeurs dans le projet contiennent une virgule, un espace ou un saut de ligne (ex. `adaptive_pressure_advance_model`). Valeurs simples (`inherits`, `filament_id`, conditions de compatibilité) : texte échappé sans guillemets.
- **Profils proposés** (`Template.profiles`) : les cases des réglages (groupe `slot`, nom propre, `user` vrai si la case est un préréglage utilisateur d'Orca), puis les préréglages (`user` ou `other`), avec leur `default_filament_colour`. Les préréglages des cases ne sont pas répétés dans la liste ; la page (`profOpts`) les remet dans le groupe « Tes préréglages » avec l'indice de leur case, triés par nom comme dans Orca. L'indice d'un profil est sa place dans cette liste : en dessous de `slot_count` c'est une case, au-delà un préréglage (`Template.profile`). Choix automatique (`default_profile`) : la case placée si elle a la bonne matière, sinon le plus proche parmi cases et préréglages (pas `other`) : même matière d'abord, puis couleur la plus proche ; un préréglage sans couleur passe après ceux qui en ont une.
- **Réglages du projet** (`build_project_config`, entrée `preset`) : pour un filament fait d'un préréglage, chaque réglage de filament vient du préréglage, et ses lignes (`filament_self_index`, `filament_extruder_variant`) sont **ses variantes de buse**, comme Orca les écrit dans un projet (`full_fff_config`). `filament_settings_id` = nom du préréglage, `filament_ids` = son `filament_id`, `inherits_group` = son parent, conditions de compatibilité = les siennes, et **`different_settings_to_system` vide** : à l'ouverture, `Preset::load_external_config` ne remet alors aucune valeur à celles du parent, et `PresetCollection::load_external_preset` trouve le préréglage du même nom avec exactement ces valeurs (`profile_print_params_same`, qui ignore la couleur des cases) : il le sélectionne au lieu de créer une copie « nom(projet.3mf) ». La purge et la tête prévue viennent de la case la plus proche du préréglage (`closest_slot`).
- **Couleur choisie** : la page envoie `color` (« #RRGGBB ») pour un filament ; `check_plan` la garde (`pick`) si elle est valide, et elle remplace la couleur du modèle dans `filament_colour`.
- **Dossier des fichiers convertis** (`options.json` : `out` = `beside` / `downloads` / `folder`, `out_dir`) : `output_folder` le calcule à l'écriture ; un dossier choisi qui n'existe plus revient « à côté du 3MF ». Message `outdir {mode, dir}` de la page ; un dossier introuvable est refusé (`err_out_dir`) sans changer le choix ; l'analyse affichée est renvoyée avec le nouveau dossier.

## 9 quater. La U1 gourmande (0.4.1)

- **Dessin** : un seul SVG dans `<template id="u1t">` (aucun fichier image), copié trois fois par la page : dans la colonne de gauche (`#u1small`, accueil, analyse en cours et fichier prêt), dans l'analyse à côté de « Burp ! » (`#mini`, en petit) et dans le grand cadre `#eat` (`#eatU`, fixe, par-dessus l'onglet). Le cadrage de chaque copie se règle par `viewBox`. Parties nommées par classes (`u-gl` porte vitrée = mâchoire, `u-ey` yeux, `u-fl` fichier, `u-pr` pièce imprimée, `u-bb` bulle du rot…).
- **États** = une classe CSS sur le `<svg>` (`u1Set`) : `idle` (respire, cligne), `hungry` (porte ouverte, crocs, langue, bave, têtes qui sautillent), `chomp` (le fichier tombe par le haut ouvert, la porte claque, miettes), `chew` (la porte mâche, la tête imprime, la pièce monte, barre sur l'écran), `burp` (bulle avec les couleurs), `spit` (le fichier ressort, langue verte), et depuis la 0.5.0 `full` (la pièce imprimée reste dans la U1, avec `idle`). Toutes les animations sont en CSS ; `prefers-reduced-motion: reduce` les coupe et la page saute le spectacle.
- **Enchaînement** : `dragenter` → `hungry` (grand cadre, `pointer-events: none` pour ne pas gêner le glisser) ; `drop` ou fichier choisi → `readFile` : pas un 3MF ou plus de 500 Mo (`M3D_UP.MAXUP`) → `spit` + message d'erreur ; sinon `eatStart` (`chomp` 1 s puis `chew`) pendant la lecture et l'analyse. Message `analysis` → `eatBurp` : couleurs distinctes de `filaments` (8 au plus), la pièce prend ces couleurs, `burp` 1,8 s, puis le cadre se ferme. Message `error` → `spit`. Un clic sur le cadre le ferme ; fermeture de secours au bout de 90 s. Les analyses lancées autrement (boutons « Analyser », chemin collé, notification) n'ouvrent pas le grand cadre, mais la U1 de la colonne de gauche mâche pendant la vue « analyse en cours ».

## 9 quinquies. L'interface (0.5.0)

- **Même style que multiACE Bridge** (variables CSS en tête de `PAGE`) : fond `--ground #1C1D20`, barre `--bar #18191C`, cartes `--card #222428` et `--raise #26282C`, bords `--edge` / `--edge2`, texte `--fg #E9EAEC` et `--muted #9C9DA0`. Une seule couleur d'action, `--teal #22B3A5`, réservée à l'action suivante (Analyser, Convertir, Copier le chemin, Fermer) ; `--amber #F0A73C` pour « à convertir » et les alertes, `--coral #EC6A5E` pour les erreurs. **Rond = filament** (pastilles, bobines), **carré = numéro ou état** (`.num`, `.mk`).
- **Vues** : `body[data-v]` vaut `home`, `busy`, `an` ou `res` ; les blocs portent `.v` et la ou les vues où ils s'affichent (`.vh`, `.vb`, `.va`, `.vr`), plus `.blk` / `.grd` pour leur type d'affichage. `view(v)` change de vue, `renderHead()` refait le titre, le sous-titre, la légende des couleurs et l'état de la U1 de gauche (`chew` en `busy`, `idle full` en `res`).
  - `home` : la U1 (`#u1zone`), le chemin à coller (`#pathRow`), les derniers 3MF (`#recent`), les réglages (`#rig`, `rigHtml`) : une carte par tête T1 à T4 (buse `High flow` / `Standard` traduite par `flow()`, couleur de la bobine) et une carte « via multiACE » pour les filaments en plus ; en bas, le dossier des fichiers convertis (`#dest`).
  - `busy` : squelette du tableau (`#skel`) et texte de `progress` dans le sous-titre.
  - `an` : plaques (`#plates`, vignette si le 3MF en a une, sinon les couleurs), « Avant de convertir » (`#notes`), case « Un fichier par plaque » (`#opWrap`), tableau « Couleurs et filaments » (`renderAnalysis`), boutons Annuler et Convertir et message de suivi (`#cstatus`) en bas. Annuler (`#cancel`, aussi en `busy`, grisé pendant la conversion) revient à `home` ; pendant une analyse, `S.skip` fait ignorer le message `analysis` ou `error` qui arrivera.
  - `res` : 3 gestes (`renderResult`) ; « Copier le chemin » passe la couleur d'action au geste 2 (`S.copied`). `#back` revient à `an`, `#again` à `home`.
- **Fenêtre Réglages** (`#dlg`, boutons `#openSet` et `#editSet`) : choix des réglages (radios `tc`), `capture`, dossier des fichiers convertis (radios `out`, `#outDir`, `#outOk`), aperçu des têtes (`#dlgRig`). Échap, la croix ou Fermer la referment.
- **Police des titres** : Inter Display ExtraBold (Copyright 2016 The Inter Project Authors, SIL Open Font License 1.1), réduite aux caractères de l'onglet (nom, copyright et licence gardés dans la police) et intégrée en base64 (`@font-face` « M3D », environ 22 Ko) : aucun fichier à côté du plugin. Le texte courant reste dans la police du système (Segoe UI sous Windows).
- **Fenêtre étroite** : sous 1 100 px le texte Ko-fi se cache (le bouton reste), sous 860 px les deux colonnes passent l'une sous l'autre.
- **Fichier glissé ou choisi avec Parcourir** : la page ne connaît pas son chemin (sécurité des pages web), elle lit son contenu. Depuis la 0.5.1 elle le lit par tranches de 16 Mo (`M3D_UP.CHUNK`, `File.slice` + `FileReader`) et envoie un message `upload_part` par tranche, l'une après l'autre (`setTimeout` entre deux : Orca reste réactif), en affichant « Lecture de … (i/n) » ; puis `analyze {upload_id}`. Le plugin garde les morceaux (`Converter.uploads`, limite `UPLOAD_MAX` = 500 Mo) et les recolle. Avant, tout le fichier partait en un seul message (limite 80 Mo). Annuler pendant l'envoi arrête la lecture et envoie `upload_drop`.
- `tests/ui/render_page.js` passe par toutes les vues, la fenêtre Réglages, le changement de langue (la vue reste la même) et une fenêtre de 760 px sans défilement sur le côté.

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
- `src/slic3r/plugin/host/PluginHostPresets.cpp` : préréglages (`preset_bundle().filaments`, `Preset.config_value` = `opt_serialize`) ; `src/libslic3r/PresetBundle.cpp` (`load_config_file_config`) et `src/libslic3r/Preset.cpp` (`load_external_config`, `load_external_preset`, `profile_print_params_same`) : préréglages d'un projet à l'ouverture.
- `src/slic3r/plugin/host/PluginHostApp.cpp` : `app_info()` (langue de l'interface, fil de l'interface seulement) ; `src/slic3r/GUI/WebPanel.cpp` : page d'un onglet (`SetPage`, liens ouverts dans la page).
- `src/slic3r/plugin/` et `docs/HLSD/plugin-permissions.md` : API des plugins et droits.
