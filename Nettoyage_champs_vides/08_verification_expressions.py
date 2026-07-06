#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vérification (lecture seule) de la présence d'expressions "non renseigné /
non spécifié / non précisé" dans le CSV NETTOYÉ (sortie du script de
nettoyage précédent).

Ce script ne modifie RIEN : il sert d'audit / de contrôle, notamment pour :
  - repérer les champs volontairement laissés hors du nettoyage
    (ex. Inscription_nature, Date_complete) mais qu'on veut quand même
    surveiller,
  - vérifier qu'aucune occurrence résiduelle ne subsiste après nettoyage.

TOUTES les colonnes du CSV sont scannées (sauf Id_perenne lui-même) : dès
qu'une valeur de cellule est STRICTEMENT égale (pas de regex, sensible à la
casse/accents) à une des expressions de la liste, elle est notée :
Id_perenne + nom de la colonne + valeur.

Sorties (fichiers txt) :
  - detections_expressions_<timestamp>.txt : détail par ligne concernée
  - stats_detections_expressions_<timestamp>.txt : compteurs par champ
"""

import csv
import os
import unicodedata
from collections import Counter
from datetime import datetime

CSV_PATH = "chemin_du_csv"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"

# Liste à plat de TOUTES les expressions à détecter, quel que soit le champ
# où elles apparaissent (comparaison stricte, sans regex).
EXPRESSIONS_A_DETECTER = sorted(set([
    "Non précisée",
    "Non spécifiés",
    "Non spécifié",
    "Non spécifiée",
    "Non précisé",
    "non déchiffré",
    "Non spécifiée",
    "non daté",
    "Daté (date non spécifiée)",
    "Non indiquée",
    "Siècle non spécifié",
    "Date non spécifiée",
    "null",
    "Null"
]))

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

DETECTIONS_PATH = os.path.join(OUTPUT_DIR, f"detections_expressions_{TIMESTAMP}.txt")
STATS_PATH = os.path.join(OUTPUT_DIR, f"stats_detections_expressions_{TIMESTAMP}.txt")


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

def process():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    col_map = resolve_columns({ID_COLUMN}, fieldnames)
    id_col = col_map[ID_COLUMN]
    expressions_set = set(EXPRESSIONS_A_DETECTER)

    # Toutes les colonnes sauf Id_perenne sont scannées
    colonnes_a_scanner = [c for c in fieldnames if c != id_col]

    detections = []            # (id_perenne, colonne, valeur)
    field_counter = Counter()  # colonne -> nb d'occurrences détectées
    expr_counter = Counter()   # expression -> nb d'occurrences détectées
    rows_concerned = set()

    for row in rows:
        id_perenne = (row.get(id_col) or "").strip()
        for colonne in colonnes_a_scanner:
            valeur = row.get(colonne, "")
            if valeur in expressions_set:
                detections.append((id_perenne, colonne, valeur))
                field_counter[colonne] += 1
                expr_counter[valeur] += 1
                rows_concerned.add(id_perenne)

    # --- Écriture du détail des détections ---
    with open(DETECTIONS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Détections d'expressions non renseignées - {TIMESTAMP}\n")
        f.write(f"Fichier vérifié : {CSV_PATH}\n")
        f.write(f"Nombre total de détections : {len(detections)}\n\n")
        for id_perenne, colonne, valeur in detections:
            f.write(f'{id_perenne} ; {colonne} ; "{valeur}"\n')

    # --- Écriture des statistiques ---
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques de détection - {TIMESTAMP}\n")
        f.write(f"Fichier vérifié : {CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes du fichier                 : {len(rows)}\n")
        f.write(f"Nombre total de détections                        : {len(detections)}\n")
        f.write(f"Nombre de lignes concernées (au moins 1 détection) : {len(rows_concerned)}\n\n")

        f.write("Détail par colonne (nombre de détections, colonnes concernées uniquement) :\n")
        for colonne, count in field_counter.most_common():
            f.write(f"  {colonne} : {count}\n")

        f.write("\nDétail par expression détectée :\n")
        for expr, count in expr_counter.most_common():
            f.write(f'  "{expr}" : {count}\n')

    print("Vérification terminée.")
    print(f"  Détail  : {DETECTIONS_PATH}")
    print(f"  Stats   : {STATS_PATH}")


if __name__ == "__main__":
    process()
