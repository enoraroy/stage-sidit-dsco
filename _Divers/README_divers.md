# Matériaux complémentaires : séparateurs, thésaurus, géolocalisation des lieux de vente

Ces trois scripts ne forment pas un pipeline : ce sont des outils indépendants, produits en support d'autres traitements (nettoyage des champs à valeurs multiples, alimentation du thésaurus, désambiguïsation des lieux). Chacun peut être exécuté isolément, dans n'importe quel ordre.

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `_uniformisation_separateurs.py` | Remplace, par `\|`, les séparateurs hétérogènes des champs dont le séparateur est connu avec certitude |
| `_liste_plat_lieux_personnes.py` | Extrait les valeurs uniques de `Region_lieu_production` et `Mentions_personnes_personnages`, à plat, pour alimenter le thésaurus |
| `_fusionner_geonames.py` | Fusionne pays et ville de vente en une seule colonne contenant l'URI GeoNames de la ville, qui désambiguïse le lieu sans traitement supplémentaire |

---

## Conventions communes

- **Encodage** : UTF-8 avec BOM (`utf-8-sig`). **Délimiteur** : point-virgule (`;`).
- **Résolution de colonnes tolérante** : les noms de colonnes attendus sont recherchés tels quels, puis par comparaison insensible aux accents/casse, avec avertissement explicite en cas de correspondance approximative.
- **Nommage des sorties** : horodatage `YYYYMMDD_HHMMSS`.
- Aucun de ces trois scripts ne fait de backup automatique du CSV source (à la différence des scripts d'imputation d'aire géographique) : chacun écrit un CSV de sortie distinct, le fichier source n'est jamais modifié en place.

---

## Description des scripts

### `_uniformisation_separateurs.py`

Uniformise, en un seul caractère `|`, les séparateurs de valeurs multiples au sein d'une même cellule — mais uniquement pour les champs dont le(s) séparateur(s) réellement utilisé(s) ont pu être identifiés avec certitude par relevé manuel :

| Champ | Séparateurs remplacés |
|---|---|
| `Materiaux` | `,` `;` `&` |
| `Techniques` | `;` |
| `Couleurs` | `;` |
| `Inscription_nature` | `;` |
| `Inscription_langue` | `;` |
| `Inscription_ecriture` | `;` |
| `Mentions_personnes_personnages` | `;` `,` |

Chaque cellule est découpée sur n'importe lequel des séparateurs listés pour son champ (repérés manuellement), chaque fragment est nettoyé (espaces superflus retirés), les fragments vides (séparateurs consécutifs ou en début/fin de cellule) sont supprimés, puis le tout est rejoint avec `|` (`"bronze ; or , argent"` → `"bronze|or|argent"`).

`Region_lieu_production` et `Etat_conservation` sont **volontairement exclus** : leurs séparateurs sont trop hétérogènes pour être traités par une simple substitution caractère par caractère, et nécessitent un traitement dédié, à part.

**Entrée** : CSV lots
**Sorties** : `lots_separateurs_uniformises_*.csv` (CSV complet, corrigé), `log_uniformisation_separateurs_*.csv` (uniquement les cellules modifiées, avant/après, par champ)

---

### `_liste_plat_lieux_personnes.py`

Extrait, pour `Region_lieu_production` (séparateurs `/`, `;`, `,`) et `Mentions_personnes_personnages` (séparateurs `;`, `,`), l'ensemble des valeurs uniques toutes lignes confondues, une fois éclatées sur leurs séparateurs respectifs et nettoyées des espaces superflus. L'objectif est d'obtenir une liste à plat, triée alphabétiquement et sans doublon, pour faciliter l'alimentation du thésaurus : plutôt que de parcourir ~54 000 lignes, on relit une liste de valeurs distinctes classée par ordre alphabétique.

Eventuellement, l'idée serait d'utiliser une distance de Levenshtein (SequenceMatcher) pour faire de l'alignement plus rapidement.

**Entrée** : CSV lots
**Sorties** : `valeurs_uniques_Region_lieu_production_*.txt`, `valeurs_uniques_Mentions_personnes_personnages_*.txt` (une valeur par ligne)

---

### `_fusionner_geonames.py`

Fusionne `Pays_vente_ou_demande` et `Ville_vente_ou_demande` en une seule colonne `lieu_vente_ou_demande`, contenant l'URI GeoNames de la ville plutôt que son nom en texte libre. L'intérêt : une fois l'URI GeoNames en main, le lieu est désambiguïsé une fois pour toutes (identifiant stable, référentiel externe), sans qu'aucun traitement de normalisation orthographique ou de résolution de doublons ne soit plus nécessaire sur ce champ.

Le nom de ville est normalisé (accents et casse retirés) avant recherche dans une table de correspondance ville → URI GeoNames (faite manuellement, compte tenu du faible nombre de villes). Si la cellule contient plusieurs villes séparées par une virgule, chacune est résolue indépendamment et les URIs obtenues sont réunies avec `|`. Si une ville n'est pas reconnue, sa valeur brute est conservée telle quelle (aucune perte de donnée) et la ligne est signalée pour vérification manuelle. Les deux colonnes source sont supprimées, la nouvelle colonne est insérée à la position de la première des deux dans l'ordre d'origine.

**Entrée** : CSV lots
**Sorties** : `lots_lieu_vente_geonames_*.csv` (CSV complet, corrigé), `log_villes_non_resolues_*.txt` (villes non reconnues, à compléter manuellement dans la table de correspondance), `log_stats_lieu_vente_*.txt`

---

## Chemins à adapter

Chaque script contient en tête une section `CSV_PATH` à modifier. Le répertoire de sortie est toujours déduit automatiquement du chemin d'entrée.
