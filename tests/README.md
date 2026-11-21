# Tests de Mange-3MF

Tests automatiques **sans OrcaSlicer** (Python 3.12 ou plus, bibliothèque standard seulement).

```
python tests/run_all.py
```

Il faut deux 3MF d'exemple dans `tests/samples/`, qui ne sont pas publiés (licences de leurs auteurs) : voir [samples/PROVENANCE.md](samples/PROVENANCE.md).

| Fichier | Ce qui est vérifié |
|---|---|
| `test_core.py` | Peinture (lecture, renumérotation, aller-retour sur les 6 000 chaînes d'un vrai modèle), lecture d'un vrai 3MF MakerWorld (557 000 triangles), conversion simple. |
| `test_multi.py` | Projet Bambu (X1C, plateau 256) à 7 couleurs sur 6 plaques : un seul fichier de 7 filaments, couleurs de chaque plaque, toutes les listes de réglages à 7 valeurs, purge 7×7, positions dans le plateau de la U1, cohérence des fichiers internes, peinture d'une 7ᵉ couleur, rien de fusionné sur une plaque à 7 couleurs, 4 cases gardées pour moins de 4 couleurs, un fichier par plaque. |
| `test_template.py` | Réglages « OrcaSlicer 2.5.1 » complets (5 filaments + 1 couleur mélangée, deux variantes de buse par filament, purge pour 4 buses) : chaque réglage recopié depuis le bon profil, variante par variante, têtes prévues, couleurs mélangées retirées, profils de base, purge. |
| `test_variants.py` | Projet Snapmaker Orca U1 à 7 couleurs (positions gardées), plateau plus grand (350 mm), plaque trop grande, 3MF sans réglages, fichier déjà tranché, fichier qui n'est pas un 3MF, autre profil choisi pour une couleur (alerte de matière), plan incomplet ou profil inconnu refusés. |
| `test_origin.py` | Origine des fichiers : un projet d'OrcaSlicer 2.5.1 est signé « BambuStudio-02.08.01.55 » avec l'étiquette « OrcaSlicer 2.5.1 ». Réglages mémorisés acceptés ou refusés, origine affichée, fichiers « à convertir » ou « déjà pour la U1 », étiquette ajoutée au fichier converti. |
| `test_presets.py` | Préréglages de filament d'Orca : valeurs écrites par Orca (textes, guillemets, nombres, aller-retour), noms sans projet, lecture dans un faux Orca (utilisateur, système, copies de projet, autre imprimante), profils proposés et choix automatique, réglages du projet faits depuis un préréglage (variantes, parents, conditions, aucun écart noté) et reconnus tels quels, conversion avec couleur choisie, dossier des fichiers convertis. |
| `test_lang.py` | Langues : chaque langue de `TEXTS` a tous les textes et les mêmes valeurs `{0}`, `{1}`… ; textes demandés par le code et par la page tous traduits, noms de couleurs ; page de l'onglet (textes en JSON, langue de départ) ; langue d'Orca ou du système (`fr_FR`, `French_France`, `de_DE`…) ; retraduction d'un message déjà fait ; analyse, alerte, noms des fichiers et erreur en anglais. |
| `test_plugin.py` | Le plugin dans un **faux OrcaSlicer** (`fake_orca.py`) : enregistrement et droits, version de l'en-tête lue par Orca = version de l'onglet, onglet (nom, icône de la U1 au trait, page), liste des Téléchargements, mémorisation des réglages, analyse, nouveau plan, conversion, écriture sans écraser, page reconstruite (derniers résultats renvoyés), notification à l'ouverture d'un projet puis « prête », langue (Orca en français ou en allemand, anglais choisi puis « Auto », choix gardé, analyse et résultat renvoyés traduits, notifications et erreurs en anglais), préréglages proposés, dossier choisi (refusé s'il n'existe pas, gardé, fichier écrit dedans), erreurs. |

Fichiers d'aide :

- `common.py` : outils communs, réglages « utilisateur » de test (simples, et complets façon Orca 2.5.1) ;
- `make_samples.py` : fabrique des projets de test (plusieurs plaques, 7 couleurs, peinture) à partir de l'exemple Pokéballs ;
- `fake_orca.py` : faux module `orca` (onglet, notifications, profils, préréglages de filament écrits comme Orca, export de projet, langue d'Orca) ;
- `samples/` : 3MF d'exemple (voir `samples/PROVENANCE.md`) ;
- `ui/` : rendu de l'onglet dans Chrome pour refaire les captures de `docs/captures/` (français) et `docs/captures/en/` (anglais) : `python tests/ui/make_captures.py`, nécessite Node, `npm install` dans `tests/ui`, Chrome et Pillow. Vérifie aussi le changement de langue dans la page, le bouton Ko-fi et la U1 gourmande (bouche ouverte, avale, mâche, rote les couleurs, recrache), et capture la U1 qui a faim (`4_glouton.png`). Les visuels de `docs/visuals/` (Orca Cloud, GitHub) se refont ensuite avec `node tests/ui/make_visuals.js` (logo pris dans `docs/visuals/logo/`).

Les tests lisent les messages en français (`common.py` règle `LANGUAGE=fr_FR`) ; l'anglais est vérifié par `test_lang.py` et `test_plugin.py`.

Les fichiers fabriqués pendant les tests vont dans un dossier temporaire, jamais dans ce dossier.
