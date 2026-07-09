"""
Normalisation des cellules Estimation_lot à DEVISE UNIQUE (monnaie isolée
des valeurs, séparateurs uniformisés).

Étape 1/2 du chantier de normalisation : ce script ne traite QUE les
cellules qui contiennent une seule et même devise. Les cellules
multi-devises sont repérées mais laissées telles quelles (traitement prévu
dans un second script).

Règles appliquées à chaque ligne :
    1. Champ vide                                -> ignoré (pas de log).
    2. Champ "bruité" (caractère hors chiffres,   -> ignoré, signalé.
       devises reconnues, ponctuation autorisée -
       même règle que les scripts précédents)
    3. Aucune devise reconnue                     -> ignoré, signalé.
    4. Plusieurs devises différentes détectées     -> ignoré, signalé
       (sera traité dans le script "multi-devises").
    5. Une seule devise détectée :
        a. Les tokens de devise sont isolés (remplacés par un espace, pour
           ne pas fusionner accidentellement deux nombres qui n'étaient
           séparés que par la devise elle-même, ex. "£1,500£2000").
        b. Les séparateurs de milliers (virgule, point, espace suivis de
           exactement 3 chiffres) sont supprimés — les décimales
           (ex. "1.2") sont préservées.
        c. Les nombres restants sont extraits.
            - 1 nombre  -> "{devise}{valeur}"
            - 2 nombres -> "{devise}{valeur1}-{devise}{valeur2}"
            - 0 ou 3+   -> ignoré, signalé (cas trop complexe).

La devise de sortie est normalisée sur un symbole canonique :
    US$, $        -> $
    GBP, £        -> £
    EUR, €        -> €
    HK$           -> HK$ (inchangé, pour ne pas le confondre avec $ seul)

Une backup du CSV est créée avant toute modification.
"""

import csv
import os
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime

CSV_PATH = r"chemin_du_csv_avec_devises"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
ESTIMATION_COLUMN = "Estimation_lot"

CURRENCY_TOKEN_TO_SYMBOL = {
    "HK$": "HK$",
    "GBP": "£",
    "EUR": "€",
    "US$": "$",
    "£": "£",
    "€": "€",
    "$": "$",
}
# Ordre de reconnaissance : les tokens les plus longs d'abord (pour que
# "US$"/"HK$" soient repérés avant le "$" isolé qu'ils contiennent).
CURRENCY_TOKENS_SORTED = sorted(CURRENCY_TOKEN_TO_SYMBOL, key=len, reverse=True)

ALLOWED_PUNCTUATION = {",", ".", "/", "-", "(", ")", "|", ";", " ", "\u00a0", "\n", "\r", "–", "\u0008", "\u0009"}

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP_PATH = os.path.join(OUTPUT_DIR, f"BACKUP_{TIMESTAMP}_" + os.path.basename(CSV_PATH))
OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"lots_prix_uniformises_monodevise_{TIMESTAMP}.csv")
LOG_REFORMATAGES_PATH = os.path.join(OUTPUT_DIR, f"log_reformatages_prix_{TIMESTAMP}.txt")
LOG_SIGNALEMENTS_PATH = os.path.join(OUTPUT_DIR, f"log_signalements_prix_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_stats_prix_{TIMESTAMP}.txt")

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


def extract_currency_symbols(valeur):
    """Retourne l'ensemble des SYMBOLES CANONIQUES de devise détectés dans
    la valeur (élimination progressive des tokens les plus longs pour
    éviter les faux doublons du type '$' inclus dans 'US$')."""
    reste = valeur
    symboles = set()
    for token in CURRENCY_TOKENS_SORTED:
        if token in reste:
            symboles.add(CURRENCY_TOKEN_TO_SYMBOL[token])
            reste = reste.replace(token, "")
    return symboles


def caracteres_inattendus(valeur):
    reste = valeur
    for token in CURRENCY_TOKENS_SORTED:
        reste = reste.replace(token, "")
    return sorted(set(c for c in reste if not (c.isdigit() or c in ALLOWED_PUNCTUATION)))


def isoler_devise(valeur):
    """Remplace chaque occurrence d'un token de devise par un espace (et
    non une chaîne vide), pour ne pas fusionner deux nombres qui n'étaient
    séparés que par la devise elle-même (ex. '£1,500£2000')."""
    reste = valeur
    for token in CURRENCY_TOKENS_SORTED:
        reste = reste.replace(token, " ")
    return reste


def nettoyer_separateurs_milliers(texte):
    """Supprime les séparateurs de milliers (virgule, point, espace, espace
    insécable) suivis d'exactement 3 chiffres non suivis d'un autre
    chiffre. Les décimales (ex. '1.2') ne sont pas affectées, car elles ne
    comportent pas 3 chiffres après le séparateur."""
    resultat = texte
    for _ in range(3):
        resultat = re.sub(r"(\d)[,.\s\u00a0](\d{3})(?!\d)", r"\1\2", resultat)
    return resultat


NUMERO_REGEX = re.compile(r"\d+(?:\.\d+)?")

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

    reformatages = []  # (id_perenne, catalog_id, ancienne, nouvelle)
    signalements = defaultdict(list)  # raison -> [(id_perenne, catalog_id, valeur, detail)]

    for row in rows:
        id_perenne = (row.get(id_col) or "").strip()
        catalog_id = (row.get(catalog_col) or "").strip()
        valeur = row.get(estimation_col, "") or ""

        if valeur.strip() == "":
            continue  # règle 1 : vide -> ignoré, pas de log

        if caracteres_inattendus(valeur):
            signalements["bruit"].append((id_perenne, catalog_id, valeur, ""))
            continue  # règle 2

        symboles = extract_currency_symbols(valeur)

        if len(symboles) == 0:
            signalements["sans_devise"].append((id_perenne, catalog_id, valeur, ""))
            continue  # règle 3

        if len(symboles) > 1:
            signalements["multi_devises"].append(
                (id_perenne, catalog_id, valeur, ", ".join(sorted(symboles)))
            )
            continue  # règle 4 : traité dans un script séparé

        # règle 5 : devise unique
        symbole = next(iter(symboles))
        isole = isoler_devise(valeur)
        nettoye = nettoyer_separateurs_milliers(isole)
        nombres = NUMERO_REGEX.findall(nettoye)

        if len(nombres) == 0:
            signalements["aucun_nombre"].append((id_perenne, catalog_id, valeur, ""))
            continue
        if len(nombres) > 2:
            signalements["trop_de_nombres"].append(
                (id_perenne, catalog_id, valeur, f"{len(nombres)} nombres : {nombres}")
            )
            continue

        if len(nombres) == 2:
            nouvelle_valeur = f"{symbole}{nombres[0]}-{symbole}{nombres[1]}"
        else:
            nouvelle_valeur = f"{symbole}{nombres[0]}"

        row[estimation_col] = nouvelle_valeur
        reformatages.append((id_perenne, catalog_id, valeur, nouvelle_valeur))

    # ---- Écriture du CSV modifié ----
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    # ---- Log des reformatages ----
    with open(LOG_REFORMATAGES_PATH, "w", encoding="utf-8") as f:
        f.write(f"Log des reformatages (devise unique) - {TIMESTAMP}\n")
        f.write(f"Nombre total de reformatages : {len(reformatages)}\n\n")
        for id_perenne, catalog_id, ancienne, nouvelle in reformatages:
            ancienne_clean = ancienne.replace("\n", " ").replace("\r", " ").strip()
            f.write(f'{id_perenne} ; {catalog_id} ; "{ancienne_clean}" -> "{nouvelle}"\n')

    # ---- Log des signalements ----
    libelles = {
        "bruit": "Lignes ignorées (caractères inattendus détectés)",
        "sans_devise": "Lignes ignorées (aucune devise reconnue)",
        "multi_devises": "Lignes ignorées (plusieurs devises différentes - à traiter séparément)",
        "aucun_nombre": "Lignes ignorées (aucun nombre exploitable trouvé)",
        "trop_de_nombres": "Lignes ignorées (plus de 2 nombres trouvés - cas trop complexe)",
    }
    with open(LOG_SIGNALEMENTS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Log des signalements - lignes NON modifiées - {TIMESTAMP}\n\n")
        for cle, libelle in libelles.items():
            liste = signalements.get(cle, [])
            f.write(f"--- {libelle} ({len(liste)}) ---\n")
            for id_perenne, catalog_id, valeur, detail in liste:
                valeur_clean = valeur.replace("\n", " ").replace("\r", " ").strip()
                if detail:
                    f.write(f'{id_perenne} ; {catalog_id} ; "{valeur_clean}" ; détail : {detail}\n')
                else:
                    f.write(f'{id_perenne} ; {catalog_id} ; "{valeur_clean}"\n')
            f.write("\n")

    # ---- Statistiques ----
    with open(LOG_STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques - uniformisation des prix (devise unique) - {TIMESTAMP}\n")
        f.write(f"Fichier source : {CSV_PATH}\n")
        f.write(f"Backup         : {BACKUP_PATH}\n")
        f.write(f"CSV modifié    : {OUTPUT_CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes du fichier : {len(rows)}\n")
        f.write(f"Nombre total de reformatages       : {len(reformatages)}\n\n")
        for cle, libelle in libelles.items():
            f.write(f"{libelle} : {len(signalements.get(cle, []))}\n")

    print("Traitement terminé.")
    print(f"  CSV modifié      : {OUTPUT_CSV_PATH}")
    print(f"  Log reformatages : {LOG_REFORMATAGES_PATH}")
    print(f"  Log signalements : {LOG_SIGNALEMENTS_PATH}")
    print(f"  Log stats        : {LOG_STATS_PATH}")


if __name__ == "__main__":
    process()
