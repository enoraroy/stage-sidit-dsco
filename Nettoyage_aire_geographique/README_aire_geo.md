# Imputation et harmonisation de l'aire géographique de production

## Contexte et hypothèses

Certaines lignes disposaient d'une `Region_lieu_production` renseignée, mais sans `Aire_geographique_production` imputée par le LLM (« origine inconnue »), alors que le LLM avait pourtant pour consigne d'imputer cette donnée à partir du thésaurus fourni par le DAI.

L'hypothèse retenue : si une valeur de `Region_lieu_production` était déjà renseignée ailleurs dans le tableur — sur l'ensemble des quelque 54 000 lignes — avec une aire géographique connue, cette correspondance pouvait servir à imputer les lignes manquantes correspondantes ; et si la correspondance était unique mais absente du thésaurus, l'imputation restait possible à la main, cas par cas.

## Difficultés rencontrées

Cette approche s'est révélée plus complexe qu'anticipé :

- plusieurs aires géographiques distinctes pouvaient correspondre à une même valeur de `Region_lieu_production` — Paris, par exemple, se retrouvait associée à différents continents selon les lignes ;
- certaines régions de production étaient inconnues du thésaurus, notamment des villes très précises ou des orthographes différentes ;
- plusieurs régions de production pouvaient être renseignées sur une même ligne, suffisamment éloignées pour que leurs aires géographiques ne concordent pas — un cas parfois tranchable à l'œil, mais qui ne se généralise pas.

En raison de ces difficultés, une bonne partie de l'imputation a dû être réalisée manuellement : environ **255 lignes** une fois dédupliquées (aire inconnue ou plusieurs régions renseignées), et **215 cas ambigus** où une même valeur de région pouvait correspondre à plusieurs aires géographiques distinctes — certains non triviaux, par exemple « province ottomane », à laquelle le LLM avait imputé des aires très diverses.

---

## Vue d'ensemble du pipeline

```
30_imputer_lieux_manquants.py        (thesaurus + correspondance deduite du CSV)
        │
        │  lots_aire_imputee_*.csv
        │  a_completer_regions_non_reconnues_*.csv
        │  a_completer_regions_ambigues_*.csv
        ▼
   completion manuelle des deux fichiers "a_completer_*"
   (colonne Aire_a_appliquer)
        │
        ▼
31_application_imputation_lieux_manquants.py
        │
        │  lots_aire_completee_*.csv
        ▼
32_verif_aire_geo.py                  (diagnostic global, lecture seule)
        │
        │  incoherences_aire_recap_*.csv
        ▼
   completion manuelle du recapitulatif
   (colonne Aire_a_retenir)
        │
        ▼
33_appliquer_dernieres_decisions.py
        │
        │  lots_aire_harmonisee_*.csv
        ▼
34_harmoniser_aire_geographique.py    (canonicalisation de l'ordre des combinaisons)
        │
        │  lots_aire_canonicalisee_*.csv
```

`32_verif_aire_geo.py` est un diagnostic global, indépendant du statut « origine inconnue » : il peut être relancé après `44` ou `45` pour vérifier qu'aucune incohérence résiduelle ne subsiste, sans qu'il fasse à proprement parler partie d'une seule passe linéaire.

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `30_imputer_lieux_manquants.py` | Impute `Aire_geographique_production` depuis le thésaurus ou une correspondance déduite du CSV ; signale les cas non résolus |
| `31_application_imputation_lieux_manquants.py` | Applique les décisions manuelles prises sur les régions non reconnues et ambiguës |
| `32_verif_aire_geo.py` | Diagnostic en lecture seule : régions associées à plusieurs aires distinctes, sur tout le CSV |
| `33_appliquer_dernieres_decisions.py` | Applique les décisions du récapitulatif, en réalignant *toutes* les lignes de la région concernée |
| `34_harmoniser_aire_geographique.py` | Canonicalise l'ordre des aires dans les valeurs multiples (`"A\|B"` / `"B\|A"` → une seule forme) |

---

## Conventions communes

- **Encodage** : UTF-8 avec BOM (`utf-8-sig`). **Délimiteur** : point-virgule (`;`).
- **Backup automatique** : chaque script qui modifie le CSV commence par en créer une copie horodatée (`BACKUP_*`) avant toute écriture.
- **Résolution de colonnes tolérante** : les noms de colonnes attendus sont recherchés tels quels, puis — s'ils sont absents — par comparaison insensible aux accents/casse, avec un message d'avertissement explicite. Le script s'arrête si une colonne reste introuvable.
- **Fichiers « à compléter »** : produits en CSV avec une colonne vide à remplir à la main (`Aire_a_appliquer`, `Aire_a_retenir`), puis relus par le script suivant. Les fichiers de décisions eux-mêmes ne sont jamais modifiés par les scripts qui les consomment.
- **Nommage des sorties** : horodatage `YYYYMMDD_HHMMSS`.

---

## Description des scripts

### `30_imputer_lieux_manquants.py`

Pour chaque ligne où `Aire_geographique_production` vaut exactement « Origine inconnue » et où `Region_lieu_production` est renseignée, l'imputation suit un ordre de priorité strict :

1. **Thésaurus externe** (`thesaurus_lieux.csv`) — priorité absolue, même si le CSV suggère autre chose.
2. **À défaut**, une correspondance déduite du CSV lui-même : si la région n'est associée, ailleurs dans le fichier, qu'à une **seule** aire distincte (hors « origine inconnue »), cette aire est imputée.
3. **Si plusieurs aires distinctes** sont associées à la région ailleurs dans le CSV → signalée comme *ambiguë*, pas imputée automatiquement.
4. **Si la région est introuvable** dans le thésaurus et dans le CSV → signalée comme *non reconnue*, pas imputée.

Les conflits internes au thésaurus (une même région associée à deux termes candidats différents) sont détectés, retirés des correspondances utilisées, et signalés à part — ces régions ne bénéficient donc d'aucune imputation automatique et n'apparaissent dans aucun des deux fichiers « à compléter » produits.

**Entrées** : CSV lots, `thesaurus_lieux.csv`
**Sorties** : `lots_aire_imputee_*.csv`, `log_imputations_aire_*.txt`, `a_completer_regions_non_reconnues_*.csv`, `a_completer_regions_ambigues_*.csv` (une ligne par région distincte, triée par nombre de lignes concernées décroissant), `log_stats_aire_*.txt`

---

### `31_application_imputation_lieux_manquants.py`

Relit les deux fichiers « à compléter » une fois leur colonne `Aire_a_appliquer` remplie à la main, et applique la décision à toute ligne dont `Aire_geographique_production` vaut encore « Origine inconnue » et dont la région correspond. Si une même région a reçu deux décisions différentes entre les deux fichiers (erreur de saisie), le conflit est signalé et **aucune des deux n'est appliquée** pour cette région, plutôt que de trancher arbitrairement à la place de l'utilisateur.

**Entrées** : CSV produit par le précédent, les deux fichiers de décisions complétés
**Sorties** : `lots_aire_completee_*.csv`, `log_application_decisions_aire_*.txt`, `log_stats_application_aire_*.txt`

---

### `32_verif_aire_geo.py`

Diagnostic de cohérence globale, en lecture seule : ce script scanne **toutes** les lignes du CSV. Une région est signalée dès que deux aires distinctes (ou plus) lui sont associées quelque part dans le fichier, qu'il y ait eu ou non une imputation à faire.

**Entrée** : CSV le plus à jour
**Sorties** : `incoherences_aire_detail_*.txt` (détail ligne par ligne par région concernée), `incoherences_aire_recap_*.csv` (une ligne par région, avec les aires trouvées et une colonne `Aire_a_retenir` à compléter)

---

### `33_appliquer_dernieres_decisions.py`

Relit le récapitulatif de `33` une fois sa colonne `Aire_a_retenir` complétée. Pour chaque région ayant reçu une décision, **toutes** les lignes portant cette région voient leur `Aire_geographique_production` alignée sur la valeur décidée — y compris celles qui avaient déjà une valeur, différente ou non, puisque l'objectif est de rendre cohérentes entre elles toutes les lignes d'une même région, pas seulement de compléter les vides.

**Entrées** : CSV le plus à jour, récapitulatif complété de `32`
**Sorties** : `lots_aire_harmonisee_*.csv`, `log_application_incoherences_aire_*.txt`, `log_stats_application_incoherences_aire_*.txt`

---

### `34_harmoniser_aire_geographique.py`

Dernière étape : les valeurs multiples (plusieurs aires séparées par `|`) peuvent apparaître dans des ordres différents selon les lignes (`"Maghreb|Monde iranien – Caucase"` vs `"Monde iranien – Caucase|Maghreb"`), ce qui produit des doublons purement liés à l'ordre. Chaque cellule est découpée sur `|`, triée alphabétiquement (insensible à la casse et aux diacritiques), puis réunie — toutes les lignes portant la même combinaison, quel que soit l'ordre d'origine, se retrouvent avec une valeur canonique identique. Aucune autre colonne n'est touchée.

**Entrée** : CSV le plus à jour
**Sorties** : `lots_aire_canonicalisee_*.csv`, `log_canonicalisation_aire_*.txt`, `log_stats_canonicalisation_aire_*.txt` (distribution des valeurs avant/après)

---

## Résultats

Une fois l'imputation et l'harmonisation menées à leur terme, le champ `Aire_geographique_production` compte **57 combinaisons distinctes** (aires seules ou associations de plusieurs aires séparées par `|`), mais l'immense majorité des ~49 700 lots renseignés se concentre sur seulement **10 aires géographiques** (plus le vide), les combinaisons multiples restant marginales. Les aires les plus représentées, très largement majoritaires :

| Aire géographique | Effectif |
|---|---|
| Monde iranien – Caucase | 15 433 |
| Sous-continent indien | 8 702 |
| Asie Mineure et Europe orientale | 6 191 |
| Europe occidentale | 6 006 |
| Asie du sud-est | 4 876 |
| Proche-Orient arabe | 4 039 |
| Maghreb | 3 047 |
| Péninsule arabique | 371 |
| Amérique du Nord | 200 |
| Afrique subsaharienne | 327 |

Les combinaisons de plusieurs aires (`Maghreb\|Proche-Orient arabe`, `Monde iranien – Caucase\|Proche-Orient arabe`…) représentent chacune quelques unités à quelques dizaines de lots, sur les 57 combinaisons recensées.

---

## Chemins à adapter

Chaque script contient en tête une section `CSV_PATH` (et, pour `41`, `42`, `44`, `THESAURUS_PATH` / les chemins de décisions) à modifier. Les répertoires de sortie sont toujours déduits automatiquement du chemin d'entrée.
