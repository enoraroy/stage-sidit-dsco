# Détection et traitement des erreurs d'inscription du LLM

## Contexte

Au fil de l'appréhension des données, des corrections manuelles et de la révision du corpus, il est apparu que le LLM inventait parfois des notices. Plus problématique que l'invention de lots entiers — plus facile à repérer —, les valeurs hallucinées ressemblaient presque en tous points aux valeurs originales, sauf à la consultation du catalogue, chose impossible pour 56 000 lots.

Toutefois, une forme d'invention plus visible a pu être identifiée : les inscriptions. Sans que cela lui soit demandé, le LLM tentait de déchiffrer les caractères visibles sur l'image associée au lot et ajoutait ces valeurs aux champs d'inscription (`Inscription_transcription`, `Inscription_transliterration`), voire au début de la notice elle-même. La détection de ces anomalies repose sur deux critères principaux :

- le fait qu'une notice **commence par des caractères non latins** (arabes ou hébreux), indiquant vraisemblablement que l'image placée au-dessus de la notice a été océrisée par le LLM ;
- le fait qu'un champ d'inscription soit **renseigné alors que sa valeur n'apparaît pas dans la notice**, indiquant qu'il ne s'agissait pas d'une information fournie par le catalogue mais d'une invention du modèle.

Une fois ces anomalies détectées, un arbitrage manuel permet de choisir et d'appliquer les décisions, lot par lot.

---

## Vue d'ensemble du pipeline

```
21_detection_ocr_bizarre.py
        │
        │  rapport_anomalies_inscriptions_*.csv
        │  log_anomalies_inscriptions_*.txt
        │  log_stats_anomalies_inscriptions_*.txt
        ▼
22_arbitrer_anomalies.py   (interface Tkinter, reprise de session)
        │
        │  arbitrages_contenu_absent_notice.csv  (nom fixe)
        ▼
23_appliquer_suppression_inscription.py
        │
        │  lots_champs_absents_corriges_*.csv
        ▼
   corrections manuelles sur le CSV produit  (décisions "A CORRIGER")
        │
        ▼
24_stats_hallucinations_llm.py
        │
        └─ stats_arbitrages_*.tex  +  affichage console
```

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `21_detection_ocr_bizarre.py` | Détecte les trois types d'anomalies liées aux inscriptions et produit un rapport CSV |
| `22_arbitrer_anomalies.py` | Interface graphique de révision manuelle des anomalies `CONTENU_ABSENT_NOTICE` |
| `23_appliquer_suppression_inscription.py` | Vide les champs marqués `A SUPPRIMER` et produit un nouveau CSV lots |
| `24_stats_hallucinations_llm.py` | Calcule les statistiques du fichier d'arbitrages et génère un fragment LaTeX |

---

## Conventions communes

- **Encodage** : UTF-8 avec BOM (`utf-8-sig`) sur tous les fichiers CSV en entrée et en sortie. Les champs d'inscription peuvent contenir de l'arabe ou de l'hébreu ; aucune conversion destructive n'est appliquée aux valeurs d'origine.
- **Délimiteur** : point-virgule (`;`).
- **Nommage des sorties** : horodatage `YYYYMMDD_HHMMSS`, sauf le fichier d'arbitrages qui porte un nom fixe pour permettre la reprise de session sans écrasement accidentel.
- **Non-modification des sources** : aucun script ne modifie les fichiers en entrée. Toute sortie est un nouveau fichier.

---

## Description des scripts

### `21_detection_ocr_probleme.py`

Parcourt le CSV lots et signale trois types d'anomalies, chacune étant un indice possible d'une OCRisation ou d'une invention non sollicitée par le LLM.

**TYPE 1 — `CONTENU_ABSENT_NOTICE`**  
`Inscription_transcription` ou `Inscription_transliterration` contient une valeur dont le contenu n'apparaît pas dans la notice du lot. La méthode repose sur la recherche du plus long segment commun contigu (`difflib.SequenceMatcher.find_longest_match`) entre le champ normalisé et la notice normalisée. En dessous d'un seuil de ratio, le champ est considéré comme absent de la notice et donc suspect. C'est le type d'anomalie qui fait l'objet de l'arbitrage manuel dans le script suivant.

**TYPE 2 — `NOTICE_DEBUT_NON_LATIN`**  
La notice commence par un premier caractère alphabétique en écriture arabe ou hébraïque. Les chiffres et la ponctuation en tête sont ignorés (neutres). Une notice censée reproduire un texte de catalogue de vente occidental ne devrait pas commencer ainsi.

**TYPE 3 — `BOOLEEN_INCOHERENT`**  
Le champ `Inscription_booleen` vaut `Non` alors qu'au moins un des six champs d'inscription (`nature`, `langue`, `ecriture`, `transcription`, `transliterration`, `traduction`) contient une valeur.

Paramètres ajustables en tête de script : seuil de ratio (`SEUIL_RATIO_SUSPECT`), longueur minimale du champ contrôlé (`LONGUEUR_MIN_CONTROLE`), taille minimale d'un segment valide (`TAILLE_MIN_SEGMENT_VALIDE`).

**Entrée** : CSV lots  
**Sorties** :
- `rapport_anomalies_inscriptions_*.csv` — une ligne par anomalie, avec colonne `Decision_manuelle` laissée vide
- `log_anomalies_inscriptions_*.txt` — log détaillé lisible
- `log_stats_anomalies_inscriptions_*.txt` — compteurs par type

---

### `22_arbitrer_anomalies.py`

Interface Tkinter de révision manuelle. **Ne traite que le type `CONTENU_ABSENT_NOTICE`** : les anomalies des deux autres types présentes dans le rapport sont ignorées dès le chargement (car peu nombreuses, donc traitées manuellement).

Pour chaque anomalie, l'outil affiche :
- le champ concerné, sa valeur, et un extrait de contexte issu du rapport ;
- la **notice complète** du lot, relue depuis le CSV lots via `Id_perenne` (le rapport ne contient qu'un extrait) ;
- un bouton pour ouvrir la ou les pages Arkindex associées au lot (le champ `Lien_page_arkindex` peut contenir plusieurs liens séparés par `|`, chacun ouvert dans un nouvel onglet).

Les décisions possibles sont :

| Décision | Sens |
|---|---|
| `OK - contenu justifie, garder tel quel` | Anomalie réelle mais voulue, rien à faire |
| `FAUX POSITIF - contenu bien present dans la notice` | Faux positif du détecteur |
| `A CORRIGER - inscription erronee, a modifier` | Le champ est faux ; correction manuelle requise sur le CSV produit par le script 23 |
| `A SUPPRIMER - inscription invalidee, a retirer` | Le champ doit être vidé ; traité automatiquement par le script 23 |
| `INCERTAIN - a revoir plus tard` | À traiter ultérieurement |

**Reprise de session** : si le fichier d'arbitrages existe déjà au démarrage, les anomalies déjà traitées sont sautées automatiquement. On peut fermer et rouvrir l'outil sans perdre sa progression.

> Ce script n'écrit jamais dans le rapport d'anomalies ni dans le CSV lots.

**Entrées** : rapport d'anomalies + CSV lots  
**Sortie** : `arbitrages_contenu_absent_notice.csv` (nom fixe, réécrit intégralement à chaque enregistrement pour éviter toute corruption en cas de fermeture brutale)

---

### `23_appliquer_suppression_inscription.py`

Lit le fichier d'arbitrages et vide les cellules des champs marqués `A SUPPRIMER`. Toutes les autres décisions sont ignorées : les corrections `A CORRIGER` sont à effectuer manuellement directement sur le CSV produit par ce script. Une ligne n'est jamais supprimée ; seule la cellule du champ concerné est vidée.

**Entrées** : `arbitrages_contenu_absent_notice.csv` + CSV lots  
**Sortie** : `lots_champs_absents_corriges_*.csv`

---

### `24_stats_hallucinations_llm.py`

Produit des statistiques sur le fichier d'arbitrages en vue de leur intégration dans un rapport. Les résultats sont affichés en console et exportés sous forme d'un **fragment LaTeX** directement intégrable (`\begin{table}...\end{table}`), dans le style `booktabs` de la note de synthèse sur le dédoublonnage.

Trois tables sont produites :
- répartition des décisions (effectifs et pourcentages) ;
- répartition par champ concerné ;
- répartition par maison de vente — extraite comme le premier mot de `Identifiant_catalogue` avant le premier `_` (ex. `Bonhams_2014_...` → `Bonhams`).

**Entrée** : `arbitrages_contenu_absent_notice.csv`  
**Sortie** : `stats_arbitrages_*.tex`

---

## Ordre d'exécution

1. `21_detection_ocr_bizarre.py`
2. `22_arbitrer_anomalies.py` — autant de sessions que nécessaire, reprise automatique
3. `23_appliquer_suppression_inscription.py`
4. Corrections manuelles sur le CSV produit à l'étape 3 (décisions `A CORRIGER`)
5. `24_stats_hallucinations_llm.py`

---

## Chemins à adapter

Chaque script contient en tête une section avec les chemins des fichiers d'entrée. Les répertoires de sortie sont toujours déduits automatiquement du chemin d'entrée.
