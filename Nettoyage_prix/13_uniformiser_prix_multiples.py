"""
Normalisation des cellules Estimation_lot MULTI-DEVISES.

Étape 2/2 de normalisation (fait suite au script des cellules
à devise unique). Ce script traite les cellules contenant PLUSIEURS devises
différentes, où le séparateur entre groupes de prix est trop variable pour
être détecté explicitement (espace, point-virgule, slash, parenthèses,
rien du tout, etc.).

Principe retenu (plus robuste qu'une détection de séparateur) :
    la devise précède toujours le(s) nombre(s) auquel(s) elle s'applique.
    On parcourt donc la cellule token par token (devise ou nombre) dans
    l'ordre d'apparition ; chaque nombre rencontré est assigné à la
    dernière devise vue. Cela gère nativement les cas comme
    "£2,000 - 3,000 ($2,600 - 3,900, €2,200 - 3,300)" où le second nombre
    d'un groupe n'a pas son propre symbole.

Règles appliquées à chaque ligne :
    1. Champ vide                                -> ignoré (pas de log).
    2. Champ "bruité" (même règle que les scripts précédents)
                                                    -> ignoré, signalé.
    3. Moins de 2 devises différentes détectées    -> ignoré, signalé
       (traité par le script "devise unique").
    4. Un nombre apparaît AVANT toute devise        -> ignoré, signalé
       (impossible de l'assigner).
    5. Une devise se retrouve avec 0 ou plus de 2   -> ignoré, signalé
       nombres assignés                              (cas trop complexe).
    6. Sinon : chaque groupe devise/nombres est formaté comme pour le
       mono-devise ("{devise}{val1}-{devise}{val2}" ou "{devise}{val}"),
       puis les groupes sont joints par "|", dans l'ordre d'apparition des
       devises dans la cellule d'origine.

Exemple :
    "£12,000-18,000 US$20,000-30,000 €15,000-22,000"
    -> "£12000-£18000|$20000-$30000|€15000-€22000"

Une backup du CSV est créée avant toute modification.
"""

import csv
import os
import re
import shutil
import unicodedata
from collections import defaultdict
from datetime import datetime

CSV_PATH = r"chemin_du_csv_avec_prix_uniques_uniformises"

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
CURRENCY_TOKENS_SORTED = sorted(CURRENCY_TOKEN_TO_SYMBOL, key=len, reverse=True)

ALLOWED_PUNCTUATION = {",", ".", "/", "-", "(", ")", "|", ";", " ", "\u00a0", "\n", "\r", "–", "\u0008", "\u0009"}

OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP_PATH = os.path.join(OUTPUT_DIR, f"BACKUP_{TIMESTAMP}_" + os.path.basename(CSV_PATH))
OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"lots_prix_uniformises_multidevise_{TIMESTAMP}.csv")
LOG_REFORMATAGES_PATH = os.path.join(OUTPUT_DIR, f"log_reformatages_prix_multidevise_{TIMESTAMP}.txt")
LOG_SIGNALEMENTS_PATH = os.path.join(OUTPUT_DIR, f"log_signalements_prix_multidevise_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_stats_prix_multidevise_{TIMESTAMP}.txt")

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


def caracteres_inattendus(valeur):
    reste = valeur
    for token in CURRENCY_TOKENS_SORTED:
        reste = reste.replace(token, "")
    return sorted(set(c for c in reste if not (c.isdigit() or c in ALLOWED_PUNCTUATION)))


def extract_currency_symbols(valeur):
    reste = valeur
    symboles = set()
    for token in CURRENCY_TOKENS_SORTED:
        if token in reste:
            symboles.add(CURRENCY_TOKEN_TO_SYMBOL[token])
            reste = reste.replace(token, "")
    return symboles


def nettoyer_separateurs_milliers(texte):
    resultat = texte
    for _ in range(3):
        resultat = re.sub(r"(\d)[,.\s\u00a0](\d{3})(?!\d)", r"\1\2", resultat)
    return resultat


# Pattern combiné : devise (tokens les plus longs d'abord) OU nombre
TOKEN_PATTERN = re.compile(
    "|".join([re.escape(t) for t in CURRENCY_TOKENS_SORTED] + [r"\d+(?:\.\d+)?"])
)


def grouper_par_devise(texte_nettoye):
    """Parcourt le texte token par token (devise ou nombre) et assigne
    chaque nombre à la dernière devise rencontrée.
    Retourne (groupes, erreur) :
        - groupes : liste ordonnée de (symbole, [valeurs]) selon l'ordre
          d'apparition des devises
        - erreur  : chaîne décrivant un problème bloquant, ou None
    """
    ordre_symboles = []
    groupes = defaultdict(list)
    devise_courante = None

    for m in TOKEN_PATTERN.finditer(texte_nettoye):
        texte_token = m.group()
        if texte_token in CURRENCY_TOKEN_TO_SYMBOL:
            symbole = CURRENCY_TOKEN_TO_SYMBOL[texte_token]
            devise_courante = symbole
            if symbole not in ordre_symboles:
                ordre_symboles.append(symbole)
        else:
            # c'est un nombre
            if devise_courante is None:
                return None, f"nombre '{texte_token}' rencontré avant toute devise"
            groupes[devise_courante].append(texte_token)

    for symbole in ordre_symboles:
        nb_valeurs = len(groupes[symbole])
        if nb_valeurs == 0 or nb_valeurs > 2:
            return None, f"devise '{symbole}' associée à {nb_valeurs} valeur(s) (attendu : 1 ou 2)"

    return [(s, groupes[s]) for s in ordre_symboles], None


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
            continue  # règle 1

        if caracteres_inattendus(valeur):
            signalements["bruit"].append((id_perenne, catalog_id, valeur, ""))
            continue  # règle 2

        symboles = extract_currency_symbols(valeur)
        if len(symboles) < 2:
            signalements["pas_multi_devise"].append(
                (id_perenne, catalog_id, valeur, f"{len(symboles)} devise(s) détectée(s)")
            )
            continue  # règle 3 : géré par le script mono-devise

        nettoye = nettoyer_separateurs_milliers(valeur)
        groupes, erreur = grouper_par_devise(nettoye)

        if erreur:
            signalements["cas_complexe"].append((id_perenne, catalog_id, valeur, erreur))
            continue  # règles 4/5

        # règle 6 : formatage final
        parties = []
        for symbole, valeurs in groupes:
            if len(valeurs) == 2:
                parties.append(f"{symbole}{valeurs[0]}-{symbole}{valeurs[1]}")
            else:
                parties.append(f"{symbole}{valeurs[0]}")
        nouvelle_valeur = "|".join(parties)

        row[estimation_col] = nouvelle_valeur
        reformatages.append((id_perenne, catalog_id, valeur, nouvelle_valeur))

    # ---- Écriture du CSV modifié ----
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    # ---- Log des reformatages ----
    with open(LOG_REFORMATAGES_PATH, "w", encoding="utf-8") as f:
        f.write(f"Log des reformatages (multi-devises) - {TIMESTAMP}\n")
        f.write(f"Nombre total de reformatages : {len(reformatages)}\n\n")
        for id_perenne, catalog_id, ancienne, nouvelle in reformatages:
            ancienne_clean = ancienne.replace("\n", " ").replace("\r", " ").strip()
            f.write(f'{id_perenne} ; {catalog_id} ; "{ancienne_clean}" -> "{nouvelle}"\n')

    # ---- Log des signalements ----
    libelles = {
        "bruit": "Lignes ignorées (caractères inattendus détectés)",
        "pas_multi_devise": "Lignes ignorées (moins de 2 devises - géré par le script mono-devise)",
        "cas_complexe": "Lignes ignorées (structure trop complexe ou ambiguë)",
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
        f.write(f"Statistiques - uniformisation des prix (multi-devises) - {TIMESTAMP}\n")
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
