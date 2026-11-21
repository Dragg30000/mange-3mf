# Historique des versions — Mange-3MF (Snapmaker U1)

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
