# -*- coding: utf-8 -*-
"""
Script 23 - Appliquer les suppressions de champs issues de l'arbitrage manuel.

Fait suite a l'outil d'arbitrage (revue_manuelle_contenu_absent.py).

Lit le fichier d'arbitrages et le CSV lots, puis vide les cellules des
champs marques "A SUPPRIMER" dans les decisions d'arbitrage. Les lignes
sont conservees ; seul le contenu du champ concerne est efface.

Les anomalies marquees avec d'autres decisions (OK, FAUX POSITIF,
A CORRIGER, INCERTAIN) ne sont pas touchees : les corrections manuelles
se font directement sur le CSV produit par ce script.

Entrees :
    - arbitrages_contenu_absent_notice.csv  (produit par l'outil d'arbitrage)
    - CSV lots source (lots_prix_vente_valeur_devise_separees_*.csv)

Sortie :
    - lots_champs_absents_corriges_YYYYMMDD_HHMMSS.csv
"""

import csv
import os
from datetime import datetime


# --- Chemins a adapter ---
ARBITRAGE_CSV_PATH = r"arbitrages_contenu_absent_notice.csv"
LOTS_CSV_PATH = r"chemin_du_csv_des_lots.csv"

OUTPUT_DIR = os.path.dirname(LOTS_CSV_PATH)

DELIMITER = ";"
DECISION_SUPPRIMER = "A SUPPRIMER - inscription invalidee, a retirer"

COL_ID = "Id_perenne"
COL_CHAMP = "champ_concerne"
COL_DECISION = "Decision_manuelle"


def charger_suppressions(path):
    """
    Renvoie un dict  Id_perenne -> ensemble de champs a vider,
    construit a partir des lignes dont la decision est DECISION_SUPPRIMER.
    """
    suppressions = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        for row in reader:
            decision = (row.get(COL_DECISION) or "").strip()
            if decision != DECISION_SUPPRIMER:
                continue
            id_perenne = (row.get(COL_ID) or "").strip()
            champ = (row.get(COL_CHAMP) or "").strip()
            if not id_perenne or not champ:
                continue
            suppressions.setdefault(id_perenne, set()).add(champ)
    return suppressions


def charger_lots(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        colonnes = reader.fieldnames
        lignes = list(reader)
    return colonnes, lignes


def appliquer_suppressions(colonnes, lignes, suppressions):
    """
    Pour chaque ligne du CSV lots, vide les champs indiques dans
    suppressions pour l'Id_perenne correspondant.
    Renvoie (lignes_modifiees, stats).
    """
    nb_lots_modifies = 0
    nb_champs_vides = 0
    champs_inconnus = set()

    for row in lignes:
        id_perenne = (row.get(COL_ID) or "").strip()
        champs_a_vider = suppressions.get(id_perenne)
        if not champs_a_vider:
            continue

        lot_modifie = False
        for champ in champs_a_vider:
            if champ not in colonnes:
                champs_inconnus.add(champ)
                continue
            if row.get(champ, "") != "":
                row[champ] = ""
                nb_champs_vides += 1
                lot_modifie = True

        if lot_modifie:
            nb_lots_modifies += 1

    stats = {
        "nb_lots_modifies": nb_lots_modifies,
        "nb_champs_vides": nb_champs_vides,
        "champs_inconnus": champs_inconnus,
    }
    return lignes, stats


def ecrire_csv(path, colonnes, lignes):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=colonnes, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(lignes)


def main():
    print("--- Script 23 : application des suppressions de champs ---")

    print(f"Chargement des arbitrages : {ARBITRAGE_CSV_PATH}")
    suppressions = charger_suppressions(ARBITRAGE_CSV_PATH)
    nb_lots_concernes = len(suppressions)
    nb_suppressions_total = sum(len(v) for v in suppressions.values())
    print(f"  {nb_suppressions_total} suppression(s) a appliquer sur {nb_lots_concernes} lot(s)")

    if nb_suppressions_total == 0:
        print("Aucune suppression a effectuer. Fin du script.")
        return

    print(f"Chargement du CSV lots : {LOTS_CSV_PATH}")
    colonnes, lignes = charger_lots(LOTS_CSV_PATH)
    print(f"  {len(lignes)} ligne(s) chargee(s), {len(colonnes)} colonne(s)")

    print("Application des suppressions...")
    lignes, stats = appliquer_suppressions(colonnes, lignes, suppressions)

    if stats["champs_inconnus"]:
        print(f"  ATTENTION : champ(s) introuvable(s) dans le CSV lots, ignores :")
        for c in sorted(stats["champs_inconnus"]):
            print(f"    - {c}")

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_sortie = f"lots_champs_absents_corriges_{horodatage}.csv"
    chemin_sortie = os.path.join(OUTPUT_DIR, nom_sortie)

    print(f"Ecriture du CSV corrige : {chemin_sortie}")
    ecrire_csv(chemin_sortie, colonnes, lignes)

    print(f"Termine.")
    print(f"  Lots modifies        : {stats['nb_lots_modifies']}")
    print(f"  Champs vides         : {stats['nb_champs_vides']}")
    print(f"  Fichier produit      : {nom_sortie}")


if __name__ == "__main__":
    main()
