
"""
Bilan stat construit en lisant les fichiers de log déjà produits par les scripts précédents
(aucune relecture du CSV, aucune modification de quoi que ce soit).

Sources lues (chemins à compléter ci-dessous ; laisser "" pour ignorer une
source si le fichier n'existe pas / n'a pas été généré) :

    - log_ajouts_devise_<timestamp>.txt          (script 11)
    - log_signalements_devise_<timestamp>.txt    (script 11)
    - sans_devise_detail_<timestamp>.txt         (script 09)
    - log_reformatages_prix_<timestamp>.txt              (script 12, mono-devise)
    - log_signalements_prix_<timestamp>.txt              (script 12, mono-devise)
    - log_reformatages_prix_multidevise_<timestamp>.txt  (script 13, multi-devises)
    - log_signalements_prix_multidevise_<timestamp>.txt  (script 13, multi-devises)

Plus une liste d'Id_perenne modifiés MANUELLEMENT (à coller dans
IDS_MODIFIES_MANUELLEMENT ci-dessous), pour les inclure dans le bilan
global.

Sortie : un unique fichier texte de bilan, avec tous les compteurs.
"""

import os
import re
from collections import Counter
from datetime import datetime

DOSSIER = r"\Programmes\output"

LOG_AJOUTS_DEVISE = os.path.join(DOSSIER, "log_ajouts_devise_20260708_142600.txt")
LOG_SIGNALEMENTS_DEVISE = os.path.join(DOSSIER, "log_signalements_devise_20260708_142600.txt")
LOG_SANS_DEVISE_DETAIL = os.path.join(DOSSIER, "sans_devise_detail_<A_COMPLETER>.txt")

LOG_REFORMATAGES_MONO = os.path.join(DOSSIER, "log_reformatages_prix_20260708_150048.txt")
LOG_SIGNALEMENTS_MONO = os.path.join(DOSSIER, "log_signalements_prix_20260708_150048")

LOG_REFORMATAGES_MULTI = os.path.join(DOSSIER, "log_reformatages_prix_multidevise_20260708_152723.txt")
LOG_SIGNALEMENTS_MULTI = os.path.join(DOSSIER, "log_signalements_prix_multidevise_20260708_152723.txt")

#ici, copier-coller la liste des id fusionnés manuellement
IDS_MODIFIES_MANUELLEMENT = []

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BILAN_PATH = os.path.join(DOSSIER, f"bilan_reformatage_prix_{TIMESTAMP}.txt")

def lire_lignes(path):
    """Retourne les lignes du fichier, ou None si le fichier est absent /
    non renseigné."""
    if not path or "<A_COMPLETER>" in path:
        return None
    if not os.path.isfile(path):
        print(f"[IGNORÉ] Fichier introuvable : {path}")
        return None
    with open(path, encoding="utf-8") as f:
        return f.readlines()


def compter_lignes_ajouts(path):
    """Compte les lignes de log_ajouts_devise_*.txt (format :
    'id ; catalog ; mode=... ; ancienne -> nouvelle'). Retourne
    (total, Counter par mode) ou (None, None) si fichier absent."""
    lignes = lire_lignes(path)
    if lignes is None:
        return None, None
    data = [l for l in lignes if " ; mode=" in l]
    par_mode = Counter()
    for l in data:
        m = re.search(r"mode=(\w+)", l)
        if m:
            par_mode[m.group(1)] += 1
    return len(data), par_mode


def compter_lignes_reformatages(path):
    """Compte les lignes de type 'id ; catalog ; "ancienne" -> "nouvelle"'."""
    lignes = lire_lignes(path)
    if lignes is None:
        return None
    data = [l for l in lignes if " -> " in l]
    return len(data)


def compter_sections_signalements(path):
    """Pour les logs de signalements avec sections
    '--- libelle (N) ---', retourne un dict {libelle: N}, ou None si
    fichier absent."""
    lignes = lire_lignes(path)
    if lignes is None:
        return None
    resultats = {}
    for l in lignes:
        m = re.match(r"--- (.+?) \((\d+)\) ---", l.strip())
        if m:
            resultats[m.group(1)] = int(m.group(2))
    return resultats


def compter_sans_devise(path):
    """Lit sans_devise_detail_*.txt (script 09), compte par catégorie
    ('vide' / 'sans_devise'). Retourne un Counter, ou None si absent."""
    lignes = lire_lignes(path)
    if lignes is None:
        return None
    par_categorie = Counter()
    for l in lignes:
        parts = [p.strip() for p in l.strip().split(" ; ")]
        if len(parts) >= 3 and parts[2] in ("vide", "sans_devise"):
            par_categorie[parts[2]] += 1
    return par_categorie


def fmt(valeur):
    return "N/A (fichier non fourni)" if valeur is None else str(valeur)


def process():
    lignes_bilan = []

    def ecrire(texte=""):
        lignes_bilan.append(texte)
        print(texte)

    ecrire("=" * 70)
    ecrire(f"BILAN DU CHANTIER DEVISE / UNIFORMISATION DES PRIX - {TIMESTAMP}")
    ecrire("=" * 70)

    # --- 1. Lignes identifiées comme "sans devise" (script 09) ---
    ecrire("\n--- 1. Lignes sans devise identifiées (script 09) ---")
    sans_devise = compter_sans_devise(LOG_SANS_DEVISE_DETAIL)
    if sans_devise is None:
        ecrire(f"  {fmt(None)}")
    else:
        ecrire(f"  Vides            : {sans_devise.get('vide', 0)}")
        ecrire(f"  Sans devise (texte présent) : {sans_devise.get('sans_devise', 0)}")
        ecrire(f"  Total            : {sum(sans_devise.values())}")

    # --- 2. Ajouts de devise effectués (script 11) ---
    ecrire("\n--- 2. Devises ajoutées automatiquement (script 11) ---")
    total_ajouts, par_mode = compter_lignes_ajouts(LOG_AJOUTS_DEVISE)
    if total_ajouts is None:
        ecrire(f"  {fmt(None)}")
    else:
        ecrire(f"  Total ajouts               : {total_ajouts}")
        ecrire(f"    dont via liste manuelle  : {par_mode.get('manuel', 0)}")
        ecrire(f"    dont devinées (catalogue): {par_mode.get('devine_unique', 0)}")

    ecrire("\n--- 2bis. Lignes non corrigées automatiquement (script 11) ---")
    signal_devise = compter_sections_signalements(LOG_SIGNALEMENTS_DEVISE)
    if signal_devise is None:
        ecrire(f"  {fmt(None)}")
    else:
        total_signal_devise = 0
        for libelle, n in signal_devise.items():
            ecrire(f"  {libelle} : {n}")
            total_signal_devise += n
        ecrire(f"  Total non corrigé : {total_signal_devise}")

    # --- 3. Reformatage mono-devise (script 12) ---
    ecrire("\n--- 3. Reformatages mono-devise (script 12) ---")
    total_mono = compter_lignes_reformatages(LOG_REFORMATAGES_MONO)
    ecrire(f"  Total reformatées : {fmt(total_mono)}")

    signal_mono = compter_sections_signalements(LOG_SIGNALEMENTS_MONO)
    total_signal_mono = None
    if signal_mono is not None:
        total_signal_mono = 0
        for libelle, n in signal_mono.items():
            ecrire(f"    (non modifiées) {libelle} : {n}")
            total_signal_mono += n
        ecrire(f"  Total non modifiées (mono) : {total_signal_mono}")
    else:
        ecrire(f"  Total non modifiées (mono) : {fmt(None)}")

    # --- 4. Reformatage multi-devises (script 13) ---
    ecrire("\n--- 4. Reformatages multi-devises (script 13) ---")
    total_multi = compter_lignes_reformatages(LOG_REFORMATAGES_MULTI)
    ecrire(f"  Total reformatées : {fmt(total_multi)}")

    signal_multi = compter_sections_signalements(LOG_SIGNALEMENTS_MULTI)
    total_signal_multi = None
    if signal_multi is not None:
        total_signal_multi = 0
        for libelle, n in signal_multi.items():
            ecrire(f"    (non modifiées) {libelle} : {n}")
            total_signal_multi += n
        ecrire(f"  Total non modifiées (multi) : {total_signal_multi}")
    else:
        ecrire(f"  Total non modifiées (multi) : {fmt(None)}")

    # --- 5. Modifications manuelles ---
    ecrire("\n--- 5. Modifications manuelles ---")
    nb_manuel = len(IDS_MODIFIES_MANUELLEMENT)
    ecrire(f"  Nombre d'Id_perenne modifiés à la main : {nb_manuel}")
    if nb_manuel:
        doublons = [id_ for id_, c in Counter(IDS_MODIFIES_MANUELLEMENT).items() if c > 1]
        if doublons:
            ecrire(f"  [ATTENTION] Id_perenne en double dans la liste manuelle : {doublons}")

    # --- 6. Total consolidé ---
    ecrire("\n--- 6. Total consolidé (reformatages automatiques + manuels) ---")
    composantes = [total_mono, total_multi, nb_manuel]
    if all(c is not None for c in composantes):
        total_general = sum(composantes)
        ecrire(f"  Reformatages automatiques (mono + multi) : {(total_mono or 0) + (total_multi or 0)}")
        ecrire(f"  Modifications manuelles                  : {nb_manuel}")
        ecrire(f"  TOTAL GÉNÉRAL                             : {total_general}")
    else:
        ecrire("  Incomplet : au moins un des fichiers de log requis est manquant.")

    ecrire("\n" + "=" * 70)

    with open(BILAN_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes_bilan) + "\n")

    print(f"\nBilan écrit dans : {BILAN_PATH}")


if __name__ == "__main__":
    process()
