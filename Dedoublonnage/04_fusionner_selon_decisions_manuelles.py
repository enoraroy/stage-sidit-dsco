"""
Applique les décisions prises manuellement (fichier revue_manuelle.log) sur
les doublons dont la notice était jugée "significative" par
fusionner_doublons.py, et qui avaient donc été laissés de côté pour
traitement manuel.

FORMAT DES LIGNES DE DÉCISION ATTENDUES DANS LE LOG :

    ... INFO   FUSIONNER  groupe=<Identifiant_catalogue>|<Numero_lot>  id_traite=<Id_perenne>  notes='...'
    ... INFO   SUPPRIMER  groupe=<Identifiant_catalogue>|<Numero_lot>  id_traite=<Id_perenne>  notes='...'
    ... INFO   IGNORER    groupe=<Identifiant_catalogue>|<Numero_lot>  notes='...'

(Les champs sont séparés par au moins deux espaces, ce qui permet de gérer
les noms de catalogue ou de notes contenant eux-mêmes un simple espace.)

Pour chaque décision :

  - FUSIONNER : on retrouve, dans le groupe (même Identifiant_catalogue +
    même Numero_lot), la ligne "originale" (logique identifier_original,
    identique à fusionner_doublons.py), puis on fusionne dans cette ligne
    la page PDF et le lien Arkindex de la ligne doublon (Id_perenne=
    id_traite). La ligne doublon est ensuite supprimée. Fusion des champs
    strictement identique à fusionner_doublons.py (union triée des pages,
    union ordonnée et dédupliquée des liens).

  - SUPPRIMER : on supprime simplement la ligne Id_perenne=id_traite, sans
    rien fusionner (suppression pure, décision prise manuellement).

  - IGNORER : on ne touche à rien. La décision est seulement notée dans le
    rapport, pour traçabilité.

  - Si l'Id_perenne indiqué (id_traite) n'existe plus dans le CSV (déjà
    traité, ligne supprimée par ailleurs, typo, etc.) : on l'indique par un
    simple print (et une ligne dans le rapport), PUIS ON CONTINUE — le
    programme ne s'arrête jamais pour cette raison.

  - Si plusieurs décisions contradictoires existent pour le même groupe
    dans le log (reprises de session), seule la DERNIÈRE rencontrée dans le
    fichier est appliquée (comportement "reprise" classique).

SORTIE :
  - Un CSV avec les décisions appliquées (le fichier de travail).
  - Un rapport .txt résumant les opérations effectuées.
"""

import re
import pandas as pd
from pathlib import Path
from datetime import datetime

# CSV sur lequel appliquer les décisions manuelles. Il s'agit normalement du
# CSV déjà produit par fusionner_doublons.py (celui qui contient encore les
# doublons "notice significative" en attente de traitement manuel).
INPUT_CSV = Path(r"chemin_du_csv_fusionné")
LOG_PATH = Path(r"chemin_fichier_revue_manuelle.log")

OUTPUT_DIR = Path("chemin_du_dossier")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SEP  = "=" * 70
SEP2 = "-" * 70

ACTIONS_VALIDES = {"FUSIONNER", "SUPPRIMER", "IGNORER"}


# ── Fonctions utilitaires (identiques à fusionner_doublons.py) ───────────

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


def identifier_original(grp: pd.DataFrame) -> int:
    """Index pandas de la ligne désignée comme originale dans un groupe."""
    candidats = grp[grp["Titre_lot"].str.strip() != ""]
    if candidats.empty:
        candidats = grp
    return candidats.apply(nb_champs_remplis, axis=1).idxmax()


def decomposer_pipe(valeur: str) -> list[str]:
    return [v.strip() for v in str(valeur).split("|") if v.strip()]


def fusionner_pages(vals: list[str]) -> str:
    pages = set()
    for v in vals:
        for token in decomposer_pipe(v):
            p = to_page(token)
            if p is not None:
                pages.add(p)
    return "|".join(str(p) for p in sorted(pages))


def fusionner_liens(vals: list[str]) -> str:
    vus = set()
    resultat = []
    for v in vals:
        for token in decomposer_pipe(v):
            if token not in vus:
                vus.add(token)
                resultat.append(token)
    return "|".join(resultat)


# ── Parsing du log de revue manuelle ──────────────────────────────────────

def parser_log(chemin_log: Path) -> tuple[dict, list]:
    """
    Lit le log et retourne :
      - decisions : dict {groupe: {"action":..., "id_traite":..., "notes":...}}
      - ordre     : liste des groupes dans l'ordre de première apparition
    Seule la DERNIÈRE occurrence d'un groupe (en cas de reprise de session)
    est conservée dans `decisions`.
    """
    decisions = {}
    ordre = []

    with open(chemin_log, encoding="utf-8") as f:
        for ligne_brute in f:
            ligne = ligne_brute.strip()
            if "INFO" not in ligne:
                continue

            champs = re.split(r"\s{2,}", ligne)
            if len(champs) < 4:
                continue

            # champs[0] = horodatage, champs[1] = "INFO", champs[2] = action
            action = champs[2]
            if action not in ACTIONS_VALIDES:
                continue

            groupe = None
            id_traite = None
            notes = ""
            for champ in champs[3:]:
                if champ.startswith("groupe="):
                    groupe = champ[len("groupe="):]
                elif champ.startswith("id_traite="):
                    id_traite = champ[len("id_traite="):]
                elif champ.startswith("notes="):
                    notes = champ[len("notes="):].strip("'")

            if groupe is None:
                continue

            if groupe not in decisions:
                ordre.append(groupe)
            decisions[groupe] = {
                "action": action,
                "id_traite": id_traite,
                "notes": notes,
            }

    return decisions, ordre


# ── Chargement du CSV ──────────────────────────────────────────────────────

df = pd.read_csv(INPUT_CSV, sep=";", encoding="utf-8-sig", dtype=str, low_memory=False)
print(f"-> {len(df)} lignes chargées")

for col in ["Numero_lot", "Identifiant_catalogue", "Titre_lot",
            "Lien_page_arkindex", "Numero_page_pdf", "Notice", "Id_perenne"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str).str.strip()

df_out = df.copy()

# Index Id_perenne -> position pandas, pour retrouver rapidement une ligne.
# (reconstruit si besoin après suppression, mais on ne supprime qu'à la fin)
index_par_id = {}
for idx, id_p in df_out["Id_perenne"].items():
    index_par_id.setdefault(id_p, idx)

print()

# ── Chargement du log ──────────────────────────────────────────────────────
print(SEP)
print("LECTURE DU LOG DE REVUE MANUELLE")


decisions, ordre = parser_log(LOG_PATH)
print(f"-> {len(decisions)} décisions distinctes chargées depuis le log")
print()

# ── Application des décisions ─────────────────────────────────────────────
print(SEP)
print("APPLICATION DES DÉCISIONS")


indices_a_supprimer = set()
n_fusion       = 0
n_suppr        = 0
n_ignore       = 0
n_introuvable  = 0
lignes_rapport = []

for groupe in ordre:
    dec = decisions[groupe]
    action    = dec["action"]
    id_traite = dec["id_traite"]
    notes     = dec["notes"]

    catalogue, _, numero_lot = groupe.rpartition("|")

    # -- IGNORER : rien à faire, on trace juste --
    if action == "IGNORER":
        n_ignore += 1
        msg = f"  [IGNORE]    groupe={groupe}  notes='{notes}'"
        print(msg)
        lignes_rapport.append(msg)
        continue

    # -- FUSIONNER / SUPPRIMER : il faut retrouver la ligne du doublon --
    if id_traite is None or id_traite not in index_par_id:
        n_introuvable += 1
        msg = (f"  [INTROUVABLE] Id_perenne='{id_traite}'  groupe={groupe}  "
               f"action={action}  -> ignoré, on continue")
        print(msg)
        lignes_rapport.append(msg)
        continue

    idx_dup = index_par_id[id_traite]

    # -- SUPPRIMER : suppression pure, pas de fusion de champs --
    if action == "SUPPRIMER":
        indices_a_supprimer.add(idx_dup)
        n_suppr += 1
        msg = f"  [SUPPRIME]  Id={id_traite}  groupe={groupe}  notes='{notes}'"
        print(msg)
        lignes_rapport.append(msg)
        continue

    # -- FUSIONNER : logique identique à fusionner_doublons.py --
    if action == "FUSIONNER":
        masque_grp = (
            (df_out["Identifiant_catalogue"] == catalogue)
            & (df_out["Numero_lot"] == numero_lot)
        )
        grp = df_out[masque_grp]

        if idx_dup not in grp.index:
            n_introuvable += 1
            msg = (f"  [ATTENTION] Id={id_traite} n'appartient pas au groupe "
                   f"{groupe} d'après le CSV actuel -> ignoré, on continue")
            print(msg)
            lignes_rapport.append(msg)
            continue

        idx_original = identifier_original(grp)

        if idx_original == idx_dup:
            # Cas limite : le doublon lui-même a été désigné "original"
            # (plus de champs remplis que toute autre ligne du groupe).
            # On ne peut pas fusionner une ligne sur elle-même : on écarte
            # cette ligne des candidats et on retente.
            autres = grp.drop(index=idx_dup)
            if autres.empty:
                n_introuvable += 1
                msg = (f"  [ATTENTION] Id={id_traite} : impossible de "
                       f"déterminer une ligne originale distincte dans le "
                       f"groupe {groupe} -> ignoré, on continue")
                print(msg)
                lignes_rapport.append(msg)
                continue
            idx_original = identifier_original(autres)

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

        indices_a_supprimer.add(idx_dup)
        n_fusion += 1

        id_original = df_out.loc[idx_original, "Id_perenne"]
        msg = (f"  [FUSIONNE] Id={id_traite} -> original={id_original} "
               f"groupe={groupe} | pages: '{page_orig}'->'{nouvelle_page}' "
               f"| liens: '{lien_orig}'->'{nouveau_lien}' | notes='{notes}'")
        print(msg)
        lignes_rapport.append(msg)

print()
print(f"Fusions effectuées   : {n_fusion}")
print(f"Suppressions pures   : {n_suppr}")
print(f"Décisions ignorées   : {n_ignore}")
print(f"Id introuvables      : {n_introuvable}")
print()

# ── Suppression des lignes traitées ───────────────────────────────────────
n_avant = len(df_out)
df_out = df_out.drop(index=list(indices_a_supprimer)).reset_index(drop=True)
n_apres = len(df_out)

print(f"Lignes avant suppression : {n_avant}")
print(f"Lignes après suppression : {n_apres}")
print(f"Lignes supprimées        : {n_avant - n_apres}")
print()

# ── Export ─────────────────────────────────────────────────────────────────


ts = datetime.now().strftime("%Y%m%d_%H%M%S")

out_csv = OUTPUT_DIR / f"lots_decisions_appliquees_{ts}.csv"
df_out.to_csv(out_csv, sep=";", index=False, encoding="utf-8-sig")
print(f"  CSV      : {out_csv}")

out_txt = OUTPUT_DIR / f"rapport_decisions_manuelles_{ts}.txt"
contenu_rapport = (
    f"RAPPORT D'APPLICATION DES DÉCISIONS MANUELLES\n{SEP}\n\n"
    f"Généré le              : {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}\n"
    f"CSV source             : {INPUT_CSV}\n"
    f"Log de revue manuelle  : {LOG_PATH}\n\n"
    f"Décisions distinctes   : {len(decisions)}\n"
    f"Fusions effectuées     : {n_fusion}\n"
    f"Suppressions pures     : {n_suppr}\n"
    f"Décisions ignorées     : {n_ignore}\n"
    f"Id introuvables        : {n_introuvable}\n\n"
    f"Lignes source          : {n_avant}\n"
    f"Lignes après traitement: {n_apres}\n"
    f"Lignes supprimées      : {n_avant - n_apres}\n\n"
    f"{SEP2}\n"
    f"DÉTAIL DES OPÉRATIONS\n"
    f"{SEP2}\n\n"
    + "\n".join(lignes_rapport) + "\n"
)
out_txt.write_text(contenu_rapport, encoding="utf-8")
print(f"  Rapport  : {out_txt}")
print()
