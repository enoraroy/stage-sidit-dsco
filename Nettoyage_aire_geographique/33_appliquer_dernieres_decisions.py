"""
Application des décisions manuelles prises dans le
récapitulatif produit par le script précédent (incoherences_aire_recap_*.csv),
une fois sa colonne "Aire_a_retenir" complétée.

Pour chaque région présente dans le récapitulatif avec une décision
("Aire_a_retenir" non vide), TOUTES les lignes du CSV portant cette région
(Region_lieu_production) voient leur Aire_geographique_production alignée
sur la valeur décidée — y compris les lignes qui avaient déjà une valeur
(différente ou non de la décision), puisque le but est de rendre toutes
les lignes de cette région cohérentes entre elles.

Les lignes dont la région n'apparaît pas dans le récapitulatif, ou dont la
décision a été laissée vide, ne sont pas modifiées.

Une backup du CSV est créée avant toute modification. Le récapitulatif
n'est jamais modifié.
"""

import csv
import os
import shutil
import unicodedata
from collections import Counter
from datetime import datetime

CSV_PATH = r"chemin_du_csv"

RECAP_PATH = r"incoherences_aire_recap_20260717_145513.csv"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
AIRE_COLUMN = "Aire_geographique_production"
REGION_COLUMN = "Region_lieu_production"

COLONNE_A_REMPLIR = "Aire_a_retenir"

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP_PATH = os.path.join(OUTPUT_DIR, f"BACKUP_{TIMESTAMP}_" + os.path.basename(CSV_PATH))
OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"lots_aire_harmonisee_{TIMESTAMP}.csv")
LOG_APPLICATIONS_PATH = os.path.join(OUTPUT_DIR, f"log_application_incoherences_aire_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_stats_application_incoherences_aire_{TIMESTAMP}.txt")


def _normalize(nom):
    s = unicodedata.normalize("NFKD", nom)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def resolve_columns(expected_columns, fieldnames, label=""):
    normalized_real = {_normalize(f): f for f in fieldnames}
    resolved = {}
    unresolved = []

    for col in expected_columns:
        if col in fieldnames:
            resolved[col] = col
            continue
        match = normalized_real.get(_normalize(col))
        if match:
            print(f"[ATTENTION]{label} Colonne \"{col}\" absente telle quelle ; "
                  f"correspondance trouvée avec la colonne réelle \"{match}\". "
                  f"Utilisation de \"{match}\".")
            resolved[col] = match
        else:
            unresolved.append(col)

    if unresolved:
        raise ValueError(
            f"Colonnes attendues introuvables{label} (même approximativement) : "
            + ", ".join(unresolved)
            + "\nColonnes disponibles : " + ", ".join(fieldnames)
        )
    return resolved


def backup_csv():
    shutil.copy2(CSV_PATH, BACKUP_PATH)
    print(f"Backup créé : {BACKUP_PATH}")


def charger_decisions(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        col_map = resolve_columns(
            {REGION_COLUMN, COLONNE_A_REMPLIR}, fieldnames, label=" (récapitulatif)"
        )
        col_region = col_map[REGION_COLUMN]
        col_decision = col_map[COLONNE_A_REMPLIR]
        rows = list(reader)

    decisions = {}
    nb_vides = 0
    for row in rows:
        region = (row.get(col_region) or "").strip()
        decision = (row.get(col_decision) or "").strip()
        if not region:
            continue
        if not decision:
            nb_vides += 1
            continue
        decisions[region] = decision

    return decisions, nb_vides


def process():
    backup_csv()

    decisions, nb_vides = charger_decisions(RECAP_PATH)
    print(f"Décisions chargées : {len(decisions)} région(s) ({nb_vides} laissée(s) vide(s) dans le récapitulatif)")

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    col_map = resolve_columns({ID_COLUMN, CATALOG_COLUMN, AIRE_COLUMN, REGION_COLUMN}, fieldnames)
    id_col = col_map[ID_COLUMN]
    catalog_col = col_map[CATALOG_COLUMN]
    aire_col = col_map[AIRE_COLUMN]
    region_col = col_map[REGION_COLUMN]

    modifications = []   # (id_perenne, catalog_id, region, ancienne_aire, nouvelle_aire)
    deja_conformes = 0
    regions_modifiees = Counter()

    for row in rows:
        region = (row.get(region_col) or "").strip()
        if region not in decisions:
            continue

        aire_decidee = decisions[region]
        aire_actuelle = (row.get(aire_col) or "").strip()

        if aire_actuelle == aire_decidee:
            deja_conformes += 1
            continue

        id_perenne = (row.get(id_col) or "").strip()
        catalog_id = (row.get(catalog_col) or "").strip()
        row[aire_col] = aire_decidee
        modifications.append((id_perenne, catalog_id, region, aire_actuelle, aire_decidee))
        regions_modifiees[region] += 1

    # ---- Écriture du CSV modifié ----
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    # ---- Log des modifications ----
    with open(LOG_APPLICATIONS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Log d'harmonisation de l'aire géographique - {TIMESTAMP}\n")
        f.write(f"Nombre total de modifications : {len(modifications)}\n\n")
        for id_perenne, catalog_id, region, ancienne_aire, nouvelle_aire in modifications:
            f.write(
                f'{id_perenne} ; {catalog_id} ; region="{region}" ; '
                f'"{ancienne_aire}" -> "{nouvelle_aire}"\n'
            )

    # ---- Statistiques ----
    with open(LOG_STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques - harmonisation aire géographique (script 17bis/17ter) - {TIMESTAMP}\n")
        f.write(f"Fichier source   : {CSV_PATH}\n")
        f.write(f"Récapitulatif    : {RECAP_PATH}\n")
        f.write(f"Backup           : {BACKUP_PATH}\n")
        f.write(f"CSV modifié      : {OUTPUT_CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes du fichier         : {len(rows)}\n")
        f.write(f"Régions avec décision dans le récapitulatif : {len(decisions)}\n")
        f.write(f"Régions laissées vides dans le récapitulatif : {nb_vides}\n\n")
        f.write(f"Nombre total de modifications               : {len(modifications)}\n")
        f.write(f"  dont régions distinctes effectivement modifiées : {len(regions_modifiees)}\n")
        f.write(f"Lignes déjà conformes à la décision (non modifiées) : {deja_conformes}\n")

    print("Traitement terminé.")
    print(f"  CSV modifié : {OUTPUT_CSV_PATH}")
    print(f"  Log         : {LOG_APPLICATIONS_PATH}")
    print(f"  Stats       : {LOG_STATS_PATH}")


if __name__ == "__main__":
    process()
