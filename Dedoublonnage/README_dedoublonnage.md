# Pipeline de dédoublonnage des lots de vente

Ce dossier regroupe les scripts utilisés pour détecter, analyser et corriger les doublons présents dans le tableur CSV des lots, issu de l'OCRisation/LLM des catalogues de vente. Le corpus contient des doublons pour plusieurs raisons distinctes, propres au pipeline en amont : une notice originale peut être entièrement réinventée, un numéro de lot mal océrisé, une simple image associée à un lot interprétée comme un lot à part entière, ou encore un même numéro de lot attribué deux fois par erreur par le catalogue lui-même.

## Méthode

1. **Nettoyer les anomalies de lignes** repérables sur l'identifiant catalogue (champ vide ou valeur peu cohérente au regard des autres valeurs du champ) — étape amont, non détaillé ici (faite par filtre sur le logiciel de tableur)
2. **Identifier et fusionner les doublons exacts**, les lignes identiques sur tous les champs — `01_detection_doublons_exacts.py`.
3. **Identifier les lignes sans numéro de lot** (image ou texte seul rattaché au lot voisin, page de couverture/introduction, publicité pour une vente à venir) — ces cas sont répertoriés à la main puis mis de côté dans une liste à fusionner, ou à conserver, plutôt qu'un traitement automatique (car c'est vraiment au cas par cas).
4. **Identifier et traiter les lignes qui partagent le même identifiant de catalogue *et* le même numéro de lot** — le coeur du protocole, couvert par `02_analyser_doublon.py`, `03_fusionner_doublons.py`, la revue manuelle, et `04_fusionner_selon_decisions_manuelles.py`.
5. **Identifier les numéros de lot incohérents** (qui ne suivent pas une suite logique par rapport à leurs voisins, ex. `235, 236, 237, 1, 2, 3, 4, 238`) — `00_detection_problemes_numero_lot.py`.

L'étape 4 ne peut pas être entièrement automatisée : la notice originale et le doublon ne sont pas identifiables sans regard humain dès qu'une notice s'étend sur plusieurs pages, que le LLM a pu l'inventer de toutes pièces (vérification nécessaire sur la page du catalogue), ou que le catalogue lui-même attribue deux fois le même numéro de lot à des lots différents (ce qui demande une correction avec ajout de suffixe, hors périmètre des scripts). Le seul cas automatisable sans risque est celui d'une notice vide ou non informationnelle — un LLM qui, faute de contenu, produit des formulations non uniformisées comme « Notice textuelle non fournie », « description non fournie dans le prompt », « notice manquante », etc. C'est cette liste de formulations, repérée empiriquement puis traduite en expressions régulières, qui permet de traiter ces cas au même titre que les notices vides.

Une fois un doublon identifié, trois traitements sont possibles : la **suppression totale** s'il n'apporte aucune information supplémentaire ; la **fusion** avec l'original (automatique ou manuelle) si la notice est vide ou non informationnelle — déplacement du lien Arkindex et du numéro de page PDF vers l'original, en ajout, séparés par un pipe et réordonnés par ordre croissant ; le **traitement manuel** si la notice contient une information réelle, ce qui impose de vérifier sur Arkindex qu'elle vient bien du catalogue et n'a pas été inventée par le LLM.

Les fichiers intermédiaires sont au format CSV (`;`, `utf-8-sig`). Deux scripts (`00` et `01`) sont des outils de contrôle indépendants pour les étapes 5 et 2 ; les scripts `02` à `05` forment le protocole et doivent être exécutés dans cet ordre, avec une étape de revue manuelle entre `03` et `04`. Le script `06` permet de quantifier l'effet global du dédoublonnage.

---

Fichier d'entrée attendu :

| Fichier | Description |
|---|---|
| CSV export lots | Export des lots avec, entre autres, les colonnes `Identifiant_catalogue`, `Numero_lot`, `Titre_lot`, `Numero_page_pdf`, `Lien_page_arkindex`, `Notice`, `Id_perenne` |

Fichiers de sortie principaux :

| Fichier | Produit par | Utilisé par |
|---|---|---|
| `anomalies_ocr_numeros_lot_*.txt` | 00 | revue manuelle |
| `doublons_stricts_lots_*.txt` | 01 | revue manuelle |
| `doublons_analyses_*.csv` / `doublons_suspects_*.csv` / `resume_doublons_*.txt` | 02 | revue manuelle |
| `lots_fusionnes_*.csv` | 03 | 04, 06 |
| `rapport_fusion_*.txt` | 03 | revue manuelle |
| `revue_manuelle.log` | rédigé à la main, à partir de 02/03 | 04 |
| `lots_decisions_appliquees_*.csv` | 04 | 05, 06 |
| `rapport_decisions_manuelles_*.txt` | 04 | revue manuelle |
| `doublons_restants_*.txt` | 05 | revue manuelle |
| `quantification_dedoublonnage_maison_*.pdf` | 06 | — |

---

## Description des scripts

### `00_detection_problemes_numero_lot.py` — Détection des erreurs OCR sur `Numero_lot`

Pour chaque catalogue, compare — pour chaque ligne `i` et ses deux voisines immédiates — le chemin "via `i`" (`|lot[i]-lot[i-1]| + |lot[i+1]-lot[i]|`) au chemin direct entre les voisins (`|lot[i+1]-lot[i-1]|`). Si le ratio entre les deux dépasse `RATIO_THRESHOLD` et que l'écart absolu dépasse `ABS_THRESHOLD`, la ligne est signalée : c'est le signe qu'un numéro de lot a probablement été mal océrisé (ex. `139 → 5 → 141`).

> Note méthodologique : ce script ne corrige rien, il repère uniquement les incohérences numériques pour orientation vers une vérification manuelle du fichier source. Il ne fonctionne que sur les lots numériques valides (`Numero_lot_num`), au moins trois par catalogue.

Sorties : `anomalies_ocr_numeros_lot_*.txt` (liste brute des `Id_perenne` suspects + détail des séquences et ratios).

---

### `01_detection_doublons_exacts.py` — Détection des doublons stricts

Outil de diagnostic indépendant. Regroupe les lignes strictement identiques sur un jeu de colonnes de comparaison (`Identifiant_catalogue`, `Titre_lot`, `Numero_lot` par défaut, ou toutes les colonnes sauf `Id_perenne`/`TRI` en mode automatique). Les valeurs sont normalisées (`strip`, `lower` optionnel) avant comparaison ; deux `NaN` sont considérés égaux entre eux, mais différents d'une chaîne vide explicite.

> Ce script ne fait aucune hypothèse sur la page PDF ni sur le contenu de la notice — c'est une comparaison texte pure. Il capture donc des doublons différents (souvent complémentaires) de ceux détectés par `02_analyser_doublon.py`.

Sorties : `doublons_stricts_lots_*.txt` (liste brute + groupes de doublons avec taille et aperçu des champs communs).

---

### `02_analyser_doublon.py` — Analyse des doublons par proximité de page

Un groupe de lignes est un doublon **confirmé** si les trois conditions sont vraies pour toutes les paires du groupe : même `Identifiant_catalogue`, même `Numero_lot`, et `Numero_page_pdf` à ± `SEUIL_PAGE` pages d'écart. Si l'écart de page dépasse le seuil (mais que les pages sont valides), le groupe est classé **suspect** plutôt que confirmé. Si une page est vide ou non numérique, la paire est ignorée (ni confirmée ni suspecte).

Dans chaque groupe confirmé, une ligne "originale" est désignée (celle avec un `Titre_lot` non vide et le plus de champs remplis) ; les autres lignes sont des doublons. Leur champ `Notice` est ensuite classé en trois catégories — `vide`, `non_sig` (formule-placeholder du type "Notice non fournie", repérée par une liste de regex), `significative` — pour préparer la décision de fusion du script suivant.

> Les `Id_perenne` listés dans `IDS_EXCLUS` (couvertures introductives, publicités, cas incertains) sont mis de côté avant toute détection : ils ne peuvent être ni original ni doublon.

Sorties : `doublons_analyses_*.csv` (doublons confirmés + catégorie de notice), `doublons_suspects_*.csv`, `resume_doublons_*.txt`.

---

### `03_fusionner_doublons.py` — Fusion automatique des doublons non significatifs

Reprend la détection de `02_analyser_doublon.py` (mêmes `SEUIL_PAGE`, `IDS_EXCLUS`, patterns de notice) et l'applique :

- Si la notice du doublon est `vide` ou `non_sig` : fusion — la page PDF et le lien Arkindex du doublon sont rapatriés dans la ligne originale (union triée des pages, union dédupliquée des liens, dans l'ordre des pages), puis la ligne doublon est supprimée.
- Si la notice est `significative` : rien n'est modifié, la ligne est conservée pour traitement manuel.

Indépendamment de cette logique, les `Id_perenne` listés dans `A_FUSIONNER_DIRECT` sont **toujours** fusionnés avec l'original de leur groupe — même si le groupe est suspect ou si la notice est significative. C'est une liste de décisions manuelles explicites qui outrepasse la détection automatique.

> Note méthodologique : `A_FUSIONNER_DIRECT` sert à tracer les cas déjà tranchés à la main sans les faire dépendre du seuil de page ou de la classification de notice — utile notamment quand plusieurs pages consécutives du PDF appartiennent au même lot malgré un OCR incohérent.

Sorties : `lots_fusionnes_*.csv` (fichier de travail avec les doublons non significatifs supprimés), `rapport_fusion_*.txt` (détail fusionné/ignoré/forcé, valeurs avant/après).

---

### *(étape manuelle)* `revue_manuelle.log`

Entre `03` et `04`, les groupes laissés de côté (notice jugée significative) sont examinés à la main et consignés dans `revue_manuelle.log`, au format :

```
... INFO   FUSIONNER  groupe=<Identifiant_catalogue>|<Numero_lot>  id_traite=<Id_perenne>  notes='...'
... INFO   SUPPRIMER  groupe=<Identifiant_catalogue>|<Numero_lot>  id_traite=<Id_perenne>  notes='...'
... INFO   IGNORER    groupe=<Identifiant_catalogue>|<Numero_lot>  notes='...'
```

> Note : j'ai produit ce fichier dans le cadre d'une interface HTML qui m'aidait pour trier, mais le principe demeure le même. Il s'agit de vérifier à la main.

---

### `04_fusionner_selon_decisions_manuelles.py` — Application des décisions manuelles

Lit `revue_manuelle.log` et applique, sur le CSV produit par `03`, chaque décision : `FUSIONNER` (même logique de fusion de champs qu'à l'étape 03, avec retour à l'original du groupe via `identifier_original`), `SUPPRIMER` (suppression pure, sans fusion), `IGNORER` (aucune modification, tracé pour mémoire).

> Note méthodologique : si un `Id_perenne` du log n'existe plus dans le CSV (déjà traité, ligne supprimée par ailleurs, coquille), le script l'indique par un message et continue. En cas de décisions contradictoires pour un même groupe (reprises de session), seule la dernière rencontrée dans le fichier est appliquée.

Sorties : `lots_decisions_appliquees_*.csv`, `rapport_decisions_manuelles_*.txt`.

---

### `05_verif_doublon.py` — Vérification des doublons restants

Contrôle sur le CSV final (`04`) : pour chaque `Identifiant_catalogue`, regroupe les lignes par `Numero_lot` (les `Id_perenne` de `IDS_EXCLUS` étant mis de côté au préalable) et liste les groupes où plusieurs `Id_perenne` partagent encore la même clé. Aucune logique de page ou de notice ici, uniquement une image de ce qu'il reste après fusion.

Sorties : `doublons_restants_*.txt`.

---

### `06_statistique_dedoublonnage.py` — Quantification globale du dédoublonnage

Compare quatre fichiers correspondant aux quatre étapes du pipeline (fichier brut sans `Id_perenne`, fichier après un premier dédoublonnage manuel, fichier après dédoublonnage automatique, fichier après dédoublonnage manuel final) et calcule le nombre et le taux de lignes supprimées à chaque transition, ainsi que le taux global. Les `Id_perenne` de `A_FUSIONNER_DIRECT` (décisions manuelles explicites traitées par `03`) sont reclassés du décompte "automatique" vers le décompte "manuel", pour ne pas gonfler artificiellement l'efficacité de la détection automatique.

Produit également deux graphiques en bâtons (effectifs et part relative par `Maison_vente_ou_demandeur`, avant/après dédoublonnage complet), triés par perte d'effectif décroissante.

Sorties : `quantification_dedoublonnage_maison_effectifs.pdf`, `quantification_dedoublonnage_maison_pourcentage.pdf`.

---

## Limites

Sans contrôle ligne par ligne du tableur — irréaliste vu le volume (54 605 lignes) — aucune garantie n'est possible que le dédoublonnage soit parfait. Certaines notices n'ont par ailleurs pas été océrisées ni récupérées : lorsqu'un lot s'étend sur plusieurs pages, le LLM efface parfois complètement la notice ou ne l'océrise pas. Aussi, sans process certain de dédoublonnage automatique, difficile de faire un intervalle de confiance.

---

## Dépendances

```
pip install pandas numpy matplotlib
```

Versions testées :

```
python        3.11
pandas        2.x
numpy         1.x
matplotlib    3.x
```
