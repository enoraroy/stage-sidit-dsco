#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nettoyage automatisé du CSV de catalogues de vente.

Étapes effectuées :
    1. Backup du CSV original (avant toute opération).
    2. Remplacement STRICT (comparaison exacte, sans regex) des valeurs
       "non renseignées / non spécifiées / non précisées" par une chaîne vide,
       avec traçabilité complète par Id_perenne dans un fichier txt.
    3. Détection des lignes où Inscription_booleen = "Non" alors que des
       champs d'inscription contiennent quand même une valeur -> écriture
       des Id_perenne + valeurs concernées dans un fichier txt dédié.
    4. Génération de compteurs / statistiques dans un fichier txt dédié.

Le CSV nettoyé, ainsi que les 3 fichiers txt (modifications, incohérences,
statistiques) et la backup, sont écrits dans le même dossier que le CSV
source, avec un horodatage commun pour retrouver facilement un lot d'outputs.
"""

import csv
import os
import shutil
import unicodedata
from collections import Counter
from datetime import datetime

CSV_PATH = r"chemin_du_csv"

DELIMITER = ";"
ID_COLUMN = "Id_perenne"
BOOL_COLUMN = "Inscription_booleen"

# Champs d'inscription à vérifier pour la détection d'incohérence
# (Inscription_booleen = "Non" mais champ renseigné quand même)
INSCRIPTION_FIELDS = [
    "Inscription_nature",
    "Inscription_langue",
    "Inscription_ecriture",
    "Inscription_transcription",
    "Inscription_transliterration",
    "Inscription_traduction",
]

# Champ -> liste des valeurs STRICTES (comparaison exacte) à vider
FIELDS_TO_CLEAN = {
    "Epoque_periode_dynastie": ["Non précisée"],
    "Materiaux": ["Non spécifiés"],
    "Techniques": ["Non spécifiés"],
    "Provenance": ["Non précisée", "Non spécifié", "Non spécifiée", "Non spécifiés"],
    "Inscription_langue": ["Non précisée"],
    "Inscription_ecriture": ["Non précisé"],
    "Inscription_transcription": ["non déchiffré", "Non précisée"],
    "Inscription_transliterration": ["Non précisée"],
    "Inscription_traduction": ["Non précisée"],
    "Mentions_oeuvres_comparaison": ["Non précisée"],
    "Inscription_nature" : ["Non précisée"],
    "Date_complete" : ["Non précisée", "Non spécifiée", "non daté", "Daté (date non spécifiée)", "Non indiquée", "Siècle non spécifié", "Date non spécifiée"],
    "Region_lieu_production" : ["Non précisée"]
}

# Valeurs considérées comme "vides" UNIQUEMENT pour la détection d'incohérence
# (pas de nettoyage/vidage réel dans le CSV) sur des champs qui ne sont pas
# dans FIELDS_TO_CLEAN mais qui contiennent des valeurs par défaut non pertinentes.
NEUTRAL_VALUES_FOR_DETECTION = {
    "Inscription_nature": ["Non précisée"],
}

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP_PATH = os.path.join(OUTPUT_DIR, f"BACKUP_{TIMESTAMP}_" + os.path.basename(CSV_PATH))
OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"lots_nettoyes_{TIMESTAMP}.csv")
LOG_MODIFICATIONS_PATH = os.path.join(OUTPUT_DIR, f"log_modifications_{TIMESTAMP}.txt")
LOG_INCOHERENCES_PATH = os.path.join(OUTPUT_DIR, f"log_incoherences_inscription_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_statistiques_{TIMESTAMP}.txt")


def _normalize(nom):
    """Normalise un nom de colonne (minuscules, sans accents) pour la
    détection de correspondance approximative en cas de faute de frappe
    dans l'en-tête réel du CSV."""
    s = unicodedata.normalize("NFKD", nom)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def resolve_columns(expected_columns, fieldnames):
    """Vérifie que chaque colonne attendue existe exactement dans l'en-tête.
    Si une colonne est absente, tente de retrouver la colonne réelle par
    correspondance normalisée (accents/casse) et prévient l'utilisateur.
    Retourne un dict {colonne_attendue: colonne_reelle}."""
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


# ------------------------------------------------------------------
# TRAITEMENT PRINCIPAL
# ------------------------------------------------------------------

def process():
    backup_csv()

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Résolution robuste des noms de colonnes attendus vs colonnes réelles
    all_expected = set(FIELDS_TO_CLEAN) | set(INSCRIPTION_FIELDS) | {ID_COLUMN, BOOL_COLUMN}
    col_map = resolve_columns(all_expected, fieldnames)

    id_col = col_map[ID_COLUMN]
    bool_col = col_map[BOOL_COLUMN]

    modifications_log = []          # (id_perenne, champ, ancienne_valeur)
    field_mod_counter = Counter()   # champ -> nb de valeurs vidées
    rows_with_any_mod = set()

    incoherences_log = []           # (id_perenne, {champ: valeur})
    incoherence_rows = 0

    # ---- PASSE 1 : nettoyage strict de TOUTES les lignes ----
    for row in rows:
        id_perenne = (row.get(id_col) or "").strip()
        for champ_attendu, valeurs_strictes in FIELDS_TO_CLEAN.items():
            champ_reel = col_map[champ_attendu]
            valeur_actuelle = row.get(champ_reel, "")
            if valeur_actuelle in valeurs_strictes:
                modifications_log.append((id_perenne, champ_reel, valeur_actuelle))
                field_mod_counter[champ_reel] += 1
                rows_with_any_mod.add(id_perenne)
                row[champ_reel] = ""

    # ---- PASSE 2 : détection d'incohérence, APRÈS nettoyage ----
    # (les rows sont déjà nettoyées ci-dessus, donc les champs vidés par la
    # passe 1 ne peuvent plus générer de faux positifs ici)
    for row in rows:
        id_perenne = (row.get(id_col) or "").strip()
        bool_val = (row.get(bool_col) or "").strip()
        if bool_val.lower() != "non":
            continue

        valeurs_presentes = {}
        for champ_attendu in INSCRIPTION_FIELDS:
            champ_reel = col_map[champ_attendu]
            v = row.get(champ_reel, "")
            if v is None or v.strip() == "":
                continue
            # Valeurs neutres : traitées comme vides pour la détection
            # uniquement (elles ne sont pas vidées dans le CSV de sortie).
            if v in NEUTRAL_VALUES_FOR_DETECTION.get(champ_attendu, []):
                continue
            valeurs_presentes[champ_reel] = v

        if valeurs_presentes:
            incoherences_log.append((id_perenne, valeurs_presentes))
            incoherence_rows += 1

    # --- Écriture du CSV nettoyé ---
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    # --- Écriture du log des modifications ---
    with open(LOG_MODIFICATIONS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Log des modifications - {TIMESTAMP}\n")
        f.write(f"Nombre total de modifications : {len(modifications_log)}\n\n")
        for id_perenne, champ, ancienne_valeur in modifications_log:
            f.write(f'{id_perenne} ; {champ} ; valeur supprimée : "{ancienne_valeur}"\n')

    # --- Écriture du log des incohérences ---
    with open(LOG_INCOHERENCES_PATH, "w", encoding="utf-8") as f:
        f.write(f"Log des incohérences (Inscription_booleen = Non, mais champ(s) renseigné(s)) - {TIMESTAMP}\n")
        f.write(f"Nombre de lignes concernées : {incoherence_rows}\n\n")
        for id_perenne, valeurs in incoherences_log:
            f.write(f"{id_perenne} :\n")
            for champ, v in valeurs.items():
                v_clean = v.replace("\n", " ").replace("\r", " ").strip()
                f.write(f'    {champ} = "{v_clean}"\n')
            f.write("\n")

    # --- Écriture des statistiques ---
    with open(LOG_STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques de nettoyage - {TIMESTAMP}\n")
        f.write(f"Fichier source      : {CSV_PATH}\n")
        f.write(f"Backup               : {BACKUP_PATH}\n")
        f.write(f"CSV nettoyé          : {OUTPUT_CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes traitées                      : {len(rows)}\n")
        f.write(f"Nombre total d'opérations de nettoyage effectuées    : {len(modifications_log)}\n")
        f.write(f"Nombre de lignes ayant subi au moins une modification: {len(rows_with_any_mod)}\n\n")
        f.write("Détail par champ (nombre de valeurs vidées) :\n")
        for champ_attendu in FIELDS_TO_CLEAN:
            champ_reel = col_map[champ_attendu]
            f.write(f"  {champ_reel} : {field_mod_counter.get(champ_reel, 0)}\n")
        f.write("\n")
        f.write(
            "Nombre de lignes avec incohérence "
            f"(Inscription_booleen = Non mais champ(s) d'inscription renseigné(s)) : {incoherence_rows}\n"
        )

    print("Traitement terminé.")
    print(f"  CSV nettoyé        : {OUTPUT_CSV_PATH}")
    print(f"  Log modifications  : {LOG_MODIFICATIONS_PATH}")
    print(f"  Log incohérences   : {LOG_INCOHERENCES_PATH}")
    print(f"  Log statistiques   : {LOG_STATS_PATH}")


if __name__ == "__main__":
    process()
