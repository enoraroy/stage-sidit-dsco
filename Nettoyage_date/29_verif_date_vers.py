"""
Script 29 - Recensement des lignes dont Date_complete contient a la fois
le mot "vers" ET un terme de siecle.

Fait suite au script 28. Lecture seule.

Criteres de selection :
    1. Date_complete contient "vers" (mot entier, toute casse)
    2. Date_complete contient un terme de siecle (toute casse) :
           siecle, siecles, century, centuries

Exemples captures :
    vers le 19e siecle
    vers le debut du 18e siecle
    vers le 10th century

Exemples NON captures :
    vers 1850       (annee, pas de siecle)
    19e siecle      (pas de "vers")

Sorties :
    - affichage console (valeurs distinctes + detail ligne par ligne)
    - log_vers_siecle_YYYYMMDD_HHMMSS.csv

Note : Personnellement, cela m'était utile d'avoir un autre csv pour ne pas toucher au premier
de peur de faire quelque chose d'involontaire. Avoir un second csv me permet de surligner, supprimer
identifier les id problématiques et les traiter plus précisément. D'où cette stratégie, même si
on aurait pu tout à fait se contenter de filtres excel!

"""

import csv
import os
import re
from collections import Counter
from datetime import datetime

CSV_PATH = r"lots_dates_arabes_corriges.csv"

OUTPUT_DIR = os.path.dirname(CSV_PATH)
DELIMITER = ";"
COLONNE_DATE = "Date_complete"
COL_ID = "Id_perenne"
COL_CATALOGUE = "Identifiant_catalogue"
COL_DATE_BASSE = "Date_plus_basse"
COL_DATE_HAUTE = "Date_plus_haute"


PATTERN_VERS = re.compile(r"\bvers\b", flags=re.IGNORECASE)

PATTERN_SIECLE = re.compile(
    r"\bsi\xe8?cles?\b|\bcentur(?:y|ies)\b",
    flags=re.IGNORECASE,
)


def est_vers_siecle(valeur):
    if not valeur:
        return False
    if not PATTERN_VERS.search(valeur):
        return False
    if not PATTERN_SIECLE.search(valeur):
        return False
    return True


def main():
    print("--- Script 29 : recensement vers + siecle dans Date_complete ---")
    print(f"Source : {CSV_PATH}")

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    colonnes_manquantes = [
        c for c in [COLONNE_DATE, COL_DATE_BASSE, COL_DATE_HAUTE]
        if c not in fieldnames
    ]
    if colonnes_manquantes:
        print(f"ERREUR : colonne(s) introuvable(s) : {', '.join(colonnes_manquantes)}")
        return

    print(f"  {len(rows)} lignes chargees.\n")

    cas = []
    for row in rows:
        valeur = (row.get(COLONNE_DATE) or "").strip()
        if not est_vers_siecle(valeur):
            continue
        cas.append({
            "Id_perenne":            (row.get(COL_ID) or "").strip(),
            "Identifiant_catalogue": (row.get(COL_CATALOGUE) or "").strip(),
            "Date_complete":         valeur,
            "Date_plus_basse":       (row.get(COL_DATE_BASSE) or "").strip(),
            "Date_plus_haute":       (row.get(COL_DATE_HAUTE) or "").strip(),
        })


    print(f"Lignes concernees : {len(cas)}")
    print()

    if cas:
        compteur = Counter(c["Date_complete"] for c in cas)
        print("--- Valeurs Date_complete distinctes (frequence decroissante) ---")
        for valeur, n in compteur.most_common():
            print(f"  [{n:>4}x]  {valeur}")
        print()
        print("--- Detail (Id_perenne | Date_complete | basse | haute) ---")
        for c in cas:
            print(
                f"  {c['Id_perenne']:<12}  "
                f"{c['Date_complete']:<50}  "
                f"basse={c['Date_plus_basse'] or '(vide)':>6}  "
                f"haute={c['Date_plus_haute'] or '(vide)'}"
            )


    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_log = f"log_vers_siecle_{horodatage}.csv"
    chemin_log = os.path.join(OUTPUT_DIR, nom_log)

    with open(chemin_log, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Id_perenne", "Identifiant_catalogue",
                        "Date_complete", "Date_plus_basse", "Date_plus_haute"],
            delimiter=DELIMITER,
        )
        writer.writeheader()
        writer.writerows(cas)

    print()
    print(f"Log ecrit : {chemin_log}")
    print(f"  {len(cas)} ligne(s) recensee(s)")


if __name__ == "__main__":
    main()
