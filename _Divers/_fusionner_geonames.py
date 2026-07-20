"""
Fusion de Pays_vente_ou_demande et Ville_vente_ou_demande en une seule
colonne lieu_vente_ou_demande contenant les URIs GeoNames des villes.

Regles :
    - La colonne lieu_vente_ou_demande est INSEREE a la place des deux
      colonnes source (Pays et Ville), qui sont SUPPRIMEES.
    - Si la cellule Ville contient plusieurs valeurs separees par une
      virgule (ex. "San Francisco, New York"), chaque ville est
      resolue independamment vers son URI GeoNames, et les URIs sont
      reunies dans la cellule de sortie separees par "|".
    - Si une ville n'est pas reconnue dans la table de correspondance,
      la valeur brute est conservee telle quelle (ni URI ni perte de
      donnee), et la ligne est loguee pour verification manuelle.
    - Si la cellule Ville est vide, la colonne lieu_vente_ou_demande
      reste vide (Pays seul n'est pas resolu en URI de ville).
"""

import csv
import os
import unicodedata
from datetime import datetime


CSV_PATH = r"C:\Users\Enora\Documents\Université\Stage M1-M2\Docus_travail\Docus_travail_2\Programmes\output\lots_epoque_autre_supprime_20260716_110709.csv"

DELIMITER = ";"

PAYS_COLUMN = "Pays_vente_ou_demande"
VILLE_COLUMN = "Ville_vente_ou_demande"
NOUVELLE_COLUMN = "lieu_vente_ou_demande"

SEPARATEUR_VILLES_ENTREE = ","
SEPARATEUR_URIS_SORTIE = "|"

# Table de correspondance ville (normalisee) -> URI GeoNames
# La cle est la valeur normalisee (minuscules, sans diacritiques, strippee)
# pour absorber les variations de casse ou d'accentuation dans le CSV.
GEONAMES = {
    "cologne":           "https://www.geonames.org/2886242/koeln.html",
    "londres":           "https://www.geonames.org/2643743/london.html",
    "los angeles":       "https://www.geonames.org/5368361/los-angeles.html",
    "neuilly-sur-seine": "https://www.geonames.org/2990611/neuilly-sur-seine.html",
    "new york":          "https://www.geonames.org/5128581/new-york-city.html",
    "paris":             "https://www.geonames.org/2988507/paris.html",
    "san francisco":     "https://www.geonames.org/5391959/san-francisco.html",
}

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"lots_lieu_vente_geonames_{TIMESTAMP}.csv")
LOG_NON_RESOLUS_PATH = os.path.join(OUTPUT_DIR, f"log_villes_non_resolues_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_stats_lieu_vente_{TIMESTAMP}.txt")

def _normalize_colname(nom):
    s = unicodedata.normalize("NFKD", nom)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _normalize_ville(valeur):
    """Normalise une valeur de ville pour la comparer a la table GEONAMES."""
    s = unicodedata.normalize("NFKD", valeur)
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


def resoudre_ville(ville_brute):
    """Renvoie (uri_ou_valeur_brute, resolu: bool)."""
    uri = GEONAMES.get(_normalize_ville(ville_brute))
    if uri:
        return uri, True
    return ville_brute, False

def process():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    col_map = resolve_columns({PAYS_COLUMN, VILLE_COLUMN}, fieldnames)
    pays_col = col_map[PAYS_COLUMN]
    ville_col = col_map[VILLE_COLUMN]

    # Construction des nouveaux fieldnames :
    # la nouvelle colonne remplace les deux colonnes source, a la position
    # de la premiere des deux (Pays ou Ville, selon laquelle arrive en premier)
    idx_pays = fieldnames.index(pays_col)
    idx_ville = fieldnames.index(ville_col)
    idx_insertion = min(idx_pays, idx_ville)

    colonnes_a_supprimer = {pays_col, ville_col}
    nouveaux_fieldnames = []
    insere = False
    for col in fieldnames:
        if col in colonnes_a_supprimer:
            if not insere:
                nouveaux_fieldnames.append(NOUVELLE_COLUMN)
                insere = True
            # sinon : deuxieme colonne supprimee, on ne l'ajoute pas
        else:
            nouveaux_fieldnames.append(col)

    nb_lignes_resolues = 0
    nb_lignes_partielles = 0
    nb_lignes_ville_vide = 0
    nb_uris_total = 0
    non_resolus = []  # (numero_ligne, id_perenne, ville_brute)

    for numero_ligne, row in enumerate(rows, start=2):
        ville_brute = (row.get(ville_col) or "").strip()

        if ville_brute == "":
            row[NOUVELLE_COLUMN] = ""
            nb_lignes_ville_vide += 1
        else:
            fragments = [v.strip() for v in ville_brute.split(SEPARATEUR_VILLES_ENTREE) if v.strip()]
            uris = []
            nb_non_resolus_ligne = 0
            for fragment in fragments:
                uri, resolu = resoudre_ville(fragment)
                uris.append(uri)
                if resolu:
                    nb_uris_total += 1
                else:
                    nb_non_resolus_ligne += 1
                    id_perenne = (row.get("Id_perenne") or "").strip()
                    non_resolus.append((numero_ligne, id_perenne, fragment))

            row[NOUVELLE_COLUMN] = SEPARATEUR_URIS_SORTIE.join(uris)

            if nb_non_resolus_ligne == 0:
                nb_lignes_resolues += 1
            else:
                nb_lignes_partielles += 1

        # suppression des colonnes source de la ligne
        for col in colonnes_a_supprimer:
            if col in row:
                del row[col]

    # ---- Ecriture du CSV modifie ----
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=nouveaux_fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    # ---- Log des villes non resolues ----
    with open(LOG_NON_RESOLUS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Villes non resolues (valeur brute conservee telle quelle) - {TIMESTAMP}\n")
        f.write(f"Nombre : {len(non_resolus)}\n\n")
        for numero_ligne, id_perenne, ville in non_resolus:
            f.write(f"ligne {numero_ligne} ; Id_perenne={id_perenne} ; ville=\"{ville}\"\n")

    # ---- Statistiques ----
    with open(LOG_STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques - fusion lieu_vente_ou_demande - {TIMESTAMP}\n")
        f.write(f"Fichier source : {CSV_PATH}\n")
        f.write(f"CSV modifie    : {OUTPUT_CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes (hors entete) : {len(rows)}\n")
        f.write(f"Lignes avec Ville vide                : {nb_lignes_ville_vide}\n")
        f.write(f"Lignes entierement resolues en URI    : {nb_lignes_resolues}\n")
        f.write(f"Lignes partiellement non resolues     : {nb_lignes_partielles}\n")
        f.write(f"Total URIs GeoNames inserees          : {nb_uris_total}\n")
        f.write(f"Total villes non resolues (log)       : {len(non_resolus)}\n\n")
        f.write("Table de correspondance utilisee :\n")
        for ville_norm, uri in GEONAMES.items():
            f.write(f"  {ville_norm} -> {uri}\n")

    print("Traitement termine.")
    print(f"  Lignes resolues : {nb_lignes_resolues}")
    print(f"  Lignes partiellement non resolues : {nb_lignes_partielles}")
    print(f"  Villes non resolues : {len(non_resolus)}")
    print(f"  CSV modifie : {OUTPUT_CSV_PATH}")
    print(f"  Log non resolus : {LOG_NON_RESOLUS_PATH}")
    print(f"  Log stats : {LOG_STATS_PATH}")


if __name__ == "__main__":
    process()
