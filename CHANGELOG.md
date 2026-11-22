# Historique des versions — Mange-3MF (Snapmaker U1)

## 0.5.0 — 22/11/2026

- **Nouvelle interface**, dans le même style que multiACE Bridge : fond sombre, cartes T1 à T4 pour les têtes, bobines rondes pour les filaments, et une seule couleur turquoise, celle de l'action suivante. L'onglet a 4 vues :
  - **accueil** : à gauche la U1 qui a faim (glisse un 3MF sur elle, clique dessus ou colle un chemin) ; à droite les derniers 3MF de tes Téléchargements et tes réglages, montrés comme sur l'imprimante : une carte par tête avec sa buse (High flow ou Standard) et la couleur de sa bobine, les filaments en plus « via multiACE » ;
  - **analyse en cours** : la U1 mâche, la page dit où elle en est ;
  - **analyse** : le fichier avec ses couleurs en titre, les plaques en vignettes, « Avant de convertir » (ce qu'il faut savoir, case « Un fichier par plaque ») et le tableau « Couleurs et filaments ». **Convertir** reste en bas de l'onglet ;
  - **fichier prêt** : « L'ouvrir dans Orca : 3 gestes » (copier le chemin, Fichier › Ouvrir un projet, coller et valider), puis « Revenir aux couleurs » ou « Convertir un autre 3MF ». La U1 montre la pièce imprimée.
- **Fenêtre Réglages** (bouton en haut de l'onglet, ou « Modifier » sur l'accueil) : réglages mémorisés ou réglages actuels d'Orca, « Mémoriser les réglages actuels d'Orca », dossier des fichiers convertis. Échap ou Fermer la referme.
- Toutes les actions et animations de la 0.4 sont gardées : glisser-déposer, clic sur la U1, Parcourir, chemin collé, Analyser, profil ou couleur choisis pour chaque filament, un fichier par plaque, langue, Copier le lien Ko-fi ; la U1 avale, mâche, rote les couleurs et recrache ce qui n'est pas un 3MF.
- **Un même profil pour plusieurs couleurs**, plus clair à l'écran : la liste des profils n'affiche plus la couleur de tes bobines (« 1 · Elegoo PLA · PLA » au lieu de « … (noir) ») et la pastille du profil a disparu. Chaque filament garde la couleur du modèle (ou celle que tu choisis en cliquant sur sa pastille), quel que soit le profil, et un profil peut servir pour autant de couleurs que tu veux. C'était déjà le cas à la conversion, l'écran laissait croire le contraire.
- **Tous tes préréglages** dans « Tes préréglages », dans l'ordre alphabétique comme dans Orca : ceux qui sont aussi dans tes réglages (par exemple Anycubic PLA) n'en sont plus retirés. Les choisir dans un groupe ou dans l'autre donne le même profil.
- Bouton **Annuler** à côté de Convertir : retour à l'accueil sans rien écrire. Pendant l'analyse, il l'abandonne (le résultat qui arrive ensuite est ignoré). Grisé pendant la conversion.
- Buses nommées « High flow » et « Standard », comme dans multiACE Bridge.
- Titres en Inter Display (licence SIL Open Font License), seulement les caractères de l'onglet (22 Ko) : le plugin reste un seul fichier.
- Onglet lisible dans une petite fenêtre (une seule colonne sous 860 px de large).
- Tests : 335 vérifications, dont un même profil pour toutes les couleurs (chacune garde la sienne) ; la page rendue dans Chrome passe par les 4 vues, la fenêtre Réglages, le bouton Annuler et la liste complète de tes préréglages, en français et en anglais, et vérifie qu'une fenêtre étroite ne défile pas sur le côté. Nouvelle capture `5_reglages.png`.

## 0.4.2 — 22/11/2026

- **Numéro de version corrigé** : la 0.4.1 annonçait encore « 0.4.0 » à Orca (fenêtre Plugins, mises à jour d'Orca Cloud) alors que l'onglet affichait 0.4.1. L'en-tête du plugin et l'onglet disent maintenant tous les deux 0.4.2, et un test vérifie qu'ils restent pareils.
- **Nouveau logo** : la U1 en petit monstre gourmand qui croque un fichier 3MF, avec ses 4 têtes de couleur sur le dessus. Il remplace le cube croqué dans l'onglet d'Orca (version d'une seule couleur, au trait comme les icônes d'Orca) et sur les visuels du dépôt et d'Orca Cloud. Fichiers du logo dans `docs/visuals/logo/`.
- Tests : 329 vérifications.

## 0.4.1 — 21/11/2026

- **La U1 a faim** : dans « Le 3MF à manger », une U1 dessinée (sa vraie silhouette : haut ouvert, 4 têtes garées, porte vitrée, écran) attend ton 3MF. Glisse un fichier sur l'onglet : elle ouvre la bouche, l'avale, le mâche pendant l'analyse, puis rote les couleurs du modèle. Pas un 3MF : elle le recrache. Un clic sur elle ouvre le choix d'un fichier, un clic pendant le spectacle le coupe. Animations coupées si Windows est réglé pour réduire les animations. Dessin fait dans la page : le plugin reste un seul fichier.
- **Fichiers signés** : le fichier converti s'appelle « modèle - U1-by-Dragg.3mf » (par plaque : « modèle - U1-by-Dragg - plaque 2.3mf »). Un ancien suffixe « - U1 » ou « - U1-by-Dragg » est retiré du nom d'origine : il n'est jamais doublé.
- Tests : 327 vérifications, et la page rendue dans Chrome vérifie la U1 (bouche ouverte au survol d'un fichier, avale, mâche, rote les couleurs de l'analyse, recrache ce qui n'est pas un 3MF, clic = choix d'un fichier).

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
