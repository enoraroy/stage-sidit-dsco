
"""
Détection (lecture seule) de toutes les régions
(Region_lieu_production) associées à PLUSIEURS aires géographiques
différentes (Aire_geographique_production) dans le CSV, indépendamment du
cas "origine inconnue".

Contrairement au script 17 (qui ne signale une région ambiguë que si elle
possède au moins une ligne "origine inconnue" à imputer), ce script scanne
l'ensemble des lignes du CSV : une région peut donc être détectée ici même
si aucune de ses lignes n'a jamais été "origine inconnue" — c'est un
diagnostic de cohérence générale du champ Aire_geographique_production par
rapport à Region_lieu_production.

Ce script ne modifie RIEN : il ne fait que lire et rapporter.

Règles :
    - Les lignes avec Region_lieu_production vide sont ignorées.
    - Les lignes avec Aire_geographique_production vide, ou égale à
      "origine inconnue", sont ignorées pour la construction des
      associations (elles n'apportent pas d'information sur la "bonne"
      aire), mais restent listées dans le détail pour information.
    - Une région est signalée dès que 2 aires distinctes (ou plus) lui
      sont associées ailleurs dans le CSV.
"""

import csv
import os
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime


CSV_PATH = r"chemin_du_csv"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
AIRE_COLUMN = "Aire_geographique_production"
REGION_COLUMN = "Region_lieu_production"

VALEUR_INCONNUE = "Origine inconnue"

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

DETAIL_PATH = os.path.join(OUTPUT_DIR, f"incoherences_aire_detail_{TIMESTAMP}.txt")
RECAP_PATH = os.path.join(OUTPUT_DIR, f"incoherences_aire_recap_{TIMESTAMP}.csv")


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
            "Colonnes attendues introuvables (même approximativement) : "
            + ", ".join(unresolved)
            + "\nColonnes disponibles : " + ", ".join(fieldnames)
        )
    return resolved


def process():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    col_map = resolve_columns({ID_COLUMN, CATALOG_COLUMN, AIRE_COLUMN, REGION_COLUMN}, fieldnames)
    id_col = col_map[ID_COLUMN]
    catalog_col = col_map[CATALOG_COLUMN]
    aire_col = col_map[AIRE_COLUMN]
    region_col = col_map[REGION_COLUMN]

    # region -> aire -> nb de lignes ; region -> liste des lignes (pour le détail)
    region_vers_aires = defaultdict(Counter)
    region_vers_lignes = defaultdict(list)  # region -> [(id_perenne, catalog_id, aire)]

    for row in rows:
        region = (row.get(region_col) or "").strip()
        if not region:
            continue
        aire = (row.get(aire_col) or "").strip()
        id_perenne = (row.get(id_col) or "").strip()
        catalog_id = (row.get(catalog_col) or "").strip()

        region_vers_lignes[region].append((id_perenne, catalog_id, aire))

        if aire and aire != VALEUR_INCONNUE:
            region_vers_aires[region][aire] += 1

    # Régions avec plusieurs aires distinctes réellement renseignées
    regions_incoherentes = {
        region: aires for region, aires in region_vers_aires.items() if len(aires) > 1
    }

    # ---- Détail ----
    with open(DETAIL_PATH, "w", encoding="utf-8") as f:
        f.write(f"Régions associées à plusieurs aires géographiques - {TIMESTAMP}\n")
        f.write(f"Fichier vérifié : {CSV_PATH}\n")
        f.write(f"Nombre de régions concernées : {len(regions_incoherentes)}\n\n")

        for region, aires in sorted(regions_incoherentes.items(), key=lambda x: -sum(x[1].values())):
            f.write(f"--- Région : \"{region}\" ---\n")
            f.write(f"  Aires distinctes trouvées : {', '.join(sorted(aires))}\n")
            for id_perenne, catalog_id, aire in region_vers_lignes[region]:
                marque = "" if aire and aire != VALEUR_INCONNUE else "  (origine inconnue ou vide)"
                f.write(f'  {id_perenne} ; {catalog_id} ; aire="{aire}"{marque}\n')
            f.write("\n")

    # ---- Récapitulatif dédupliqué (format éditable, comme les fichiers du script 17) ----
    with open(RECAP_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=DELIMITER)
        writer.writerow([
            REGION_COLUMN, "Aires_distinctes", "Detail_par_aire",
            "Nb_lignes_total_region", "Aire_a_retenir"
        ])
        for region, aires in sorted(regions_incoherentes.items(), key=lambda x: -sum(x[1].values())):
            detail_par_aire = "; ".join(f"{aire} ({n})" for aire, n in aires.most_common())
            nb_total = len(region_vers_lignes[region])
            writer.writerow([region, ", ".join(sorted(aires)), detail_par_aire, nb_total, ""])

    print("Vérification terminée.")
    print(f"  Régions incohérentes détectées : {len(regions_incoherentes)}")
    print(f"  Détail       : {DETAIL_PATH}")
    print(f"  Récapitulatif: {RECAP_PATH}")


if __name__ == "__main__":
    process()
