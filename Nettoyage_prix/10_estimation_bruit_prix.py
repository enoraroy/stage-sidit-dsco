"""
Détection (lecture seule) du "bruit" dans le champ Estimation_lot : toute
valeur contenant, en plus des chiffres et des devises reconnues, un
caractère qui n'est PAS dans la liste des symboles autorisés.

Devises reconnues (recherche de sous-chaîne, sensible à la casse) :
    US$, HK$, GBP, £, €, $, EUR

Symboles autorisés (en plus des chiffres et des devises) :
    , . / - ( ) | ;
    + l'espace ( ), car les valeurs contiennent souvent plusieurs
      fourchettes de prix juxtaposées, ex. :
      "£2,000-3,000 US$3,300-5,000 €2,400-3,700"
      Sans autoriser l'espace, ce type de ligne (parfaitement propre)
      serait signalé à tort comme bruité.

Pour chaque ligne où un caractère inattendu est trouvé, on note :
Id_perenne, Identifiant_catalogue, caractères inattendus, valeur brute.

Ce script ne modifie PAS le CSV : il ne fait que lire et rapporter -> le but est d'ensuite corriger
à la main car il faut systématiquement se reporter au catalogue ! (ou, dans le cas où des catalogues
n'ont qu'une seule monnaie, se reporter aux autres lots du catalogue, d'où le script 11)
"""

import csv
import os
import unicodedata
from collections import Counter
from datetime import datetime

CSV_PATH = r"chemin_du_csv"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
ESTIMATION_COLUMN = "Estimation_lot"

CURRENCY_TOKENS = ["$", "EUR","US$", "HK$", "GBP", "£", "€"]
ALLOWED_PUNCTUATION = {",", ".", "/", "-", "(", ")", "|", ";", " ", "\u00a0", "\n", "\r"}

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

DETAIL_PATH = os.path.join(OUTPUT_DIR, f"bruit_estimation_detail_{TIMESTAMP}.txt")
STATS_PATH = os.path.join(OUTPUT_DIR, f"bruit_estimation_stats_{TIMESTAMP}.txt")


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


def caracteres_inattendus(valeur):
    """Retire les tokens de devise de la valeur, puis renvoie l'ensemble
    trié des caractères restants qui ne sont ni des chiffres ni dans
    ALLOWED_PUNCTUATION."""
    reste = valeur
    for token in sorted(CURRENCY_TOKENS, key=len, reverse=True):
        reste = reste.replace(token, "")
    inattendus = sorted(set(c for c in reste if not (c.isdigit() or c in ALLOWED_PUNCTUATION)))
    return inattendus

def process():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    col_map = resolve_columns({ID_COLUMN, CATALOG_COLUMN, ESTIMATION_COLUMN}, fieldnames)
    id_col = col_map[ID_COLUMN]
    catalog_col = col_map[CATALOG_COLUMN]
    estimation_col = col_map[ESTIMATION_COLUMN]

    detections = []  # (id_perenne, identifiant_catalogue, caracteres, valeur_brute)
    catalog_counts = Counter()
    char_counts = Counter()

    for row in rows:
        id_perenne = (row.get(id_col) or "").strip()
        catalog_id = (row.get(catalog_col) or "").strip()
        valeur = row.get(estimation_col, "") or ""

        if valeur.strip() == "":
            continue  # géré par le script de comptage "sans devise"

        inattendus = caracteres_inattendus(valeur)
        if inattendus:
            detections.append((id_perenne, catalog_id, inattendus, valeur))
            catalog_counts[catalog_id] += 1
            for c in inattendus:
                char_counts[c] += 1

    # --- Détail ---
    with open(DETAIL_PATH, "w", encoding="utf-8") as f:
        f.write(f"Lignes bruitées dans {estimation_col} - {TIMESTAMP}\n")
        f.write(f"Fichier vérifié : {CSV_PATH}\n")
        f.write(f"Devises reconnues     : {', '.join(CURRENCY_TOKENS)}\n")
        f.write(f"Symboles autorisés    : {' '.join(sorted(ALLOWED_PUNCTUATION))} (+ chiffres + devises)\n")
        f.write(f"Nombre total de lignes bruitées : {len(detections)}\n\n")
        for id_perenne, catalog_id, inattendus, valeur in detections:
            valeur_clean = valeur.replace("\n", " ").replace("\r", " ").strip()
            f.write(
                f'{id_perenne} ; {catalog_id} ; caractères inattendus : '
                f'{"".join(inattendus)} ; "{valeur_clean}"\n'
            )

    # --- Statistiques ---
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques - lignes bruitées - {TIMESTAMP}\n")
        f.write(f"Fichier vérifié : {CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes du fichier : {len(rows)}\n")
        f.write(f"Nombre de lignes bruitées          : {len(detections)}\n\n")

        f.write("Détail par Identifiant_catalogue :\n")
        for catalog_id, count in catalog_counts.most_common():
            f.write(f"  {catalog_id} : {count}\n")

        f.write("\nDétail par caractère inattendu rencontré :\n")
        for char, count in char_counts.most_common():
            f.write(f'  "{char}" : {count}\n')

    print("Détection terminée.")
    print(f"  Détail : {DETAIL_PATH}")
    print(f"  Stats  : {STATS_PATH}")


if __name__ == "__main__":
    process()
