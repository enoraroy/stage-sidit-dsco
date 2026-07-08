"""
detecteur_anomalies_ocr_lots.py
================================
Détecte les erreurs d'OCRisation dans la colonne Numero_lot d'un tableur CSV.

PRINCIPE DE DÉTECTION :
    Pour chaque ligne i appartenant au même catalogue, on compare :

      chemin_via_i  = |lot[i] - lot[i-1]| + |lot[i+1] - lot[i]|
      chemin_direct = |lot[i+1] - lot[i-1]|
      ratio         = chemin_via_i / chemin_direct

    Si ratio ≥ RATIO_THRESHOLD  ET  chemin_via_i ≥ ABS_THRESHOLD,
    la ligne est signalée comme suspecte.

    Intuition : si "passer par" le numéro de lot de la ligne i est
    bien plus long que le chemin direct entre ses deux voisins,
    ce numéro est probablement une erreur d'OCR.

    Exemple normal   :  139 → 140 → 141   ratio = 1      → OK
    Exemple anormal  :  139 →   5 → 141   ratio = 135    → SIGNALÉ

SORTIE :
    Un fichier .txt dans le dossier output/ contenant :
      - Paramètres utilisés
      - Section 1 : liste brute des Id_perenne suspects
      - Section 2 : détail de chaque anomalie (séquence, ratio, écart)
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

INPUT_PATH = ("chemin_du_csv")

OUTPUT_DIR = ("dossier_de_sortie")

RATIO_THRESHOLD = 5

ABS_THRESHOLD = 10

CSV_SEP = ";"


def charger_csv(path: str, sep: str) -> pd.DataFrame:
    """Charge le CSV en essayant plusieurs encodages courants."""
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(path, sep=sep, encoding=encoding, low_memory=False)
            print(f"      Encodage utilisé : {encoding}")
            return df
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"      Erreur inattendue ({encoding}) : {e}")
            continue
    raise ValueError(
        f"Impossible de lire le fichier. Vérifiez le chemin et l'encodage :\n{path}"
    )


def detecter_anomalies(
    df: pd.DataFrame,
    ratio_threshold: float,
    abs_threshold: float,
) -> list[dict]:
    """
    Parcourt chaque catalogue et signale les lignes dont le numéro de lot
    est incohérent par rapport à ses voisins immédiats.

    Retourne une liste de dictionnaires, un par anomalie détectée.
    """
    anomalies = []

    if "Identifiant_catalogue" not in df.columns:
        raise KeyError(
            "Colonne 'Identifiant_catalogue' introuvable dans le CSV.\n"
            "Vérifiez le séparateur et les noms de colonnes."
        )
    if "Numero_lot_num" not in df.columns:
        raise KeyError("La colonne 'Numero_lot_num' n'a pas été créée.")

    for catalogue, groupe in df.groupby("Identifiant_catalogue", sort=False):
        # Lignes avec un numéro de lot numérique valide, dans l'ordre du fichier
        valides = groupe[groupe["Numero_lot_num"].notna()].copy()
        valides.reset_index(drop=True, inplace=True)

        n = len(valides)
        if n < 3:
            # Impossible de détecter une anomalie sans au moins 3 points
            continue

        lots = valides["Numero_lot_num"].values
        ids  = valides["Id_perenne"].values

        for i in range(1, n - 1):
            prev = lots[i - 1]
            curr = lots[i]
            nxt  = lots[i + 1]

            chemin_via  = abs(curr - prev) + abs(nxt - curr)
            chemin_dir  = abs(nxt - prev)

            if chemin_dir < 1:
                # Voisins identiques (ou quasi) : flag si la déviation est grande
                if chemin_via >= abs_threshold * 2:
                    anomalies.append(
                        _anomalie(ids[i], catalogue, prev, curr, nxt,
                                  "inf (voisins égaux)", chemin_via)
                    )
            else:
                ratio = chemin_via / chemin_dir
                if ratio >= ratio_threshold and chemin_via >= abs_threshold:
                    anomalies.append(
                        _anomalie(ids[i], catalogue, prev, curr, nxt,
                                  round(ratio, 2), round(chemin_via, 0))
                    )

    return anomalies


def _anomalie(id_p, catalogue, prev, curr, nxt, ratio, ecart) -> dict:
    """Construit un dictionnaire d'anomalie."""
    return {
        "Id_perenne"    : id_p,
        "Catalogue"     : catalogue,
        "Lot_precedent" : int(prev),
        "Lot_suspect"   : int(curr),
        "Lot_suivant"   : int(nxt),
        "Ratio"         : ratio,
        "Ecart_total"   : ecart,
    }


def ecrire_rapport(
    anomalies : list[dict],
    output_dir: str,
    input_path: str,
    params    : dict,
) -> str:
    """
    Écrit le rapport dans un fichier .txt horodaté.
    Retourne le chemin complet du fichier créé.
    """
    os.makedirs(output_dir, exist_ok=True)

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"anomalies_ocr_numeros_lot_{ts}.txt"
    filepath = os.path.join(output_dir, filename)

    sep_ligne = "─" * 65

    with open(filepath, "w", encoding="utf-8") as f:

        # ── En-tête ──────────────────────────────────────────────
        f.write("RAPPORT D'ANOMALIES OCR — NUMÉROS DE LOTS\n")
        f.write(sep_ligne + "\n")
        f.write(f"Généré le           : {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}\n")
        f.write(f"Fichier source      : {input_path}\n")
        f.write(f"Seuil ratio         : ≥ {params['ratio']}\n")
        f.write(f"Écart absolu min    : ≥ {params['abs']}\n")
        f.write(f"Anomalies trouvées  : {len(anomalies)}\n\n")

        # ── Section 1 : liste brute ───────────────────────────────
        f.write(sep_ligne + "\n")
        f.write("SECTION 1 — LISTE DES Id_perenne SUSPECTS\n")
        f.write(sep_ligne + "\n\n")

        if anomalies:
            for a in anomalies:
                f.write(f"{a['Id_perenne']}\n")
        else:
            f.write("(aucune anomalie détectée avec ces paramètres)\n")
        f.write("\n")

        # ── Section 2 : détail ────────────────────────────────────
        f.write(sep_ligne + "\n")
        f.write("SECTION 2 — DÉTAIL DES ANOMALIES\n")
        f.write(sep_ligne + "\n\n")

        if anomalies:
            for a in anomalies:
                f.write(
                    f"  Id_perenne   : {a['Id_perenne']}\n"
                    f"  Catalogue    : {a['Catalogue']}\n"
                    f"  Séquence     : {a['Lot_precedent']}  →  "
                    f"[! {a['Lot_suspect']} !]  →  {a['Lot_suivant']}\n"
                    f"  Ratio        : {a['Ratio']}\n"
                    f"  Écart total  : {a['Ecart_total']}\n\n"
                )
        else:
            f.write("(aucune anomalie détectée)\n")

    return filepath



def main():
    print()
    print("  Détecteur d'anomalies OCR — Numéros de lots")

    # ── Étape 1 : chargement ─────────────────────────────────────
    print(f"\n[1/3] Chargement du fichier CSV...")
    print(f"      {INPUT_PATH}")
    try:
        df = charger_csv(INPUT_PATH, CSV_SEP)
    except (ValueError, FileNotFoundError) as e:
        print(f"\n  ERREUR : {e}")
        sys.exit(1)

    n_lignes   = len(df)
    n_catalogues = df["Identifiant_catalogue"].nunique()
    print(f"      {n_lignes} lignes chargées, {n_catalogues} catalogue(s) distinct(s)")

    # ── Étape 2 : préparation de Numero_lot ──────────────────────
    df["Numero_lot_num"] = pd.to_numeric(df["Numero_lot"], errors="coerce")
    n_valides = int(df["Numero_lot_num"].notna().sum())
    n_vides   = n_lignes - n_valides
    print(f"      {n_valides} lignes avec un numéro de lot numérique "
          f"({n_vides} ignorées : vides ou non numériques)")

    # ── Étape 3 : détection ──────────────────────────────────────
    print(f"\n[2/3] Détection des anomalies "
          f"(ratio ≥ {RATIO_THRESHOLD}, écart ≥ {ABS_THRESHOLD})...")
    try:
        anomalies = detecter_anomalies(df, RATIO_THRESHOLD, ABS_THRESHOLD)
    except KeyError as e:
        print(f"\n  ERREUR de colonne : {e}")
        sys.exit(1)

    print(f"      → {len(anomalies)} anomalie(s) détectée(s)")

    # ── Étape 4 : écriture du rapport ────────────────────────────
    print(f"\n[3/3] Écriture du rapport dans :\n      {OUTPUT_DIR}")
    params   = {"ratio": RATIO_THRESHOLD, "abs": ABS_THRESHOLD}
    filepath = ecrire_rapport(anomalies, OUTPUT_DIR, INPUT_PATH, params)
    print(f"      Fichier créé : {os.path.basename(filepath)}")

    print("Terminé !")


if __name__ == "__main__":
    main()
