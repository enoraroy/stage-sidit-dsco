
"""
Quantifie l'effet du dedoublonnage en comparant quatre fichiers,
correspondant aux quatre etapes successives du pipeline :

  1. ORIGINAL_CSV : le fichier brut de depart, avant tout dedoublonnage
     (pas de colonne Id_perenne).
  2. V1_CSV       : le fichier apres un premier dedoublonnage MANUEL
     (c'est le fichier reellement donne en entree a fusionner_doublons.py).
  3. AUTO_CSV     : le fichier apres dedoublonnage AUTOMATIQUE
     (sortie de fusionner_doublons.py, ex: lots_fusionnes_*.csv).
  4. FINAL_CSV    : le fichier apres dedoublonnage MANUEL final
     (sortie de appliquer_decisions_manuelles.py, ex:
     lots_decisions_appliquees_*.csv).

Les trois transitions successives sont donc :
  ORIGINAL_CSV -> V1_CSV    : dedoublonnage MANUEL (1er passage)
  V1_CSV       -> AUTO_CSV  : dedoublonnage AUTOMATIQUE
  AUTO_CSV     -> FINAL_CSV : dedoublonnage MANUEL (2eme passage)

RECAP STATISTIQUE (imprime dans la console) :
  - Nombre de lignes a chaque etape (original, v1, auto, final).
  - Nombre de lignes supprimees a chaque transition (les trois listees
    ci-dessus), avec les taux associes.
  - Nombre total supprime (manuel + automatique + manuel) et taux global.

  RECLASSEMENT A_FUSIONNER_DIRECT :
    Les Id_perenne listes dans A_FUSIONNER_DIRECT sont fusionnes par
    fusionner_doublons.py (donc disparaissent entre V1_CSV et AUTO_CSV),
    mais ce sont des decisions MANUELLES explicites (revue au cas par
    cas), pas des detections automatiques. On les retire donc du
    decompte "automatique" (V1_CSV -> AUTO_CSV) et on les ajoute au
    decompte manuel total, sans changer les totaux de lignes de chaque
    fichier.

GRAPHIQUES (deux fichiers PDF distincts) :
  Pour Maison_vente_ou_demandeur uniquement :
    A) Effectifs (nb de notices) avant vs apres dedoublonnage complet.
    B) Part relative (%) avant vs apres dedoublonnage complet.
  Diagrammes en batons groupes : une barre "avant" et une barre "apres"
  cote a cote pour chaque maison.

  Les maisons sont ordonnees par PERTE D'EFFECTIF (avant - apres), de la
  plus impactee par le dedoublonnage a la moins impactee.

  "Avant" = fichier original (ORIGINAL_CSV).
  "Apres" = fichier dedoublonne complet (FINAL_CSV).

SORTIE :
  Deux fichiers PDF distincts, dans le meme dossier que FINAL_CSV :
    - quantification_dedoublonnage_maison_effectifs.pdf
    - quantification_dedoublonnage_maison_pourcentage.pdf
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# ── Chemins ────────────────────────────────────────────────────────────────
ORIGINAL_CSV = Path("chemin_du_csv_original")

# Fichier de depart REEL de fusionner_doublons.py, obtenu apres un premier
# dedoublonnage manuel effectue sur ORIGINAL_CSV. Tout ce qui a disparu
# entre ORIGINAL_CSV et V1_CSV releve donc d'un traitement MANUEL, pas de
# la detection automatique.
V1_CSV = Path("chemin_du_premier_csv_avant_traitement_auto")
AUTO_CSV = Path("chemin_csv_fusion_auto")
FINAL_CSV = Path("chemin_csv_fusions_manuelles_appliquees")

OUTPUT_DIR = FINAL_CSV.parent  # meme dossier que le CSV final
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SEP  = "=" * 70
SEP2 = "-" * 70

COL_MAISON = "Maison_vente_ou_demandeur"
VALEUR_INCONNUE = "Inconnu"

# ── Fusions forcees a reclasser en "manuel" ─────────────────────────────────
# Meme liste que A_FUSIONNER_DIRECT dans fusionner_doublons.py : ce sont des
# Id_perenne de doublons fusionnes automatiquement par le script (entre
# V1_CSV et AUTO_CSV), mais suite a une decision manuelle explicite (revue
# au cas par cas), donc a compter ici comme des suppressions "manuelles" et
# non "automatiques".
A_FUSIONNER_DIRECT = [
    "19863","19862",    "19861","19860",
    "19859","19858",    "19857","19856",
    "19855","19854",    "19853","19852",
    "19851","19850",    "19849","19848",
    "19847","19846",    "19933","19932",
    "19931","19930",    "19929","19928",
    "19927","19926",    "19925","19924",
    "20364","20363",    "20362","20361",
    "20360","20359",    "23314","23313",
    "23312","23311",    "23310","23309",
    "23308","23307",    "24914","24913",
    "34626","34625",    "34624","34623",
    "34622","34621",    "34620","34619",
    "34618","34617",    "34616","34615",
    "34614","34613",    "34612","34611",
    "32341","32340",    "32339","32338",
    "32337","32336",    "32335","32334",
    "32333","32332",     "32331","32330",
]

def charger_csv(chemin: Path) -> pd.DataFrame:
    df = pd.read_csv(chemin, sep=";", encoding="utf-8-sig", dtype=str, low_memory=False)
    return df


def nettoyer_colonne(df: pd.DataFrame, col: str) -> pd.Series:
    """Renvoie la colonne en str, valeurs vides/NaN remplacees par VALEUR_INCONNUE."""
    s = df[col].fillna("").astype(str).str.strip()
    s = s.replace("", VALEUR_INCONNUE)
    return s


def tracer_barres_groupees(ax, categories, valeurs_avant, valeurs_apres, titre, ylabel, en_pourcentage=False):
    x = np.arange(len(categories))
    largeur = 0.4

    ax.bar(x - largeur / 2, valeurs_avant, width=largeur, label="Avant dedoublonnage", color="#4C72B0")
    ax.bar(x + largeur / 2, valeurs_apres, width=largeur, label="Apres dedoublonnage", color="#DD8452")

    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=90 if len(categories) > 15 else 45, ha="right", fontsize=7)
    ax.set_ylabel(ylabel)
    ax.set_title(titre)
    ax.legend()
    if en_pourcentage:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))


df_original = charger_csv(ORIGINAL_CSV)
df_v1       = charger_csv(V1_CSV)
df_auto     = charger_csv(AUTO_CSV)
df_final    = charger_csv(FINAL_CSV)

n_original = len(df_original)
n_v1       = len(df_v1)
n_auto     = len(df_auto)
n_final    = len(df_final)

print(f"-> Original (avant tout dedoublonnage)        : {n_original} lignes")
print(f"-> V1 (apres 1er dedoublonnage manuel)         : {n_v1} lignes")
print(f"-> Apres dedoublonnage automatique              : {n_auto} lignes")
print(f"-> Apres dedoublonnage manuel final (complet)   : {n_final} lignes")
print()

# ── Recap statistique ───────────────────────────────────────────────────────
print("RECAP STATISTIQUE DU DEDOUBLONNAGE")
print(SEP)
print()

# Trois transitions successives, chacune comparee au fichier qui la precede
# reellement dans le pipeline (et non systematiquement a ORIGINAL_CSV).
n_supprime_manuel_1 = n_original - n_v1     # ORIGINAL_CSV -> V1_CSV (manuel)
n_supprime_auto     = n_v1 - n_auto         # V1_CSV -> AUTO_CSV (automatique)
n_supprime_manuel_2 = n_auto - n_final      # AUTO_CSV -> FINAL_CSV (manuel)

# ── Reclassement des fusions forcees (A_FUSIONNER_DIRECT) ───────────────────
# La transition automatique reelle est V1_CSV -> AUTO_CSV. Si un Id de
# A_FUSIONNER_DIRECT est present dans V1_CSV et absent de AUTO_CSV, c'est
# qu'il a ete fusionne (supprime) par fusionner_doublons.py, donc compte
# dans n_supprime_auto. On le bascule vers le decompte manuel, puisque
# c'est une decision manuelle explicite.
n_force_reclasse = 0

if "Id_perenne" in df_v1.columns and "Id_perenne" in df_auto.columns:
    ids_v1   = set(df_v1["Id_perenne"].fillna("").astype(str).str.strip())
    ids_auto = set(df_auto["Id_perenne"].fillna("").astype(str).str.strip())

    ids_reclasses        = [i for i in A_FUSIONNER_DIRECT if i in ids_v1 and i not in ids_auto]
    ids_encore_presents  = [i for i in A_FUSIONNER_DIRECT if i in ids_v1 and i in ids_auto]
    ids_absents_de_v1    = [i for i in A_FUSIONNER_DIRECT if i not in ids_v1]

    n_force_reclasse = len(ids_reclasses)

    print(f"Id A_FUSIONNER_DIRECT au total                      : {len(A_FUSIONNER_DIRECT)}")
    print(f"Id A_FUSIONNER_DIRECT reclasses (auto -> manuel)    : {n_force_reclasse}")
    if ids_encore_presents:
        print(f"Id A_FUSIONNER_DIRECT encore presents dans AUTO_CSV : {len(ids_encore_presents)}")
        print("            (pas encore fusionnes a ce stade, non reclasses)")
        for id_present in ids_encore_presents:
            print(f"     present : {id_present}")
    if ids_absents_de_v1:
        print(f"Id A_FUSIONNER_DIRECT absents de V1_CSV             : {len(ids_absents_de_v1)}")
        for id_absent in ids_absents_de_v1:
            print(f"     absent : {id_absent}")
    print()
else:
    print("ATTENTION : colonne 'Id_perenne' absente de V1_CSV ou AUTO_CSV")
    print("            -> reclassement A_FUSIONNER_DIRECT impossible, ignore")
    print()

n_supprime_auto         -= n_force_reclasse
n_supprime_manuel_total  = n_supprime_manuel_1 + n_supprime_manuel_2 + n_force_reclasse
n_supprime_total         = n_original - n_final

taux_manuel_1_vs_orig     = (n_supprime_manuel_1     / n_original * 100) if n_original else 0
taux_auto_vs_v1           = (n_supprime_auto         / n_v1       * 100) if n_v1       else 0
taux_manuel_2_vs_auto     = (n_supprime_manuel_2     / n_auto     * 100) if n_auto     else 0
taux_manuel_total_vs_orig = (n_supprime_manuel_total / n_original * 100) if n_original else 0
taux_total_vs_orig        = (n_supprime_total        / n_original * 100) if n_original else 0

print(f"Total de lignes (fichier original)                        : {n_original}")
print(f"Total de lignes (fichier v1, apres 1er manuel)             : {n_v1}")
print(f"Total de lignes (fichier automatique)                      : {n_auto}")
print(f"Total d'Id apres dedoublonnage complet (final)             : {n_final}")
print()
print(f"Dedoublonne manuellement (original -> v1)                  : {n_supprime_manuel_1}")
print(f"Dedoublonne via regles automatiques (v1 -> auto)            : {n_supprime_auto}")
print(f"Dedoublonne manuellement (auto -> final)                   : {n_supprime_manuel_2}")
print(f"Dedoublonne manuellement au total (1er + reclasses + 2e)    : {n_supprime_manuel_total}")
print(f"Dedoublonne au total (manuel + automatique)                 : {n_supprime_total}")
print()
print(f"Taux dedoublonnage manuel 1er passage (vs original)         : {taux_manuel_1_vs_orig:.2f} %")
print(f"Taux dedoublonnage automatique (vs v1)                      : {taux_auto_vs_v1:.2f} %")
print(f"Taux dedoublonnage manuel 2e passage (vs auto)               : {taux_manuel_2_vs_auto:.2f} %")
print(f"Taux dedoublonnage manuel total (vs original)                : {taux_manuel_total_vs_orig:.2f} %")
print(f"Taux dedoublonnage global (vs original)                      : {taux_total_vs_orig:.2f} %")
print()

# ── Preparation des donnees pour les graphiques ────────────────────────────
print(SEP)
print("PREPARATION DES GRAPHIQUES")
print(SEP)
print()

if COL_MAISON not in df_original.columns or COL_MAISON not in df_final.columns:
    raise ValueError(f"Colonne attendue absente du CSV : {COL_MAISON}")

serie_maison_avant = nettoyer_colonne(df_original, COL_MAISON)
serie_maison_apres = nettoyer_colonne(df_final, COL_MAISON)

counts_maison_avant = serie_maison_avant.value_counts()
counts_maison_apres = serie_maison_apres.value_counts()

# Uniquement les maisons presentes dans FINAL_CSV (et non l'union avec
# ORIGINAL_CSV) : l'original peut contenir des variantes de noms non
# nettoyees/non normalisees qui n'existent plus apres dedoublonnage, ce qui
# bruiterait le graphique. Triees par PERTE D'EFFECTIF (avant - apres)
# decroissante : la maison la plus impactee par le dedoublonnage (celle qui
# a perdu le plus de notices) arrive en premier.
categories_maison = sorted(
    counts_maison_apres.index,
    key=lambda c: counts_maison_avant.get(c, 0) - counts_maison_apres.get(c, 0),
    reverse=True,
)

print(f"-> {len(categories_maison)} maisons de vente / demandeurs distincts")
print("-> Classement (perte d'effectif avant -> apres) :")
for c in categories_maison:
    perte = counts_maison_avant.get(c, 0) - counts_maison_apres.get(c, 0)
    print(f"     {c:<40} perte = {perte}")
print()

valeurs_avant = [counts_maison_avant.get(c, 0) for c in categories_maison]
valeurs_apres = [counts_maison_apres.get(c, 0) for c in categories_maison]
pct_avant     = [counts_maison_avant.get(c, 0) / n_original * 100 if n_original else 0 for c in categories_maison]
pct_apres     = [counts_maison_apres.get(c, 0) / n_final    * 100 if n_final    else 0 for c in categories_maison]

# ── Graphique 1 : effectifs ─────────────────────────────────────────────────
print(SEP)
print("EXPORT DES GRAPHIQUES")
print(SEP)

out_pdf_effectifs = OUTPUT_DIR / "quantification_dedoublonnage_maison_effectifs.pdf"
fig, ax = plt.subplots(figsize=(max(10, len(categories_maison) * 0.35), 6))
tracer_barres_groupees(
    ax, categories_maison, valeurs_avant, valeurs_apres,
    "Nombre de notices par maison de vente / demandeur\n"
    "(effectifs, avant vs apres dedoublonnage — triees par perte d'effectif)",
    "Nombre de notices",
)
fig.tight_layout()
fig.savefig(out_pdf_effectifs)
plt.close(fig)
print(f"  PDF effectifs    : {out_pdf_effectifs}")

# ── Graphique 2 : part relative ─────────────────────────────────────────────
out_pdf_pourcentage = OUTPUT_DIR / "quantification_dedoublonnage_maison_pourcentage.pdf"
fig, ax = plt.subplots(figsize=(max(10, len(categories_maison) * 0.35), 6))
tracer_barres_groupees(
    ax, categories_maison, pct_avant, pct_apres,
    "Part de notices par maison de vente / demandeur\n"
    "(part relative, avant vs apres dedoublonnage — triees par perte d'effectif)",
    "Part des notices (%)",
    en_pourcentage=True,
)
fig.tight_layout()
fig.savefig(out_pdf_pourcentage)
plt.close(fig)
print(f"  PDF pourcentage  : {out_pdf_pourcentage}")
print()
