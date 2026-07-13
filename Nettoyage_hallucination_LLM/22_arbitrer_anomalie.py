"""
Interface graphique (Tkinter) d'arbitrage manuel des anomalies de type
CONTENU_ABSENT_NOTICE (Inscription_transcription ou
Inscription_transliterration absente de la Notice), issues du rapport
genere par detecter_anomalies_inscriptions.py.

Cet outil ne traite QUE ce type d'anomalie : les autres types eventuels
presents dans le rapport (NOTICE_DEBUT_NON_LATIN, BOOLEEN_INCOHERENT)
sont ignores des le chargement.

IMPORTANT - LECTURE SEULE : cet outil n'ecrit JAMAIS dans le rapport
d'anomalies ni dans le CSV lots. Ces deux fichiers sont uniquement lus.
La seule ecriture effectuee par le programme est le fichier d'arbitrages
separe (ARBITRAGE_CSV_PATH) : les decisions y sont enregistrees au fur
et a mesure, mais ne sont jamais "appliquees" aux donnees source. Un
script distinct serait necessaire pour repercuter ces decisions sur le
CSV lots, si besoin, plus tard.

Pour chaque anomalie du rapport :
    - affiche le champ concerne et sa valeur
    - affiche la NOTICE COMPLETE du lot correspondant (relue depuis le
      CSV lots via Id_perenne, car le rapport d'anomalies ne contient
      qu'un extrait de contexte)
    - permet d'ouvrir la ou les pages Arkindex liees au lot dans le
      navigateur (Lien_page_arkindex peut contenir PLUSIEURS liens
      separes par "|" : dans ce cas, chaque lien est ouvert dans un
      nouvel onglet)
    - permet de choisir une decision d'arbitrage parmi une liste
      predefinie, avec un commentaire libre optionnel

Reprise de session : au demarrage, le fichier d'arbitrages existant (si
present) est relu, et les anomalies deja arbitrees sont sautees
automatiquement -> on peut fermer et rouvrir l'outil sans perdre sa
progression.

Attention encodage : les champs peuvent contenir de l'arabe ou de
l'hebreu. Toute lecture/ecriture CSV se fait en UTF-8 (utf-8-sig). Si
l'arabe/l'hebreu ne s'affiche pas correctement dans l'interface, changer
la police definie dans POLICE_TEXTE plus bas (ex. "Segoe UI" ou "Arial
Unicode MS" sous Windows, generalement mieux fournies).
"""

import csv
import os
import tkinter as tk
import webbrowser
from tkinter import ttk, scrolledtext, messagebox


# A adapter : chemins des fichiers generes par les scripts precedents
ANOMALIES_CSV_PATH = r"Crapport_anomalies_inscriptions_.csv"
LOTS_CSV_PATH = r"chemin_du_csv_des_lots.csv"

# Cet outil ne traite QUE les anomalies de ce type (les autres types
# eventuellement presents dans le rapport sont ignores des le chargement)
TYPE_ANOMALIE_TRAITE = "CONTENU_ABSENT_NOTICE"

DELIMITER = ";"

# Fichier de sortie des arbitrages : nom FIXE (pas de timestamp), pour
# pouvoir reprendre la session plus tard sans creer un nouveau fichier
# a chaque lancement. C'est le SEUL fichier ecrit par cet outil : le
# rapport d'anomalies et le CSV lots sont ouverts en lecture seule et ne
# sont jamais modifies, quelle que soit la decision prise.
ARBITRAGE_CSV_PATH = os.path.join(
    os.path.dirname(ANOMALIES_CSV_PATH), "arbitrages_contenu_absent_notice.csv"
)

ID_COLUMN_LOTS = "Id_perenne"
NOTICE_COLUMN_LOTS = "Notice"
LIEN_ARKINDEX_COLUMN_LOTS = "Lien_page_arkindex"
TITRE_LOT_COLUMN_LOTS = "Titre_lot"

SEPARATEUR_LIENS = "|"

DECISIONS_POSSIBLES = [
    "OK - contenu justifie, garder tel quel",
    "FAUX POSITIF - contenu bien present dans la notice",
    "A CORRIGER - inscription erronee, a modifier",
    "A SUPPRIMER - inscription invalidee, a retirer",
    "INCERTAIN - a revoir plus tard",
]

POLICE_TEXTE = ("Segoe UI", 11)
POLICE_TITRE = ("Segoe UI", 11, "bold")


def charger_anomalies(path, type_anomalie_filtre=None):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        lignes = list(reader)
    if type_anomalie_filtre is None:
        return lignes
    return [row for row in lignes if (row.get("type_anomalie") or "").strip() == type_anomalie_filtre]


def charger_index_lots(path):
    """Renvoie un dict Id_perenne -> ligne du CSV lots, pour retrouver
    rapidement la notice complete et le lien Arkindex d'un lot."""
    index = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        for row in reader:
            id_perenne = (row.get(ID_COLUMN_LOTS) or "").strip()
            if id_perenne:
                index[id_perenne] = row
    return index


def charger_arbitrages_existants(path):
    """Renvoie un dict cle -> ligne de decision deja enregistree, pour
    permettre la reprise de session."""
    if not os.path.exists(path):
        return {}
    arbitrages = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        for row in reader:
            cle = cle_anomalie(row)
            arbitrages[cle] = row
    return arbitrages


def cle_anomalie(row):
    """Cle unique identifiant une anomalie, utilisee pour reperer si
    elle a deja ete arbitree."""
    return (
        (row.get("numero_ligne") or "").strip(),
        (row.get("Id_perenne") or "").strip(),
        (row.get("type_anomalie") or "").strip(),
        (row.get("champ_concerne") or "").strip(),
    )


class ApplicationArbitrage(tk.Tk):

    def __init__(self, anomalies, index_lots, arbitrages_existants):
        super().__init__()

        self.title("Arbitrage manuel (lecture seule) - contenu absent de la notice")
        self.geometry("1000x750")
        # Hauteur minimale pour que les boutons de navigation restent toujours visibles
        self.minsize(800, 600)

        self.anomalies = anomalies
        self.index_lots = index_lots
        self.arbitrages = dict(arbitrages_existants)  # cle -> dict deja sauvegarde

        # liste des anomalies restant a traiter (celles pas encore dans self.arbitrages)
        self.anomalies_a_traiter = [a for a in self.anomalies if cle_anomalie(a) not in self.arbitrages]
        self.position = 0

        self._liens_courants = []

        self._construire_interface()
        self._afficher_anomalie_courante()

    # ------------------------------------------------------------------
    def _construire_interface(self):
        # ----------------------------------------------------------------
        # ZONE HAUTE : progression + infos
        # ----------------------------------------------------------------
        cadre_haut = ttk.Frame(self, padding=10)
        cadre_haut.pack(fill="x")

        self.label_progression = ttk.Label(cadre_haut, text="", font=POLICE_TITRE)
        self.label_progression.pack(side="left")

        self.label_infos = ttk.Label(cadre_haut, text="", font=POLICE_TEXTE, justify="left")
        self.label_infos.pack(side="left", padx=20)

        # ----------------------------------------------------------------
        # ZONE BAS : navigation — packee EN PREMIER avec side="bottom"
        # pour qu'elle soit toujours visible quelle que soit la hauteur
        # du contenu au-dessus. C'est la cause du bug original : en
        # packant la navigation en dernier avec side="top" (defaut), elle
        # etait expulsee hors de la fenetre quand les zones de texte se
        # vidaient et que Tkinter recalculait la geometrie.
        # ----------------------------------------------------------------
        cadre_nav = ttk.Frame(self, padding=10)
        cadre_nav.pack(side="bottom", fill="x")

        self.bouton_precedent = ttk.Button(cadre_nav, text="< Precedent", command=self._precedent)
        self.bouton_precedent.pack(side="left")

        self.bouton_passer = ttk.Button(cadre_nav, text="Passer (sans decider)", command=self._suivant)
        self.bouton_passer.pack(side="left", padx=10)

        self.bouton_enregistrer = ttk.Button(
            cadre_nav, text="Enregistrer et suivant >", command=self._enregistrer_et_suivant
        )
        self.bouton_enregistrer.pack(side="right")

        # ----------------------------------------------------------------
        # ZONE MILIEU : contenu (champ, notice, lien, decision)
        # packee apres la navigation pour occuper l'espace restant
        # ----------------------------------------------------------------
        cadre_contenu = ttk.Frame(self)
        cadre_contenu.pack(fill="both", expand=True)

        # --- champ concerne ---
        cadre_champ = ttk.LabelFrame(cadre_contenu, text="Champ concerne / valeur", padding=10)
        cadre_champ.pack(fill="x", padx=10, pady=5)

        self.texte_champ = scrolledtext.ScrolledText(cadre_champ, height=4, wrap="word", font=POLICE_TEXTE)
        self.texte_champ.pack(fill="x")
        self.texte_champ.configure(state="disabled")

        # --- decision --- packee EN PREMIER avec side="bottom" pour
        # qu'elle soit toujours visible, avant que la notice ne prenne
        # l'espace restant avec expand=True
        cadre_decision = ttk.LabelFrame(cadre_contenu, text="Decision", padding=10)
        cadre_decision.pack(side="bottom", fill="x", padx=10, pady=5)

        self.variable_decision = tk.StringVar()
        for decision in DECISIONS_POSSIBLES:
            ttk.Radiobutton(
                cadre_decision, text=decision, value=decision, variable=self.variable_decision
            ).pack(anchor="w")

        ttk.Label(cadre_decision, text="Commentaire (optionnel) :", font=POLICE_TEXTE).pack(anchor="w", pady=(8, 0))
        self.entree_commentaire = ttk.Entry(cadre_decision, font=POLICE_TEXTE)
        self.entree_commentaire.pack(fill="x")

        # --- bouton arkindex --- aussi en bottom, au-dessus de la decision
        cadre_lien = ttk.Frame(cadre_contenu, padding=10)
        cadre_lien.pack(side="bottom", fill="x")

        self.bouton_arkindex = ttk.Button(
            cadre_lien, text="Ouvrir la/les page(s) Arkindex", command=self._ouvrir_arkindex
        )
        self.bouton_arkindex.pack(side="left")

        self.label_lien = ttk.Label(cadre_lien, text="", font=POLICE_TEXTE)
        self.label_lien.pack(side="left", padx=10)

        # --- notice complete --- packee en dernier, prend l'espace restant
        cadre_notice = ttk.LabelFrame(cadre_contenu, text="Notice complete du lot", padding=10)
        cadre_notice.pack(fill="both", expand=True, padx=10, pady=5)

        self.texte_notice = scrolledtext.ScrolledText(cadre_notice, wrap="word", font=POLICE_TEXTE)
        self.texte_notice.pack(fill="both", expand=True)
        self.texte_notice.configure(state="disabled")

    # ------------------------------------------------------------------
    def _anomalie_courante(self):
        if 0 <= self.position < len(self.anomalies_a_traiter):
            return self.anomalies_a_traiter[self.position]
        return None

    def _afficher_anomalie_courante(self):
        anomalie = self._anomalie_courante()

        total_restant = len(self.anomalies_a_traiter)
        total_general = len(self.anomalies)
        total_traite = total_general - total_restant

        if anomalie is None:
            self.label_progression.config(
                text=f"Toutes les anomalies ont ete arbitrees ({total_traite} / {total_general})."
            )
            self.label_infos.config(text="")
            self._remplacer_texte(self.texte_champ, "")
            self._remplacer_texte(self.texte_notice, "Arbitrage termine. Vous pouvez fermer la fenetre.")
            self.label_lien.config(text="")
            self.bouton_arkindex.state(["disabled"])
            self.bouton_enregistrer.state(["disabled"])
            self.bouton_passer.state(["disabled"])
            self.bouton_precedent.state(["disabled"])
            return

        # Des anomalies restent : tous les boutons sont actifs
        self.bouton_enregistrer.state(["!disabled"])
        self.bouton_passer.state(["!disabled"])
        self.bouton_precedent.state(["!disabled"] if self.position > 0 else ["disabled"])

        self.label_progression.config(
            text=f"Anomalie {self.position + 1} / {total_restant} restantes  "
                 f"(deja arbitrees : {total_traite} / {total_general})"
        )

        id_perenne = (anomalie.get("Id_perenne") or "").strip()
        infos = (
            f"Id_perenne : {id_perenne}    "
            f"Catalogue : {anomalie.get('Identifiant_catalogue', '')}    "
            f"Type : {anomalie.get('type_anomalie', '')}    "
            f"Ratio : {anomalie.get('ratio_inclusion', '')}"
        )
        self.label_infos.config(text=infos)

        # --- champ concerne ---
        contenu_champ = (
            f"Champ : {anomalie.get('champ_concerne', '')}\n\n"
            f"Valeur : {anomalie.get('valeur_champ', '')}\n\n"
            f"Contexte (extrait du rapport) : {anomalie.get('contexte_notice', '')}"
        )
        self._remplacer_texte(self.texte_champ, contenu_champ)

        # --- notice complete, relue depuis le CSV lots ---
        lot = self.index_lots.get(id_perenne)
        if lot is not None:
            titre_lot = (lot.get(TITRE_LOT_COLUMN_LOTS) or "").strip()
            notice_complete = (lot.get(NOTICE_COLUMN_LOTS) or "").strip()
            contenu_notice = f"Titre du lot : {titre_lot}\n\n{notice_complete}"
        else:
            contenu_notice = "(lot introuvable dans le CSV lots pour cet Id_perenne)"
        self._remplacer_texte(self.texte_notice, contenu_notice)

        # --- lien(s) arkindex ---
        liens = self._recuperer_liens(lot)
        if liens:
            self.label_lien.config(text=f"{len(liens)} page(s) liee(s)")
            self.bouton_arkindex.state(["!disabled"])
        else:
            self.label_lien.config(text="(aucun lien Arkindex trouve)")
            self.bouton_arkindex.state(["disabled"])
        self._liens_courants = liens

        # reinitialisation des champs de decision
        self.variable_decision.set("")
        self.entree_commentaire.delete(0, "end")

    def _recuperer_liens(self, lot):
        if lot is None:
            return []
        valeur = (lot.get(LIEN_ARKINDEX_COLUMN_LOTS) or "").strip()
        if valeur == "":
            return []
        return [lien.strip() for lien in valeur.split(SEPARATEUR_LIENS) if lien.strip()]

    def _ouvrir_arkindex(self):
        liens = getattr(self, "_liens_courants", [])
        if not liens:
            messagebox.showinfo("Aucun lien", "Aucune page Arkindex n'est associee a ce lot.")
            return
        for lien in liens:
            webbrowser.open_new_tab(lien)

    # ------------------------------------------------------------------
    def _vider_texte(self, widget):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def _remplacer_texte(self, widget, contenu):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", contenu)
        widget.configure(state="disabled")

    # ------------------------------------------------------------------
    def _enregistrer_et_suivant(self):
        anomalie = self._anomalie_courante()
        if anomalie is None:
            return

        decision = self.variable_decision.get()
        if decision == "":
            messagebox.showwarning("Decision manquante", "Choisir une decision avant d'enregistrer.")
            return

        commentaire = self.entree_commentaire.get().strip()

        cle = cle_anomalie(anomalie)
        ligne_arbitrage = dict(anomalie)
        ligne_arbitrage["Decision_manuelle"] = decision
        ligne_arbitrage["Commentaire_arbitrage"] = commentaire

        self.arbitrages[cle] = ligne_arbitrage
        self._sauvegarder_arbitrages()

        # retire l'anomalie traitee de la liste et reste a la meme position
        del self.anomalies_a_traiter[self.position]
        if self.position >= len(self.anomalies_a_traiter):
            self.position = max(0, len(self.anomalies_a_traiter) - 1)

        self._afficher_anomalie_courante()

    def _suivant(self):
        if self.position < len(self.anomalies_a_traiter) - 1:
            self.position += 1
            self._afficher_anomalie_courante()

    def _precedent(self):
        if self.position > 0:
            self.position -= 1
            self._afficher_anomalie_courante()

    def _sauvegarder_arbitrages(self):
        """Reecrit l'integralite du fichier d'arbitrages a chaque
        decision : plus lent que d'ajouter une ligne, mais plus sur
        (aucun risque de fichier CSV corrompu en cas de fermeture
        brutale de l'application en cours d'ecriture)."""
        if not self.arbitrages:
            return

        colonnes_base = list(next(iter(self.arbitrages.values())).keys())
        # on s'assure que Decision_manuelle et Commentaire_arbitrage sont bien presents
        for colonne_supplementaire in ("Decision_manuelle", "Commentaire_arbitrage"):
            if colonne_supplementaire not in colonnes_base:
                colonnes_base.append(colonne_supplementaire)

        with open(ARBITRAGE_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=colonnes_base, delimiter=DELIMITER)
            writer.writeheader()
            for ligne in self.arbitrages.values():
                writer.writerow(ligne)


def main():
    print(f"Chargement des anomalies depuis : {ANOMALIES_CSV_PATH}")
    print(f"  (filtre applique : type_anomalie == {TYPE_ANOMALIE_TRAITE})")
    anomalies = charger_anomalies(ANOMALIES_CSV_PATH, type_anomalie_filtre=TYPE_ANOMALIE_TRAITE)
    print(f"  {len(anomalies)} anomalie(s) de type {TYPE_ANOMALIE_TRAITE} chargee(s)")

    print(f"Chargement de l'index des lots depuis : {LOTS_CSV_PATH}")
    index_lots = charger_index_lots(LOTS_CSV_PATH)
    print(f"  {len(index_lots)} lot(s) indexe(s)")

    print(f"Chargement des arbitrages existants depuis : {ARBITRAGE_CSV_PATH}")
    arbitrages_existants = charger_arbitrages_existants(ARBITRAGE_CSV_PATH)
    print(f"  {len(arbitrages_existants)} arbitrage(s) deja enregistre(s), seront saute(s)")

    app = ApplicationArbitrage(anomalies, index_lots, arbitrages_existants)
    app.mainloop()


if __name__ == "__main__":
    main()
