# -*- coding: utf-8 -*-
"""
Script 24 - Statistiques sur les arbitrages manuels (anomalies CONTENU_ABSENT_NOTICE).

Lit le fichier d'arbitrages produit par l'outil de revue manuelle et
produit un fragment LaTeX pret a coller dans le rapport, dans le meme
style que la note de synthese sur le dedoublonnage (booktabs, navyblue).

Entree :
    - arbitrages_contenu_absent_notice.csv

Sortie :
    - stats_arbitrages_YYYYMMDD_HHMMSS.tex  (fragment LaTeX, pas un document complet)
    - affichage console des memes chiffres

Note : la repartition par "catalogue" (table 3) est en realite regroupee
par MAISON DE VENTE, extraite comme le premier mot de
Identifiant_catalogue (avant le premier "_"), ex. "Bonhams" pour
"Bonhams_2014_8avril_Islamic_and_Indian_Art_part3".
"""

import csv
import os
from collections import Counter
from datetime import datetime

ARBITRAGE_CSV_PATH = r"arbitrages_contenu_absent_notice.csv"

OUTPUT_DIR = os.path.dirname(ARBITRAGE_CSV_PATH)
DELIMITER = ";"

COL_DECISION = "Decision_manuelle"
COL_CHAMP = "champ_concerne"
COL_CATALOGUE = "Identifiant_catalogue"

def charger_arbitrages(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        return list(reader)


def extraire_maison(identifiant_catalogue):
    """La maison de vente est le premier mot de l'Identifiant_catalogue,
    avant le premier '_' (ex. 'Bonhams_2014_8avril_...' -> 'Bonhams')."""
    identifiant_catalogue = (identifiant_catalogue or "").strip()
    if not identifiant_catalogue:
        return "(inconnu)"
    return identifiant_catalogue.split("_")[0].strip() or "(inconnu)"


def calculer_stats(lignes):
    total = len(lignes)

    decisions = Counter(
        (row.get(COL_DECISION) or "").strip()
        for row in lignes
    )

    champs = Counter(
        (row.get(COL_CHAMP) or "").strip()
        for row in lignes
    )

    # Par maison de vente : nb d'anomalies et nb de suppressions
    par_maison = {}
    for row in lignes:
        maison = extraire_maison(row.get(COL_CATALOGUE))
        decision = (row.get(COL_DECISION) or "").strip()
        if maison not in par_maison:
            par_maison[maison] = {"total": 0, "suppressions": 0}
        par_maison[maison]["total"] += 1
        if decision.startswith("A SUPPRIMER"):
            par_maison[maison]["suppressions"] += 1

    nb_supprimes = decisions.get("A SUPPRIMER - inscription invalidee, a retirer", 0)
    nb_corriger = decisions.get("A CORRIGER - inscription erronee, a modifier", 0)
    nb_ok = decisions.get("OK - contenu justifie, garder tel quel", 0)
    nb_faux = decisions.get("FAUX POSITIF - contenu bien present dans la notice", 0)
    nb_incertain = decisions.get("INCERTAIN - a revoir plus tard", 0)

    return {
        "total": total,
        "decisions": decisions,
        "nb_supprimes": nb_supprimes,
        "nb_corriger": nb_corriger,
        "nb_ok": nb_ok,
        "nb_faux": nb_faux,
        "nb_incertain": nb_incertain,
        "champs": champs,
        "par_maison": par_maison,
    }


def afficher_console(stats):
    print(f"\nTotal d'anomalies arbitrees : {stats['total']}")
    print("\nRepartition par decision :")
    for decision, n in sorted(stats["decisions"].items(), key=lambda x: -x[1]):
        pct = n / stats["total"] * 100 if stats["total"] else 0
        print(f"  {decision:<55} {n:>5}  ({pct:.1f} %)")

    print("\nRepartition par champ concerne :")
    for champ, n in stats["champs"].most_common():
        pct = n / stats["total"] * 100 if stats["total"] else 0
        print(f"  {champ:<45} {n:>5}  ({pct:.1f} %)")

    print("\nRepartition par maison de vente (anomalies / suppressions) :")
    for maison, d in sorted(stats["par_maison"].items(), key=lambda x: -x[1]["total"]):
        print(f"  {maison:<30} {d['total']:>5} anomalie(s)  |  {d['suppressions']:>4} suppression(s)")

LABELS_DECISIONS = {
    "OK - contenu justifie, garder tel quel":           r"\textit{OK} -- contenu justifie",
    "FAUX POSITIF - contenu bien present dans la notice": r"Faux positif",
    "A CORRIGER - inscription erronee, a modifier":     r"A corriger manuellement",
    "A SUPPRIMER - inscription invalidee, a retirer":   r"A supprimer",
    "INCERTAIN - a revoir plus tard":                   r"Incertain",
}


def fmt(n):
    """Formatage avec espace fine comme separateur de milliers (style FR)."""
    return f"{n:,}".replace(",", r"\,")


def pct(n, total):
    if total == 0:
        return "---"
    return f"{n / total * 100:.1f}\\,\\%"


def generer_latex(stats):
    total = stats["total"]
    lignes = []

    lignes.append("% -------------------------------------------------------")
    lignes.append("% Fragment genere par 24_stats_arbitrages.py")
    lignes.append("% A coller dans le rapport LaTeX")
    lignes.append("% -------------------------------------------------------")
    lignes.append("")

    # --- Table 1 : decisions ---
    lignes.append(r"\begin{table}[H]")
    lignes.append(r"  \centering")
    lignes.append(r"  \begin{tabular}{lrr}")
    lignes.append(r"    \toprule")
    lignes.append(r"    D\'{e}cision d'arbitrage & Effectif & Part \\")
    lignes.append(r"    \midrule")

    ordre = [
        "OK - contenu justifie, garder tel quel",
        "FAUX POSITIF - contenu bien present dans la notice",
        "A CORRIGER - inscription erronee, a modifier",
        "A SUPPRIMER - inscription invalidee, a retirer",
        "INCERTAIN - a revoir plus tard",
    ]
    for decision in ordre:
        n = stats["decisions"].get(decision, 0)
        label = LABELS_DECISIONS.get(decision, decision)
        lignes.append(f"    {label} & {fmt(n)} & {pct(n, total)} \\\\")

    lignes.append(r"    \midrule")
    lignes.append(f"    \\textbf{{Total}} & \\textbf{{{fmt(total)}}} & \\textbf{{100\\,\\%}} \\\\")
    lignes.append(r"    \bottomrule")
    lignes.append(r"  \end{tabular}")
    lignes.append(r"  \caption{R\'{e}partition des d\'{e}cisions d'arbitrage manuel (anomalies \textsc{contenu\_absent\_notice})}")
    lignes.append(r"\end{table}")
    lignes.append("")

    # --- Table 2 : champs concernes ---
    lignes.append(r"\begin{table}[H]")
    lignes.append(r"  \centering")
    lignes.append(r"  \begin{tabular}{lrr}")
    lignes.append(r"    \toprule")
    lignes.append(r"    Champ concern\'{e} & Effectif & Part \\")
    lignes.append(r"    \midrule")

    for champ, n in stats["champs"].most_common():
        champ_tex = champ.replace("_", r"\_")
        lignes.append(f"    \\texttt{{{champ_tex}}} & {fmt(n)} & {pct(n, total)} \\\\")

    lignes.append(r"    \bottomrule")
    lignes.append(r"  \end{tabular}")
    lignes.append(r"  \caption{Anomalies par champ concern\'{e}}")
    lignes.append(r"\end{table}")
    lignes.append("")

    # --- Table 3 : par maison de vente ---
    lignes.append(r"\begin{table}[H]")
    lignes.append(r"  \centering")
    lignes.append(r"  \begin{tabular}{lrrr}")
    lignes.append(r"    \toprule")
    lignes.append(r"    Maison de vente & Anomalies & Suppressions & Taux suppression \\")
    lignes.append(r"    \midrule")

    for maison, d in sorted(stats["par_maison"].items(), key=lambda x: -x[1]["total"]):
        maison_tex = maison.replace("_", r"\_")
        lignes.append(
            f"    {maison_tex} & {fmt(d['total'])} & {fmt(d['suppressions'])} "
            f"& {pct(d['suppressions'], d['total'])} \\\\"
        )

    lignes.append(r"    \bottomrule")
    lignes.append(r"  \end{tabular}")
    lignes.append(r"  \caption{Anomalies et suppressions par maison de vente}")
    lignes.append(r"\end{table}")

    return "\n".join(lignes)


def main():
    print("--- Script 24 : statistiques sur les arbitrages ---")
    print(f"Chargement : {ARBITRAGE_CSV_PATH}")

    lignes = charger_arbitrages(ARBITRAGE_CSV_PATH)
    print(f"  {len(lignes)} arbitrage(s) charge(s)")

    if not lignes:
        print("Fichier vide ou introuvable. Fin du script.")
        return

    stats = calculer_stats(lignes)
    afficher_console(stats)

    fragment_latex = generer_latex(stats)

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_sortie = f"stats_arbitrages_{horodatage}.tex"
    chemin_sortie = os.path.join(OUTPUT_DIR, nom_sortie)

    with open(chemin_sortie, "w", encoding="utf-8") as f:
        f.write(fragment_latex)

    print(f"LaTeX ecrit : {chemin_sortie}")


if __name__ == "__main__":
    main()
