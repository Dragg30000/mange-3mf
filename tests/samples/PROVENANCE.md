# Provenance des fichiers d'exemple

Les deux fichiers viennent du dépôt public [josuanbn/bl2u1](https://github.com/josuanbn/bl2u1) (convertisseur Bambu Studio → Snapmaker Orca), où ils servent d'exemples :

| Fichier ici | Fichier d'origine | Contenu |
|---|---|---|
| `sample_dragon.3mf` | `filament_types.3mf` | « cute baby dragon » (MakerWorld, auteur Ryan, licence « Standard Digital File License »), peint en 4 couleurs, converti pour la U1. |
| `sample_pokeballs.3mf` | `u1_template.3mf` | 6 Pokéballs en 4 pièces, 4 couleurs, projet pour la U1. |

Ils servent seulement aux tests.

`tests/printers_orca.json` (dans le dépôt) reprend quelques valeurs des profils d'imprimante d'[OrcaSlicer](https://github.com/OrcaSlicer/OrcaSlicer) (`resources/profiles/*/machine/`, AGPL-3.0) : modèle, buses, plateau, volume de buse. Il sert aux tests de `test_printers.py`. **Ne pas les publier** (dépôt GitHub, Orca Cloud…) sans vérifier les licences : les modèles appartiennent à leurs auteurs.

**Sur GitHub, ces deux fichiers ne sont pas dans le dépôt.** Pour lancer les tests, télécharge `filament_types.3mf` et `u1_template.3mf` depuis [josuanbn/bl2u1](https://github.com/josuanbn/bl2u1), mets-les dans `tests/samples/` et renomme-les `sample_dragon.3mf` et `sample_pokeballs.3mf`.

Deux fichiers de plus, facultatifs, servent à `test_formats.py` s'ils sont là : `sample_prusa_drakos.3mf` (un vrai projet PrusaSlicer 2.7.4 multicolore) et `sample_cad_color.3mf` (un 3MF de logiciel de CAO avec une couleur). Eux non plus ne sont pas publiés.
