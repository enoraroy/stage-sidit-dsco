"""
Comptage (lecture seule) des lignes du CSV où le champ Estimation_lot ne
contient aucune devise reconnue.

Devises reconnues (recherche de sous-chaîne, sensible à la casse) :
    US$, HK$, GBP, £, €

Deux catégories sont distinguées :
    - "vide"        : le champ Estimation_lot est vide (ou uniquement des
                       espaces)
    - "sans_devise"  : le champ contient du texte, mais aucune des devises
                       reconnues n'y apparaît

Pour chaque ligne concernée, on note : Id_perenne, Identifiant_catalogue,
catégorie, valeur brute. Un compteur par Identifiant_catalogue est aussi
généré, pour t'aider à identifier manuellement la devise associée à chaque
catalogue par la suite.

Ce script ne modifie PAS le CSV : il ne fait que lire et rapporter.
"""

import csv
import os
import unicodedata
from collections import Counter
from datetime import datetime

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------

CSV_PATH = r"chemin_du_csv"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
ESTIMATION_COLUMN = "Estimation_lot"

CURRENCY_TOKENS = ["$", "EUR","US$", "HK$", "GBP", "£", "€"]

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

DETAIL_PATH = os.path.join(OUTPUT_DIR, f"sans_devise_detail_{TIMESTAMP}.txt")
STATS_PATH = os.path.join(OUTPUT_DIR, f"sans_devise_stats_{TIMESTAMP}.txt")

def _normalize(nom):
    s = unicodedata.normalize("NFKD", nom)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def resolve_columns(expected_columns, fieldnames):
    normalized_real = {_normalize(f): f for f in fieldnames}
    resolved = {}
    unresolved = []

    for col in expected_columns:
        if col in fieldnames:
            resolved[col] = col
            continue
        match = normalized_real.get(_normalize(col))
        if match:
            print(f"[ATTENTION] Colonne \"{col}\" absente telle quelle ; "
                  f"correspondance trouvée avec la colonne réelle \"{match}\". "
                  f"Utilisation de \"{match}\".")
            resolved[col] = match
        else:
            unresolved.append(col)

    if unresolved:
        raise ValueError(
            "Colonnes attendues introuvables dans le CSV (même approximativement) : "
            + ", ".join(unresolved)
            + "\nColonnes disponibles : " + ", ".join(fieldnames)
        )
    return resolved


def contient_devise(valeur):
    return any(token in valeur for token in CURRENCY_TOKENS)


def process():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    col_map = resolve_columns({ID_COLUMN, CATALOG_COLUMN, ESTIMATION_COLUMN}, fieldnames)
    id_col = col_map[ID_COLUMN]
    catalog_col = col_map[CATALOG_COLUMN]
    estimation_col = col_map[ESTIMATION_COLUMN]

    detections = []  # (id_perenne, identifiant_catalogue, categorie, valeur_brute)
    catalog_counts_vide = Counter()
    catalog_counts_sans_devise = Counter()

    for row in rows:
        id_perenne = (row.get(id_col) or "").strip()
        catalog_id = (row.get(catalog_col) or "").strip()
        valeur = row.get(estimation_col, "") or ""

        if valeur.strip() == "":
            detections.append((id_perenne, catalog_id, "vide", valeur))
            catalog_counts_vide[catalog_id] += 1
        elif not contient_devise(valeur):
            detections.append((id_perenne, catalog_id, "sans_devise", valeur))
            catalog_counts_sans_devise[catalog_id] += 1
        # sinon : une devise reconnue est présente -> rien à signaler

    total_vide = sum(catalog_counts_vide.values())
    total_sans_devise = sum(catalog_counts_sans_devise.values())

    # --- Détail ---
    with open(DETAIL_PATH, "w", encoding="utf-8") as f:
        f.write(f"Lignes sans devise reconnue dans {estimation_col} - {TIMESTAMP}\n")
        f.write(f"Fichier vérifié : {CSV_PATH}\n")
        f.write(f"Devises reconnues : {', '.join(CURRENCY_TOKENS)}\n")
        f.write(f"Nombre total de lignes concernées : {len(detections)}\n\n")
        for id_perenne, catalog_id, categorie, valeur in detections:
            valeur_clean = valeur.replace("\n", " ").replace("\r", " ").strip()
            f.write(f'{id_perenne} ; {catalog_id} ; {categorie} ; "{valeur_clean}"\n')

    # --- Statistiques ---
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques - lignes sans devise reconnue - {TIMESTAMP}\n")
        f.write(f"Fichier vérifié : {CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes du fichier         : {len(rows)}\n")
        f.write(f"Nombre de lignes vides ({estimation_col})  : {total_vide}\n")
        f.write(f"Nombre de lignes sans devise reconnue      : {total_sans_devise}\n")
        f.write(f"Total lignes concernées                    : {len(detections)}\n\n")

        f.write(f"Détail par Identifiant_catalogue - lignes VIDES :\n")
        for catalog_id, count in catalog_counts_vide.most_common():
            f.write(f"  {catalog_id} : {count}\n")

        f.write(f"\nDétail par Identifiant_catalogue - lignes SANS DEVISE (texte présent) :\n")
        for catalog_id, count in catalog_counts_sans_devise.most_common():
            f.write(f"  {catalog_id} : {count}\n")

    print("Comptage terminé.")
    print(f"  Détail : {DETAIL_PATH}")
    print(f"  Stats  : {STATS_PATH}")


if __name__ == "__main__":
    process()
