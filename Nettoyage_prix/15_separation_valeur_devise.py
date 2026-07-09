"""
Séparation du champ Estimation_lot (déjà uniformisé par les scripts
mono-devise / multi-devises) en 6 colonnes :

    valeur_1_estimation_lot ; devise_1_estimation_lot
    valeur_2_estimation_lot ; devise_2_estimation_lot
    valeur_3_estimation_lot ; devise_3_estimation_lot

Ces colonnes sont insérées à la place d'Estimation_lot. La colonne
Estimation_lot elle-même est CONSERVÉE dans le fichier de sortie, mais :
    - vidée pour toute ligne correctement séparée (la donnée vit désormais
      dans les colonnes valeur_X / devise_X),
    - conservée telle quelle (valeur brute inchangée) pour toute ligne
      "bruitée" / non reconnue, qui est mise de côté pour un traitement
      manuel ultérieur.

Format attendu en entrée pour une ligne "propre" (sortie des scripts de
normalisation précédents) :
    "{devise}{val}"                                (valeur unique)
    "{devise}{val1}-{devise}{val2}"                (intervalle)
    "{groupe1}|{groupe2}"  ou  "{groupe1}|{groupe2}|{groupe3}"  (multi-devises)

Règles :
    1. Champ vide                          -> rien à faire (colonnes vides,
                                               pas de log).
    2. 1 à 3 groupes, tous reconnus         -> séparation effectuée,
                                               Estimation_lot vidé.
    3. Plus de 3 groupes, ou au moins un    -> ligne mise de côté (bruit) :
       groupe non reconnu                     Estimation_lot conservé tel
                                               quel, colonnes valeur/devise
                                               vides, ligne loguée pour
                                               relecture manuelle.
"""

import csv
import os
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime


# À adapter : chemin du CSV le plus à jour (sortie du script multi-devises)
CSV_PATH = r"chemin_du_csv_avec_les_multiprix_nettoyes"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
ESTIMATION_COLUMN = "Estimation_lot"

# car on a eu ici que trois devises différentes pour un même lot. Mais possible d'en faire plus
NB_GROUPES_MAX = 3

# Symboles de prix produits par les scripts de normalisation précédents
SYMBOLES = ["HK$", "£", "€", "$"]
SYMBOLES_REGEX = "|".join(re.escape(s) for s in SYMBOLES)
GROUPE_PATTERN = re.compile(
    rf"^({SYMBOLES_REGEX})(\d+(?:\.\d+)?)(?:-({SYMBOLES_REGEX})(\d+(?:\.\d+)?))?$"
)

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP_PATH = os.path.join(OUTPUT_DIR, f"BACKUP_{TIMESTAMP}_" + os.path.basename(CSV_PATH))
OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"lots_valeur_devise_separees_{TIMESTAMP}.csv")
LOG_BRUIT_PATH = os.path.join(OUTPUT_DIR, f"log_bruit_restant_estimation_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_stats_separation_valeur_devise_{TIMESTAMP}.txt")

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


def backup_csv():
    shutil.copy2(CSV_PATH, BACKUP_PATH)
    print(f"Backup créé : {BACKUP_PATH}")


def parser_groupe(groupe):
    """Tente de parser un groupe 'devise+valeur[-devise+valeur]'.
    Retourne (valeur, devise) si reconnu, sinon (None, None)."""
    m = GROUPE_PATTERN.match(groupe.strip())
    if not m:
        return None, None
    symbole1, num1, symbole2, num2 = m.groups()
    if symbole2 is not None and symbole2 != symbole1:
        return None, None  # incohérence : deux devises différentes dans un même intervalle
    valeur = num1 if num2 is None else f"{num1}-{num2}"
    return valeur, symbole1


def parser_estimation(valeur):
    """Tente de séparer la cellule Estimation_lot complète en une liste de
    (valeur, devise) par groupe (séparés par '|').
    Retourne (liste_de_tuples, raison_echec). raison_echec est None si
    tout s'est bien passé."""
    groupes = valeur.split("|")
    if len(groupes) > NB_GROUPES_MAX:
        return None, f"plus de {NB_GROUPES_MAX} groupes ({len(groupes)})"

    resultats = []
    for g in groupes:
        val, dev = parser_groupe(g)
        if val is None:
            return None, f"groupe non reconnu : '{g.strip()}'"
        resultats.append((val, dev))
    return resultats, None


def process():
    backup_csv()

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    col_map = resolve_columns({ID_COLUMN, CATALOG_COLUMN, ESTIMATION_COLUMN}, fieldnames)
    id_col = col_map[ID_COLUMN]
    catalog_col = col_map[CATALOG_COLUMN]
    estimation_col = col_map[ESTIMATION_COLUMN]

    # Nouvelles colonnes, insérées à la place d'Estimation_lot (celui-ci
    # est conservé juste après, comme colonne de repli pour le bruit)
    nouvelles_colonnes = []
    for i in range(1, NB_GROUPES_MAX + 1):
        nouvelles_colonnes.append(f"valeur_{i}_estimation_lot")
        nouvelles_colonnes.append(f"devise_{i}_estimation_lot")

    index_estimation = fieldnames.index(estimation_col)
    nouveaux_fieldnames = (
        fieldnames[:index_estimation]
        + nouvelles_colonnes
        + [estimation_col]
        + fieldnames[index_estimation + 1:]
    )

    separations_ok = 0
    lignes_bruit = []  # (id_perenne, catalog_id, valeur, raison)
    par_nb_groupes = Counter()

    for row in rows:
        id_perenne = (row.get(id_col) or "").strip()
        catalog_id = (row.get(catalog_col) or "").strip()
        valeur = row.get(estimation_col, "") or ""

        # Initialisation des nouvelles colonnes à vide
        for col in nouvelles_colonnes:
            row[col] = ""

        if valeur.strip() == "":
            continue  # règle 1 : vide -> rien à faire

        resultats, raison_echec = parser_estimation(valeur)

        if raison_echec is not None:
            lignes_bruit.append((id_perenne, catalog_id, valeur, raison_echec))
            # Estimation_lot conservé tel quel (rien à changer, déjà la valeur d'origine)
            continue

        # règle 2 : séparation réussie
        for i, (val, dev) in enumerate(resultats, start=1):
            row[f"valeur_{i}_estimation_lot"] = val
            row[f"devise_{i}_estimation_lot"] = dev
        row[estimation_col] = ""  # vidé, la donnée vit désormais dans les colonnes valeur/devise
        separations_ok += 1
        par_nb_groupes[len(resultats)] += 1

    # ---- Écriture du CSV modifié ----
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=nouveaux_fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    # ---- Log du bruit restant ----
    with open(LOG_BRUIT_PATH, "w", encoding="utf-8") as f:
        f.write(f"Lignes mises de côté (bruit / non reconnues) - {TIMESTAMP}\n")
        f.write(f"Nombre total de lignes concernées : {len(lignes_bruit)}\n\n")
        for id_perenne, catalog_id, valeur, raison in lignes_bruit:
            valeur_clean = valeur.replace("\n", " ").replace("\r", " ").strip()
            f.write(f'{id_perenne} ; {catalog_id} ; "{valeur_clean}" ; raison : {raison}\n')

    # ---- Statistiques ----
    with open(LOG_STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques - séparation valeur/devise - {TIMESTAMP}\n")
        f.write(f"Fichier source : {CSV_PATH}\n")
        f.write(f"Backup         : {BACKUP_PATH}\n")
        f.write(f"CSV modifié    : {OUTPUT_CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes du fichier      : {len(rows)}\n")
        f.write(f"Lignes correctement séparées            : {separations_ok}\n")
        for n in range(1, NB_GROUPES_MAX + 1):
            f.write(f"  dont avec {n} groupe(s) de prix       : {par_nb_groupes.get(n, 0)}\n")
        f.write(f"Lignes mises de côté (bruit)             : {len(lignes_bruit)}\n")

    print("Traitement terminé.")
    print(f"  CSV modifié : {OUTPUT_CSV_PATH}")
    print(f"  Log bruit   : {LOG_BRUIT_PATH}")
    print(f"  Log stats   : {LOG_STATS_PATH}")


if __name__ == "__main__":
    process()
