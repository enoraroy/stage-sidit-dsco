# Stage DSCO-SIDIT — musée du Louvre

Dépôt de documentation des protocoles de traitement de données mis en place dans le cadre d'un stage au musée du Louvre, direction du soutien aux collections (DSCO), Service de l'ingénierie documentaire, des images et de traduction (SIDIT).

## Contexte

Mon stage a porté principalement sur un projet de numérisation (par un prestataire utilisant un LLM) et d'exploitation des données des catalogues de vente possédés par le DAI à des fins de :
1. d'étude et de documentation des œuvres,
2. de recherche des provenances,
3. d'études préliminaires à des acquisitions,
4. de bibliographie.

## Objectif de ce dépôt

Ce dépôt documente, dans la mesure du possible, les protocoles mis en place pour réaliser mes missions. Quand plusieurs solutions étaient envisageables, j'ai privilégié l'usage de Python pour le traitement des données et la préparation des CSV d'import. Chaque dossier correspond à une tâche effectuée durant le stage.

## Structure du dépôt

| Dossier | Contenu |
|---|---|
| `Dedoublonnage/` | Détection et traitement des doublons de lots dans le CSV export des catalogues (doublons exacts, doublons par identifiant catalogue + numéro de lot, numéros de lot incohérents). Scripts `00` à `06`. |
| `Nettoyage_champs_vides/` | Identification et suppression des valeurs non significatives inventées par le LLM pour combler un champ vide (ex. "Non précisé", "Non indiqué"). Scripts `07` et `08`. |
| `Nettoyage_prix/` | Repérage, uniformisation et structuration des champs de prix (`Estimation_lot`, et à terme `Prix_vente_final_lot`) : devises manquantes, bruit, formats multi-devises, séparation valeur/devise. Scripts `09` à `16`. |

Chaque dossier contient son propre `README.md` détaillant la méthode, le rôle de chaque script, ses entrées/sorties et ses limites.

## Approche générale

- Traçabilité : toute modification automatisée est tracée par `Id_perenne` dans des fichiers de log dédiés, pour permettre un contrôle et une correction manuelle ciblée.
- Prudence sur l'automatisation : les cas ambigus, bruités ou trop complexes ne sont jamais forcés dans un format propre — ils sont signalés et laissés de côté pour une vérification manuelle, plutôt que de risquer une correction erronée.
- Sauvegarde systématique : une copie de sauvegarde du CSV est produite avant toute modification.
