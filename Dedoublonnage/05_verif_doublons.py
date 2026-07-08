#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detecter_doublons_restants.py
------------------------------
Repere les doublons restants dans un CSV deja nettoye (issu de
fusionner_doublons.py / appliquer_decisions_manuelles.py).

PRINCIPE :
  Pour chaque Identifiant_catalogue, on regroupe les lignes par Numero_lot.
  Si plusieurs Id_perenne partagent le meme (Identifiant_catalogue,
  Numero_lot), on les considere comme doublons restants et on les liste.

  Les Id_perenne listes dans IDS_EXCLUS (couvertures introductives,
  publicites, cas incertains) sont mis de cote avant la detection : ils
  n'apparaissent jamais dans les groupes de doublons restants.

  Aucune logique de page, de notice ou de seuil ici : c'est une verification
  simple et directe, juste pour visualiser ce qu'il reste apres fusion.

SORTIE :
  Un fichier .txt listant, pour chaque groupe en doublon, l'Identifiant_catalogue,
  le Numero_lot, et la liste des Id_perenne concernes.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime

INPUT_CSV = Path("chemin_du_csv_avec_decisions_manuelles_appliquees")
OUTPUT_DIR = INPUT_CSV.parent 
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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

# ── Chargement ────────────────────────────────────────────────────────────
print("CHARGEMENT DU FICHIER CSV")
print(SEP)

df = pd.read_csv(INPUT_CSV, sep=";", encoding="utf-8-sig", dtype=str, low_memory=False)
print(f"-> {len(df)} lignes chargees")

for col in ["Identifiant_catalogue", "Numero_lot", "Id_perenne"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str).str.strip()
    else:
        raise ValueError(f"Colonne attendue absente du CSV : {col}")


# ── Exclusion des Id proteges ──────────────────────────────────────────────
masque_exclus = df["Id_perenne"].isin(IDS_EXCLUS)
n_exclus = masque_exclus.sum()
print(f"-> {n_exclus} Id_perenne proteges mis de cote (IDS_EXCLUS)")
df_travail = df[~masque_exclus].copy()
print(f"-> {len(df_travail)} lignes dans le perimetre d'analyse")
print()

# ── Detection des doublons restants ───────────────────────────────────────


groupes_doublons = []  # liste de (Identifiant_catalogue, Numero_lot, [Id_perenne, ...])

for (catalogue, numero_lot), grp in df_travail.groupby(["Identifiant_catalogue", "Numero_lot"]):
    if len(grp) < 2:
        continue
    ids = grp["Id_perenne"].tolist()
    groupes_doublons.append((catalogue, numero_lot, ids))
    msg = f"  [DOUBLON] catalogue={catalogue}  lot={numero_lot}  ids={ids}"
    print(msg)

print()
print(f"Nombre de groupes en doublon detectes : {len(groupes_doublons)}")
print(f"Nombre total de lignes concernees     : {sum(len(ids) for _, _, ids in groupes_doublons)}")
print()

# ── Export ─────────────────────────────────────────────────────────────────


ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out_txt = OUTPUT_DIR / f"doublons_restants_{ts}.txt"

contenu = (
    f"DOUBLONS RESTANTS (meme Identifiant_catalogue + meme Numero_lot)\n{SEP}\n\n"
    f"Genere le      : {datetime.now().strftime('%d/%m/%Y a %H:%M:%S')}\n"
    f"Fichier source : {INPUT_CSV}\n\n"
    f"Groupes en doublon detectes : {len(groupes_doublons)}\n"
    f"Lignes concernees           : {sum(len(ids) for _, _, ids in groupes_doublons)}\n\n"
    f"{SEP2}\n"
    f"DETAIL DES GROUPES\n"
    f"{SEP2}\n\n"
)

for catalogue, numero_lot, ids in groupes_doublons:
    contenu += f"catalogue={catalogue}  lot={numero_lot}  ids={ids}\n"

out_txt.write_text(contenu, encoding="utf-8")
print(f"  Liste des doublons restants : {out_txt}")
print()
