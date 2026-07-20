"""
Script 26 - Conversion des chiffres romains (I a XXI) en chiffres arabes
dans le champ Date_complete, a partir de la logique de detection validee
dans le script 25.

Principe :
    - Le moteur de detection (candidat maximal + suffixe ordinal/contextuel
      + filtrage par mots de contexte) est repris a l'identique du script 25,
      pour garantir que ce script convertit EXACTEMENT les memes formes que
      celles recensees dans le rapport du script 25. Rien n'est modifie dans
      le script 25 : ce script est autonome.
    - Chaque numeral romain valide est remplace par sa valeur arabe, le
      suffixe (e, er, °, " siecle", etc.) et tout le reste du texte restant
      inchanges.

Exemples :
    XIXe siecle                    -> 19e siecle
    IIe-IIIe siecle avant J.-C.    -> 2e-3e siecle avant J.-C.
    V-IVe siecle avant J.-C.       -> 5-4e siecle avant J.-C.
    Ier Empire / IIIe dynastie     -> inchanges (exclus par le filtre de contexte)

Sortie :
    - CSV complet avec Date_complete corrige :
        lots_dates_arabes_corriges_YYYYMMDD_HHMMSS.csv
    - Log des changements (uniquement les lignes modifiees) :
        log_conversion_chiffres_romains_date_YYYYMMDD_HHMMSS.csv
    - Affichage console recapitulatif
"""

import csv
import os
import re
import unicodedata
from collections import Counter
from datetime import datetime

# --- Chemin a adapter (le meme CSV source que le script 25) ---
CSV_PATH = r"chemin_du_csv"

OUTPUT_DIR = os.path.dirname(CSV_PATH)
DELIMITER = ";"
COLONNE_DATE = "Date_complete"
COL_ID = "Id_perenne"
COL_CATALOGUE = "Identifiant_catalogue"


CHIFFRES_ROMAINS = [
    "XXI", "XX", "XIX", "XVIII", "XVII", "XVI", "XV",
    "XIV", "XIII", "XII", "XI", "X",
    "IX", "VIII", "VII", "VI", "V",
    "IV", "III", "II", "I",
]

ROMAN_VALIDES = set(CHIFFRES_ROMAINS)

_roman_alt = "|".join(re.escape(r) for r in CHIFFRES_ROMAINS)

# Interdit qu'une lettre (accents compris) suive immediatement le suffixe repere,
# pour eviter par exemple de valider "er" au milieu de "vers".
_not_letter = r"(?![^\W\d_])"

# Forme ordinale "eme"/"ème" (accent optionnel), utilisee a deux endroits :
# suffixe direct (XIXeme) et deuxieme membre d'une fourchette (V-IVeme).
_eme = r"\u00e8?me"

# Suffixe attendu JUSTE APRES un bloc de lettres romaines valide :
#   - "er"                         -> Ier
#   - "eme" / "ème"                -> XIXeme, XIXème
#   - "e"                          -> XIXe
#   - "°"                          -> XIX°
#   - " siecle(s)" (accent ou non) -> XIX siecle
#   - "-<autre numeral>(er|eme|e)" -> V-IVe, XI-XIIe, XVIII-XIXeme (fourchette)
_suffixe = re.compile(
    r"\A(?:"
    + r"er" + _not_letter
    + r"|" + _eme + _not_letter
    + r"|" + r"e" + _not_letter
    + r"|" + r"°"
    + r"|" + r"\s+si\u00e8?cles?" + _not_letter
    + r"|" + r"-(?:" + _roman_alt + r")(?:er|" + _eme + r"|e)" + _not_letter
    + r")",
    flags=re.IGNORECASE,
)

# Bloc MAXIMAL de lettres I/V/X consecutives, en debut de mot.
_candidat = re.compile(r"\b[IVXivx]+")

# Mots de contexte : quand l'un d'eux apparait dans les 1-2 mots suivant le
# suffixe, on considere qu'il ne s'agit PAS d'une date de siecle mais d'un
# numero de regime/dynastie/periode -> l'occurrence est rejetee.
# Liste modifiable librement (sans accent, en minuscule ; la comparaison
# retire elle-meme les accents et la casse du texte source).
MOTS_STOP_CONTEXTE = {
    "dynastie", "dynasties",
    "republique", "republiques",
    "empire", "empires",       # ex. "Ier Empire"
    "regne", "regnes",
    "periode", "periodes",
    "intermediaire", "intermediaires",
}
NB_MOTS_CONTEXTE = 2

_mot_regex = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+")


def _sans_accents(texte):
    nfkd = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _contexte_est_stop(texte_apres_suffixe):
    mots = _mot_regex.findall(texte_apres_suffixe)[:NB_MOTS_CONTEXTE]
    return any(_sans_accents(mot) in MOTS_STOP_CONTEXTE for mot in mots)


def _trouver_spans_romains(valeur):
    """Renvoie la liste des (debut, fin, texte) des numeraux romains valides
    (memes criteres que le script 25 : suffixe + contexte), dans l'ordre
    d'apparition. (debut, fin) delimitent uniquement le numeral lui-meme,
    pas le suffixe."""
    spans = []
    for m in _candidat.finditer(valeur):
        run = m.group(0)
        if run.upper() not in ROMAN_VALIDES:
            continue

        reste = valeur[m.end():]
        suffixe_match = _suffixe.match(reste)
        if not suffixe_match:
            continue

        apres_suffixe = reste[suffixe_match.end():]
        if _contexte_est_stop(apres_suffixe):
            continue

        spans.append((m.start(), m.end(), run))
    return spans


ROMAIN_VERS_ARABE = {
    "XXI": 21, "XX": 20, "XIX": 19, "XVIII": 18, "XVII": 17, "XVI": 16,
    "XV": 15, "XIV": 14, "XIII": 13, "XII": 12, "XI": 11, "X": 10,
    "IX": 9, "VIII": 8, "VII": 7, "VI": 6, "V": 5,
    "IV": 4, "III": 3, "II": 2, "I": 1,
}


def remplacer_romains_par_arabes(valeur):
    """Remplace dans `valeur` chaque numeral romain valide par son equivalent
    arabe (suffixe et reste du texte inchanges).
    Renvoie (nouvelle_valeur, conversions) ou conversions est une liste de
    tuples (forme_romaine_originale, valeur_arabe) dans l'ordre d'apparition."""
    spans = _trouver_spans_romains(valeur)
    if not spans:
        return valeur, []

    conversions = []
    nouvelle_valeur = valeur
    # Remplacement en partant de la fin pour ne pas decaler les positions
    # des spans qui n'ont pas encore ete traites.
    for debut, fin, texte_roman in reversed(spans):
        arabe = ROMAIN_VERS_ARABE[texte_roman.upper()]
        nouvelle_valeur = nouvelle_valeur[:debut] + str(arabe) + nouvelle_valeur[fin:]
        conversions.append((texte_roman, arabe))

    conversions.reverse()  # remettre dans l'ordre d'apparition d'origine
    return nouvelle_valeur, conversions


def main():
    print("--- Script 26 : conversion des chiffres romains en chiffres arabes (Date_complete) ---")
    print(f"Source : {CSV_PATH}")

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if COLONNE_DATE not in fieldnames:
        print(f"ERREUR : colonne '{COLONNE_DATE}' introuvable dans le CSV.")
        print(f"Colonnes disponibles : {', '.join(fieldnames)}")
        return

    print(f"  {len(rows)} lignes chargees.\n")

    logs = []                       # lignes modifiees, pour le CSV de log
    compteur_conversions = Counter()  # "XIX->19" -> nb d'occurrences
    nb_lignes_modifiees = 0

    for row in rows:
        valeur = (row.get(COLONNE_DATE) or "").strip()
        if not valeur:
            continue

        nouvelle_valeur, conversions = remplacer_romains_par_arabes(valeur)
        if not conversions:
            continue  # rien a changer sur cette ligne

        row[COLONNE_DATE] = nouvelle_valeur
        nb_lignes_modifiees += 1

        conversions_str = ", ".join(f"{r}->{a}" for r, a in conversions)
        for r, a in conversions:
            compteur_conversions[f"{r.upper()}->{a}"] += 1

        logs.append({
            "Id_perenne":            (row.get(COL_ID) or "").strip(),
            "Identifiant_catalogue": (row.get(COL_CATALOGUE) or "").strip(),
            "Date_complete_avant":   valeur,
            "Date_complete_apres":   nouvelle_valeur,
            "conversions":           conversions_str,
        })


    print(f"Lignes modifiees : {nb_lignes_modifiees} / {len(rows)}")
    print()
    print("--- Conversions appliquees (toutes occurrences confondues) ---")
    for conv, n in sorted(compteur_conversions.items(), key=lambda x: -x[1]):
        print(f"  {conv:<10} : {n} occurrence(s)")

    print()
    print("--- Detail des changements ---")
    for entree in logs:
        print(f"  [{entree['Id_perenne']}] {entree['Date_complete_avant']}"
              f"   ->   {entree['Date_complete_apres']}")

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")

    nom_sortie_csv = f"lots_dates_arabes_corriges_{horodatage}.csv"
    chemin_sortie_csv = os.path.join(OUTPUT_DIR, nom_sortie_csv)

    with open(chemin_sortie_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)

    nom_log = f"log_conversion_chiffres_romains_date_{horodatage}.csv"
    chemin_log = os.path.join(OUTPUT_DIR, nom_log)

    with open(chemin_log, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Id_perenne", "Identifiant_catalogue",
                        "Date_complete_avant", "Date_complete_apres", "conversions"],
            delimiter=DELIMITER,
        )
        writer.writeheader()
        writer.writerows(logs)

    print()
    print(f"CSV corrige ecrit : {chemin_sortie_csv}")
    print(f"Log de changements ecrit : {chemin_log}")
    print(f"  {nb_lignes_modifiees} ligne(s) modifiee(s) sur {len(rows)}")


if __name__ == "__main__":
    main()
