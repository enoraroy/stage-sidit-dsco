"""
Ajout automatique de la devise manquante dans le champ Estimation_lot.

Règles appliquées, pour chaque ligne :
    1. Champ vide                              -> rien à faire (ignoré).
    2. Champ contenant déjà une devise reconnue -> rien à faire (ignoré).
    3. Champ non vide, sans devise, sans chiffre -> cas particulier signalé,
       rien à faire (on ne sait pas s'il s'agit vraiment d'un prix).
    4. Champ non vide, sans devise, avec chiffre(s) :
        a. Si un caractère "bruité" (hors chiffres/devises/ponctuation
           autorisée) est présent -> rien à faire, ligne signalée.
        b. Sinon :
            - si Identifiant_catalogue figure dans MANUAL_CURRENCY_MAP
              (liste identifiée manuellement) -> devise ajoutée APRÈS la
              valeur.
            - sinon, on regarde les AUTRES lignes du même catalogue qui ont
              déjà une devise :
                * une seule devise distincte utilisée -> on l'applique.
                * plusieurs devises distinctes utilisées -> ambiguïté,
                  signalée, rien à faire.
                * aucune devise trouvée dans le reste du catalogue ->
                  impossible à deviner, signalé, rien à faire.

Une backup du CSV est créée avant toute modification.
"""

import csv
import os
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime

CSV_PATH = r"chemin_du_csv"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
ESTIMATION_COLUMN = "Estimation_lot"

CURRENCY_TOKENS = ["$", "EUR", "US$", "HK$", "GBP", "£", "€"]

# Caractères autorisés en plus des chiffres et des devises
ALLOWED_PUNCTUATION = {",", ".", "/", "-", "(", ")", "|", ";", " ", "\u00a0", "\n", "\r"}

# Catalogues dont la devise a été identifiée manuellement
MANUAL_CURRENCY_MAP = {

}

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP_PATH = os.path.join(OUTPUT_DIR, f"BACKUP_{TIMESTAMP}_" + os.path.basename(CSV_PATH))
OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"lots_devise_ajoutee_{TIMESTAMP}.csv")
LOG_AJOUTS_PATH = os.path.join(OUTPUT_DIR, f"log_ajouts_devise_{TIMESTAMP}.txt")
LOG_SIGNALEMENTS_PATH = os.path.join(OUTPUT_DIR, f"log_signalements_devise_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_stats_ajout_devise_{TIMESTAMP}.txt")

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


def extract_currencies(valeur):
    """Retourne l'ensemble des tokens de devise trouvés dans la valeur
    (élimination progressive des tokens les plus longs pour éviter les
    doublons du type '$' inclus dans 'US$')."""
    reste = valeur
    trouves = set()
    for token in sorted(CURRENCY_TOKENS, key=len, reverse=True):
        if token in reste:
            trouves.add(token)
            reste = reste.replace(token, "")
    return trouves


def caracteres_inattendus(valeur):
    """Caractères qui ne sont ni des chiffres, ni de la ponctuation
    autorisée, ni des tokens de devise (déjà supposés absents ici)."""
    reste = valeur
    for token in sorted(CURRENCY_TOKENS, key=len, reverse=True):
        reste = reste.replace(token, "")
    return sorted(set(c for c in reste if not (c.isdigit() or c in ALLOWED_PUNCTUATION)))


def contient_chiffre(valeur):
    return any(c.isdigit() for c in valeur)


def backup_csv():
    shutil.copy2(CSV_PATH, BACKUP_PATH)
    print(f"Backup créé : {BACKUP_PATH}")

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

    # ---- Pré-passe : devises déjà utilisées, par catalogue ----
    catalog_currency_sets = defaultdict(set)
    for row in rows:
        catalog_id = (row.get(catalog_col) or "").strip()
        valeur = row.get(estimation_col, "") or ""
        devises = extract_currencies(valeur)
        if devises:
            catalog_currency_sets[catalog_id] |= devises

    ajouts = []          # (id_perenne, catalog_id, ancienne, nouvelle, mode)
    signalements = defaultdict(list)  # raison -> [(id_perenne, catalog_id, valeur, detail)]

    for row in rows:
        id_perenne = (row.get(id_col) or "").strip()
        catalog_id = (row.get(catalog_col) or "").strip()
        valeur = row.get(estimation_col, "") or ""

        if valeur.strip() == "":
            continue  # règle 1 : champ vide -> rien à faire

        if extract_currencies(valeur):
            continue  # règle 2 : devise déjà présente -> rien à faire

        if not contient_chiffre(valeur):
            signalements["sans_chiffre"].append((id_perenne, catalog_id, valeur, ""))
            continue  # règle 3

        inattendus = caracteres_inattendus(valeur)
        if inattendus:
            signalements["bruit"].append((id_perenne, catalog_id, valeur, "".join(inattendus)))
            continue  # règle 4.a

        # règle 4.b : détermination de la devise
        if catalog_id in MANUAL_CURRENCY_MAP:
            devise = MANUAL_CURRENCY_MAP[catalog_id]
            mode = "manuel"
        else:
            devises_catalogue = catalog_currency_sets.get(catalog_id, set())
            if len(devises_catalogue) == 1:
                devise = next(iter(devises_catalogue))
                mode = "devine_unique"
            elif len(devises_catalogue) > 1:
                signalements["ambigu"].append(
                    (id_perenne, catalog_id, valeur, ", ".join(sorted(devises_catalogue)))
                )
                continue
            else:
                signalements["indevinable"].append((id_perenne, catalog_id, valeur, ""))
                continue

        nouvelle_valeur = valeur.rstrip() + devise
        row[estimation_col] = nouvelle_valeur
        ajouts.append((id_perenne, catalog_id, valeur, nouvelle_valeur, mode))

    # ---- Écriture du CSV modifié ----
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    # ---- Log des ajouts ----
    with open(LOG_AJOUTS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Log des ajouts de devise - {TIMESTAMP}\n")
        f.write(f"Nombre total d'ajouts : {len(ajouts)}\n\n")
        for id_perenne, catalog_id, ancienne, nouvelle, mode in ajouts:
            f.write(
                f'{id_perenne} ; {catalog_id} ; mode={mode} ; '
                f'"{ancienne}" -> "{nouvelle}"\n'
            )

    # ---- Log des signalements ----
    libelles = {
        "bruit": "Lignes ignorées (caractères inattendus détectés)",
        "ambigu": "Lignes ignorées (plusieurs devises différentes dans le catalogue)",
        "indevinable": "Lignes ignorées (aucune devise trouvée ailleurs dans le catalogue)",
        "sans_chiffre": "Lignes ignorées (aucun chiffre détecté dans le champ)",
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
        f.write(f"Statistiques - ajout de devise - {TIMESTAMP}\n")
        f.write(f"Fichier source : {CSV_PATH}\n")
        f.write(f"Backup         : {BACKUP_PATH}\n")
        f.write(f"CSV modifié    : {OUTPUT_CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes du fichier      : {len(rows)}\n")
        f.write(f"Nombre total de devises ajoutées        : {len(ajouts)}\n")
        ajouts_par_mode = Counter(mode for *_ , mode in ajouts)
        f.write(f"  dont devinées à partir du catalogue  : {ajouts_par_mode.get('devine_unique', 0)}\n")
        f.write(f"  dont via la liste manuelle           : {ajouts_par_mode.get('manuel', 0)}\n\n")
        for cle, libelle in libelles.items():
            f.write(f"{libelle} : {len(signalements.get(cle, []))}\n")

    print("Traitement terminé.")
    print(f"  CSV modifié     : {OUTPUT_CSV_PATH}")
    print(f"  Log ajouts      : {LOG_AJOUTS_PATH}")
    print(f"  Log signalements: {LOG_SIGNALEMENTS_PATH}")
    print(f"  Log stats       : {LOG_STATS_PATH}")


if __name__ == "__main__":
    process()
