"""
detecteur_doublons_stricts_lots.py
====================================
Détecte les doublons stricts dans un tableur CSV de lots de vente.

PRINCIPE DE DÉTECTION :
    Deux lignes (ou plus) sont considérées comme doublons stricts si leurs
    valeurs sont identiques sur l'ensemble des colonnes de comparaison
    définies dans COLONNES_COMPARAISON.

    Par défaut, toutes les colonnes sont utilisées SAUF les identifiants
    techniques propres à chaque ligne (Id_perenne, Lien_page_arkindex,
    Numero_page_pdf), qui sont précisément ceux susceptibles de différer
    entre deux entrées représentant le même lot.

    Si COLONNES_COMPARAISON est laissé vide ([]), le script utilise
    automatiquement toutes les colonnes du fichier sauf les colonnes
    exclues (COLONNES_EXCLUES).

COMPARAISON :
    Avant comparaison, toutes les valeurs sont normalisées :
      - conversion en chaîne (les NaN deviennent la chaîne "")
      - suppression des espaces en début/fin
      - passage en minuscules

SORTIE :
    Un fichier .txt dans le dossier output/ contenant :
      - Parametres utilises
      - Section 1 : liste brute des Id_perenne en doublon
      - Section 2 : groupes de doublons (paires, triplets, etc.)
        avec le nombre de membres et tous les Id_perenne du groupe
"""

import os
import sys
import pandas as pd
from datetime import datetime
from itertools import combinations

# ============================================================
#  CONFIGURATION  —  a modifier selon les besoins
# ============================================================

INPUT_PATH = (r"chemin_du_csv")

OUTPUT_DIR = ("chemin_du_dossier")

CSV_SEP = ";"

# Colonnes sur lesquelles comparer les lignes.
# Ces colonnes sont suffisamment discriminantes pour identifier un doublon reel :
# un meme lot dans le meme catalogue, avec le meme titre, la meme estimation
# et les memes dimensions sera un doublon avec une tres haute certitude.
# Laisser vide ([]) pour utiliser toutes les colonnes sauf COLONNES_EXCLUES —
COLONNES_COMPARAISON = ["Identifiant_catalogue", "Titre_lot", "Numero_lot"]

# Colonnes a exclure si COLONNES_COMPARAISON est vide (mode automatique).
COLONNES_EXCLUES = [
    "Id_perenne", "TRI"
]

# Si True, strip() + lower() avant comparaison.
# Si False, comparaison exacte apres strip() seulement.
IGNORER_CASSE = False


def charger_csv(path: str, sep: str) -> pd.DataFrame:
    """Charge le CSV en essayant plusieurs encodages courants."""
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(path, sep=sep, encoding=encoding, low_memory=False,
                             dtype=str)
            print(f"      Encodage utilise : {encoding}")
            return df
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"      Erreur inattendue ({encoding}) : {e}")
            continue
    raise ValueError(
        f"Impossible de lire le fichier. Verifiez le chemin et l'encodage :\n{path}"
    )


def preparer_comparaison(df: pd.DataFrame, colonnes: list[str], ignorer_casse: bool) -> pd.DataFrame:
    """
    Retourne un DataFrame restreint aux colonnes de comparaison, avec :
      - strip() sur les valeurs non-NaN
      - lower() si ignorer_casse, sur les valeurs non-NaN
      - NaN reste NaN (pandas.duplicated / groupby traitent NaN == NaN
        dans ce contexte, ce qui est le comportement voulu ici)

    On ne fait PAS de fillna : deux cellules NaN sont considerees egales
    (meme absence de valeur), et NaN != "" (cellule vide explicite).
    """
    df_comp = df[colonnes].copy()
    for col in colonnes:
        # strip uniquement sur les cellules non-NaN
        mask = df_comp[col].notna()
        df_comp.loc[mask, col] = df_comp.loc[mask, col].astype(str).str.strip()
        if ignorer_casse:
            df_comp.loc[mask, col] = df_comp.loc[mask, col].str.lower()
    return df_comp


def detecter_doublons(
    df: pd.DataFrame,
    colonnes_comparaison: list[str],
    ignorer_casse: bool,
) -> list[dict]:
    """
    Identifie les groupes de lignes strictement identiques sur
    colonnes_comparaison.

    NaN est traite comme une valeur distincte de "" : deux lignes avec
    NaN dans le meme champ sont considerees egales sur ce champ, mais
    NaN != "".

    Retourne une liste de dictionnaires, un par groupe :
      {
        "ids"      : [id_perenne_1, id_perenne_2, ...],
        "taille"   : int,
        "exemple"  : dict   # valeurs brutes du premier membre du groupe
      }
    """
    if "Id_perenne" not in df.columns:
        raise KeyError("Colonne 'Id_perenne' introuvable dans le CSV.")

    df_comp = preparer_comparaison(df, colonnes_comparaison, ignorer_casse)

    # Numero de groupe : pandas assigne le meme entier a toutes les lignes
    # identiques (NaN == NaN dans ce contexte). Les lignes uniques recoivent
    # un numero distinct.
    # On utilise groupby sur toutes les colonnes avec dropna=False pour que
    # les NaN participent a la cle de groupe.
    df_comp["_id"] = df["Id_perenne"].astype(str).str.strip()
    df_comp["_groupe"] = (
        df_comp
        .groupby(colonnes_comparaison, dropna=False, sort=False)
        .ngroup()
    )

    print(f"      Nombre de cles de groupe distinctes : {df_comp['_groupe'].nunique()}")

    groupes = []
    for num_groupe, sous_groupe in df_comp.groupby("_groupe", sort=False):
        if len(sous_groupe) < 2:
            continue
        ids = sous_groupe["_id"].tolist()
        idx_premier = sous_groupe.index[0]
        exemple = {col: df.at[idx_premier, col] for col in colonnes_comparaison}
        groupes.append({
            "ids"    : ids,
            "taille" : len(ids),
            "exemple": exemple,
        })

    # Tri : groupes les plus grands en premier, puis par premier Id_perenne
    groupes.sort(key=lambda g: (-g["taille"], g["ids"][0]))
    return groupes


def ecrire_rapport(
    groupes      : list[dict],
    colonnes_comp: list[str],
    output_dir   : str,
    input_path   : str,
    params       : dict,
) -> str:
    """
    Ecrit le rapport dans un fichier .txt horodate.
    Retourne le chemin complet du fichier cree.
    """
    os.makedirs(output_dir, exist_ok=True)

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"doublons_stricts_lots_{ts}.txt"
    filepath = os.path.join(output_dir, filename)

    sep_ligne = "-" * 65

    # Comptages
    n_groupes   = len(groupes)
    n_ids_total = sum(g["taille"] for g in groupes)
    comptage_tailles = {}
    for g in groupes:
        t = g["taille"]
        comptage_tailles[t] = comptage_tailles.get(t, 0) + 1

    with open(filepath, "w", encoding="utf-8") as f:

        # En-tete
        f.write("RAPPORT DE DOUBLONS STRICTS — LOTS DE VENTE\n")
        f.write(sep_ligne + "\n")
        f.write(f"Genere le           : {datetime.now().strftime('%d/%m/%Y a %H:%M:%S')}\n")
        f.write(f"Fichier source      : {input_path}\n")
        f.write(f"Colonnes comparees  : {len(colonnes_comp)}\n")
        f.write(f"  (liste complete en bas de rapport)\n")
        f.write(f"Normalisation casse : {'oui' if params['ignorer_casse'] else 'non'}\n")
        f.write(f"Groupes trouves     : {n_groupes}\n")
        f.write(f"Id_perenne concernes: {n_ids_total}\n")
        if comptage_tailles:
            details = ", ".join(
                f"{nb} groupe(s) de {t}"
                for t, nb in sorted(comptage_tailles.items())
            )
            f.write(f"  Dont : {details}\n")
        f.write("\n")

        # Section 1 : liste brute
        f.write(sep_ligne + "\n")
        f.write("SECTION 1 — LISTE BRUTE DES Id_perenne EN DOUBLON\n")
        f.write(sep_ligne + "\n\n")

        if groupes:
            for g in groupes:
                for id_p in g["ids"]:
                    f.write(f"{id_p}\n")
        else:
            f.write("(aucun doublon strict detecte)\n")
        f.write("\n")

        # Section 2 : detail par groupe
        f.write(sep_ligne + "\n")
        f.write("SECTION 2 — DETAIL DES GROUPES DE DOUBLONS\n")
        f.write(sep_ligne + "\n\n")

        if groupes:
            for i, g in enumerate(groupes, start=1):
                label = {2: "PAIRE", 3: "TRIPLET", 4: "QUADRUPLET"}.get(
                    g["taille"], f"GROUPE DE {g['taille']}"
                )
                f.write(f"  [{i}] {label}\n")
                f.write(f"  Nombre de membres : {g['taille']}\n")
                f.write(f"  Id_perenne        :\n")
                for id_p in g["ids"]:
                    f.write(f"    - {id_p}\n")

                # Apercu des champs discriminants (premiers champs non vides)
                f.write(f"  Apercu (valeurs communes) :\n")
                apercu_colonnes = [
                    "Identifiant_catalogue", "Titre_lot", "Numero_lot",
                    "Titre_vente", "Maison_vente_ou_demandeur",
                    "Annee_vente_ou_demande",
                ]
                for col in apercu_colonnes:
                    if col in g["exemple"]:
                        val = str(g["exemple"][col]).strip()
                        if val and val.lower() not in ("nan", ""):
                            f.write(f"    {col:<35}: {val[:80]}\n")
                f.write("\n")
        else:
            f.write("  (aucun doublon strict detecte)\n")

        # Pied de rapport : liste complete des colonnes comparees
        f.write(sep_ligne + "\n")
        f.write("COLONNES UTILISEES POUR LA COMPARAISON\n")
        f.write(sep_ligne + "\n\n")
        for col in colonnes_comp:
            f.write(f"  {col}\n")
        f.write("\n")

    return filepath



def main():
    print()
    print("  Detecteur de doublons stricts — Lots de vente")

    # Etape 1 : chargement
    print(f"\n[1/4] Chargement du fichier CSV...")
    print(f"      {INPUT_PATH}")
    try:
        df = charger_csv(INPUT_PATH, CSV_SEP)
    except (ValueError, FileNotFoundError) as e:
        print(f"\n  ERREUR : {e}")
        sys.exit(1)

    n_lignes = len(df)
    print(f"      {n_lignes} lignes chargees, {len(df.columns)} colonnes")

    # Etape 2 : selection des colonnes de comparaison
    print(f"\n[2/4] Preparation des colonnes de comparaison...")

    if COLONNES_COMPARAISON:
        colonnes_absentes = [c for c in COLONNES_COMPARAISON if c not in df.columns]
        if colonnes_absentes:
            print(f"\n  ERREUR : colonnes introuvables dans le CSV : {colonnes_absentes}")
            sys.exit(1)
        colonnes_comp = COLONNES_COMPARAISON
        print(f"      Mode : colonnes explicites ({len(colonnes_comp)} colonnes)")
    else:
        colonnes_comp = [c for c in df.columns if c not in COLONNES_EXCLUES]
        print(f"      Mode : toutes colonnes sauf exclusions "
              f"({len(colonnes_comp)} colonnes retenues, "
              f"{len(COLONNES_EXCLUES)} exclues)")

    print(f"      Normalisation casse : {'oui' if IGNORER_CASSE else 'non'}")

    # Etape 3 : detection
    print(f"\n[3/4] Recherche des doublons stricts...")
    try:
        groupes = detecter_doublons(df, colonnes_comp, IGNORER_CASSE)
    except KeyError as e:
        print(f"\n  ERREUR de colonne : {e}")
        sys.exit(1)

    n_ids = sum(g["taille"] for g in groupes)
    print(f"      -> {len(groupes)} groupe(s) de doublons, {n_ids} Id_perenne concernes")
    if groupes:
        for taille in sorted({g["taille"] for g in groupes}):
            nb = sum(1 for g in groupes if g["taille"] == taille)
            label = {2: "paires", 3: "triplets", 4: "quadruplets"}.get(taille, f"groupes de {taille}")
            print(f"         {nb} {label}")

    # Etape 4 : rapport
    print(f"\n[4/4] Ecriture du rapport dans :\n      {OUTPUT_DIR}")
    params = {"ignorer_casse": IGNORER_CASSE}
    try:
        filepath = ecrire_rapport(groupes, colonnes_comp, OUTPUT_DIR, INPUT_PATH, params)
    except Exception as e:
        print(f"\n  ERREUR lors de l'ecriture : {e}")
        sys.exit(1)

    print(f"      Fichier cree : {os.path.basename(filepath)}")
    print("\nTermine !\n")


if __name__ == "__main__":
    main()
