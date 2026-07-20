"""
Extraction des valeurs uniques de deux champs multi-valeurs du CSV lots :

  - Region_lieu_production  : separateurs "/", ";", ","
  - Mentions_personnes_personnages : separateurs ";", ","

Produit deux fichiers .txt, un par champ, avec une valeur par ligne,
triees par ordre alphabetique, sans doublons, sans lignes vides.
"""

import csv
import os
import re
import unicodedata
from datetime import datetime


CSV_PATH = r"chemin_du_csv"

DELIMITER = ";"

CHAMPS = {
    "Region_lieu_production": re.compile(r"[/;,]"),
    "Mentions_personnes_personnages": re.compile(r"[;,]"),
}

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

def _normalize_colname(nom):
    s = unicodedata.normalize("NFKD", nom)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def resolve_columns(expected_columns, fieldnames):
    normalized_real = {_normalize_colname(f): f for f in fieldnames}
    resolved = {}
    unresolved = []
    for col in expected_columns:
        if col in fieldnames:
            resolved[col] = col
            continue
        match = normalized_real.get(_normalize_colname(col))
        if match:
            print(f"[ATTENTION] Colonne \"{col}\" absente telle quelle ; "
                  f"correspondance trouvee avec \"{match}\". Utilisation de \"{match}\".")
            resolved[col] = match
        else:
            unresolved.append(col)
    if unresolved:
        raise ValueError(
            "Colonnes introuvables : " + ", ".join(unresolved)
            + "\nColonnes disponibles : " + ", ".join(fieldnames)
        )
    return resolved


def extraire_valeurs_uniques(rows, colonne_reelle, pattern_sep):
    """Lit toutes les cellules de `colonne_reelle`, decoupe sur
    `pattern_sep`, nettoie les fragments (strip, vides exclus), et
    renvoie (ensemble_valeurs_uniques, nb_cellules_non_vides,
    nb_fragments_bruts)."""
    valeurs = set()
    nb_cellules = 0
    nb_fragments = 0

    for row in rows:
        cellule = (row.get(colonne_reelle) or "").strip()
        if cellule == "":
            continue
        nb_cellules += 1
        fragments = pattern_sep.split(cellule)
        for fragment in fragments:
            fragment = fragment.strip()
            if fragment == "":
                continue
            nb_fragments += 1
            valeurs.add(fragment)

    return valeurs, nb_cellules, nb_fragments


def process():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"Fichier source : {CSV_PATH}")
    print(f"Nombre de lignes (hors entete) : {len(rows)}")
    print()

    col_map = resolve_columns(set(CHAMPS.keys()), fieldnames)

    for champ, pattern_sep in CHAMPS.items():
        colonne_reelle = col_map[champ]
        valeurs, nb_cellules, nb_fragments = extraire_valeurs_uniques(rows, colonne_reelle, pattern_sep)
        valeurs_triees = sorted(valeurs, key=lambda v: unicodedata.normalize("NFKD", v).casefold())

        output_path = os.path.join(OUTPUT_DIR, f"valeurs_uniques_{champ}_{TIMESTAMP}.txt")
        with open(output_path, "w", encoding="utf-8") as f_out:
            for valeur in valeurs_triees:
                f_out.write(valeur + "\n")

        print(f"[{champ}]")
        print(f"  Cellules non vides : {nb_cellules}")
        print(f"  Fragments bruts (apres decoupage) : {nb_fragments}")
        print(f"  Valeurs uniques : {len(valeurs_triees)}")
        print(f"  Fichier de sortie : {output_path}")
        print()


if __name__ == "__main__":
    process()
