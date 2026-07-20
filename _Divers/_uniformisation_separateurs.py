"""
Uniformisation des separateurs de valeurs multiples au sein
d'une meme cellule, pour les champs ou les separateurs heterogenes ont ete
releves manuellement.

Champs traites et separateurs consideres (remplaces par "|") :
    Materiaux                        : ","  ";"  "&"
    Techniques                       : ";"
    Couleurs                         : ";"
    Inscription_nature               : ";"
    Inscription_langue               : ";"
    Inscription_ecriture             : ";"
    Mention_personnes_personnages    : ";"  ","

Champs volontairement NON traites (separateurs trop heterogenes, a traiter
a part plus tard) :
    Region_lieu_production, Etat_conservation

Principe :
    Pour chaque champ concerne, chaque caractere separateur liste est
    considere comme une frontiere entre valeurs. On decoupe la cellule sur
    n'importe lequel de ces caracteres, on nettoie les espaces en trop
    autour de chaque valeur, on retire les valeurs vides (separateurs
    consecutifs ou en debut/fin), puis on rejoint le tout avec "|".

    Exemple : "bronze ; or , argent"  ->  "bronze|or|argent"

Lecture seule sur le fichier source : le resultat est ecrit dans un
nouveau CSV complet, avec en plus un log des lignes/champs modifies.

Sortie :
    - lots_separateurs_uniformises_YYYYMMDD_HHMMSS.csv (CSV complet corrige)
    - log_uniformisation_separateurs_YYYYMMDD_HHMMSS.csv (changements uniquement)
    - affichage console recapitulatif
"""

import csv
import os
import re
from collections import Counter
from datetime import datetime


# --- Chemin a adapter ---
CSV_PATH = r"chemin_du_csv"

OUTPUT_DIR = os.path.dirname(CSV_PATH)
DELIMITER = ";"
COL_ID = "Id_perenne"
COL_CATALOGUE = "Identifiant_catalogue"

# --- Champs a uniformiser et leurs separateurs actuels (a adapter si besoin) ---
CHAMPS_SEPARATEURS = {
    "Materiaux":                     [",", ";", "&"],
    "Techniques":                    [";"],
    "Couleurs":                      [";"],
    "Inscription_nature":            [";"],
    "Inscription_langue":            [";"],
    "Inscription_ecriture":          [";"],
    "Mentions_personnes_personnages": [";", ","],
}


def uniformiser_valeur(valeur, separateurs):
    """Decoupe `valeur` sur n'importe lequel des `separateurs`, nettoie
    chaque morceau et rejoint avec "|". Renvoie la valeur inchangee si
    elle est vide ou si aucun separateur n'est present."""
    if not valeur or not valeur.strip():
        return valeur

    motif = "[" + "".join(re.escape(s) for s in separateurs) + "]"
    morceaux = re.split(motif, valeur)
    morceaux = [m.strip() for m in morceaux if m.strip()]
    return "|".join(morceaux)


def main():
    print(f"Source : {CSV_PATH}")

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    champs_manquants = [c for c in CHAMPS_SEPARATEURS if c not in fieldnames]
    if champs_manquants:
        print(f"ERREUR : champ(s) introuvable(s) dans le CSV : {', '.join(champs_manquants)}")
        print(f"Colonnes disponibles : {', '.join(fieldnames)}")
        return

    print(f"  {len(rows)} lignes chargees.\n")

    logs = []                     # une entree par (ligne, champ) modifie
    compteur_par_champ = Counter()
    lignes_modifiees = set()

    for i, row in enumerate(rows):
        for champ, separateurs in CHAMPS_SEPARATEURS.items():
            valeur_avant = (row.get(champ) or "").strip()
            if not valeur_avant:
                continue

            valeur_apres = uniformiser_valeur(valeur_avant, separateurs)
            if valeur_apres == valeur_avant:
                continue

            row[champ] = valeur_apres
            compteur_par_champ[champ] += 1
            lignes_modifiees.add(i)

            logs.append({
                "Id_perenne":            (row.get(COL_ID) or "").strip(),
                "Identifiant_catalogue": (row.get(COL_CATALOGUE) or "").strip(),
                "champ":                 champ,
                "valeur_avant":          valeur_avant,
                "valeur_apres":          valeur_apres,
            })

    print(f"Lignes modifiees (au moins un champ) : {len(lignes_modifiees)} / {len(rows)}")
    print(f"Total de modifications (ligne x champ) : {len(logs)}")
    print()
    print("--- Modifications par champ ---")
    for champ, n in sorted(compteur_par_champ.items(), key=lambda x: -x[1]):
        print(f"  {champ:<32} : {n}")

    print()
    print("--- Detail des changements ---")
    for entree in logs:
        print(f"  [{entree['Id_perenne']}] {entree['champ']:<32} "
              f"{entree['valeur_avant']!r}  ->  {entree['valeur_apres']!r}")

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")

    nom_sortie_csv = f"lots_separateurs_uniformises_{horodatage}.csv"
    chemin_sortie_csv = os.path.join(OUTPUT_DIR, nom_sortie_csv)

    with open(chemin_sortie_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    nom_log = f"log_uniformisation_separateurs_{horodatage}.csv"
    chemin_log = os.path.join(OUTPUT_DIR, nom_log)

    with open(chemin_log, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Id_perenne", "Identifiant_catalogue", "champ",
                        "valeur_avant", "valeur_apres"],
            delimiter=DELIMITER,
        )
        writer.writeheader()
        writer.writerows(logs)

    print()
    print(f"CSV corrige ecrit : {chemin_sortie_csv}")
    print(f"Log de changements ecrit : {chemin_log}")
    print(f"  {len(lignes_modifiees)} ligne(s) modifiee(s), {len(logs)} changement(s) au total")


if __name__ == "__main__":
    main()
