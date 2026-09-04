# Stage DSCO-SIDIT — musée du Louvre

Dépôt de documentation des protocoles de traitement de données mis en place dans le cadre d'un stage au musée du Louvre, direction du soutien aux collections (DSCO), Service de l'ingénierie documentaire, des images et de traduction (SIDIT). Pour des raisons de confidentialité du projet, la diffusion du site réalisé sur Omeka S est limitée et indisponible sur ce dépôt public.

## Contexte

Dans le cadre d’un projet de valorisation de corpus documentaires, j’ai contribué à la transformation de données issues de catalogues de ventes aux enchères en une base exploitable pour les équipes du Département des Arts de l’Islam du musée du Louvre.

Le projet portait sur un corpus d’environ 250 catalogues, représentant environ 55 000 lots de vente. L’objectif était de dépasser la consultation catalogue par catalogue et de permettre une recherche transversale dans les informations relatives aux lots, aux œuvres, aux provenances, aux dimensions, aux prix, etc.

Mes missions :
- Nettoyage et structuration de données avec Python, à partir de fichiers CSV issus du processus d’extraction ;
- Contrôle, normalisation et préparation des données en vue de leur intégration dans une base exploitable ;
- Mise en cohérence des données avec les référentiels et vocabulaires utilisés au musée du Louvre ;
- Conception et réalisation d’un site web interne avec Omeka S, permettant aux agents du DAI de rechercher, parcourir et exploiter le corpus, au sein d'une interface adaptée à leurs besoins.

Bref, un projet mêlant traitement de données avec Python et développement d’un outil de consultation interne avec Omeka S.

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
