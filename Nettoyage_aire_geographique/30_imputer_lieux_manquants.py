"""
Imputation automatique de l'Aire_geographique_production lorsque celle-ci
vaut "origine inconnue", à partir de Region_lieu_production.

Deux sources sont utilisées, dans cet ordre de PRIORITÉ :
    1. Le thésaurus externe (thesaurus_lieux.csv, colonnes
       "Terme candidat" ; "Si") -> priorité ABSOLUE. "Terme candidat" est
       l'aire géographique à assigner, "Si" est la région/le lieu qui
       déclenche cette assignation.
    2. À défaut, une correspondance déduite du CSV lui-même : pour chaque
       région déjà associée ailleurs à une (ou plusieurs) aire(s)
       géographique(s) renseignée(s) (différente de "origine inconnue"),
       on regarde si une seule aire distincte est utilisée pour cette
       région.

Règles :
    1. Aire_geographique_production != "origine inconnue" -> rien à faire.
    2. Region_lieu_production vide                         -> rien à faire
       (pas de log).
    3. Region trouvée dans le thésaurus -> imputation directe (priorité
       absolue, même si le CSV suggère autre chose).
    4. Sinon, région retrouvée dans le CSV avec UNE SEULE aire distincte
       associée ailleurs -> imputation.
    5. Sinon, région retrouvée dans le CSV avec PLUSIEURS aires distinctes
       associées ailleurs -> signalée, PAS imputée.
    6. Sinon (région introuvable dans le thésaurus ET dans le CSV) ->
       signalée comme "non reconnue", PAS imputée : à trancher
       manuellement (récapitulatif dédupliqué fourni pour faciliter
       l'arbitrage).

Une backup du CSV principal est créée avant toute modification. Le
thésaurus n'est jamais modifié.
"""

import csv
import os
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime

CSV_PATH = r"chemin_du_csv"

THESAURUS_PATH = r"chemin_thesaurus_lieux.csv"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
AIRE_COLUMN = "Aire_geographique_production"
REGION_COLUMN = "Region_lieu_production"

THESAURUS_COL_TERME = "Terme candidat"
THESAURUS_COL_SI = "Si"

# Valeur exacte considérée comme "à imputer" (comparaison stricte)
VALEUR_INCONNUE = "Origine inconnue"

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP_PATH = os.path.join(OUTPUT_DIR, f"BACKUP_{TIMESTAMP}_" + os.path.basename(CSV_PATH))
OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"lots_aire_imputee_{TIMESTAMP}.csv")
LOG_IMPUTATIONS_PATH = os.path.join(OUTPUT_DIR, f"log_imputations_aire_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_stats_aire_{TIMESTAMP}.txt")

# Fichiers "à compléter" : une ligne par région (dédupliquée), avec une
# colonne vide à remplir à la main. Un script suivant (18) lira ces
# fichiers une fois complétés pour appliquer les décisions.
A_COMPLETER_NON_RECONNUES_PATH = os.path.join(OUTPUT_DIR, f"a_completer_regions_non_reconnues_{TIMESTAMP}.csv")
A_COMPLETER_AMBIGUES_PATH = os.path.join(OUTPUT_DIR, f"a_completer_regions_ambigues_{TIMESTAMP}.csv")
COLONNE_A_REMPLIR = "Aire_a_appliquer"


def _normalize(nom):
    s = unicodedata.normalize("NFKD", nom)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def resolve_columns(expected_columns, fieldnames, label=""):
    normalized_real = {_normalize(f): f for f in fieldnames}
    resolved = {}
    unresolved = []

    for col in expected_columns:
        if col in fieldnames:
            resolved[col] = col
            continue
        match = normalized_real.get(_normalize(col))
        if match:
            print(f"[ATTENTION]{label} Colonne \"{col}\" absente telle quelle ; "
                  f"correspondance trouvée avec la colonne réelle \"{match}\". "
                  f"Utilisation de \"{match}\".")
            resolved[col] = match
        else:
            unresolved.append(col)

    if unresolved:
        raise ValueError(
            f"Colonnes attendues introuvables{label} (même approximativement) : "
            + ", ".join(unresolved)
            + "\nColonnes disponibles : " + ", ".join(fieldnames)
        )
    return resolved


def backup_csv():
    shutil.copy2(CSV_PATH, BACKUP_PATH)
    print(f"Backup créé : {BACKUP_PATH}")

def charger_thesaurus(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        col_map = resolve_columns(
            {THESAURUS_COL_TERME, THESAURUS_COL_SI}, fieldnames, label=" (thésaurus)"
        )
        col_terme = col_map[THESAURUS_COL_TERME]
        col_si = col_map[THESAURUS_COL_SI]
        rows = list(reader)

    thesaurus = {}
    conflits = defaultdict(set)
    for row in rows:
        region = (row.get(col_si) or "").strip()
        terme = (row.get(col_terme) or "").strip()
        if not region or not terme:
            continue
        if region in thesaurus and thesaurus[region] != terme:
            conflits[region].add(thesaurus[region])
            conflits[region].add(terme)
        else:
            thesaurus[region] = terme

    if conflits:
        print("[ATTENTION] Conflits internes détectés dans le thésaurus (région -> plusieurs termes candidats) :")
        for region, termes in conflits.items():
            print(f"    {region} : {', '.join(sorted(termes))}")
            thesaurus.pop(region, None)  # entrée ambiguë retirée, non utilisée pour l'imputation

    return thesaurus, conflits


def process():
    backup_csv()

    thesaurus, conflits_thesaurus = charger_thesaurus(THESAURUS_PATH)
    print(f"Thésaurus chargé : {len(thesaurus)} correspondance(s) région -> aire géographique.")

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    col_map = resolve_columns(
        {ID_COLUMN, CATALOG_COLUMN, AIRE_COLUMN, REGION_COLUMN}, fieldnames
    )
    id_col = col_map[ID_COLUMN]
    catalog_col = col_map[CATALOG_COLUMN]
    aire_col = col_map[AIRE_COLUMN]
    region_col = col_map[REGION_COLUMN]

    # ---- Pré-passe : correspondances région -> aires distinctes, déduites du CSV ----
    region_vers_aires = defaultdict(set)
    for row in rows:
        aire = (row.get(aire_col) or "").strip()
        region = (row.get(region_col) or "").strip()
        if region and aire and aire != VALEUR_INCONNUE:
            region_vers_aires[region].add(aire)

    imputations = []       # (id_perenne, catalog_id, region, aire_imputee, source)
    regions_ambigues = defaultdict(lambda: {"aires": set(), "count": 0})  # region -> {aires, count}
    regions_non_reconnues = Counter()  # region -> nb de lignes concernées

    for row in rows:
        id_perenne = (row.get(id_col) or "").strip()
        catalog_id = (row.get(catalog_col) or "").strip()
        aire = (row.get(aire_col) or "").strip()
        region = (row.get(region_col) or "").strip()

        if aire != VALEUR_INCONNUE:
            continue  # règle 1

        if region == "":
            continue  # règle 2 : rien à faire, pas de log

        # règle 3 : priorité absolue au thésaurus
        if region in thesaurus:
            aire_imputee = thesaurus[region]
            row[aire_col] = aire_imputee
            imputations.append((id_perenne, catalog_id, region, aire_imputee, "thesaurus"))
            continue

        # règle 4/5 : déduction à partir du CSV
        aires_possibles = region_vers_aires.get(region, set())
        if len(aires_possibles) == 1:
            aire_imputee = next(iter(aires_possibles))
            row[aire_col] = aire_imputee
            imputations.append((id_perenne, catalog_id, region, aire_imputee, "deduit_csv"))
            continue
        elif len(aires_possibles) > 1:
            regions_ambigues[region]["aires"] |= aires_possibles
            regions_ambigues[region]["count"] += 1
            continue

        # règle 6 : région introuvable partout
        regions_non_reconnues[region] += 1

    # ---- Écriture du CSV modifié ----
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    # ---- Log des imputations ----
    with open(LOG_IMPUTATIONS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Log des imputations d'aire géographique - {TIMESTAMP}\n")
        f.write(f"Nombre total d'imputations : {len(imputations)}\n\n")
        for id_perenne, catalog_id, region, aire_imputee, source in imputations:
            f.write(
                f'{id_perenne} ; {catalog_id} ; region="{region}" ; '
                f'aire_imputee="{aire_imputee}" ; source={source}\n'
            )

    # ---- Fichier à compléter : régions non reconnues (dédupliqué) ----
    # Une ligne par région distincte, triée par nombre de lignes concernées
    # décroissant (pour prioriser). Remplir la colonne "Aire_a_appliquer"
    # puis passer le fichier au script 18 pour application.
    with open(A_COMPLETER_NON_RECONNUES_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=DELIMITER)
        writer.writerow([REGION_COLUMN, "Nb_lignes_concernees", COLONNE_A_REMPLIR])
        for region, n in regions_non_reconnues.most_common():
            writer.writerow([region, n, ""])

    # ---- Fichier à compléter : régions ambiguës (dédupliqué) ----
    # "Aires_trouvees_dans_csv" est fourni à titre indicatif (les aires déjà
    # associées ailleurs à cette région) ; la colonne "Aire_a_appliquer" est
    # à remplir avec le choix final, qui peut différer de la liste indicative.
    with open(A_COMPLETER_AMBIGUES_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=DELIMITER)
        writer.writerow([REGION_COLUMN, "Aires_trouvees_dans_csv", "Nb_lignes_concernees", COLONNE_A_REMPLIR])
        lignes_ambigues = sorted(
            regions_ambigues.items(), key=lambda item: item[1]["count"], reverse=True
        )
        for region, info in lignes_ambigues:
            writer.writerow([region, ", ".join(sorted(info["aires"])), info["count"], ""])

    if conflits_thesaurus:
        print("[ATTENTION] Conflits internes détectés dans le thésaurus (voir sortie ci-dessus) — "
              "ces régions ne sont couvertes par aucune imputation automatique et n'apparaissent "
              "dans aucun des deux fichiers à compléter ; ajoute-les toi-même si besoin.")

    # ---- Statistiques ----
    with open(LOG_STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques - imputation aire géographique - {TIMESTAMP}\n")
        f.write(f"Fichier source    : {CSV_PATH}\n")
        f.write(f"Thésaurus utilisé : {THESAURUS_PATH}\n")
        f.write(f"Backup            : {BACKUP_PATH}\n")
        f.write(f"CSV modifié       : {OUTPUT_CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes du fichier             : {len(rows)}\n")
        f.write(f"Nombre total d'imputations                     : {len(imputations)}\n")
        imputations_par_source = Counter(source for *_, source in imputations)
        f.write(f"  dont via le thésaurus (priorité absolue)    : {imputations_par_source.get('thesaurus', 0)}\n")
        f.write(f"  dont déduites du CSV (aire unique associée) : {imputations_par_source.get('deduit_csv', 0)}\n\n")
        nb_lignes_ambigues = sum(info["count"] for info in regions_ambigues.values())
        nb_lignes_non_reconnues = sum(regions_non_reconnues.values())
        f.write(f"Lignes signalées (régions ambiguës)            : {nb_lignes_ambigues}\n")
        f.write(f"  dont régions distinctes ambiguës             : {len(regions_ambigues)}\n")
        f.write(f"Lignes signalées (régions non reconnues)       : {nb_lignes_non_reconnues}\n")
        f.write(f"  dont régions distinctes non reconnues        : {len(regions_non_reconnues)}\n")
        if conflits_thesaurus:
            f.write(f"\nConflits internes détectés dans le thésaurus (ignorés) : {len(conflits_thesaurus)} région(s)\n")
            for region, termes in conflits_thesaurus.items():
                f.write(f'  "{region}" : {", ".join(sorted(termes))}\n')

    print("Traitement terminé.")
    print(f"  CSV modifié                : {OUTPUT_CSV_PATH}")
    print(f"  Log imputations            : {LOG_IMPUTATIONS_PATH}")
    print(f"  À compléter (non reconnues): {A_COMPLETER_NON_RECONNUES_PATH}")
    print(f"  À compléter (ambiguës)     : {A_COMPLETER_AMBIGUES_PATH}")
    print(f"  Log stats                  : {LOG_STATS_PATH}")


if __name__ == "__main__":
    process()
