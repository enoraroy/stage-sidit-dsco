# Nettoyage des champs vides

Ce dossier contient les scripts Python de nettoyage et de vérification du CSV (colonne `Id_perenne` comme identifiant de traçabilité). Il s'agit ici d'identifier et de vider les valeurs non significatives des champs, que le LLM a inventé pour remplacer un vide, ou un NA. Il s'agit par exemple d'expression comme "Non indiqué", "Non précisé".

Les deux scripts fonctionnent en pipeline :

```
CSV brut ──▶ 07_nettoyage_champs.py ──▶ CSV nettoyé ──▶ 08_verification_expressions.py ──▶ rapport de vérification
```

---

## 1. `07_nettoyage_champs.py`

Nettoie automatiquement les champs contenant des valeurs "non renseignées" strictement identifiées, et détecte les incohérences liées au champ `Inscription_booleen`.

### Ce qu'il fait

1. **Backup** — copie horodatée du CSV source (`BACKUP_<timestamp>_<nom_original>.csv`) créée avant toute lecture ou écriture.
2. **Nettoyage strict** (passe 1) — pour chaque champ listé dans `FIELDS_TO_CLEAN`, si la valeur de la cellule est **exactement égale** (comparaison stricte, sans regex, sensible à la casse et aux accents) à une des expressions attendues, elle est vidée. Chaque suppression est tracée par `Id_perenne`.
3. **Détection d'incohérence** (passe 2, exécutée après le nettoyage) — pour les lignes où `Inscription_booleen = "Non"`, vérifie si un des champs d'inscription contient tout de même une valeur. `Inscription_nature = "Non précisée"` est ignoré pour cette détection uniquement (valeur neutre, pas une véritable incohérence) sans être modifié dans le CSV.
4. **Statistiques** — compteurs par champ, nombre total d'opérations, nombre de lignes modifiées, nombre de lignes incohérentes.

### Champs nettoyés (`FIELDS_TO_CLEAN`)

| Champ | Expressions strictes vidées |
|---|---|
| `Epoque_periode_dynastie` | `Non précisée` |
| `Materiaux` | `Non spécifiés` |
| `Techniques` | `Non spécifiés` |
| `Provenance` | `Non précisée`, `Non spécifié`, `Non spécifiée`, `Non spécifiés` |
| `Inscription_langue` | `Non précisée` |
| `Inscription_ecriture` | `Non précisé` |
| `Inscription_transcription` | `non déchiffré`, `Non précisée` |
| `Inscription_transliterration` | `Non précisée` |
| `Inscription_traduction` | `Non précisée` |
| `Mentions_oeuvres_comparaison` | `Non précisée` |


### Champs vérifiés pour l'incohérence (`INSCRIPTION_FIELDS`)

`Inscription_nature`, `Inscription_langue`, `Inscription_ecriture`, `Inscription_transcription`, `Inscription_transliterration`, `Inscription_traduction`

### Configuration

Modifier la constante en tête de fichier avant exécution :

```python
CSV_PATH = r"C:\chemin\vers\le\fichier.csv"
```

### Sorties (dans le même dossier que le CSV source)

| Fichier | Contenu |
|---|---|
| `BACKUP_<timestamp>_<nom_original>.csv` | Copie de sauvegarde du CSV avant modification |
| `lots_nettoyes_<timestamp>.csv` | CSV nettoyé |
| `log_modifications_<timestamp>.txt` | Détail : `Id_perenne ; champ ; valeur supprimée` |
| `log_incoherences_inscription_<timestamp>.txt` | `Id_perenne` + champs/valeurs incohérents avec `Inscription_booleen = Non` |
| `log_statistiques_<timestamp>.txt` | Compteurs globaux et par champ |

### Exécution

```bash
python 07_nettoyage_champs.py
```

---

## 2. `08_verification_expressions.py`

Script de **contrôle en lecture seule** (ne modifie rien), à exécuter **après** `07_nettoyage_champs.py`, sur le CSV nettoyé produit par ce dernier.

### Ce qu'il fait

Scanne **toutes les colonnes** du CSV (à l'exception d'`Id_perenne`) et recherche, dans **chaque cellule**, une correspondance **strictement exacte** avec une expression de la liste `EXPRESSIONS_A_DETECTER` — indépendamment du champ dans lequel elle apparaît. Chaque correspondance trouvée est notée : `Id_perenne`, nom de la colonne, valeur.

Utile pour :
- vérifier qu'aucune occurrence résiduelle des expressions ciblées (on peut donc en rajouter) ne subsiste après le nettoyage,
- repérer des occurrences inattendues dans des colonnes non anticipées (ex. `Titre_lot`, `Notice`, `References_bibliographiques`...).

### Expressions recherchées (`EXPRESSIONS_A_DETECTER`)

`Non précisée`, `Non précisé`, `Non spécifié`, `Non spécifiée`, `Non spécifiés`, `non déchiffré`, `non daté`, `Daté (date non spécifiée)`, `Non indiquée`, `Siècle non spécifié`, `Date non spécifiée`

### Configuration

```python
CSV_PATH = r"C:\chemin\vers\lots_nettoyes_<timestamp>.csv"
```

### Sorties (dans le même dossier que le CSV vérifié)

| Fichier | Contenu |
|---|---|
| `detections_expressions_<timestamp>.txt` | Détail : `Id_perenne ; colonne ; "valeur"` pour chaque détection |
| `stats_detections_expressions_<timestamp>.txt` | Nombre total de détections, lignes concernées, compteurs par colonne et par expression |

### Exécution

```bash
python 08_verification_expressions.py
```

---

## Notes communes aux deux scripts

- **Comparaison stricte uniquement** : aucune regex, aucune normalisation implicite de la valeur comparée (espaces, casse, accents comptent).
- **Encodage** : lecture/écriture en `utf-8-sig` (compatible avec un export Excel contenant des accents).
- **Délimiteur CSV** : `;`
- Aucune dépendance externe — bibliothèque standard Python uniquement (`csv`, `os`, `shutil`, `unicodedata`, `collections`, `datetime`).
