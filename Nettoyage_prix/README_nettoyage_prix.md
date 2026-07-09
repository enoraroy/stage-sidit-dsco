# Nettoyage des prix (Estimation_lot et Prix_vente_final_lot)

Ce dossier regroupe les scripts utilisés pour repérer, uniformiser et structurer les champs de prix du tableur CSV des lots (`Estimation_lot`, et à terme `Prix_vente_final_lot`, sur le même principe). Ces champs sont hétérogènes pour plusieurs raisons propres au pipeline en amont : catalogues qui n'affichent jamais la devise (implicite, connue seulement du contexte de la vente), fourchettes de prix multi-devises séparées par des ponctuations très variables (espace, point-virgule, slash, parenthèses, ou rien du tout), séparateurs de milliers confondus avec des décimales, ou bruit d'OCR/LLM.

## Méthode

1. **Repérer les lignes sans devise.** Rien ne sert de nettoyer puis reformater un prix si l'information de devise est manquante. On raisonne par la négative : toute ligne non vide qui ne contient aucun des tokens de devise reconnus (`EUR`, `€`, `$`, `£`, `US$`, `HK$`, `GBP`...) est mise de côté. Ces lignes sont ensuite regroupées par `Identifiant_catalogue`, pour concentrer l'effort là où il a le plus d'impact — sans surprise, essentiellement les catalogues Boisgirard, qui n'affichent presque jamais de devise — avant de généraliser à tous les catalogues concernés — `09_compter_lignes_sans_monnaie.py`.
2. **Assigner automatiquement la devise manquante.** On part du principe qu'un catalogue donné utilise une seule et même devise, quel que soit l'objet vendu. C'est une hypothèse forte, mais c'est la seule qui permette d'assigner une devise à plusieurs centaines de lots d'un coup plutôt qu'à la main, ligne par ligne. Elle repose sur une liste de correspondances identifiées manuellement (catalogue → devise) et, à défaut, sur la devise déjà utilisée ailleurs dans le même catalogue si elle est unique — `11_ajout_devise.py`.
3. **Repérer le bruit.** Une ligne est "bruitée" si elle contient, au-delà des chiffres, des devises reconnues et d'une ponctuation autorisée (`, . / - ( ) | ;` + espace), un caractère qui n'y a pas sa place. Ces cas ne peuvent être corrigés qu'à la main (retour au catalogue source nécessaire) — `10_estimation_bruit_prix.py`.
4. **Uniformiser les notices "monoprix".** Une notice monoprix n'a qu'une seule devise et un seul intervalle de valeur. C'est le cas le plus simple à traiter : il suffit d'isoler la devise du reste, puis d'extraire les nombres indépendamment de la ponctuation qui les sépare — `12_uniformiser_prix_unique.py`.
5. **Uniformiser les notices "multiprix".** Les lots affichant plusieurs devises (typiquement livres/dollars/euros pour un même lot) ne peuvent pas être traités comme au point 4 : il faut d'abord associer correctement chaque valeur à sa devise, malgré des séparateurs très ambigus entre les groupes de prix, avant d'appliquer les mêmes règles d'uniformisation — `13_uniformiser_prix_multiples.py`.
6. **Séparer valeur et devise dans des colonnes dédiées.** Une fois les prix uniformisés, on éclate `Estimation_lot` en `valeur_N_estimation_lot` / `devise_N_estimation_lot` (jusqu'à 3 couples). Cela évite d'imposer arbitrairement une devise à une valeur dans une seule colonne texte, et laisse la structure du tableur souple pour d'éventuels ajouts de devise futurs — `15_separation_valeur_devise.py`.

Le même protocole (étapes 1 à 6) est destiné à être répliqué à l'identique sur `Prix_vente_final_lot`, les cas de figure à traiter étant sensiblement les mêmes. Seule l'étape de quantification (`14_statistiques_prix.py`) a pour l'instant été faite uniquement sur `Estimation_lot`, ce champ étant à la fois plus volumineux et plus bruité.

> Note méthodologique : à chaque étape, les cas limites (bruit, devises ambiguës, structures non reconnues) sont mis de côté et signalés plutôt que forcés dans un format propre. Pour l'étape 6 en particulier, une ligne non résolue conserve sa valeur brute d'origine dans `Estimation_lot` plutôt que d'être ventilée dans les nouvelles colonnes `valeur_N` / `devise_N`, l'objectif étant de ne jamais faire migrer du bruit vers des colonnes propres.

---

Fichier d'entrée attendu :

| Fichier | Description |
|---|---|
| CSV export lots (nettoyé) | Sortie du dossier `Nettoyage` (`lots_nettoyes_*.csv`), avec entre autres les colonnes `Identifiant_catalogue`, `Estimation_lot` (et à terme `Prix_vente_final_lot`), `Id_perenne` |

Fichiers de sortie principaux :

| Fichier | Produit par | Utilisé par |
|---|---|---|
| `sans_devise_detail_*.txt` / `sans_devise_stats_*.txt` | 09 | assignation manuelle (`MANUAL_CURRENCY_MAP` de 11), 14 |
| `bruit_estimation_detail_*.txt` / `bruit_estimation_stats_*.txt` | 10 | revue manuelle, 14 |
| `lots_devise_ajoutee_*.csv` | 11 | 12 |
| `log_ajouts_devise_*.txt` / `log_signalements_devise_*.txt` / `log_stats_ajout_devise_*.txt` | 11 | 14 |
| `lots_prix_uniformises_monodevise_*.csv` | 12 | 13 |
| `log_reformatages_prix_*.txt` / `log_signalements_prix_*.txt` / `log_stats_prix_*.txt` | 12 | 14 |
| `lots_prix_uniformises_multidevise_*.csv` | 13 | 15 |
| `log_reformatages_prix_multidevise_*.txt` / `log_signalements_prix_multidevise_*.txt` / `log_stats_prix_multidevise_*.txt` | 13 | 14 |
| `bilan_reformatage_prix_*.txt` | 14 | revue manuelle, suivi d'avancement |
| `lots_valeur_devise_separees_*.csv` | 15 | — |
| `log_bruit_restant_estimation_*.txt` / `log_stats_separation_valeur_devise_*.txt` | 15 | revue manuelle |

---

## Description des scripts

### `09_compter_lignes_sans_monnaie.py` — Détection des lignes sans devise

Outil de diagnostic indépendant, en lecture seule. Distingue deux catégories : `vide` (le champ `Estimation_lot` est vide) et `sans_devise` (du texte est présent, mais aucun des tokens de devise reconnus — `US$`, `HK$`, `GBP`, `£`, `€`, `$`, `EUR` — n'y apparaît). Un compteur par `Identifiant_catalogue` est produit, pour orienter en priorité vers les catalogues les plus concernés.

> Note méthodologique : ce comptage sert avant tout de base à l'assignation manuelle de devise par catalogue (`MANUAL_CURRENCY_MAP` du script 11).

Sorties : `sans_devise_detail_*.txt` (détail ligne par ligne), `sans_devise_stats_*.txt` (compteurs globaux et par catalogue).

---

### `10_estimation_bruit_prix.py` — Détection du bruit

Outil de diagnostic indépendant, en lecture seule. Une ligne non vide est signalée dès qu'elle contient un caractère qui n'est ni un chiffre, ni un token de devise reconnu, ni l'un des symboles de ponctuation autorisés (`, . / - ( ) | ;` + espace, espace insécable, retour chariot). Les caractères inattendus rencontrés sont listés et comptés.

> Ces cas ne sont volontairement pas traités automatiquement — ils nécessitent un retour systématique au catalogue source pour être tranchés à la main, sauf dans le cas des catalogues à devise unique, couvert par le script 11.

Sorties : `bruit_estimation_detail_*.txt` (détail par ligne, caractères en cause), `bruit_estimation_stats_*.txt` (compteurs par catalogue et par caractère).

---

### `11_ajout_devise.py` — Assignation automatique de la devise manquante

Pour chaque ligne sans devise (et sans bruit), la devise est déterminée dans cet ordre : (a) `Identifiant_catalogue` présent dans `MANUAL_CURRENCY_MAP` (liste de correspondances identifiées à la main) ; (b) à défaut, devise unique déjà utilisée par ailleurs dans le même catalogue. Si plusieurs devises différentes coexistent dans le catalogue, ou si aucune n'est trouvée, la ligne est signalée plutôt que devinée au hasard. La devise est ajoutée après la valeur existante.

> Note méthodologique : l'hypothèse "une devise par catalogue" est forte et peut théoriquement être mise en défaut par un catalogue mixte ; c'est le compromis retenu pour éviter un remplissage entièrement manuel sur plusieurs centaines de lots.

Sorties : `lots_devise_ajoutee_*.csv` (fichier de travail), `log_ajouts_devise_*.txt` (détail des ajouts, par mode), `log_signalements_devise_*.txt` (lignes non corrigées, par raison), `log_stats_ajout_devise_*.txt`.

---

### `12_uniformiser_prix_unique.py` — Uniformisation des notices monoprix

Traite uniquement les cellules à devise unique (les cellules multi-devises sont repérées mais laissées de côté pour le script 13). La devise est isolée du reste de la valeur, les séparateurs de milliers sont supprimés (les décimales sont préservées), puis les nombres restants sont extraits pour produire soit `{devise}{valeur}`, soit `{devise}{valeur1}-{devise}{valeur2}` selon qu'il s'agit d'une valeur unique ou d'un intervalle.

> Note méthodologique : la distinction séparateur-de-milliers / décimale repose sur l'hypothèse qu'un séparateur suivi d'exactement 3 chiffres non suivis d'un autre chiffre est un séparateur de milliers ; sinon, c'est une décimale.

Sorties : `lots_prix_uniformises_monodevise_*.csv`, `log_reformatages_prix_*.txt`, `log_signalements_prix_*.txt` (bruit, sans devise, multi-devises, aucun/trop de nombres), `log_stats_prix_*.txt`.

---

### `13_uniformiser_prix_multiples.py` — Uniformisation des notices multiprix

Traite les cellules contenant plusieurs devises différentes, où le séparateur entre groupes de prix est trop variable pour être détecté explicitement (espace, point-virgule, slash, parenthèses, ou rien du tout). Le principe retenu est que la devise précède toujours le(s) nombre(s) auquel(s) elle s'applique : la cellule est parcourue token par token (devise ou nombre), et chaque nombre est assigné à la dernière devise rencontrée. Chaque groupe devise/valeurs est ensuite formaté comme au script 12, puis les groupes sont joints par `|`.

Sorties : `lots_prix_uniformises_multidevise_*.csv`, `log_reformatages_prix_multidevise_*.txt`, `log_signalements_prix_multidevise_*.txt` (bruit, pas multi-devise, structure trop complexe), `log_stats_prix_multidevise_*.txt`.

---

### `14_statistiques_prix.py` — Bilan consolidé

Lit uniquement les fichiers de log déjà produits par les scripts 09, 11, 12 et 13, et en tire un bilan chiffré unique (lignes sans devise identifiées, devises ajoutées automatiquement par mode, reformatages mono/multi-devises réussis et échoués par raison). Inclut également une liste d'`Id_perenne` corrigés manuellement (`IDS_MODIFIES_MANUELLEMENT`), comptée à part et intégrée au total consolidé.
Cette étape sert à quantifier la part de nettoyage automatisée par rapport à ce qui reste, ou a dû être, traité à la main.

Sorties : `bilan_reformatage_prix_*.txt`.

---

### `15_separation_valeur_devise.py` — Séparation valeur / devise

Éclate `Estimation_lot`, une fois uniformisé, en 6 colonnes (`valeur_1_estimation_lot`, `devise_1_estimation_lot`, ... jusqu'à 3 couples), insérées à la place d'`Estimation_lot`. Une ligne correctement séparée voit `Estimation_lot` vidé (la donnée vit désormais dans les colonnes `valeur_N`/`devise_N`) ; une ligne non reconnue (plus de 3 groupes, ou un groupe qui ne correspond pas au format attendu) conserve sa valeur brute inchangée dans `Estimation_lot` et est mise de côté pour relecture manuelle. Ce choix évite de faire remonter du bruit dans des colonnes nouvellement structurées.

Sorties : `lots_valeur_devise_separees_*.csv`, `log_bruit_restant_estimation_*.txt`, `log_stats_separation_valeur_devise_*.txt`.

---

## Limites

L'hypothèse centrale du script 11 (une devise unique par catalogue) est forte et non vérifiée systématiquement — elle peut être mise en défaut par un catalogue véritablement mixte, auquel cas des lots resteraient assignés à tort à la mauvaise devise sans être détectés comme tels par le pipeline. Les cas bruités (script 10) et les structures non reconnues (scripts 12, 13, 15) ne sont volontairement jamais forcés dans un format propre : ils restent signalés et conservés dans leur colonne d'origine, en attente d'un traitement manuel avec retour au catalogue source.

```
python 3.11
```
