"""
Script 25 - Recensement des valeurs du champ Date_complete contenant
des chiffres romains (I a XXI, majuscules ou minuscules).

Lecture seule : aucune modification du CSV source.

L'objectif est de lister toutes les valeurs concernees pour preparer
leur correction (conversion en chiffres arabes) dans un script distinct.

Rappel des cas pas à modif (pas de chiffres romains, donc pas detectes) :
    2011-2013 / circa 1982 / 20e-21e siecle / deuxieme quart du 17e siecle

Cas cibles, bien detectes :
    fin du XIXe siecle / Epoque Edo (1603-1868), XIXe siecle
    fin du XIXe - debut du XXe siecles / V-IVe siecle avant J.-C.
    XIIe/XIIIe siecle / Style Louis XVI, XIXe siecle (XVI exclu, XIX garde)
    XIXeme - XXeme siecles / XVIIIeme-XIXeme siecle / Fin du XIXeme siecle
    XIXeme siecle (jattes); XVIIIeme siecle (plat) / XVIIIeme siecle, circa 1765

Cas exclus volontairement (faux positifs regles) :
    Ier Empire / IIIe dynastie / IIIe Republique   -> ordinal de regime/dynastie,
                                                       pas une date de siecle
    Amenhotep III, ...                              -> pas suivi d'un suffixe ordinal

Methode en 3 etapes :
    1. Reperage d'un bloc MAXIMAL de lettres I/V/X consecutives (\\b en debut de mot),
       ce qui evite tout probleme d'ordre entre formes imbriquees (VI/VIII, etc.).
    2. Validation : le bloc doit correspondre a un numeral romain cohérent (I a XXI).
    3. Le numeral doit etre immediatement suivi d'un suffixe ordinal/contextuel
       (e, er, eme/ème, °, " siecle(s)", ou un enchainement du type "V-IVe" /
       "XVIII-XIXeme"), ET les 1-2 mots qui suivent ce suffixe ne doivent PAS
       faire partie d'une liste de mots de contexte "non-date" (dynastie,
       republique, empire, regne...).

Sortie :
    - affichage console detaille (valeur + occurrences)
    - rapport_chiffres_romains_date_YYYYMMDD_HHMMSS.csv
"""

import csv
import os
import re
import unicodedata
from collections import Counter
from datetime import datetime

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

NB_MOTS_CONTEXTE = 2  # nombre de mots suivants inspectes

_mot_regex = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+")


def _sans_accents(texte):
    """Retire les accents et met en minuscule, pour comparaison robuste."""
    nfkd = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _contexte_est_stop(texte_apres_suffixe):
    """True si l'un des NB_MOTS_CONTEXTE mots suivants est un mot de contexte
    "non-date" (dynastie, republique, empire, etc.)."""
    mots = _mot_regex.findall(texte_apres_suffixe)[:NB_MOTS_CONTEXTE]
    return any(_sans_accents(mot) in MOTS_STOP_CONTEXTE for mot in mots)


def _trouver_romains(valeur):
    """Renvoie la liste des formes romaines valides, suffixees ET dont le
    contexte suivant n'est pas exclu, dans l'ordre d'apparition (casse
    d'origine conservee)."""
    resultats = []
    for m in _candidat.finditer(valeur):
        run = m.group(0)
        if run.upper() not in ROMAN_VALIDES:
            continue  # bloc de lettres I/V/X mais pas un numeral legal

        reste = valeur[m.end():]
        suffixe_match = _suffixe.match(reste)
        if not suffixe_match:
            continue  # pas de suffixe ordinal/contextuel -> pas retenu

        apres_suffixe = reste[suffixe_match.end():]
        if _contexte_est_stop(apres_suffixe):
            continue  # mot de contexte "non-date" juste apres -> rejete

        resultats.append(run)
    return resultats


def contient_romain(valeur):
    """Renvoie True si la valeur contient au moins un chiffre romain valide."""
    return bool(_trouver_romains(valeur))


def extraire_romains(valeur):
    """Renvoie la liste des formes romaines trouvees (casse d'origine)."""
    return _trouver_romains(valeur)


# ------------------------------------------------------------------
# TRAITEMENT
# ------------------------------------------------------------------

def main():
    print("--- Script 25 : recensement des chiffres romains dans Date_complete ---")
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

    # --- Collecte ---
    cas = []          # liste de dicts pour le CSV de sortie
    compteur_valeurs = Counter()   # valeur brute -> nb de lignes
    compteur_formes  = Counter()   # forme romaine trouvee -> nb d'occurrences

    for row in rows:
        valeur = (row.get(COLONNE_DATE) or "").strip()
        if not valeur:
            continue
        formes = extraire_romains(valeur)
        if not formes:
            continue

        compteur_valeurs[valeur] += 1
        for f in formes:
            compteur_formes[f.upper()] += 1

        cas.append({
            "Id_perenne":            (row.get(COL_ID) or "").strip(),
            "Identifiant_catalogue": (row.get(COL_CATALOGUE) or "").strip(),
            "Date_complete":         valeur,
            "formes_romaines":       ", ".join(formes),
        })

    nb_lignes  = len(cas)
    nb_valeurs = len(compteur_valeurs)

    print(f"Lignes avec chiffre(s) romain(s) : {nb_lignes}")
    print(f"Valeurs distinctes concernees     : {nb_valeurs}")
    print()

    print("--- Formes romaines trouvees (toutes occurrences confondues) ---")
    for forme, n in sorted(compteur_formes.items(), key=lambda x: -x[1]):
        print(f"  {forme:<8} : {n} occurrence(s)")

    print()
    print("--- Valeurs distinctes (triees par frequence decroissante) ---")
    for valeur, n in compteur_valeurs.most_common():
        formes = extraire_romains(valeur)
        formes_str = ", ".join(dict.fromkeys(f.upper() for f in formes))  # dedoublonne, ordre preserve
        print(f"  [{n:>4}x]  {valeur}   ->  formes : {formes_str}")

    horodatage  = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_sortie  = f"rapport_chiffres_romains_date_{horodatage}.csv"
    chemin_sortie = os.path.join(OUTPUT_DIR, nom_sortie)

    with open(chemin_sortie, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Id_perenne", "Identifiant_catalogue", "Date_complete", "formes_romaines"],
            delimiter=DELIMITER,
        )
        writer.writeheader()
        writer.writerows(cas)

    print()
    print(f"Rapport CSV ecrit : {chemin_sortie}")
    print(f"  {nb_lignes} ligne(s) recensee(s), {nb_valeurs} valeur(s) distincte(s)")


if __name__ == "__main__":
    main()
