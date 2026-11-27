# Historique des versions — Mange-3MF

## 0.7.1 — 28/11/2026

- **Flashforge, et bien d'autres marques vérifiées** (demandé par Dragg : « flashforge aussi stp et trouve d'autres ») : les 71 marques d'Orca 2.5.1 passées en revue ; les imprimantes à plusieurs couleurs sont essayées avec leurs vrais profils d'Orca (73 imprimantes, 33 en 0.7.0) :
  - **Flashforge** : AD5X avec l'IFS (une buse, 4 bobines), Creator 5 et 5 Pro (changeur de 4 têtes, comme la U1 mais sans multiACE), Adventurer 5M et 5M Pro, Guider4 Pro, Adventurer A5 ; leurs préréglages système (« @FF AD5X », « @FF C5P »…) sont reconnus par leur liste d'imprimantes ;
  - **IDEX et doubles têtes** : Snapmaker J1, Artisan, A350 Dual, UltiMaker S5, RatRig V-Core 4 IDEX, Z-Bolt Dual, Vivedino Xplorer IDEX ; et **4 têtes** : Vivedino Xplorer IQEX, WonderMaker ZR Ultra. Une carte par tête, et l'alerte quand le modèle a plus de couleurs que de têtes ;
  - **boîtes à couleurs** : Creality Hi, K1 avec la CFS, K2 Pro ; Qidi X-Plus 4, Q2C ; Voron 2.4, Trident ; Co Print ChromaSet ; LH Stinger MMU ; Phrozen Arco ; Anker M5C ; Sovol SV08 ; Bambu Lab A2L ;
  - **plusieurs buses** : Raise3D Pro3, Bambu Lab H2D Pro.
- **Noms courts** : la marque reste quand le reste du nom commence par un chiffre (« Voron 2.4 350 », « UltiMaker 2+ », au lieu de « 2.4 350 », « 2+ ») ; marques d'Orca ajoutées (Voron, Phrozen, WonderMaker, Co Print, FLSun, FELIX, TwoTrees…). Le fichier converti est signé « AD5X-by-Dragg », « Creator 5 Pro-by-Dragg »…
- Tests : 691 vérifications, dont `test_printers.py` (155). Dans Chrome, `check_070.py` montre aussi les cartes de la Flashforge AD5X, de la Creator 5 Pro et de la Snapmaker J1.

## 0.7.0 — 27/11/2026

- **Toutes les imprimantes d'Orca** (demandé par Dragg : « pas uniquement U1 ? Bambu, Elegoo, Anycubic ? », puis « la H3C et la P3C de Bambu Lab, et toutes les Prusa ») : le projet converti est fait pour l'imprimante de tes réglages, quelle qu'elle soit. Quatre familles, lues dans ses réglages d'Orca (nombre de buses, `single_extruder_multi_material`) :
  - **changeur d'outils** (Snapmaker U1, Prusa XL 5T, Prusa CORE One INDX 4 ou 8 têtes) : une case par tête, comme sur la U1 ;
  - **une buse et une boîte à couleurs** (Bambu Lab A1, P1S, P2S, X1, H2S avec l'AMS ; Prusa MK4, MK4S, CORE One avec MMU3 ; Anycubic Kobra 3 V2, S1, X avec l'ACE Pro ; Elegoo Centauri Carbon ; Creality K1C, K2 ; Qidi Q2…) : les couleurs du modèle vont dans les emplacements dont la bobine leur ressemble le plus, les autres suivent ;
  - **plusieurs buses** (Bambu Lab H2D, H2C, X2D) : chaque emplacement garde la buse prévue dans tes réglages. La Bambu Lab H3C (changeur de 9 têtes) et la P3C ne sont pas encore dans Orca : le plugin est prêt (testé avec des profils imités, de 6 à 9 buses) ;
  - **une seule bobine** (Prusa MINI, MK4S, CORE One… sans boîte) : nouvelle case **« Tout en une couleur »**, toutes les pièces et la peinture sur ton filament (dans l'onglet et dans le panneau).
- **Tes réglages, par imprimante** : « Mémoriser les réglages actuels d'Orca » garde un jeu de réglages par imprimante (la U1 et la P1S, par exemple). Tu passes de l'une à l'autre d'un clic (« Pour : P1S · U1 », sur l'accueil et en haut de l'analyse) ou dans la fenêtre Réglages (une carte par imprimante, « Retirer » pour l'oublier). Une analyse en cours est refaite pour l'imprimante choisie. Les réglages mémorisés par la 0.6 sont repris tels quels, et une 0.6 relit encore ceux de l'imprimante choisie.
- **La carte de ton imprimante**, sur l'accueil et dans les Réglages : une colonne par tête sur un changeur d'outils (au-delà de 5 têtes, la dernière colonne les résume), sinon tes bobines reliées à ta buse, ou à tes buses (gauche et droite sur une H2D, numérotées au-delà).
- **Purge calculée comme Orca** sur une imprimante à une buse ou plusieurs : d'après les couleurs du projet converti (la formule d'Orca, avec la purge minimale de ta buse : son volume, moins la longue rétraction à la coupe), sauf entre deux de tes bobines restées à leur place (ta purge, telle que dans tes réglages). Vers un filament de support : 230 ; depuis : au moins 700, comme Orca. Changeurs d'outils : comme avant.
- **Alertes de capacité** selon ton imprimante : « 7 couleurs pour 4 emplacements : ta P1S a besoin de plus de bobines chargées », « 6 filaments pour 5 têtes : ta XL 5T ne peut en charger que 5 à la fois », « 3 couleurs pour une seule bobine : coche « Tout en une couleur » », et toujours « au-delà de 4, ta U1 a besoin de multiACE ».
- **Fichiers signés du nom de ton imprimante** : `… - P1S-by-Dragg.3mf`, `… - Kobra S1-by-Dragg.3mf` (`… - U1-by-Dragg.3mf` pour la U1, comme avant). La signature d'une conversion d'avant est retirée du nom.
- **« Déjà pour ta P1S »** : un projet OrcaSlicer (ou Bambu Studio pour une Bambu Lab) fait pour ton imprimante n'est plus « à convertir », et le panneau de Préparer dit « Ce 3MF n'est pas réglé pour ta P1S ». Sans imprimante mémorisée, un projet OrcaSlicer est pris tel quel.
- Les préréglages système d'Orca faits pour ton imprimante (« @BBL P1S », « @U1 »…) passent d'abord. Une imprimante résine est refusée à la mémorisation.
- La U1 reste la mascotte. Le nom du plugin dans Orca reste « Mange-3MF (Snapmaker U1) » pour que la mise à jour remplace bien l'ancienne version.
- Tests : 640 vérifications, dont `test_printers.py` (104) avec les vrais profils de 33 imprimantes d'Orca (Bambu Lab, Prusa, Anycubic, Elegoo, Creality, Qidi, Snapmaker ; H3C et P3C imitées). Dans Chrome, `check_070.py` vérifie la carte de chaque famille, le choix de l'imprimante, « Retirer », les alertes, « Tout en une couleur » et le panneau. Nouveau visuel `07_printers.jpg`.

## 0.6.1 — 27/11/2026

- **Préréglages système d'Orca dans la liste de chaque couleur**, en plus des tiens (demandé par Dragg : « peut-on avoir les filaments de base aussi de Orca système ? ») : après « Dans tes réglages » et « Tes préréglages », la liste propose tous les préréglages système qu'Orca te montre pour ta U1 (ceux cochés dans sa fenêtre de choix des filaments), un groupe par marque comme dans Orca : « Préréglages système · Generic », « · Polymaker », « · SUNLU »… Dans l'onglet et dans le panneau de Préparer.
- Le choix d'office reste un de tes profils. Un préréglage système n'est choisi d'office que si aucun de tes profils n'a la matière du modèle (PETG…), comme en 0.6.0, et alors le mieux adapté à la U1 (même s'il n'est pas coché dans Orca).
- Un préréglage système choisi est lu en entier dans Orca à la conversion, et la mémoire des choix le reprend la fois suivante pour la même couleur.
- Orca réglée sur une autre imprimante que tes réglages mémorisés : les préréglages faits pour toutes les imprimantes sont proposés aussi.
- Le groupe « Profils d'Orca » s'appelle maintenant « Préréglages système », comme dans Orca.

## 0.6.0 — 26/11/2026

- **Projets PrusaSlicer (Printables)** : ils sont maintenant convertis comme les autres. Le projet est relu comme un projet Orca : un sous-objet par volume (pièces, pièces négatives, modificateurs, bloqueurs et forceurs de supports), peinture des couleurs, des supports et de la couture, couleur de chaque extrudeur, instances en plus, changements de couleur et pauses par hauteur, plages de couches, hauteurs de couches variables, réglages par objet courants (parois, couches du dessus et du dessous, remplissage, supports, bordure, purge dans le remplissage ou l'objet). Les réglages par objet qui n'existent pas dans Orca sont nommés dans une alerte. Les projets pour imprimante résine (SLA) sont refusés, comme les fichiers déjà tranchés (`.gcode.3mf`, `.bgcode`). Dans la liste des Téléchargements, un projet PrusaSlicer est « à convertir ».
- **3MF bruts en couleurs** (Fusion, Onshape, 3D Builder…) : leurs couleurs (groupes de couleurs et matériaux du 3MF) deviennent des filaments : la couleur de chaque objet, de chaque pièce d'un assemblage, et des triangles d'une autre couleur (peints).
- **Profils d'Orca pour une matière qui te manque** : si le modèle veut du PETG (ou du TPU…) et qu'aucun de tes profils n'en est, la liste propose les profils d'Orca prévus pour ta U1 dans cette matière (groupe « Profils d'Orca »), le meilleur est choisi d'office et « Avant de convertir » le dit : « Aucun de tes profils n'est du PETG : je propose « Generic PETG @U1 0.4 nozzle »… ». Le profil est relu en entier dans Orca à la conversion.
- **Mémoire des choix** : un profil changé à la main pour une couleur est repris la fois suivante pour la même couleur (ou presque) et la même matière, avec « ton choix de la dernière fois » sous la couleur. Remettre le profil proposé d'office l'oublie ; **Oublier mes choix de profils**, en bas de la fenêtre Réglages, efface tout.
- **Supports de l'auteur, au choix** : case « Garder les supports de l'auteur » (dans l'onglet et dans le panneau de Préparer) quand le projet a des supports : son type de supports et ses filaments de support et d'interface (renumérotés) passent dans le projet converti ; décochée, ce sont tes réglages. Largeur de ligne, vitesses et ventilation restent les tiennes. Tes choix de profils, de couleurs et tes couleurs en plus restent quand tu la coches ou la décoches, et le choix est gardé pour les fichiers suivants.
- **Allemand, espagnol et italien** : l'onglet, le panneau, les notifications et les noms des fichiers par plaque existent maintenant en 5 langues. L'onglet suit la langue d'Orca, ou celle choisie en haut à droite.
- Tests : 531 vérifications, dont `test_formats.py` (PrusaSlicer, CAO, projet résine) et `test_choices.py` (mémoire, profils d'Orca, supports) ; un vrai projet PrusaSlicer de 727 000 triangles peints est converti. Dans Chrome, `check_060.py` vérifie les nouveautés dans l'onglet et le panneau. Nouvelle capture `7_nouveautes.png`, nouveau visuel `06_new.jpg`.

## 0.5.3 — 24/11/2026

- **La U1 à côté du plateau** : quand Orca ouvre un 3MF qui n'est pas réglé pour la U1, elle apparaît dans un panneau à droite du plateau, dans Préparer et Aperçu : « Miam ! Ce 3MF n'est pas réglé pour ta U1 ». **Le manger** lance l'analyse avec tes réglages, et le panneau montre une ligne par filament : pastille pour changer la couleur, profil au choix parmi tes réglages et tes préréglages, cases libres, « + Ajouter une couleur », alertes. **Convertir** écrit le fichier, puis « C'est prêt ! » avec **Copier le chemin**. **Pas maintenant** ou la croix la rangent ; elle revient au prochain 3MF pas réglé pour la U1.
- **Un 3MF glissé sur le panneau** (ou choisi en cliquant « Dépose un 3MF ici ») suit le même chemin, sans passer par l'onglet (500 Mo au plus, lu par morceaux).
- **Même travail que l'onglet** : l'analyse lancée dans le panneau s'affiche aussi dans l'onglet (plaques, « Un fichier par plaque »…), et un profil, une couleur ou une couleur en plus changés d'un côté se retrouvent de l'autre.
- **Réglage** en bas du panneau (« Quand un 3MF n'est pas réglé : je viens ici / une notification / rien ») ou dans la fenêtre Réglages (« Quand Orca ouvre un 3MF pas réglé pour ta U1 »), avec le bouton « Mettre la U1 dans Préparer ». « Une notification » garde le fonctionnement d'avant. Si la U1 mâche déjà un 3MF, ou si cet Orca ne sait pas afficher de panneau (il faut la 2.5.1), c'est aussi une notification.
- **Bobines redessinées** dans les cartes des têtes (accueil et fenêtre Réglages) : pleines, dessinées en SVG, nettes à toutes les tailles.
- **Annuler** pendant une analyse ne bloque plus l'analyse suivante : chaque analyse a un numéro, et la page ignore celle qui a été annulée.
- Tests : 437 vérifications, dont 74 pour le panneau (Miam, Pas maintenant, glisser, conversion, plan partagé avec l'onglet, réglage, langue, Orca sans panneaux) ; le panneau est rendu dans Chrome en français et en anglais. Nouvelle capture `6_panneau.png`, nouveau visuel `05_prepare.jpg`.

## 0.5.2 — 23/11/2026

- **Couleurs en plus** : bouton « + Ajouter une couleur » sous « Couleurs et filaments ». Chaque couleur en plus devient un filament du projet que le modèle n'utilise pas, prêt pour peindre ou changer la couleur d'une pièce dans Orca (Orca ne laisse pas ajouter de filament au projet). Couleur et profil au choix, croix pour la retirer ; par défaut, la prochaine bobine de tes réglages qui n'est pas encore dans le tableau. 16 filaments au plus par fichier. Elles restent quand la langue change ou quand tu coches « Un fichier par plaque ».
- **Cases libres modifiables** : les cases de la U1 que le modèle n'utilise pas (« case libre ») ont maintenant une pastille et une liste de profils, comme les autres lignes. Sans changement, elles gardent ta bobine, comme avant.
- Une couleur en plus ne sert à aucune pièce : les pièces, la peinture et le G-code ne changent pas tant que tu ne l'utilises pas.
- Tests : 357 vérifications (couleurs en plus dans le projet, pièces et peinture identiques, limite de 16, cases libres) ; la page vérifie l'ajout, la couleur, le retrait, la limite, la légende, le changement de langue et de plan.

## 0.5.1 — 22/11/2026

- **Gros fichiers en glisser-déposer et avec Parcourir** : jusqu'à 500 Mo au lieu de 80 Mo. La page lit le fichier par morceaux de 16 Mo et les envoie l'un après l'autre (« Lecture de … (3/7) »), le plugin les recolle puis analyse comme d'habitude. Orca ne se fige pas, et Annuler arrête la lecture. Les fichiers de Téléchargements et les chemins collés étaient déjà lus directement sur le disque, sans limite.
- Tests : 343 vérifications (morceaux dans le désordre, morceau manquant, Annuler, limite) ; la page vérifie l'envoi par morceaux, le texte de lecture, Annuler pendant l'envoi et le refus au-delà de la limite.

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
