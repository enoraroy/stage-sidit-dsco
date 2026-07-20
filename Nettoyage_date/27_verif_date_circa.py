"""
Script 27 - Recensement des lignes dont Date_complete contient un
marqueur d'approximation temporelle (circa, ca., c.) portant sur autre
chose qu'une annee en chiffres arabes.

Fait suite au script 26 (conversion des chiffres romains). Le CSV source
est donc le CSV corrige produit par le script 26.

Criteres de selection (une ligne est retenue si TOUS ces points sont vrais) :
    1. Date_complete contient un marqueur circa :
           circa / ca / ca. / c.  (avec ou sans point, toute casse)
       "c" seul sans point uniquement en debut de valeur suivi d'un espace.
    2. La valeur ne decrit PAS une date av./ap. J.-C.
       Formes couvertes : av. J.-C. / avant J.-C. / ap. J.-C. / apres J.-C.
       / apres J.-C. / J.-C. / J.C. / JC seuls.
    3. Le circa ne porte PAS directement sur une annee a 4 chiffres,
       seule ou en plage (ex. circa 1982, circa 1170-1200, ca. 1900,
       c. 1960's). Ces cas ont des bornes calculables et ne posent pas
       de probleme de standardisation.

Exemples captures (siecles, periodes, formules non numeriques) :
    ca. 18e-19e siecle
    c. 20e siecle
    circa deuxieme quart du 17e siecle
    circa 10e siecle
    circa 8th century

Exemples NON captures :
    circa 1982          (annee 4 chiffres)
    circa 1170-1200     (plage d'annees)
    ca. 1900            (annee 4 chiffres)
    c. 1960's           (annee 4 chiffres + suffixe)
    1er siecle av. J.-C.   (J.-C.)
    2e siecle ap. J.-C.    (J.-C.)
    2011-2013              (pas de circa)

Lecture seule : aucune modification du CSV source.

Sorties :
    - affichage console (valeurs distinctes + detail ligne par ligne)
    - log_circa_YYYYMMDD_HHMMSS.csv
"""

import csv
import os
import re
from collections import Counter
from datetime import datetime


# --- Chemin a adapter : CSV produit par le script 26 ---
CSV_PATH = r"chemin_du_csv"

OUTPUT_DIR = os.path.dirname(CSV_PATH)
DELIMITER = ";"
COLONNE_DATE = "Date_complete"
COL_ID = "Id_perenne"
COL_CATALOGUE = "Identifiant_catalogue"
COL_DATE_BASSE = "Date_plus_basse"
COL_DATE_HAUTE = "Date_plus_haute"


# ------------------------------------------------------------------
# PATTERNS
# ------------------------------------------------------------------

# 1. Marqueur circa
PATTERN_CIRCA = re.compile(
    r"(?:^|(?<=[\s\-,\(]))"
    r"(?:circa\.?|ca\.?|c\.)"
    r"(?=[\s\-,\(]|$)",
    flags=re.IGNORECASE,
)
PATTERN_C_SEUL = re.compile(r"^c(?=\s)", flags=re.IGNORECASE)


def contient_circa(valeur):
    return bool(PATTERN_CIRCA.search(valeur) or PATTERN_C_SEUL.search(valeur))


# 2. Exclusion J.-C. : couvre toutes les graphies courantes
#    av. J.-C. / avant J.-C. / ap. J.-C. / apres J.-C. / apres J.-C.
#    ainsi que J.-C. / J.C. / JC seuls (siecles antiques sans "av" explicite)
PATTERN_JC = re.compile(
    r"(?:"
    r"\b(?:av(?:ant)?|ap(?:r[eè]s)?)\.?\s+[Jj]"  # av. J / avant J / ap. J / apres J
    r"|[Jj]\.?-?[Cc]\.?"                           # J.-C. / J.C. / JC seuls
    r")",
    flags=re.IGNORECASE,
)


def est_avant_apres_jc(valeur):
    return bool(PATTERN_JC.search(valeur))


# 3. Exclusion annee : circa suivi directement de 4 chiffres,
#    seuls ou en plage (circa 1982 / circa 1170-1200 / c. 1960's)
#    car le problème ne portait pas sur ces cas, donc pas besoin de les
#    vérifier manuellement
PATTERN_ANNEE = re.compile(
    r"(?:circa\.?|ca\.?|c\.)\s*\d{4}(?:\s*[-\u2013]\s*\d{4})?",
    flags=re.IGNORECASE,
)


def est_circa_annee(valeur):
    return bool(PATTERN_ANNEE.search(valeur))

def est_circa_a_traiter(valeur):
    if not valeur:
        return False
    if not contient_circa(valeur):
        return False
    if est_avant_apres_jc(valeur):
        return False
    if est_circa_annee(valeur):
        return False
    return True


def main():
    print("--- Script 27 : recensement circa (hors annees et J.-C.) dans Date_complete ---")
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
        if not est_circa_a_traiter(valeur):
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
                f"{c['Date_complete']:<45}  "
                f"basse={c['Date_plus_basse'] or '(vide)':>6}  "
                f"haute={c['Date_plus_haute'] or '(vide)'}"
            )


    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_log = f"log_circa_{horodatage}.csv"
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
