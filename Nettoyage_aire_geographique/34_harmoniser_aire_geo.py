"""
Canonicalisation des valeurs multiples du champ
Aire_geographique_production.

Probleme : les valeurs composees (plusieurs aires separees par "|") peuvent
apparaitre dans des ordres differents selon les lignes, produisant des
doublons semantiques :
    "Maghreb|Monde iranien – Caucase"
    "Monde iranien – Caucase|Maghreb"
    -> sont la meme chose.

Solution : pour chaque cellule, les aires sont decoupees sur "|", triees
alphabetiquement (insensible a la casse et aux diacritiques), puis
reunies. Toutes les lignes portant la meme combinaison d'aires (quel que
soit l'ordre d'origine) se retrouvent ainsi avec la meme valeur canonique.

Ce script :
    - cree une backup du CSV source
    - reecrit le champ Aire_geographique_production avec les valeurs
      canonicalisees
    - produit un log des modifications (avant/apres) et des stats
    - n'impacte aucune autre colonne
"""

import csv
import os
import shutil
import unicodedata
from collections import Counter
from datetime import datetime

CSV_PATH = r"chemin_du_csv"

DELIMITER = ";"
SEPARATEUR_AIRES = "|"
ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
AIRE_COLUMN = "Aire_geographique_production"

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP_PATH = os.path.join(OUTPUT_DIR, f"BACKUP_{TIMESTAMP}_" + os.path.basename(CSV_PATH))
OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"lots_aire_canonicalisee_{TIMESTAMP}.csv")
LOG_MODIFS_PATH = os.path.join(OUTPUT_DIR, f"log_canonicalisation_aire_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_stats_canonicalisation_aire_{TIMESTAMP}.txt")


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


def canonicaliser(valeur_brute):
    """Decoupe sur "|", strip chaque fragment, trie alphabetiquement
    (insensible a la casse et aux diacritiques), reunit.
    Renvoie la valeur canonique."""
    if not valeur_brute or not valeur_brute.strip():
        return valeur_brute
    fragments = [f.strip() for f in valeur_brute.split(SEPARATEUR_AIRES) if f.strip()]
    if len(fragments) <= 1:
        return valeur_brute.strip()
    fragments_tries = sorted(fragments, key=_normalize)
    return SEPARATEUR_AIRES.join(fragments_tries)


def process():
    shutil.copy2(CSV_PATH, BACKUP_PATH)
    print(f"Backup cree : {BACKUP_PATH}")

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    col_map = resolve_columns({ID_COLUMN, CATALOG_COLUMN, AIRE_COLUMN}, fieldnames)
    id_col = col_map[ID_COLUMN]
    catalog_col = col_map[CATALOG_COLUMN]
    aire_col = col_map[AIRE_COLUMN]

    modifications = []          # (id_perenne, catalog_id, avant, apres)
    valeurs_avant = Counter()   # distribution avant
    valeurs_apres = Counter()   # distribution apres
    nb_inchangees = 0

    for row in rows:
        valeur_brute = (row.get(aire_col) or "").strip()
        valeurs_avant[valeur_brute] += 1

        valeur_canon = canonicaliser(valeur_brute)
        valeurs_apres[valeur_canon] += 1

        if valeur_canon != valeur_brute:
            id_perenne = (row.get(id_col) or "").strip()
            catalog_id = (row.get(catalog_col) or "").strip()
            modifications.append((id_perenne, catalog_id, valeur_brute, valeur_canon))
            row[aire_col] = valeur_canon
        else:
            nb_inchangees += 1

    # ---- Ecriture du CSV ----
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    # ---- Log des modifications ----
    with open(LOG_MODIFS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Log canonicalisation Aire_geographique_production - {TIMESTAMP}\n")
        f.write(f"Nombre de lignes modifiees : {len(modifications)}\n\n")
        for id_perenne, catalog_id, avant, apres in modifications:
            f.write(f"Id_perenne={id_perenne} ; catalogue={catalog_id}\n")
            f.write(f'  avant : "{avant}"\n')
            f.write(f'  apres : "{apres}"\n\n')

    # ---- Stats : valeurs distinctes avant/apres ----
    with open(LOG_STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques - canonicalisation Aire_geographique_production - {TIMESTAMP}\n")
        f.write(f"Fichier source : {CSV_PATH}\n")
        f.write(f"Backup         : {BACKUP_PATH}\n")
        f.write(f"CSV modifie    : {OUTPUT_CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes (hors entete)  : {len(rows)}\n")
        f.write(f"Lignes modifiees (ordre canonicalise) : {len(modifications)}\n")
        f.write(f"Lignes inchangees                     : {nb_inchangees}\n\n")
        f.write(f"Valeurs distinctes AVANT : {len(valeurs_avant)}\n")
        f.write(f"Valeurs distinctes APRES : {len(valeurs_apres)}\n")
        f.write(f"  (reduction de {len(valeurs_avant) - len(valeurs_apres)} doublon(s) d'ordre)\n\n")
        f.write("=== DISTRIBUTION DES VALEURS APRES CANONICALISATION ===\n")
        for valeur, nb in sorted(valeurs_apres.items(), key=lambda x: (-x[1], _normalize(x[0]))):
            f.write(f"  {nb:5d}  {valeur}\n")

    print("Traitement termine.")
    print(f"  Lignes modifiees : {len(modifications)}")
    print(f"  Valeurs distinctes : {len(valeurs_avant)} -> {len(valeurs_apres)} "
          f"(-{len(valeurs_avant) - len(valeurs_apres)} doublon(s) d'ordre)")
    print(f"  CSV modifie    : {OUTPUT_CSV_PATH}")
    print(f"  Log modifs     : {LOG_MODIFS_PATH}")
    print(f"  Log stats      : {LOG_STATS_PATH}")


if __name__ == "__main__":
    process()
