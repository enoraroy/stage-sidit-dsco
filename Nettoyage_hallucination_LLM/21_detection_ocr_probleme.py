"""
Detection de trois types d'anomalies liees aux inscriptions, chacune etant
un indice possible d'une ocerisation ou d'une invention non demandee par
le LLM :

  TYPE 1 - CONTENU_ABSENT_NOTICE
      Inscription_transcription ou Inscription_transliterration contient
      une information absente de la Notice (le texte source du
      catalogue). Methode : recherche du plus long segment commun
      contigu (difflib.SequenceMatcher.find_longest_match) entre le
      champ inscription normalise et la notice normalisee. Sous un
      seuil de ratio, le champ est considere comme absent -> suspect.

  TYPE 2 - NOTICE_DEBUT_NON_LATIN
      La Notice commence par un premier caractere alphabetique en
      ecriture arabe ou hebraique (les chiffres et la ponctuation en
      tete sont ignores, ils sont neutres). Une notice cense reproduire
      un texte de catalogue de vente occidental ne devrait normalement
      pas commencer ainsi -> suspect.

  TYPE 3 - BOOLEEN_INCOHERENT
      Inscription_booleen vaut "Non" alors qu'au moins un des 6 champs
      d'inscription (nature, langue, ecriture, transcription,
      transliterration, traduction) contient une valeur -> incoherence.

Chaque anomalie detectee est ecrite comme une ligne du rapport CSV de
sortie, avec une colonne "Decision_manuelle" laissee VIDE, a completer
a la main pour arbitrer ce qu'il faut faire de chaque cas (ex. "faux
positif", "a corriger", "a supprimer"...).

Attention encodage : les champs peuvent contenir de l'arabe ou de l'hebreu
(caracteres non-ASCII, ecriture de droite a gauche). Tout le fichier est
lu et ecrit en UTF-8 (utf-8-sig en entree/sortie). Aucune conversion ni
translitteration destructive n'est appliquee aux valeurs elles-memes :
seule une COPIE normalisee est utilisee pour la comparaison du TYPE 1,
les valeurs d'origine (et leurs contextes) sont conservees telles quelles
dans les logs et le rapport.
"""

import csv
import os
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

CSV_PATH = r"chemin_du_csv_des_lots"

DELIMITER = ";"

ID_COLUMN = "Id_perenne"
CATALOG_COLUMN = "Identifiant_catalogue"
NOTICE_COLUMN = "Notice"
BOOLEEN_COLUMN = "Inscription_booleen"

TRANSCRIPTION_COLUMN = "Inscription_transcription"
TRANSLITERATION_COLUMN = "Inscription_transliterration"

# Les 6 champs d'inscription (utilises pour le controle du TYPE 3 :
# est-ce que l'un d'eux contient quelque chose alors que le booleen dit
# "Non" ?)
TOUS_CHAMPS_INSCRIPTION = [
    "Inscription_nature",
    "Inscription_langue",
    "Inscription_ecriture",
    "Inscription_transcription",
    "Inscription_transliterration",
    "Inscription_traduction",
]

# Champs controles pour le TYPE 1 (contenu absent de la notice) : ceux
# susceptibles de reprendre litteralement un texte lisible sur l'objet
CHAMPS_CONTENU = [TRANSCRIPTION_COLUMN, TRANSLITERATION_COLUMN]

# --- Parametres TYPE 1 ---
LONGUEUR_MIN_CONTROLE = 4          # longueur mini du champ (normalise) pour etre controle
SEUIL_RATIO_SUSPECT = 0.5          # sous ce ratio, contenu considere absent de la notice
TAILLE_MIN_SEGMENT_VALIDE = 3      # taille mini (car. non-espace) pour qu'un match soit valide
NB_MOTS_CONTEXTE = 10               # mots affiches avant/apres le segment trouve
LONGUEUR_EXTRAIT_REPLI = 300        # repli si aucun segment localisable

# --- Parametres TYPE 2 ---
# Plages Unicode des ecritures hebraique et arabe (blocs principaux +
# extensions/formes presentees)
PLAGES_HEBREU = [(0x0590, 0x05FF), (0xFB1D, 0xFB4F)]
PLAGES_ARABE = [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]

# --- Parametres TYPE 3 ---
VALEUR_BOOLEEN_NON = "non"  # comparaison apres normalisation (casefold + strip)


OUTPUT_DIR = os.path.dirname(CSV_PATH)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_RAPPORT_PATH = os.path.join(OUTPUT_DIR, f"rapport_anomalies_inscriptions_{TIMESTAMP}.csv")
LOG_SUSPECTS_PATH = os.path.join(OUTPUT_DIR, f"log_anomalies_inscriptions_{TIMESTAMP}.txt")
LOG_STATS_PATH = os.path.join(OUTPUT_DIR, f"log_stats_anomalies_inscriptions_{TIMESTAMP}.txt")


def _normalize_colname(nom):
    s = unicodedata.normalize("NFKD", nom)
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
                  f"correspondance trouvee avec la colonne reelle \"{match}\". "
                  f"Utilisation de \"{match}\".")
            resolved[col] = match
        else:
            unresolved.append(col)

    if unresolved:
        raise ValueError(
            "Colonnes attendues introuvables dans le CSV (meme approximativement) : "
            + ", ".join(unresolved)
            + "\nColonnes disponibles : " + ", ".join(fieldnames)
        )
    return resolved


# ------------------------------------------------------------------
# TYPE 1 - contenu absent de la notice
# ------------------------------------------------------------------

_PATTERN_ALPHANUM = re.compile(r"\w", flags=re.UNICODE)
_PATTERN_MOTS = re.compile(r"\S+", flags=re.UNICODE)


def normaliser_avec_indices(texte):
    """Normalise `texte` caractere original par caractere original, et
    renvoie (texte_normalise, indices) ou indices[k] est l'indice, dans
    `texte`, du caractere original a l'origine de texte_normalise[k]."""
    caracteres = []
    indices = []

    for i, c in enumerate(texte or ""):
        decomp = unicodedata.normalize("NFKD", c)
        base = "".join(d for d in decomp if not unicodedata.combining(d))
        if base == "":
            continue
        base = base.casefold()
        for b in base:
            if _PATTERN_ALPHANUM.match(b):
                caracteres.append(b)
                indices.append(i)
            else:
                if caracteres and caracteres[-1] == " ":
                    continue
                caracteres.append(" ")
                indices.append(i)

    while caracteres and caracteres[0] == " ":
        caracteres.pop(0)
        indices.pop(0)
    while caracteres and caracteres[-1] == " ":
        caracteres.pop()
        indices.pop()

    return "".join(caracteres), indices


def ratio_inclusion(texte_court_normalise, texte_long_normalise):
    if not texte_court_normalise:
        return 1.0, None, None
    if not texte_long_normalise:
        return 0.0, None, None
    sm = SequenceMatcher(None, texte_court_normalise, texte_long_normalise, autojunk=False)
    match = sm.find_longest_match(0, len(texte_court_normalise), 0, len(texte_long_normalise))
    if match.size == 0:
        return 0.0, None, None

    segment = texte_court_normalise[match.a: match.a + match.size]
    if len(segment.replace(" ", "")) < TAILLE_MIN_SEGMENT_VALIDE:
        return 0.0, None, None

    ratio = match.size / len(texte_court_normalise)
    pos_debut = match.b
    pos_fin = match.b + match.size - 1
    return ratio, pos_debut, pos_fin


def extraire_contexte(texte_original, indice_debut, indice_fin, nb_mots=NB_MOTS_CONTEXTE):
    if indice_debut is None or indice_fin is None:
        return texte_original[:LONGUEUR_EXTRAIT_REPLI]

    mots = list(_PATTERN_MOTS.finditer(texte_original))
    if not mots:
        return texte_original[:LONGUEUR_EXTRAIT_REPLI]

    idx_mot_debut = 0
    for k, m in enumerate(mots):
        if m.start() <= indice_debut:
            idx_mot_debut = k
        else:
            break

    idx_mot_fin = len(mots) - 1
    for k, m in enumerate(mots):
        if m.end() - 1 >= indice_fin:
            idx_mot_fin = k
            break

    idx_contexte_debut = max(0, idx_mot_debut - nb_mots)
    idx_contexte_fin = min(len(mots) - 1, idx_mot_fin + nb_mots)

    debut_char = mots[idx_contexte_debut].start()
    fin_char = mots[idx_contexte_fin].end()

    extrait = texte_original[debut_char:fin_char]
    prefixe = "[...] " if idx_contexte_debut > 0 else ""
    suffixe = " [...]" if idx_contexte_fin < len(mots) - 1 else ""

    seg_original_debut = max(0, min(len(extrait), indice_debut - debut_char))
    seg_original_fin = max(seg_original_debut, min(len(extrait), indice_fin - debut_char + 1))
    extrait_marque = (
        extrait[:seg_original_debut]
        + ">>>" + extrait[seg_original_debut:seg_original_fin] + "<<<"
        + extrait[seg_original_fin:]
    )

    return prefixe + extrait_marque + suffixe


def controler_contenu_absent(champ, valeur_brute, notice_brute, notice_normalisee, indices_notice):
    """Renvoie un dict d'anomalie si le contenu de `valeur_brute` n'est
    pas retrouve dans la notice, sinon None."""
    valeur_normalisee, _ = normaliser_avec_indices(valeur_brute)

    if valeur_normalisee == "" or len(valeur_normalisee) < LONGUEUR_MIN_CONTROLE:
        return None

    if notice_normalisee == "":
        return {
            "type_anomalie": "CONTENU_ABSENT_NOTICE",
            "champ_concerne": champ,
            "valeur_champ": valeur_brute,
            "ratio_inclusion": "0.000",
            "contexte_notice": "(notice vide)",
        }

    ratio, pos_debut_norm, pos_fin_norm = ratio_inclusion(valeur_normalisee, notice_normalisee)
    if ratio >= SEUIL_RATIO_SUSPECT:
        return None  # contenu retrouve dans la notice -> pas d'anomalie

    if pos_debut_norm is not None:
        indice_debut_orig = indices_notice[pos_debut_norm]
        indice_fin_orig = indices_notice[pos_fin_norm]
        contexte = extraire_contexte(notice_brute, indice_debut_orig, indice_fin_orig)
    else:
        contexte = extraire_contexte(notice_brute, None, None)

    return {
        "type_anomalie": "CONTENU_ABSENT_NOTICE",
        "champ_concerne": champ,
        "valeur_champ": valeur_brute,
        "ratio_inclusion": f"{ratio:.3f}",
        "contexte_notice": contexte,
    }


# ------------------------------------------------------------------
# TYPE 2 - notice commencant par une ecriture non latine (arabe/hebreu)
# ------------------------------------------------------------------

def _script_du_caractere(c):
    cp = ord(c)
    for a, b in PLAGES_HEBREU:
        if a <= cp <= b:
            return "hebreu"
    for a, b in PLAGES_ARABE:
        if a <= cp <= b:
            return "arabe"
    return "latin_ou_autre"


def controler_notice_debut_non_latin(notice_brute):
    """Cherche le premier caractere ALPHABETIQUE de la notice (les
    chiffres, espaces et ponctuation en tete sont ignores car neutres).
    Si ce premier caractere alphabetique est en ecriture arabe ou
    hebraique, renvoie un dict d'anomalie ; sinon None."""
    for c in notice_brute or "":
        if c.isalpha():
            script = _script_du_caractere(c)
            if script in ("hebreu", "arabe"):
                return {
                    "type_anomalie": "NOTICE_DEBUT_NON_LATIN",
                    "champ_concerne": NOTICE_COLUMN,
                    "valeur_champ": c,
                    "ratio_inclusion": "",
                    "contexte_notice": (notice_brute or "")[:LONGUEUR_EXTRAIT_REPLI],
                    "ecriture_detectee": script,
                }
            return None  # premier caractere alphabetique deja latin/autre -> ok
    return None  # aucun caractere alphabetique dans la notice


# ------------------------------------------------------------------
# TYPE 3 - Inscription_booleen = Non alors qu'un champ est rempli
# ------------------------------------------------------------------

def controler_booleen_incoherent(row, col_map_inscription, booleen_brut):
    booleen_normalise = (booleen_brut or "").strip().casefold()
    if booleen_normalise != VALEUR_BOOLEEN_NON:
        return None  # rien a verifier si le booleen n'est pas "Non"

    champs_remplis = []
    for champ in TOUS_CHAMPS_INSCRIPTION:
        colonne_reelle = col_map_inscription[champ]
        valeur = (row.get(colonne_reelle) or "").strip()
        if valeur != "":
            champs_remplis.append((champ, valeur))

    if not champs_remplis:
        return None  # coherent : booleen "Non" et aucun champ rempli

    resume = " ; ".join(f"{champ}=\"{valeur}\"" for champ, valeur in champs_remplis)
    return {
        "type_anomalie": "BOOLEEN_INCOHERENT",
        "champ_concerne": BOOLEEN_COLUMN,
        "valeur_champ": resume,
        "ratio_inclusion": "",
        "contexte_notice": "",
    }


def process():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in, delimiter=DELIMITER)
        fieldnames = reader.fieldnames
        rows = list(reader)

    colonnes_attendues = (
        {ID_COLUMN, CATALOG_COLUMN, NOTICE_COLUMN, BOOLEEN_COLUMN}
        | set(TOUS_CHAMPS_INSCRIPTION)
    )
    col_map = resolve_columns(colonnes_attendues, fieldnames)

    id_col = col_map[ID_COLUMN]
    catalog_col = col_map[CATALOG_COLUMN]
    notice_col = col_map[NOTICE_COLUMN]
    booleen_col = col_map[BOOLEEN_COLUMN]

    lignes_rapport = []
    compteur_par_type = {"CONTENU_ABSENT_NOTICE": 0, "NOTICE_DEBUT_NON_LATIN": 0, "BOOLEEN_INCOHERENT": 0}

    for numero_ligne, row in enumerate(rows, start=2):  # start=2 : ligne 1 = entete
        id_perenne = (row.get(id_col) or "").strip()
        catalog_id = (row.get(catalog_col) or "").strip()
        notice_brute = row.get(notice_col, "") or ""
        booleen_brut = row.get(booleen_col, "") or ""

        anomalies_ligne = []

        # --- TYPE 1 : contenu absent de la notice ---
        notice_normalisee, indices_notice = normaliser_avec_indices(notice_brute)
        for champ in CHAMPS_CONTENU:
            colonne_reelle = col_map[champ]
            valeur_brute = row.get(colonne_reelle, "") or ""
            if valeur_brute.strip() == "":
                continue
            anomalie = controler_contenu_absent(
                champ, valeur_brute, notice_brute, notice_normalisee, indices_notice
            )
            if anomalie:
                anomalies_ligne.append(anomalie)

        # --- TYPE 2 : notice debutant en ecriture non latine ---
        anomalie_notice = controler_notice_debut_non_latin(notice_brute)
        if anomalie_notice:
            anomalies_ligne.append(anomalie_notice)

        # --- TYPE 3 : booleen incoherent ---
        anomalie_booleen = controler_booleen_incoherent(row, col_map, booleen_brut)
        if anomalie_booleen:
            anomalies_ligne.append(anomalie_booleen)

        for anomalie in anomalies_ligne:
            compteur_par_type[anomalie["type_anomalie"]] += 1
            lignes_rapport.append({
                "numero_ligne": numero_ligne,
                "Id_perenne": id_perenne,
                "Identifiant_catalogue": catalog_id,
                "type_anomalie": anomalie["type_anomalie"],
                "champ_concerne": anomalie["champ_concerne"],
                "valeur_champ": anomalie["valeur_champ"],
                "ratio_inclusion": anomalie["ratio_inclusion"],
                "contexte_notice": anomalie["contexte_notice"],
                "Decision_manuelle": "",  # colonne a completer a la main
            })

    # ---- Ecriture du rapport CSV ----
    with open(OUTPUT_RAPPORT_PATH, "w", newline="", encoding="utf-8-sig") as f_out:
        fieldnames_rapport = [
            "numero_ligne", "Id_perenne", "Identifiant_catalogue",
            "type_anomalie", "champ_concerne", "valeur_champ",
            "ratio_inclusion", "contexte_notice", "Decision_manuelle",
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames_rapport, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(lignes_rapport)

    # ---- Log detaille, lisible ----
    with open(LOG_SUSPECTS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Anomalies inscriptions detectees - {TIMESTAMP}\n")
        f.write(f"Nombre total d'anomalies : {len(lignes_rapport)}\n")
        f.write("Types : CONTENU_ABSENT_NOTICE / NOTICE_DEBUT_NON_LATIN / BOOLEEN_INCOHERENT\n\n")
        for cas in lignes_rapport:
            f.write("-" * 70 + "\n")
            f.write(f"Ligne CSV        : {cas['numero_ligne']}\n")
            f.write(f"Id_perenne       : {cas['Id_perenne']}\n")
            f.write(f"Identifiant_catalogue : {cas['Identifiant_catalogue']}\n")
            f.write(f"Type d'anomalie  : {cas['type_anomalie']}\n")
            f.write(f"Champ concerne   : {cas['champ_concerne']}\n")
            f.write(f"Valeur           : {cas['valeur_champ']}\n")
            if cas["ratio_inclusion"] != "":
                f.write(f"Ratio d'inclusion : {cas['ratio_inclusion']}\n")
            if cas["contexte_notice"] != "":
                f.write(f"Contexte notice  :\n{cas['contexte_notice']}\n")
            f.write("\n")

    # ---- Statistiques ----
    with open(LOG_STATS_PATH, "w", encoding="utf-8") as f:
        f.write(f"Statistiques - detection anomalies inscriptions - {TIMESTAMP}\n")
        f.write(f"Fichier source : {CSV_PATH}\n\n")
        f.write(f"Nombre total de lignes du fichier : {len(rows)}\n")
        f.write(f"Nombre total d'anomalies detectees : {len(lignes_rapport)}\n\n")
        for type_anomalie, nb in compteur_par_type.items():
            f.write(f"  {type_anomalie} : {nb}\n")

    print("Traitement termine.")
    for type_anomalie, nb in compteur_par_type.items():
        print(f"  {type_anomalie} : {nb}")
    print(f"  Total anomalies : {len(lignes_rapport)}")
    print(f"  Rapport CSV : {OUTPUT_RAPPORT_PATH}")
    print(f"  Log detaille : {LOG_SUSPECTS_PATH}")
    print(f"  Log stats : {LOG_STATS_PATH}")


if __name__ == "__main__":
    process()
