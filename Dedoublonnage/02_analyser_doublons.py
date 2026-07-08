"""
Analyse des doublons dans le fichier CSV de lots de vente.

Regles de detection (les TROIS conditions doivent etre vraies) :
  1. Meme Identifiant_catalogue
  2. Meme Numero_lot
  3. Numero_page_pdf a +- SEUIL_PAGE pages d'ecart entre les deux lignes

Cas particuliers :
  - Si une des deux pages est vide ou non numerique -> IGNORE (on ne peut pas conclure)
  - Si catalogue + numero_lot matchent mais pages a > SEUIL_PAGE -> SUSPECT (signale separement)

Phase 1 : identification des groupes confirmes + collecte des suspects
Phase 2 : analyse du champ Notice des lignes dupliquees confirmees
"""

import pandas as pd
import re
from pathlib import Path
from datetime import datetime
from itertools import combinations

# ── Chemins ───────────────────────────────────────────────────────────────────
INPUT_CSV = Path("chemin_du_csv")
OUTPUT_DIR = Path("chemin_du_dossier")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Seuil de proximite de page ────────────────────────────────────────────────
# Deux lignes sont doublons confirmes seulement si |page_A - page_B| <= SEUIL_PAGE.
# Au-dela, elles passent en section SUSPECTS.
SEUIL_PAGE = 2

# ── Id_perenne a exclure de toute l'analyse ───────────────────────────────────
# Ces lots sont proteges : ils ne peuvent pas etre designes comme doublons
# ni comme originaux. Si un groupe ne contient QUE des Id exclus, il disparait.
# Si un groupe contient des Id exclus ET des Id normaux, seuls les Id exclus
# sont retires ; le groupe subsiste s'il reste >= 2 lignes normales.
IDS_EXCLUS = {
    # Couvertures introductives
    "39848", "38942", "36703", "44142", "38866", "25047",
    "18155", "16448", "11787", "10709", "9210", "11727", "11728",
    # Publicites pour prochaines ventes
    "56874", "56873", "41639", "39531", "4040", "4039",
    # Id specifique (statut incertain)
    "47384",
}

SEP  = "=" * 70
SEP2 = "-" * 70

# ── Patterns notices non significatives ──────────────────────────────────────
# Chaque pattern correspond a une formule-type produite par l'OCR ou le LLM
# qui ne constitue pas une vraie description du lot.
PATTERNS = [
    # -- Formules "notice manquante / non fournie" -------------------------
    r"notice\s*\(.*?\)\s*manquante",
    r"Notice non disponible.",
    r"notice\s+non\s+(disponible|fournie)",
    r"notice\s+(manquante|absente)",
    r"notice\s+descriptive\s+(manquante|non\s+fournie)",
    r"notice\s+textuelle\s+non\s+fournie",
    r"notice\s+compl\S*\s+n.{0,2}est\s+pas\s+fourni",
    r"notice\s+non\s+disponible\s+via\s+ocr",
    r"notice\s+pour\s+le\s+lot\s+\w+",
    # "Notice non fournie" suivi de n'importe quoi (blabla LLM)
    r"notice\s+non\s+fournie.*",
    # -- Formules "texte / description manquant(e)" ------------------------
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
    # -- Formules "information manquante" ----------------------------------
    r"information\s+manquante",
    r"information\s+non\s+disponible",
    r"la\s+description\s+textuelle\s+de\s+ce\s+lot\s+n.a\s+pas\s+\S*\s+fourni[e]?",
    # -- Formules courtes (champ rempli d'un placeholder) -----------------
    r"^manquant[e]?\.?$",
    r"^absent[e]?\.?$",
    # "A completer" / "a completer" / "A Completer" etc. (seul dans le champ)
    r"^[aà]\s+compl[eé]ter\.?$",
]
RE_NON_SIG  = re.compile("|".join(PATTERNS), re.IGNORECASE)
RE_NUM_SEUL = re.compile(r"^(lot\s+)?\d+\s*$", re.IGNORECASE)

# ── Fonctions utilitaires ─────────────────────────────────────────────────────

def est_vide(v) -> bool:
    """Retourne True si la valeur est NaN ou une chaine vide."""
    return pd.isna(v) or str(v).strip() == ""

def nb_champs_remplis(row) -> int:
    """Compte le nombre de champs non vides dans une ligne."""
    return sum(1 for v in row if not est_vide(v))

def nettoyer(val) -> str:
    """Strip + suppression des caracteres parasites (BOM, NBSP, retours chariot)."""
    s = str(val)
    for old, new in [("\ufeff", ""), ("\r", ""), ("\u00a0", " "), ("\u202f", " ")]:
        s = s.replace(old, new)
    return s.strip()

def to_page(val) -> int | None:
    """
    Convertit Numero_page_pdf en entier.
    Retourne None si la valeur est vide ou non numerique.
    """
    s = str(val).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None

def pages_proches(p1, p2, seuil: int) -> bool | None:
    """
    Compare deux numeros de page.
    Retourne :
      True  -> |p1 - p2| <= seuil  (doublon confirme)
      False -> |p1 - p2| >  seuil  (suspect)
      None  -> au moins une page est invalide (ignore)
    """
    if p1 is None or p2 is None:
        return None
    return abs(p1 - p2) <= seuil

def identifier_original(grp: pd.DataFrame) -> int:
    """
    Choisit l'index pandas de la ligne "originale" dans un groupe.
    Critere : celle qui a un Titre_lot non vide ET le plus de champs remplis.
    En cas d'egalite, on prend la premiere.
    """
    candidats = grp[grp["Titre_lot"].str.strip() != ""]
    if candidats.empty:
        candidats = grp
    return candidats.apply(nb_champs_remplis, axis=1).idxmax()

def classer_notice(val) -> str:
    """
    Classe la notice en trois categories :
      'vide'          -> NaN ou chaine vide
      'non_sig'       -> formule-placeholder (patterns ci-dessus ou numero seul)
      'significative' -> contenu reel
    """
    if est_vide(val):
        return "vide"
    t = nettoyer(val)
    if not t:
        return "vide"
    return "non_sig" if (RE_NON_SIG.search(t) or RE_NUM_SEUL.match(t)) else "significative"


# ── Chargement ────────────────────────────────────────────────────────────────
print()
print(SEP)
print("CHARGEMENT DU FICHIER CSV")

df = pd.read_csv(INPUT_CSV, sep=";", encoding="utf-8-sig", dtype=str, low_memory=False)
print(f"-> {len(df)} lignes chargees")
print(f"-> Colonnes : {list(df.columns)}")
print()

# Nettoyage des colonnes utiles (strip, NaN -> "")
for col in ["Numero_lot", "Identifiant_catalogue", "Titre_lot",
            "Lien_page_arkindex", "Numero_page_pdf", "Notice", "Id_perenne"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str).str.strip()

if "Notice" in df.columns:
    df["Notice"] = df["Notice"].apply(nettoyer)

# ── Exclusion des Id proteges ─────────────────────────────────────────────────
masque_exclus = df["Id_perenne"].isin(IDS_EXCLUS)
n_exclus = masque_exclus.sum()
print(f"Id_perenne proteges trouves dans le fichier et mis de cote : {n_exclus}")
df_travail = df[~masque_exclus].copy()
print(f"Lignes restantes pour l'analyse                            : {len(df_travail)}")
print()


# ── Phase 1 — Identification des groupes de doublons ─────────────────────────
print("PHASE 1 — IDENTIFICATION DES GROUPES DE DOUBLONS")
print(f"Criteres : meme Identifiant_catalogue + meme Numero_lot + pages a +- {SEUIL_PAGE}")
print()

# On pre-groupe par (catalogue, numero_lot) — criteres 1 et 2.
# Pour chaque pre-groupe de >= 2 lignes, on applique ensuite la regle de page.
CLE = ["Identified_catalogue", "Numero_lot"]

groupes_confirmes = {}   # cle -> DataFrame  (doublon confirme, toutes pages valides et proches)
groupes_suspects  = {}   # cle -> DataFrame  (catalogue+lot matchent, mais pages trop eloignees)
# Note : les pre-groupes avec une page invalide sont silencieusement ignores.

n_ignores_page = 0  # compteur de paires ignorees faute de page numerique

for cle, grp in df_travail.groupby(["Identifiant_catalogue", "Numero_lot"]):
    if len(grp) < 2:
        continue

    indices = list(grp.index)

    # Pour les groupes de taille > 2, on verifie toutes les paires.
    # Un groupe est "confirme" si TOUTES ses paires passent le filtre page.
    # Un groupe est "suspect" si AU MOINS UNE paire echoue le filtre page
    # (et aucune page n'est invalide pour cette paire).
    # Un groupe est "ignore" si AU MOINS UNE paire a une page invalide
    # ET qu'il n'y a pas par ailleurs de paire confirmee.

    pages = {idx: to_page(grp.loc[idx, "Numero_page_pdf"]) for idx in indices}

    resultats_paires = []  # True / False / None pour chaque paire
    for i1, i2 in combinations(indices, 2):
        resultats_paires.append(pages_proches(pages[i1], pages[i2], SEUIL_PAGE))

    # Si toutes les paires sont None -> on ne peut rien conclure, on ignore
    if all(r is None for r in resultats_paires):
        n_ignores_page += len(grp) * (len(grp) - 1) // 2
        continue

    # Si au moins une paire est False (ecart trop grand, pages valides) -> suspect
    # Sinon (toutes True ou melange True/None) -> confirme
    if any(r is False for r in resultats_paires):
        groupes_suspects[cle] = grp
    else:
        groupes_confirmes[cle] = grp

nb_confirmes = len(groupes_confirmes)
nb_suspects  = len(groupes_suspects)
nb_en_trop   = sum(len(v) - 1 for v in groupes_confirmes.values())
nb_total     = len(df_travail)

print(f"Groupes confirmes (toutes conditions OK)       : {nb_confirmes}")
print(f"Groupes suspects  (pages trop eloignees)       : {nb_suspects}")
print(f"Paires ignorees   (page vide ou non numerique) : {n_ignores_page}")
print(f"Lignes totales dans le perimetre d'analyse     : {nb_total}")
print(f"Lignes en trop (a supprimer apres fusion)      : {nb_en_trop}")
print(f"Lignes attendues apres fusion                  : {nb_total - nb_en_trop}")
print()

# Designation des originaux et doublons dans les groupes confirmes
ids_doublons      = []
map_original      = {}
originaux_par_cle = {}

for cle, grp in groupes_confirmes.items():
    idx_original = identifier_original(grp)
    id_original  = grp.loc[idx_original, "Id_perenne"]
    originaux_par_cle[cle] = id_original

    ids_grp = grp.drop(index=idx_original)["Id_perenne"].tolist()
    ids_doublons.extend(ids_grp)
    for id_dup in ids_grp:
        map_original[id_dup] = id_original

print(f"Lignes non-originales identifiees : {len(ids_doublons)}")
print()


# ── Phase 2 — Analyse du champ Notice des doublons confirmes ─────────────────

print("PHASE 2 — ANALYSE DU CHAMP NOTICE DES LIGNES DUPLIQUEES (CONFIRMES)")


df_dup = df_travail[df_travail["Id_perenne"].isin(ids_doublons)].copy()
df_dup["cat_notice"]  = df_dup["Notice"].apply(classer_notice)
df_dup["id_original"] = df_dup["Id_perenne"].map(map_original)
cpt = df_dup["cat_notice"].value_counts()

print(f"Total de lignes-doublons analysees              : {len(df_dup)}")
print(f"  -> Notices SIGNIFICATIVES (contenu reel)       : {cpt.get('significative', 0)}")
print(f"  -> Notices NON SIGNIFICATIVES (formules vides) : {cpt.get('non_sig', 0)}")
print(f"  -> Notices VIDES (NaN / chaine vide)           : {cpt.get('vide', 0)}")
print()

# ── Detail des groupes confirmes ──────────────────────────────────────────────

print(f"DETAIL DES {nb_confirmes} GROUPES CONFIRMES")


for cle, grp in groupes_confirmes.items():
    catalogue, numero_lot = cle
    id_original    = originaux_par_cle[cle]
    ligne_original = grp[grp["Id_perenne"] == id_original].iloc[0]
    lignes_doublons = grp[grp["Id_perenne"] != id_original]

    print()
    print(f"Groupe : catalogue={catalogue}  |  numero_lot={numero_lot}  "
          f"|  {len(grp)} ligne(s) au total")

    notice_orig  = str(ligne_original["Notice"]).replace("\n", " | ")
    extrait_orig = notice_orig[:200] + ("..." if len(notice_orig) > 200 else "")
    cat_orig     = classer_notice(ligne_original["Notice"])
    page_orig    = ligne_original.get("Numero_page_pdf", "")
    print(
        f"  [ORIGINAL]  Id_perenne   : {ligne_original['Id_perenne']}\n"
        f"              Titre_lot    : {ligne_original['Titre_lot']}\n"
        f"              Page PDF     : {page_orig}\n"
        f"              Notice       : [{cat_orig}] {extrait_orig}"
    )

    for _, row in lignes_doublons.iterrows():
        cat     = classer_notice(row["Notice"])
        notice  = str(row["Notice"]).replace("\n", " | ")
        extrait = notice[:200] + ("..." if len(notice) > 200 else "")
        page    = row.get("Numero_page_pdf", "")
        ecart   = ""
        p1 = to_page(page_orig)
        p2 = to_page(page)
        if p1 is not None and p2 is not None:
            ecart = f"  (ecart page : {abs(p1 - p2)})"

        print(
            f"  [DOUBLON]   Id_perenne   : {row['Id_perenne']}\n"
            f"              Titre_lot    : {row['Titre_lot']}\n"
            f"              Page PDF     : {page}{ecart}\n"
            f"              Notice       : [{cat}] {extrait}\n"
            f"              -> Double l'original : {id_original} "
            f"(notice originale : [{cat_orig}] {extrait_orig[:80]}{'...' if len(extrait_orig) > 80 else ''})"
        )
print()

# ── Detail des groupes suspects ───────────────────────────────────────────────
if groupes_suspects:

    print(f"GROUPES SUSPECTS ({nb_suspects}) — meme catalogue + meme lot, pages trop eloignees")
    print(f"  (seuil depasse : ecart > {SEUIL_PAGE} pages — a verifier manuellement)")


    for cle, grp in groupes_suspects.items():
        catalogue, numero_lot = cle
        print()
        print(f"  Suspect : catalogue={catalogue}  |  numero_lot={numero_lot}  "
              f"|  {len(grp)} ligne(s)")
        for _, row in grp.iterrows():
            cat    = classer_notice(row["Notice"])
            notice = str(row["Notice"]).replace("\n", " | ")
            extrait = notice[:120] + ("..." if len(notice) > 120 else "")
            print(
                f"    Id_perenne : {row['Id_perenne']}\n"
                f"    Page PDF   : {row.get('Numero_page_pdf', '')}\n"
                f"    Titre_lot  : {row['Titre_lot']}\n"
                f"    Notice     : [{cat}] {extrait}"
            )
    print()


# ── Export ────────────────────────────────────────────────────────────────────
print(SEP)
print("EXPORT DES RESULTATS")


ts = datetime.now().strftime("%Y%m%d_%H%M%S")

# CSV des doublons confirmes avec categorie de notice
cols_export = [c for c in [
    "Id_perenne", "id_original", "Identifiant_catalogue", "Numero_lot",
    "Numero_page_pdf", "Lien_page_arkindex", "Titre_lot", "Notice", "cat_notice",
] if c in df_dup.columns]

out_csv = OUTPUT_DIR / f"doublons_analyses_{ts}.csv"
df_dup[cols_export].to_csv(out_csv, sep=";", index=False, encoding="utf-8-sig")
print(f"  CSV doublons confirmes : {out_csv}")

# CSV des suspects
if groupes_suspects:
    df_suspects = pd.concat(groupes_suspects.values())
    out_csv_susp = OUTPUT_DIR / f"doublons_suspects_{ts}.csv"
    cols_susp = [c for c in [
        "Id_perenne", "Identifiant_catalogue", "Numero_lot",
        "Numero_page_pdf", "Lien_page_arkindex", "Titre_lot", "Notice",
    ] if c in df_suspects.columns]
    df_suspects[cols_susp].to_csv(out_csv_susp, sep=";", index=False, encoding="utf-8-sig")
    print(f"  CSV suspects           : {out_csv_susp}")

# Resume texte
out_txt = OUTPUT_DIR / f"resume_doublons_{ts}.txt"
out_txt.write_text(
    f"RESUME DE L'ANALYSE DES DOUBLONS\n{SEP}\n\n"
    f"Id_perenne proteges (exclus de l'analyse)  : {n_exclus}\n"
    f"Lignes dans le perimetre d'analyse         : {nb_total}\n"
    f"Seuil de proximite de page                 : +- {SEUIL_PAGE}\n\n"
    f"Groupes confirmes (toutes conditions OK)   : {nb_confirmes}\n"
    f"Groupes suspects  (pages trop eloignees)   : {nb_suspects}\n"
    f"Paires ignorees   (page invalide)          : {n_ignores_page}\n\n"
    f"Lignes en trop (a supprimer apres fusion)  : {nb_en_trop}\n"
    f"Lignes attendues apres fusion              : {nb_total - nb_en_trop}\n\n"
    f"-- Notice des lignes dupliquees confirmees --\n"
    f"  Significatives         : {cpt.get('significative', 0)}\n"
    f"  Non significatives     : {cpt.get('non_sig', 0)}\n"
    f"  Vides                  : {cpt.get('vide', 0)}\n",
    encoding="utf-8",
)
print(f"  Resume texte           : {out_txt}")
print()



# 1. CHARGEMENT
#    Le CSV est lu avec pandas (encodage utf-8-sig, separateur ";", tout en str).
#    Les colonnes utiles sont nettoyees : NaN -> "", strip des espaces.
#    La colonne Notice passe aussi par nettoyer() pour supprimer BOM,
#    retours chariot et espaces insecables.
#
# 2. EXCLUSION DES IDS PROTEGES
#    Les lignes dont l'Id_perenne figure dans IDS_EXCLUS sont ecartees
#    avant toute analyse. Elles ne peuvent etre ni originales ni doublons.
#    Si un groupe contient un Id exclu ET des Ids normaux, seule la ligne
#    exclue est retiree ; le groupe subsiste si >= 2 lignes normales restent.
#
# 3. DETECTION DES GROUPES DE DOUBLONS (Phase 1)
#    Trois conditions cumulatives pour qu'un groupe soit "confirme" :
#      a) Meme Identifiant_catalogue
#      b) Meme Numero_lot
#      c) Numero_page_pdf a +- SEUIL_PAGE pages d'ecart entre toutes les paires
#
#    Cas particuliers traites pour chaque paire de lignes :
#      - Page vide ou non numerique des deux cotes -> paire IGNOREE
#        (on ne peut pas conclure ; si toutes les paires du groupe sont ignorees,
#         le groupe entier disparait)
#      - Pages valides mais ecart > SEUIL_PAGE -> groupe classe SUSPECT
#        (signale separement, pas comptabilise comme doublon confirme)
#      - Pages valides et ecart <= SEUIL_PAGE -> paire CONFIRMEE
#        (si toutes les paires valides du groupe sont confirmees, groupe CONFIRME)
#
#    Pour chaque groupe confirme, on designe un "original" :
#      - priorite aux lignes avec un Titre_lot non vide
#      - parmi celles-ci, on prend celle avec le plus de champs remplis
#      - en cas d'egalite, la premiere dans l'ordre du fichier
#    Toutes les autres lignes du groupe sont des "doublons".
#
# 4. CLASSIFICATION DES NOTICES (Phase 2)
#    Appliquee uniquement aux doublons confirmes.
#    Chaque notice est classee en trois categories :
#      - "vide"          : NaN ou chaine vide
#      - "non_sig"       : formule-placeholder (patterns regex) ou numero seul
#                          Inclut : "A completer", "Notice non fournie + blabla",
#                          et toutes les formules LLM repertoriees dans PATTERNS.
#      - "significative" : contenu reel (tout le reste)
#    La notice de l'original est aussi classifiee et affichee pour comparaison.
#
# 5. AFFICHAGE CONSOLE
#    Section A — Groupes confirmes :
#      Pour chaque groupe, la ligne [ORIGINAL] puis chaque [DOUBLON] avec :
#      Id_perenne, Titre_lot, Page PDF, Notice + categorie, ecart de page,
#      et rappel de l'original double (Id + extrait de notice).
#    Section B — Groupes suspects :
#      Liste des groupes ou catalogue + lot matchent mais pages trop eloignees.
#      Affiches pour verification manuelle, sans designation original/doublon.
#
# 6. EXPORT
#    - CSV horodate "doublons_analyses_*.csv" : lignes-doublons confirmees
#      avec categorie de notice et Id_perenne de leur original.
#    - CSV horodate "doublons_suspects_*.csv" : lignes des groupes suspects.
#    - TXT horodate "resume_doublons_*.txt"   : resume chiffre complet.
