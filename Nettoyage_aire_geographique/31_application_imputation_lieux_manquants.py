"""
Application des décisions manuelles sur l'Aire_geographique_production,
prises dans les deux fichiers "à compléter" produits par le script 17
(régions non reconnues et régions ambiguës), une fois leur colonne
"Aire_a_appliquer" remplie à la main.

Pour chaque ligne du CSV où Aire_geographique_production vaut encore
"origine inconnue" :
    - si Region_lieu_production correspond à une région pour laquelle une
      décision a été saisie (colonne "Aire_a_appliquer" non vide, dans l'un
      des deux fichiers de décisions), la valeur est appliquée ;
    - sinon, la ligne reste inchangée (décision pas encore prise, ou région
      absente des fichiers de décisions).

Si la même région a reçu deux décisions différentes (une dans chaque
fichier, par erreur), c'est signalé et AUCUNE des deux n'est appliquée pour
cette région (pour éviter de trancher au hasard à la place de l'utilisateur).

Une backup du CSV est créée avant toute modification. Les fichiers de
décisions ne sont jamais modifiés.
"""

import csv
import os
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime

CSV_PATH = r"chemin_du_csv"

# À adapter : fichiers "à compléter" produits par le script 17, une fois remplis
DECISIONS_NON_RECONNUES_PATH = r"a_completer_regions_non_reconnues_20260717_112605.csv"

DECISIONS_AMBIGUES_PATH = r"a_completer_regions_ambigues_20260717_112605.csv"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
AIRE_COLUMN = "Aire_geographique_production"
REGION_COLUMN = "Region_lieu_production"

COLONNE_A_REMPLIR = "Aire_a_appliquer"

VALEUR_INCONNUE = "Origine inconnue"

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP_PATH = os.path.join(OUTPUT_DIR, f"BACKUP_{TIMESTAMP}_" + os.path.basename(CSV_PATH))
OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"lots_aire_completee_{TIMESTAMP}.csv")
LOG_APPLICATIONS_PATH = os.path.join(OUTPUT_DIR, f"log_application_decisions_aire_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_stats_application_aire_{TIMESTAMP}.txt")


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


def charger_decisions(path, label):
    """Lit un fichier 'à compléter' et retourne un dict région -> aire
    décidée, en ne gardant que les lignes où la colonne Aire_a_appliquer a
    été remplie. Retourne aussi le nombre de lignes encore vides (non
    traitées par l'utilisateur)."""
    if not os.path.isfile(path):
        print(f"[ATTENTION] Fichier de décisions introuvable ({label}) : {path}")
        return {}, 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        col_map = resolve_columns(
            {REGION_COLUMN, COLONNE_A_REMPLIR}, fieldnames, label=f" ({label})"
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


def fusionner_decisions(decisions_non_reconnues, decisions_ambigues):
    """Fusionne les deux dicts de décisions. En cas de conflit (même région
    avec une décision différente dans chacun des deux fichiers), la région
    est retirée des deux (aucune application), et le conflit est retourné
    pour signalement."""
    fusion = dict(decisions_non_reconnues)
    conflits = {}
    for region, decision in decisions_ambigues.items():
        if region in fusion and fusion[region] != decision:
            conflits[region] = {fusion[region], decision}
            del fusion[region]
        else:
            fusion[region] = decision
    for region in conflits:
        fusion.pop(region, None)
    return fusion, conflits


def process():
    backup_csv()

    decisions_non_reconnues, nb_vides_non_reconnues = charger_decisions(
        DECISIONS_NON_RECONNUES_PATH, "régions non reconnues"
    )
    decisions_ambigues, nb_vides_ambigues = charger_decisions(
        DECISIONS_AMBIGUES_PATH, "régions ambiguës"
    )
    print(f"Décisions chargées : {len(decisions_non_reconnues)} (non reconnues), "
          f"{len(decisions_ambigues)} (ambiguës)")

    decisions, conflits = fusionner_decisions(decisions_non_reconnues, decisions_ambigues)
    if conflits:
        print("[ATTENTION] Régions avec une décision différente dans les deux fichiers "
              "(aucune des deux n'est appliquée) :")
        for region, valeurs in conflits.items():
            print(f"    {region} : {', '.join(sorted(valeurs))}")

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    col_map = resolve_columns({ID_COLUMN, CATALOG_COLUMN, AIRE_COLUMN, REGION_COLUMN}, fieldnames)
    id_col = col_map[ID_COLUMN]
    catalog_col = col_map[CATALOG_COLUMN]
    aire_col = col_map[AIRE_COLUMN]
    region_col = col_map[REGION_COLUMN]

    applications = []  # (id_perenne, catalog_id, region, aire_appliquee)
    regions_toujours_non_resolues = Counter()

    for row in rows:
        aire = (row.get(aire_col) or "").strip()
        if aire != VALEUR_INCONNUE:
            continue

        region = (row.get(region_col) or "").strip()
        if not region:
            continue

        if region in decisions:
            id_perenne = (row.get(id_col) or "").strip()
            catalog_id = (row.get(catalog_col) or "").strip()
            aire_appliquee = decisions[region]
            row[aire_col] = aire_appliquee
            applications.append((id_perenne, catalog_id, region, aire_appliquee))
        else:
            regions_toujours_non_resolues[region] += 1

    # ---- Écriture du CSV modifié ----
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    # ---- Log des applications ----
    with open(LOG_APPLICATIONS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Log d'application des décisions manuelles - {TIMESTAMP}\n")
        f.write(f"Nombre total d'applications : {len(applications)}\n\n")
        for id_perenne, catalog_id, region, aire_appliquee in applications:
            f.write(f'{id_perenne} ; {catalog_id} ; region="{region}" ; aire_appliquee="{aire_appliquee}"\n')

        if conflits:
            f.write("\n--- Régions ignorées (décision différente entre les deux fichiers) ---\n")
            for region, valeurs in conflits.items():
                f.write(f'  "{region}" : {", ".join(sorted(valeurs))}\n')

        if regions_toujours_non_resolues:
            f.write("\n--- Régions toujours sans décision (dédupliquées) ---\n")
            for region, n in regions_toujours_non_resolues.most_common():
                f.write(f'  "{region}" : {n} ligne(s) concernée(s)\n')

    # ---- Statistiques ----
    with open(LOG_STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques - application des décisions aire géographique - {TIMESTAMP}\n")
        f.write(f"Fichier source          : {CSV_PATH}\n")
        f.write(f"Décisions non reconnues : {DECISIONS_NON_RECONNUES_PATH}\n")
        f.write(f"Décisions ambiguës      : {DECISIONS_AMBIGUES_PATH}\n")
        f.write(f"Backup                  : {BACKUP_PATH}\n")
        f.write(f"CSV modifié             : {OUTPUT_CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes du fichier                : {len(rows)}\n")
        f.write(f"Nombre total d'applications                       : {len(applications)}\n")
        f.write(f"Régions encore sans décision (lignes concernées)  : {sum(regions_toujours_non_resolues.values())}\n")
        f.write(f"  dont régions distinctes                          : {len(regions_toujours_non_resolues)}\n")
        f.write(f"Décisions laissées vides dans le fichier 'non reconnues' : {nb_vides_non_reconnues}\n")
        f.write(f"Décisions laissées vides dans le fichier 'ambiguës'      : {nb_vides_ambigues}\n")
        f.write(f"Régions en conflit entre les deux fichiers (ignorées)    : {len(conflits)}\n")

    print("Traitement terminé.")
    print(f"  CSV modifié       : {OUTPUT_CSV_PATH}")
    print(f"  Log applications  : {LOG_APPLICATIONS_PATH}")
    print(f"  Log stats         : {LOG_STATS_PATH}")


if __name__ == "__main__":
    process()
