import os
import re
import shutil
import pandas as pd

DOSSIER_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DOSSIER_PARENT = os.path.dirname(DOSSIER_SCRIPT)

NOM_FICHIER_CSV = "Enora_version_travail_export_lots_export_lots_13_mai.csv"
CSV_PATH = os.path.join(DOSSIER_PARENT, NOM_FICHIER_CSV)

DIR_NAME = os.path.dirname(CSV_PATH)
BASE_NAME = os.path.basename(CSV_PATH)

BACKUP_PATH = os.path.join(DIR_NAME, f"backup_1_{BASE_NAME}")
LOG_PATH = os.path.join(DIR_NAME, "journal_nettoyage_prix.txt")

CSV_SEPARATOR = '\t'

def normaliser_estimation(row, nom_colonne, journal_logs, stats):
    """
    Analyse, nettoie et normalise une cellule de prix.
    Utilise les métadonnées de la ligne pour le journal d'audit.
    """
    valeur = row[nom_colonne]
    
    # Extraction des métadonnées pour identification unique dans le log
    titre_vente = str(row.get('Titre_vente', 'Vente inconnue')).strip()
    num_lot = str(row.get('Numero_lot', 'Lot inconnu')).strip()
    titre_lot = str(row.get('Titre_lot', 'Titre inconnu')).strip()
    
    # Tronquer le titre du lot s'il est trop long pour garder le log lisible
    titre_lot_court = (titre_lot[:47] + '...') if len(titre_lot) > 50 else titre_lot
    id_lot = f"[Vente: {titre_vente} | Lot n°{num_lot} ({titre_lot_court})]"

    if pd.isna(valeur):
        stats['vides'] += 1
        return valeur
    
    text_original = str(valeur).strip()
    if not text_original:
        stats['vides'] += 1
        return valeur

    # 1. Détection de la monnaie (Insensible à la casse)
    text_minuscule = text_original.lower()
    monnaies_trouvees = set()
    
    if 'hk$' in text_minuscule:
        monnaies_trouvees.add('HK$')
    if 'us$' in text_minuscule or re.search(r'(?<!hk)\$', text_minuscule):
        monnaies_trouvees.add('$')
    if 'gbp' in text_minuscule or '£' in text_minuscule:
        monnaies_trouvees.add('£')
    if any(m in text_minuscule for m in ['eur', '€', 'euro']):
        monnaies_trouvees.add('€')

    # Vérification des règles sur la monnaie
    if len(monnaies_trouvees) == 0:
        journal_logs.append(f"{id_lot} - IGNORÉE : Aucune monnaie reconnue dans '{text_original}'")
        stats['ignorees'] += 1
        return text_original
    if len(monnaies_trouvees) > 1:
        journal_logs.append(f"{id_lot} - IGNORÉE : Plusieurs monnaies différentes détectées dans '{text_original}'")
        stats['ignorees'] += 1
        return text_original

    symbole_monnaie = list(monnaies_trouvees)[0]

    # 2. Nettoyage des séparateurs de milliers de type bruit (espaces, virgules, points)
    text_nettoye = text_original
    for _ in range(3):  
        text_nettoye = re.sub(r'(\d)[,\.\s](\d{3})(?!\d)', r'\1\2', text_nettoye)

    # 3. Extraction de toutes les séquences de chiffres isolées
    nombres = re.findall(r'\d+', text_nettoye)

    # Vérification du nombre de valeurs extraites
    if len(nombres) == 0:
        journal_logs.append(f"{id_lot} - IGNORÉE : Aucun nombre exploitable trouvé dans '{text_original}'")
        stats['ignorees'] += 1
        return text_original
    if len(nombres) > 2:
        journal_logs.append(f"{id_lot} - IGNORÉE : Cellule trop complexe ou contenant trop de valeurs ({len(nombres)}) dans '{text_original}'")
        stats['ignorees'] += 1
        return text_original

    # 4. Formatage et normalisation finale
    if len(nombres) == 2:
        min_val = int(nombres[0])
        max_val = int(nombres[1])
        text_normalise = f"{symbole_monnaie}{min_val:,} - {symbole_monnaie}{max_val:,}"
        journal_logs.append(f"{id_lot} - REFORMATÉE : '{text_original}' -> '{text_normalise}'")
        stats['reformatees'] += 1
        return text_normalise
    else:  # len(nombres) == 1
        unique_val = int(nombres[0])
        text_normalise = f"{symbole_monnaie}{unique_val:,}"
        journal_logs.append(f"{id_lot} - REFORMATÉE (Valeur unique) : '{text_original}' -> '{text_normalise}'")
        stats['reformatees'] += 1
        return text_normalise


# =====================================================================
# SCRIPT PRINCIPAL
# =====================================================================
def main():
    
    # 1. Création de la sauvegarde de sécurité
    try:
        shutil.copy2(CSV_PATH, BACKUP_PATH)
        print(f" Sauvegarde créée avec succès : '{BACKUP_PATH}'")
    except Exception as e:
        print(f"Impossible de créer la sauvegarde. Fin du programme. ({e})")
        return

    # 2. Lecture du fichier CSV
    try:
        df = pd.read_csv(CSV_PATH, sep=CSV_SEPARATOR, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, sep=CSV_SEPARATOR, encoding='latin-1')

    # Gestion de la casse du nom de colonne 'Estimation_lot'
    nom_colonne = None
    for col in df.columns:
        if col.strip().lower() == 'estimation_lot':
            nom_colonne = col
            break

    if not nom_colonne:
        print(f"Erreur : La colonne 'Estimation_lot' n'a pas été trouvée.")
        return

    # Initialisation des compteurs et des logs
    logs = []
    stats = {'reformatees': 0, 'ignorees': 0, 'vides': 0}
    total_lignes = len(df)
    
    print(" Analyse et normalisation des prix...")
    
    # 3. Application du traitement ligne par ligne via un apply (permet d'accéder à tout le context de la ligne)
    df[nom_colonne] = df.apply(
        lambda row: normaliser_estimation(row, nom_colonne, logs, stats), 
        axis=1
    )

    # 4. Écriture du fichier CSV nettoyé
    print(" Enregistrement des données modifiées...")
    df.to_csv(CSV_PATH, sep=CSV_SEPARATOR, index=False, encoding='utf-8')

    # 5. Écriture du Journal des modifications (Log)
    print(f" Génération du journal d'audit...")
    with open(LOG_PATH, 'w', encoding='utf-8') as f_log:
        f_log.write("=====================================================================\n")
        f_log.write("         JOURNAL DE NETTOYAGE DE LA COLONNE ESTIMATION_LOT            \n")
        f_log.write("=====================================================================\n\n")
        for log_line in logs:
            f_log.write(log_line + "\n")

    print(f" Total des lignes dans le fichier : {total_lignes}")
    print(f" Lignes reformatées avec succès   : {stats['reformatees']}")
    print(f" Lignes ignorées (bruitées)       : {stats['ignorees']}")
    print(f" Lignes vides                     : {stats['vides']}")
    
    print(" Traitement terminé avec succès !")
    print(f" Fichier nettoyé : '{CSV_PATH}'")
    print(f" Journal des modifications créé : '{LOG_PATH}'")

if __name__ == "__main__":
    main()