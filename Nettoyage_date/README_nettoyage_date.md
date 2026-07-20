# Uniformisation et nettoyage des champs de datation

Le LLM avait pour tâche de calculer les bornes inférieure et supérieure (`Date_plus_basse`, `Date_plus_haute`) à partir des spécifications du DAI et du champ `Date_complete` de chaque lot. Or plusieurs problèmes systématiques ont été identifiés dans le tableur :

- des résultats différents pour des cas similaires dès qu'apparaît une mention d'approximation (« circa », « ca », « c. ») ;
- des valeurs différentes ou erronées sur les indications temporelles « début », « déb. » appliquées aux millénaires, et sur « vers », « autour », « v. » appliqués aux siècles et millénaires ;
- de mauvaises bornes calculées pour les millénaires ;
- le non-respect des spécifications du DAI sur la conversion des chiffres romains en chiffres arabes.

Chaque script de ce dossier traite l'un de ces problèmes, en séparant systématiquement le **recensement** (lecture seule, pour quantifier et préparer la vérification manuelle) de la **correction automatique**, qui n'est appliquée que lorsqu'elle est sans risque.

---

## Vue d'ensemble du pipeline

```
25_recenser_chiffres_romains_date.py     (lecture seule)
        │
        │  rapport_chiffres_romains_date_*.csv
        ▼
26_conversion_chiffres_romains.py        (autonome, moteur de detection identique a 25)
        │
        │  lots_dates_arabes_corriges_*.csv
        │  log_conversion_chiffres_romains_date_*.csv
        ▼
        ├── 27_verif_date_circa.py           (lecture seule)  → log_circa_*.csv
        ├── 28_verif_date_millenaire.py       (lecture seule)  → log_millenaires_*.csv
        └── 29_verif_date_vers.py             (lecture seule)  → log_vers_siecle_*.csv
                        │
                        ▼
        corrections manuelles de Date_plus_basse / Date_plus_haute
        selon les spécifications DAI, guidées par les trois logs
```

Les scripts `27`, `28` et `29` sont indépendants entre eux : chacun relit le CSV produit par `26` et recense un type de mention différent, sans dépendre des deux autres.

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `25_recenser_chiffres_romains_date.py` | Recense les valeurs de `Date_complete` contenant un chiffre romain (I à XXI) valide |
| `26_conversion_chiffres_romains.py` | Convertit ces chiffres romains en chiffres arabes, à moteur de détection identique à `25` |
| `27_verif_date_circa.py` | Recense les mentions « circa/ca/c. » ne portant pas sur une année à 4 chiffres |
| `28_verif_date_millenaire.py` | Recense les mentions de millénaire, tous contextes confondus |
| `29_verif_date_vers.py` | Recense les mentions « vers » associées à un siècle |

---

## Conventions communes

- **Encodage** : UTF-8 avec BOM (`utf-8-sig`) sur tous les CSV en entrée et en sortie.
- **Délimiteur** : point-virgule (`;`).
- **Lecture seule sauf `26`** : les scripts `25`, `27`, `28`, `29` ne modifient jamais le CSV source — ils ne produisent qu'un rapport ou un log. Seul `26` écrit un CSV corrigé, en plus de son log de changements.
- **Nommage des sorties** : horodatage `YYYYMMDD_HHMMSS`.
- **Colonnes attendues** : `Date_complete`, `Id_perenne`, `Identifiant_catalogue`, et — à partir de `27` — `Date_plus_basse`, `Date_plus_haute`.

---

## Description des scripts

### `25_recenser_chiffres_romains_date.py`

Recense, dans `Date_complete`, toutes les valeurs contenant un chiffre romain valide (I à XXI), en distinguant les vrais cas de siècle des faux positifs. La détection se fait en trois temps : repérage d'un bloc maximal de lettres I/V/X en début de mot, validation du numéral (I à XXI uniquement), puis exigence d'un suffixe ordinal ou contextuel juste après (`e`, `er`, `°`, « siècle(s) », ou une fourchette du type `V-IVe`) — les 1 ou 2 mots suivant ce suffixe ne doivent pas non plus appartenir à une liste de mots de contexte « non-date » (`dynastie`, `république`, `empire`, `règne`, `période`…), pour exclure les numéros de régime ou de dynastie.

Cas bien capturés : `fin du XIXe siecle`, `V-IVe siecle avant J.-C.`, `XIIe/XIIIe siecle`.
Cas volontairement exclus : `Ier Empire` / `IIIe dynastie` (numéro de régime, pas de siècle), `Amenhotep III` (pas de suffixe ordinal).

**Entrée** : CSV lots (`Date_complete` renseigné)
**Sortie** : `rapport_chiffres_romains_date_*.csv` (une ligne par valeur concernée, avec les formes romaines trouvées)

---

### `26_conversion_chiffres_romains.py`

Reprend à l'identique le moteur de détection du script `25` (candidat maximal + suffixe + filtrage par mots de contexte), pour garantir que seules les formes déjà recensées par `25` sont converties — les deux scripts restent toutefois indépendants, aucun des deux ne modifie l'autre. Chaque numéral romain valide est remplacé par sa valeur arabe ; le suffixe et le reste du texte sont laissés inchangés (`XIXe siecle` → `19e siecle`, `V-IVe siecle avant J.-C.` → `5-4e siecle avant J.-C.`). Les stopwords de contexte évitent de convertir les numéros de dynastie, de règne ou de titre (`Ier Empire`, `IIIe dynastie` restent inchangés).

> Cette conversion a porté sur **10 794 lots**.

**Entrée** : CSV lots (même fichier source que `25`)
**Sorties** : `lots_dates_arabes_corriges_*.csv` (CSV complet, corrigé), `log_conversion_chiffres_romains_date_*.csv` (uniquement les lignes modifiées, avant/après)

---

### `27_verif_date_circa.py`

Fait suite à `26` : relit son CSV corrigé pour recenser les lignes où un marqueur d'approximation (`circa`, `ca.`, `c.`) porte sur autre chose qu'une année à 4 chiffres. Une ligne n'est retenue que si les trois conditions sont vraies : présence d'un marqueur circa, absence de mention av./ap. J.-C. (ces formes suivent leurs propres règles), et absence d'une année à 4 chiffres directement après le marqueur (`circa 1982`, `c. 1960's` ont des bornes calculables et ne posent pas de problème). Ce qui reste — `ca. 18e-19e siecle`, `circa deuxieme quart du 17e siecle` — sont les formulations non numériques qui nécessitent une vérification manuelle des bornes selon les spécifications du DAI.

> **323 lignes** ont ainsi été soumises à vérification manuelle. Le volume de corrections effectivement nécessaires n'est pas quantifiable a priori (cela dépend du cas par cas), mais celui des lignes à vérifier l'est.

**Entrée** : CSV corrigé par `26`
**Sortie** : `log_circa_*.csv`

---

### `28_verif_date_millenaire.py`

Fait suite à `26`. Recense toute ligne dont `Date_complete` contient un terme de millénaire, sans filtrage de contexte (`millenaire(s)`, `millennium`, `millennia`, `milleniums`) : contrairement à `circa` ou `vers`, aucun cas n'est exclu d'office, la datation d'un millénaire dépendant systématiquement d'une règle métier à appliquer manuellement.

> **440 lignes** ont été vérifiées manuellement selon les spécifications du DAI :
> - **Début de millénaire** : 250 premières années (ex. début du 1er millénaire = -1000 à -750)
> - **Fin de millénaire** : 250 dernières années (ex. fin du 1er millénaire = -250 à -1)
> - **Première moitié** : 500 premières années (ex. première moitié du 1er millénaire = -1000 à -500)
> - **Seconde moitié** : 500 dernières années (ex. seconde moitié du 1er millénaire = -500 à -1)
>
> Si l'intervalle s'étend sur deux millénaires, les règles ci-dessus s'appliquent à chaque mention séparément (ex. « 2e millénaire — début du 1er millénaire » = -2000 à -750).

**Entrée** : CSV corrigé par `26`
**Sortie** : `log_millenaires_*.csv`

---

### `29_verif_date_vers.py`

Fait suite à `26`. Recense les lignes où `Date_complete` contient à la fois le mot « vers » et un terme de siècle (`siecle(s)`, `century`/`centuries`) — par exemple `vers le 19e siecle`, `vers le debut du 18e siecle`. Les mentions « vers » appliquées à une année seule (`vers 1850`) ne sont pas concernées : elles ont une borne calculable et ne nécessitent pas de vérification.

> **175 lignes** ont été soumises à vérification manuelle, puis corrigées selon les spécifications du DAI lorsque nécessaire.

**Entrée** : CSV corrigé par `26`
**Sortie** : `log_vers_siecle_*.csv`

---

## Résultats

| Étape | Lignes concernées |
|---|---|
| Conversion des chiffres romains (25 → 26) | 11 702 lots convertis |
| Mentions « circa » hors année/J.-C. (27) | 323 lignes vérifiées manuellement |
| Mentions « vers » + siècle (29) | 175 lignes vérifiées manuellement |
| Mentions de millénaire (28) | 440 lignes vérifiées manuellement |

Le nombre de corrections effectivement appliquées à l'issue de la vérification manuelle n'est pas quantifié précisément — seul le volume de lignes soumises à vérification l'est, la nécessité d'une correction se jouant au cas par cas.

## Ordre d'exécution

1. `25_recenser_chiffres_romains_date.py`
2. `26_conversion_chiffres_romains.py`
3. `27_verif_date_circa.py`, `28_verif_date_millenaire.py`, `29_verif_date_vers.py` — dans l'ordre souhaité, indépendants les uns des autres
4. Corrections manuelles de `Date_plus_basse` / `Date_plus_haute` sur le CSV produit par `26`, guidées par les trois logs et les spécifications du DAI

---

## Chemins à adapter

Chaque script contient en tête une section `CSV_PATH` à modifier. Le répertoire de sortie (`OUTPUT_DIR`) est toujours déduit automatiquement du chemin d'entrée.
