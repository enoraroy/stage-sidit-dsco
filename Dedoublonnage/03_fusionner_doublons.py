"""
fusionner_doublons.py
---------------------
Applique la fusion des doublons confirmes dont la notice est vide ou non significative.

PRINCIPE :
  Pour chaque groupe de doublons confirmes (meme Identifiant_catalogue +
  meme Numero_lot + pages a +- SEUIL_PAGE) :

    - Si la notice du doublon est "vide" ou "non_sig" :
        -> On fusionne : on rapatrie sa page PDF et son lien Arkindex
           dans la ligne originale, puis on supprime la ligne doublon.

    - Si la notice du doublon est "significative" :
        -> On ne touche a rien. La ligne doublon est conservee telle quelle.
           Elle devra etre traitee manuellement.

  EN PLUS, INDEPENDAMMENT DE CE QUI PRECEDE :
  Les Id_perenne listes dans A_FUSIONNER_DIRECT sont TOUJOURS fusionnes avec
  l'original de leur groupe, meme si :
    - le groupe est classe "suspect" (pages hors du seuil, ou page invalide),
    - la notice du doublon est "significative".
  C'est une liste de decisions manuelles explicites qui outrepasse la
  detection automatique (SEUIL_PAGE, IDS_EXCLUS et la classification de la
  notice restent inchanges pour tous les autres cas).

FUSION DES CHAMPS :
  Numero_page_pdf  : union de toutes les valeurs numeriques, triees par ordre
                     croissant, separees par "|". Les valeurs deja multi-valuees
                     (ex: "37|38") sont decomposees avant tri.
  Lien_page_arkindex : meme logique, mais deduplication par valeur exacte
                     (on n'ajoute pas un lien deja present dans la cellule).

SORTIE :
  - Un CSV fusionne (le fichier de travail avec moins de lignes).
  - Un rapport .txt resumant les operations effectuees.
"""

import pandas as pd
import re
from pathlib import Path
from datetime import datetime
from itertools import combinations

# ── Chemins ───────────────────────────────────────────────────────────────────
INPUT_CSV = Path("chemin_du_csv")
OUTPUT_DIR = "chemin_du_dossier")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Parametres (identiques a analyse_doublons.py) ────────────────────────────
SEUIL_PAGE = 2

IDS_EXCLUS = {
    # Couvertures introductives
    "39848", "38942", "36703", "44142", "38866", "25047", "16016",
    "18155", "16448", "11787", "10709", "9210", "11727", "11728", "23955", "2854", "23955",
    # Publicites pour prochaines ventes
    "56874", "56873", "41639", "39531", "4040", "4039",
    # Id specifique (statut incertain)
    "47384",
}

# ── Fusions forcees (decisions manuelles) ────────────────────────────────────
# Id_perenne de DOUBLONS a fusionner avec l'original de leur groupe, quoi
# qu'il arrive : meme si le groupe est "suspect" (pages hors SEUIL_PAGE ou
# page invalide) et meme si la notice du doublon est "significative".
# L'original est retrouve automatiquement (meme logique identifier_original
# que pour les groupes confirmes). Ne pas mettre ici l'Id de l'original,
# uniquement celui du doublon a rapatrier/supprimer.


A_FUSIONNER_DIRECT = [
"19863","19862","19861","19860","19859","19858","19857","19856",
"19855","19854","19853","19852","19851","19850","19849","19848",
"19847","19846","19933","19932","19931","19930","19929","19928",
"19927","19926","19925","19924","20364","20363","20362","20361",
"20360","20359","23314","23313","23312","23311","23310","23309",
"23308","23307","24914","24913","34626","34625","34624","34623",
"34622","34621","34620","34619","34618","34617","34616","34615",
"34614","34613","34612","34611","32341","32340","32339","32338",
"32337","32336","32335","32334","32333","32332","32331","32330"
]


SEP  = "=" * 70
SEP2 = "-" * 70

# ── Patterns notices non significatives (identiques a analyse_doublons.py) ───
PATTERNS = [
    r"notice\s*\(.*?\)\s*manquante",
    r"notice\s+non\s+(disponible|fournie)",
    r"notice\s+(manquante|absente)",
    r"notice\s+descriptive\s+(manquante|non\s+fournie)",
    r"notice\s+textuelle\s+non\s+fournie",
    r"notice\s+compl\S*\s+n.{0,2}est\s+pas\s+fourni",
    r"notice\s+non\s+disponible\s+via\s+ocr",
    r"notice\s+pour\s+le\s+lot\s+\w+",
    r"notice\s+non\s+fournie.*",
    r"texte\s+de\s+la\s+notice\s+non\s+fourni[e]?",
    r"description\s+manquante",
    r"description\s+(du\s+lot\s+)?non\s+(disponible|fournie)",
    r"illustration\s+manquante",
    r"aucune\s+description\s+textuelle\s+fournie\s+pour\s+ce\s+lot",
    r"description\s+textuelle\s+du\s+lot\s+\d+\s+non\s+fournie(?:\s+dans\s+le\s+prompt)?",
    r"description\s+textuelle\s+(du\s+lot\s+)?(non\s+(disponible|fournie)|manquante|n.a\s+pas\s+\S*\s+fourni[e]?)",
    r"description\s+textuelle\s+non\s+fournie",
    r"pas\s+de\s+description\s+textuelle\s+fournie",
    r"aucune\s+description\s+textuelle\s+.*?n.a\s+\S*\s+fourni",
    r"aucune\s+notice\s+(textuelle|descriptive)\s+(fournie|n.est\s+fournie)",
    r"aucune\s+description\s+(textuelle\s+)?n.est\s+fournie",
    r"lot\s+non\s+d.{0,3}crit\s+textuellement",
    r"information\s+manquante",
    r"information\s+non\s+disponible",
    r"la\s+description\s+textuelle\s+de\s+ce\s+lot\s+n.a\s+pas\s+\S*\s+fourni[e]?",
    r"^manquant[e]?\.?$",
    r"^absent[e]?\.?$",
    r"^[aà]\s+compl[eé]ter\.?$",
]
RE_NON_SIG  = re.compile("|".join(PATTERNS), re.IGNORECASE)
RE_NUM_SEUL = re.compile(r"^(lot\s+)?\d+\s*$", re.IGNORECASE)

# ── Fonctions utilitaires ─────────────────────────────────────────────────────

def est_vide(v) -> bool:
    return pd.isna(v) or str(v).strip() == ""

def nb_champs_remplis(row) -> int:
    return sum(1 for v in row if not est_vide(v))

def nettoyer(val) -> str:
    s = str(val)
    for old, new in [("\ufeff", ""), ("\r", ""), ("\u00a0", " "), ("\u202f", " ")]:
        s = s.replace(old, new)
    return s.strip()

def to_page(val) -> int | None:
    """Convertit une valeur en entier de page. Retourne None si invalide."""
    s = str(val).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None

def pages_proches(p1, p2, seuil: int) -> bool | None:
    if p1 is None or p2 is None:
        return None
    return abs(p1 - p2) <= seuil

def identifier_original(grp: pd.DataFrame) -> int:
    """Index pandas de la ligne designee comme originale dans un groupe."""
    candidats = grp[grp["Titre_lot"].str.strip() != ""]
    if candidats.empty:
        candidats = grp
    return candidats.apply(nb_champs_remplis, axis=1).idxmax()

def classer_notice(val) -> str:
    if est_vide(val):
        return "vide"
    t = nettoyer(val)
    if not t:
        return "vide"
    return "non_sig" if (RE_NON_SIG.search(t) or RE_NUM_SEUL.match(t)) else "significative"

def decomposer_pipe(valeur: str) -> list[str]:
    """
    Eclate une cellule multi-valuee separee par '|' en liste de tokens non vides.
    Ex: "37|38" -> ["37", "38"]
        "37"    -> ["37"]
        ""      -> []
    """
    return [v.strip() for v in str(valeur).split("|") if v.strip()]

def fusionner_pages(vals: list[str]) -> str:
    """
    Fusionne une liste de valeurs de Numero_page_pdf (potentiellement
    multi-valuees elles-memes) en une seule chaine triee numeriquement.
    Les valeurs non numeriques sont ignorees.
    Ex: ["37|38", "40", "37"] -> "37|38|40"
    """
    pages = set()
    for v in vals:
        for token in decomposer_pipe(v):
            p = to_page(token)
            if p is not None:
                pages.add(p)
    return "|".join(str(p) for p in sorted(pages))

def fusionner_liens(vals: list[str]) -> str:
    """
    Fusionne une liste de valeurs de Lien_page_arkindex (potentiellement
    multi-valuees) en preservant l'ordre d'apparition et sans doublons.
    L'ordre global suit l'ordre numerique des pages associees — mais comme
    on ne peut pas toujours faire le lien page<->lien, on preserve simplement
    l'ordre dans lequel les liens apparaissent (original en premier).
    Ex: ["urlA|urlB", "urlB", "urlC"] -> "urlA|urlB|urlC"
    """
    vus = set()
    resultat = []
    for v in vals:
        for token in decomposer_pipe(v):
            if token not in vus:
                vus.add(token)
                resultat.append(token)
    return "|".join(resultat)

def fusionner_ligne_dans_original(df_out: pd.DataFrame, idx_original: int, idx_dup: int) -> tuple[str, str, str, str]:
    """
    Fusionne les champs Numero_page_pdf et Lien_page_arkindex de la ligne
    idx_dup dans la ligne idx_original (in place dans df_out), en suivant la
    logique standard (union triee des pages, union ordonnee dedupliquee des
    liens). Retourne (page_orig, nouvelle_page, lien_orig, nouveau_lien) pour
    les besoins d'affichage/rapport.
    """
    page_orig = df_out.loc[idx_original, "Numero_page_pdf"]
    page_dup  = df_out.loc[idx_dup, "Numero_page_pdf"]
    nouvelle_page = fusionner_pages([page_orig, page_dup])

    p_orig = to_page(page_orig) if to_page(page_orig) is not None else float("inf")
    p_dup  = to_page(page_dup)  if to_page(page_dup)  is not None else float("inf")

    lien_orig = df_out.loc[idx_original, "Lien_page_arkindex"]
    lien_dup  = df_out.loc[idx_dup, "Lien_page_arkindex"]

    contributions_liens = (
        [(p_orig, lien_orig), (p_dup, lien_dup)]
        if p_orig <= p_dup
        else [(p_dup, lien_dup), (p_orig, lien_orig)]
    )
    nouveau_lien = fusionner_liens([v for _, v in contributions_liens])

    df_out.at[idx_original, "Numero_page_pdf"]    = nouvelle_page
    df_out.at[idx_original, "Lien_page_arkindex"] = nouveau_lien

    return page_orig, nouvelle_page, lien_orig, nouveau_lien


# ── Chargement ────────────────────────────────────────────────────────────────
print()
print(SEP)
print("CHARGEMENT DU FICHIER CSV")


df = pd.read_csv(INPUT_CSV, sep=";", encoding="utf-8-sig", dtype=str, low_memory=False)
print(f"-> {len(df)} lignes chargees")

for col in ["Numero_lot", "Identifiant_catalogue", "Titre_lot",
            "Lien_page_arkindex", "Numero_page_pdf", "Notice", "Id_perenne"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str).str.strip()

if "Notice" in df.columns:
    df["Notice"] = df["Notice"].apply(nettoyer)

# ── Exclusion des Id proteges ─────────────────────────────────────────────────
masque_exclus = df["Id_perenne"].isin(IDS_EXCLUS)
n_exclus = masque_exclus.sum()
print(f"-> {n_exclus} Id_perenne proteges mis de cote")
df_travail = df[~masque_exclus].copy()
print(f"-> {len(df_travail)} lignes dans le perimetre d'analyse")
print()

# ── Detection des groupes confirmes (logique identique a analyse_doublons.py) ─
print(SEP)
print("DETECTION DES DOUBLONS CONFIRMES")


groupes_confirmes = {}
n_ignores_page = 0

for cle, grp in df_travail.groupby(["Identifiant_catalogue", "Numero_lot"]):
    if len(grp) < 2:
        continue
    indices = list(grp.index)
    pages   = {idx: to_page(grp.loc[idx, "Numero_page_pdf"]) for idx in indices}

    resultats_paires = []
    for i1, i2 in combinations(indices, 2):
        resultats_paires.append(pages_proches(pages[i1], pages[i2], SEUIL_PAGE))

    if all(r is None for r in resultats_paires):
        n_ignores_page += len(grp) * (len(grp) - 1) // 2
        continue
    # On ne retient que les groupes confirmes (pas les suspects)
    if not any(r is False for r in resultats_paires):
        groupes_confirmes[cle] = grp

print(f"Groupes confirmes detectes  : {len(groupes_confirmes)}")
print(f"Paires ignorees (page vide) : {n_ignores_page}")
print()

# ── Preparation de la fusion ──────────────────────────────────────────────────
# On travaille sur une copie de df (la version complete avec les Id exclus,
# pour ne pas les perdre dans le fichier de sortie).
df_out = df.copy()

# Index des lignes a supprimer a la fin
indices_a_supprimer = set()

# Compteurs pour le rapport
n_fusions_effectuees  = 0   # doublons vide/non_sig fusionnes et supprimes
n_fusions_ignorees    = 0   # doublons significatifs, laisses en place
n_fusions_forcees     = 0   # doublons fusionnes via A_FUSIONNER_DIRECT
n_forces_introuvables = 0   # Id de A_FUSIONNER_DIRECT non trouves dans le CSV
lignes_rapport        = []  # detail des operations pour le .txt

print(SEP)
print("APPLICATION DES FUSIONS")

print()

for cle, grp in groupes_confirmes.items():
    catalogue, numero_lot = cle
    idx_original = identifier_original(grp)
    id_original  = df_out.loc[idx_original, "Id_perenne"]
    lignes_doublons = grp.drop(index=idx_original)

    for idx_dup, row_dup in lignes_doublons.iterrows():
        cat = classer_notice(row_dup["Notice"])
        id_dup = row_dup["Id_perenne"]

        if cat == "significative":
            # Notice reelle : on ne touche a rien, on signale
            n_fusions_ignorees += 1
            msg = (f"  [IGNORE]  Id={id_dup} (notice significative) "
                   f"-> doublon de {id_original}, conserve tel quel")
            print(msg)
            lignes_rapport.append(msg)
            continue

        # Notice vide ou non_sig : on fusionne
        page_orig, nouvelle_page, lien_orig, nouveau_lien = fusionner_ligne_dans_original(
            df_out, idx_original, idx_dup
        )

        indices_a_supprimer.add(idx_dup)
        n_fusions_effectuees += 1

        msg = (f"  [FUSIONNE] Id={id_dup} [{cat}] -> original={id_original} "
               f"| pages: '{page_orig}'->'{nouvelle_page}' "
               f"| liens: '{lien_orig}'->'{nouveau_lien}'")
        print(msg)
        lignes_rapport.append(msg)

print()
print(f"Fusions effectuees (vide/non_sig supprimes) : {n_fusions_effectuees}")
print(f"Doublons conserves (notice significative)   : {n_fusions_ignorees}")
print()

# ── Fusions forcees (A_FUSIONNER_DIRECT) ──────────────────────────────────────
# Independant de la detection automatique : ces Id_perenne sont fusionnes
# avec l'original de leur groupe quel que soit le statut (suspect ou
# confirme) et quel que soit le contenu de la notice.

print("FUSIONS FORCEES (A_FUSIONNER_DIRECT)")

print()

if A_FUSIONNER_DIRECT:
    # Index Id_perenne -> position pandas, pour retrouver rapidement une ligne.
    # Reste valide tout au long du traitement : seules les VALEURS des
    # cellules changent, les lignes ne sont retirees qu'a la toute fin.
    index_par_id = {}
    for idx, id_p in df_out["Id_perenne"].items():
        index_par_id.setdefault(id_p, idx)

    for id_dup in A_FUSIONNER_DIRECT:
        if id_dup not in index_par_id:
            n_forces_introuvables += 1
            msg = f"  [INTROUVABLE] Id={id_dup} (A_FUSIONNER_DIRECT) -> ignore, on continue"
            print(msg)
            lignes_rapport.append(msg)
            continue

        idx_dup = index_par_id[id_dup]

        if idx_dup in indices_a_supprimer:
            # Deja fusionne par la detection automatique (groupe confirme,
            # notice vide/non_sig) : rien a refaire.
            msg = f"  [DEJA_FUSIONNE] Id={id_dup} (A_FUSIONNER_DIRECT) -> deja traite, on continue"
            print(msg)
            lignes_rapport.append(msg)
            continue

        catalogue = df_out.loc[idx_dup, "Identifiant_catalogue"]
        numero_lot = df_out.loc[idx_dup, "Numero_lot"]

        # Groupe "vivant" (on exclut les lignes deja marquees pour suppression)
        masque_grp = (
            (df_out["Identifiant_catalogue"] == catalogue)
            & (df_out["Numero_lot"] == numero_lot)
            & (~df_out.index.isin(indices_a_supprimer))
        )
        grp = df_out[masque_grp]

        candidats_original = grp.drop(index=idx_dup, errors="ignore")
        if candidats_original.empty:
            n_forces_introuvables += 1
            msg = (f"  [ATTENTION] Id={id_dup} (A_FUSIONNER_DIRECT) : aucune autre "
                   f"ligne dans le groupe {catalogue}|{numero_lot} -> ignore, on continue")
            print(msg)
            lignes_rapport.append(msg)
            continue

        idx_original = identifier_original(candidats_original)
        id_original = df_out.loc[idx_original, "Id_perenne"]

        page_orig, nouvelle_page, lien_orig, nouveau_lien = fusionner_ligne_dans_original(
            df_out, idx_original, idx_dup
        )

        indices_a_supprimer.add(idx_dup)
        n_fusions_forcees += 1

        msg = (f"  [FUSION_FORCEE] Id={id_dup} -> original={id_original} "
               f"groupe={catalogue}|{numero_lot} "
               f"| pages: '{page_orig}'->'{nouvelle_page}' "
               f"| liens: '{lien_orig}'->'{nouveau_lien}'")
        print(msg)
        lignes_rapport.append(msg)
else:
    print("  (A_FUSIONNER_DIRECT est vide, aucune fusion forcee)")

print()
print(f"Fusions forcees effectuees      : {n_fusions_forcees}")
print(f"Id A_FUSIONNER_DIRECT introuvables : {n_forces_introuvables}")
print()

# ── Suppression des lignes fusionnees ─────────────────────────────────────────
n_avant = len(df_out)
df_out = df_out.drop(index=list(indices_a_supprimer)).reset_index(drop=True)
n_apres = len(df_out)

print(f"Lignes avant suppression : {n_avant}")
print(f"Lignes apres suppression : {n_apres}")
print(f"Lignes supprimees        : {n_avant - n_apres}")
print()

# ── Export ────────────────────────────────────────────────────────────────────

print("EXPORT")


ts = datetime.now().strftime("%Y%m%d_%H%M%S")

# CSV fusionne
out_csv = OUTPUT_DIR / f"lots_fusionnes_{ts}.csv"
df_out.to_csv(out_csv, sep=";", index=False, encoding="utf-8-sig")
print(f"  CSV fusionne : {out_csv}")

# Rapport texte
out_txt = OUTPUT_DIR / f"rapport_fusion_{ts}.txt"
contenu_rapport = (
    f"RAPPORT DE FUSION DES DOUBLONS\n{SEP}\n\n"
    f"Genere le              : {datetime.now().strftime('%d/%m/%Y a %H:%M:%S')}\n"
    f"Fichier source         : {INPUT_CSV}\n"
    f"Seuil proximite page   : +- {SEUIL_PAGE}\n\n"
    f"Groupes confirmes      : {len(groupes_confirmes)}\n"
    f"Fusions effectuees     : {n_fusions_effectuees}  (doublons vide/non_sig supprimes)\n"
    f"Doublons conserves     : {n_fusions_ignorees}  (notice significative, a traiter manuellement)\n"
    f"Fusions forcees        : {n_fusions_forcees}  (A_FUSIONNER_DIRECT)\n"
    f"Id forces introuvables : {n_forces_introuvables}\n\n"
    f"Lignes source          : {n_avant}\n"
    f"Lignes apres fusion    : {n_apres}\n"
    f"Lignes supprimees      : {n_avant - n_apres}\n\n"
    f"{SEP2}\n"
    f"DETAIL DES OPERATIONS\n"
    f"{SEP2}\n\n"
    + "\n".join(lignes_rapport) + "\n"
)
out_txt.write_text(contenu_rapport, encoding="utf-8")
print(f"  Rapport      : {out_txt}")
print()


# ============================================================
# RECAPITULATIF DU FONCTIONNEMENT
#
# 1. CHARGEMENT
#    Meme logique qu'analyse_doublons.py : CSV en utf-8-sig, tout en str,
#    nettoyage des colonnes utiles.
#
# 2. EXCLUSION DES IDS PROTEGES
#    Les lignes dont l'Id_perenne est dans IDS_EXCLUS sont mises de cote
#    pour l'analyse, mais CONSERVEES dans df_out (elles apparaitront
#    normalement dans le CSV de sortie).
#
# 3. DETECTION DES GROUPES CONFIRMES
#    Identique a analyse_doublons.py :
#      - meme Identifiant_catalogue + meme Numero_lot
#      - toutes les paires valides a +- SEUIL_PAGE pages
#    Les suspects et les groupes avec pages invalides sont ignores ICI,
#    mais peuvent malgre tout etre traites via A_FUSIONNER_DIRECT (etape 4bis).
#
# 4. FUSION AUTOMATIQUE (pour chaque doublon d'un groupe confirme)
#    Pour chaque doublon dont la notice est "vide" ou "non_sig" :
#
#    a) Numero_page_pdf :
#       On decompose les valeurs existantes (en cas de "|" deja present),
#       on fait l'union de tous les entiers, on retrie par ordre croissant,
#       on rejoint avec "|".
#       Ex: original="37|38", doublon="40" -> "37|38|40"
#
#    b) Lien_page_arkindex :
#       On collecte les liens de l'original et du doublon dans l'ordre
#       page croissante (le lien de la page la plus petite en premier).
#       On deduplication stricte : un lien deja present n'est pas ajoute.
#       On rejoint avec "|".
#       Ex: original="urlA", doublon="urlB" (page doublon > page original)
#           -> "urlA|urlB"
#
#    Si la notice du doublon est "significative" :
#       On ne touche a rien. La ligne doublon est conservee dans le CSV
#       de sortie et signalee dans le rapport pour traitement manuel.
#
# 4bis. FUSIONS FORCEES (A_FUSIONNER_DIRECT)
#    Pour chaque Id_perenne de doublon liste dans A_FUSIONNER_DIRECT :
#      - Si l'Id est introuvable dans le CSV -> print + on continue.
#      - Si l'Id a deja ete fusionne a l'etape 4 (groupe confirme +
#        notice vide/non_sig) -> on ne refait rien, on continue.
#      - Sinon : on retrouve le groupe (meme Identifiant_catalogue +
#        Numero_lot) parmi les lignes encore "vivantes" (pas deja
#        supprimees), on identifie l'original (identifier_original),
#        puis on fusionne EXACTEMENT comme a l'etape 4 (union pages,
#        union liens) — que la notice soit significative ou non, et
#        que le groupe soit suspect ou confirme.
#
# 5. SUPPRESSION
#    Toutes les lignes doublons fusionnees (etape 4 + etape 4bis) sont
#    supprimees du DataFrame. Le CSV de sortie a donc moins de lignes que
#    la source.
#
# 6. EXPORT
#    - "lots_fusionnes_*.csv"  : fichier complet apres fusion, meme structure
#      que le fichier source (toutes colonnes conservees, meme ordre).
#    - "rapport_fusion_*.txt"  : detail de chaque operation (fusionne/ignore/
#      fusion forcee) avec les valeurs avant/apres pour Numero_page_pdf et
#      Lien_page_arkindex.

print(SEP)
print("FUSION TERMINEE")
print(SEP)
