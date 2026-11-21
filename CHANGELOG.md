# Historique des versions — Mange-3MF (Snapmaker U1)

## 0.4.0 — 21/11/2026

- **Tes préréglages de filament** : la liste des profils propose aussi tous tes préréglages utilisateur d'Orca (groupe « Tes préréglages », ceux prévus pour une autre imprimante à part), avec leur « couleur par défaut » quand ils en ont une. Le choix automatique en tient compte : même matière d'abord, puis couleur la plus proche.
- **Profils reconnus par Orca** : chaque filament est écrit avec les valeurs à jour du préréglage d'Orca du même nom, variantes de buse comprises. À l'ouverture, Orca retrouve tes préréglages au lieu d'en faire des copies nommées « …(projet.3mf) ». Les noms déjà abîmés par ces copies sont nettoyés (« Anycubic PLA(un projet.3mf)(un autre.3mf) » redevient « Anycubic PLA »).
- **Couleur au choix** : un clic sur la pastille d'un filament change sa couleur (lien « remettre celle du modèle »).
- **Dossier des fichiers convertis** : à côté du 3MF d'origine, dans Téléchargements ou dans un dossier choisi (chemin collé). Le choix est gardé.
- Tests : 324 vérifications, dont `test_presets.py` (lecture des préréglages comme Orca les écrit, noms nettoyés, réglages du projet faits depuis un préréglage, couleur choisie, dossier).

## 0.3.0 — 21/11/2026

- **En anglais ou en français** : l'onglet, les messages, les alertes, les notifications et les noms des couleurs. Par défaut, la langue d'Orca (français si Orca est en français, anglais sinon) ; liste **Auto / Français / English** en haut à droite de l'onglet, choix gardé. Le changement s'applique tout de suite, y compris à l'analyse et aux fichiers prêts déjà affichés (les profils choisis à la main sont gardés).
- Tous les textes sont dans une seule table (`TEXTS`) : une autre langue s'ajoute en traduisant un bloc.
- Fichiers par plaque nommés « … - U1 - plate 2.3mf » en anglais.
- Lien **Ko-fi** en bas de l'onglet, avec « Copier le lien », pour soutenir Dragg.
- Accents rétablis dans les messages en français.
- Tests : 256 vérifications, dont `test_lang.py` (chaque langue complète, textes de la page, retraduction) ; captures de l'onglet en français et en anglais (`docs/captures/en`).
- Mode d'emploi complet en anglais (`GUIDE.md`).
- Visuels pour Orca Cloud et GitHub (`docs/visuals` : bannière, avant / après, captures mises en scène), refaits par `node tests/ui/make_visuals.js`.

## 0.2.1 — 21/11/2026

- **Correction** : « le projet de référence doit venir d'OrcaSlicer (trouvé : BambuStudio-02.08.01.55) ». OrcaSlicer 2.5.1 signe ses propres projets « BambuStudio-02.08.01.55 » et ajoute l'étiquette « OrcaSlicer 2.5.1 » : c'est maintenant cette étiquette qui compte, pour mémoriser les réglages comme pour reconnaître un projet d'Orca.
- Les projets enregistrés par OrcaSlicer s'affichent « OrcaSlicer » (et non plus « Bambu Studio ») ; ceux réglés pour la U1 ne sont plus marqués « à convertir » et ne déclenchent plus de notification.
- L'**analyse s'affiche en haut** de l'onglet, au-dessus des réglages et de la liste des 3MF, avec les fichiers prêts juste en dessous. Les messages de la conversion s'affichent sous le bouton « Convertir ».
- Tests : 197 vérifications, dont l'origine des fichiers (`test_origin.py`) ; le faux OrcaSlicer signe ses projets comme le vrai.

## 0.2.0 — 21/11/2026

- **Onglet « Mange-3MF »** dans la fenêtre principale d'Orca, à la place de la fenêtre lancée depuis la fenêtre Plugins. Les derniers résultats (analyse, fichiers prêts, conversion en cours) sont gardés et réaffichés quand l'onglet est rouvert ou reconstruit.
- **Exactement les couleurs du modèle** : un seul fichier avec toutes les plaques et un filament par couleur (7 couleurs → 7 filaments). Fin du découpage en plusieurs fichiers de 4 couleurs et des fusions de couleurs. Seuls deux filaments identiques (même couleur, même matière, même profil) sont réunis.
- Orca garde au moins un filament par tête (4 sur la U1) : avec moins de couleurs, les cases en trop restent les bobines actuelles et l'onglet le dit.
- **Profil de filament par couleur** : un de tes profils de la même matière, couleur la plus proche ; liste pour en choisir un autre ; alerte si la matière diffère.
- Réglages du projet refaits pour N filaments à partir des réglages mémorisés : chaque réglage de filament recopié depuis le profil choisi, y compris les **variantes Haut débit / Standard** (`filament_self_index`), têtes et buses prévues, profils de base, purge entre filaments (matrice N × N par buse), couleurs mélangées retirées, filaments par fonction du traitement limités au nombre de filaments.
- **Glisser-déposer** d'un 3MF dans l'onglet (jusqu'à 80 Mo, comme « Parcourir… »).
- Notification à l'ouverture d'un 3MF venu d'ailleurs : « Préparer la conversion dans l'onglet Mange-3MF », puis une deuxième notification quand l'analyse est prête.
- Un fichier par plaque : chaque fichier n'a que les couleurs de sa plaque.
- Alerte au-delà de 16 couleurs (Orca ne peint que 16 filaments).
- Mode d'emploi : correction (le plugin ne s'ajoutait pas au menu Plugins), mise à jour depuis la 0.1.0, plus de 4 couleurs et G-code `T4`, `T5`….
- Tests : 181 vérifications (`python tests/run_all.py`), dont des réglages façon Orca 2.5.1 avec variantes de buse ; rendu de l'onglet vérifié dans Chrome (choix d'un profil, glisser-déposer).

## 0.1.0 — 21/11/2026

Première version.

- Fenêtre « Mange-3MF : convertir un 3MF pour la U1 » (menu Plugins d'OrcaSlicer 2.5).
- Sources : projets Bambu Studio / MakerWorld, Snapmaker Orca, OrcaSlicer et variantes, 3MF sans réglages. Refus clair des fichiers PrusaSlicer et des fichiers déjà tranchés.
- Couleurs gardées : filament des objets et des pièces, peinture renumérotée (format OrcaSlicer, états jusqu'à 32), modificateurs, plages de couches, changements d'outil par couche, filaments par fonction (anciens noms Bambu compris).
- Plaques gardées (noms, pièces, verrouillage, ordre d'impression), replacées sur le plateau de la U1 : même position, ou même position par rapport au centre si le plateau d'origine est différent, ou centrées si ça déborde ; alerte si une plaque est trop grande.
- Réglages de l'utilisateur : mémorisés d'un clic (copie du projet ouvert exportée par Orca), ou réglages actuels d'Orca. Refus de convertir avec des réglages qui ne sont pas ceux d'une U1.
- Plus de 4 couleurs : regroupement des plaques en le moins de fichiers possible ; fusion des couleurs les plus proches si une plaque dépasse 4 couleurs (choix pondéré par la place de chaque couleur) ; cases modifiables à la main.
- Cases choisies au plus près des bobines actuelles, avec « mets du … en tête N ».
- Notification quand un 3MF venu d'un autre logiciel est ouvert dans Orca.
- Liste des derniers 3MF des Téléchargements, chemin collé ou « Parcourir… ».
- Fichiers écrits à côté de l'original, sans jamais écraser un fichier existant.
- Avertissements : matière attendue différente du profil de la case, couleurs fusionnées, couleurs mélangées, peinture illisible.
- Tests automatiques sans OrcaSlicer : 115 vérifications (`python tests/run_all.py`).
