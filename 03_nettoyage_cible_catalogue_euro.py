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

BACKUP_PATH = os.path.join(DIR_NAME, f"backup_3_{BASE_NAME}")
LOG_MODIF_PATH = os.path.join(DIR_NAME, "journal_nettoyage_force_euro.txt")
LOG_IGNORE_PATH = os.path.join(DIR_NAME, "journal_elements_ignores_finaux_v3.txt")

CSV_SEPARATOR = '\t'

# LISTE DES CATALOGUES CIBLES (CASSE EXACTE RESPECTÉE)
CATALOGUES_EURO_FORCED = {
    "PRINTEMPS ASIATIQUE ASIE & ORIENT",
    "ARTS D'ORIENT",
    "Collection C. et à Divers Amateurs ART OTTOMAN ET D'ORIENT",
    "ARCHÉOLOGIE & ARTS D'ORIENT",
    "Orient classique, Trendy, Arty, III",
    "ARTS D'ORIENT & DE L'INDE",
    "ART TRIBAL - ART PRÉCOLOMBIEN",
    "ARTS PRÉCOLOMBIENS - ART TRIBAL ART DE L'ISLAM ARCHÉOLOGIE",
    "ARTS PRÉCOLOMBIENS - ARTS DE L'ISLAM ARTS ASIATIQUES"
}

def forcer_euro_estimation(row, nom_colonne, journal_modifs, journal_ignores, stats):
    """
    Force l'application de la monnaie '€' sur les lignes des catalogues cibles 
    qui n'ont pas pu être nettoyées par les scripts précédents.
    Respecte strictement la casse des noms de catalogues.
    """
    valeur = row[nom_colonne]
    
    # Métadonnées pour le suivi et le journal d'audit
    titre_vente = str(row.get('Titre_vente', 'Vente inconnue')).strip()
    num_lot = str(row.get('Numero_lot', 'Lot inconnu')).strip()
    titre_lot = str(row.get('Titre_lot', 'Titre inconnu')).strip()
    titre_lot_court = (titre_lot[:47] + '...') if len(titre_lot) > 50 else titre_lot
    id_lot = f"[Vente: {titre_vente} | Lot n°{num_lot} ({titre_lot_court})]"

    if pd.isna(valeur):
        stats['vides'] += 1
        return valeur
    
    texte_original = str(valeur).strip()
    if not texte_original:
        stats['vides'] += 1
        return valeur

    # Expression régulière pour détecter si la cellule est DÉJÀ PROPRE (Script 1 ou 2)
    pattern_deja_propre = r'^\s*(?:HK\$|US\$|[$£€])\d{1,3}(?:\,\d{3})*(?:\s*-\s*(?:HK\$|US\$|[$£€])\d{1,3}(?:\,\d{3})*)?(?:\s*;\s*(?:HK\$|US\$|[$£€])\d{1,3}(?:\,\d{3})*(?:\s*-\s*(?:HK\$|US\$|[$£€])\d{1,3}(?:\,\d{3})*)?)*\s*$'
    
    if re.match(pattern_deja_propre, texte_original):
        stats['deja_propres'] += 1
        return texte_original

    # Comparaison stricte avec respect de la casse (sans .lower())
    if titre_vente.strip() in CATALOGUES_EURO_FORCED:
        
        # 1. Nettoyage des bruits d'espace ou points dans les milliers
        texte_nettoye = texte_original
        for _ in range(3):  
            texte_nettoye = re.sub(r'(\d)[,\.\s](\d{3})(?!\d)', r'\1\2', texte_nettoye)
        
        # 2. Découpage de la cellule selon les séparateurs de blocs courants (/, ;, ou retour à la ligne)
        blocs_potentiels = re.split(r'[;\/\n\t]', texte_nettoye)
        intervalles_reconstruits = []
        
        for bloc in blocs_potentiels:
            # Extraction des séquences de chiffres dans ce sous-bloc
            nombres = re.findall(r'\d+', bloc)
            
            if not nombres:
                continue
            
            # Reconstruction par paires (intervalles) ou valeurs uniques
            for i in range(0, len(nombres), 2):
                if i + 1 < len(nombres):
                    val1 = int(nombres[i])
                    val2 = int(nombres[i+1])
                    intervalles_reconstruits.append(f"€{val1:,} - €{val2:,}")
                else:
                    val1 = int(nombres[i])
                    intervalles_reconstruits.append(f"€{val1:,}")
                    
        # 3. Assemblage final des blocs trouvés
        if intervalles_reconstruits:
            texte_normalise = " - ".join(intervalles_reconstruits)
            
            # --- PRINTS DE DEBUG EN CONSOLE ---
            print(f"EURO {id_lot}")
            print(f"   • Avant : {texte_original}")
            print(f"   • Après : {texte_normalise}\n")
            
            journal_modifs.append(f"{id_lot} - FORCÉ EURO : '{texte_original}' -> '{texte_normalise}'")
            stats['reformatees_forcee'] += 1
            return texte_normalise
        else:
            # Aucun nombre trouvé dans le catalogue cible
            journal_ignores.append(f"{id_lot} - TOUJOURS INEXPLOITABLE (Aucun chiffre) : '{texte_original}'")
            stats['toujours_ignorees'] += 1
            return texte_original
    else:
        # La ligne n'est pas propre mais n'appartient PAS à un catalogue cible 
        journal_ignores.append(f"{id_lot} - IGNORÉ (Hors cible de ce script) : '{texte_original}'")
        stats['toujours_ignorees'] += 1
        return texte_original


def main():
    
    if not os.path.exists(CSV_PATH):
        print(f"Erreur : Fichier CSV introuvable à l'adresse relative : '{CSV_PATH}'")
        return

    # 1. Sauvegarde de sécurité Niveau 3
    try:
        shutil.copy2(CSV_PATH, BACKUP_PATH)
        print(f" Sauvegarde 'backup_3' créée avec succès : '{BACKUP_PATH}'")
    except Exception as e:
        print(f"Erreur critique lors du backup_3 : {e}")
        return

    try:
        df = pd.read_csv(CSV_PATH, sep=CSV_SEPARATOR, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, sep=CSV_SEPARATOR, encoding='latin-1')

    nom_colonne = None
    for col in df.columns:
        if col.strip().lower() == 'estimation_lot':
            nom_colonne = col
            break

    if not nom_colonne:
        print(f"Erreur : Colonne 'Estimation_lot' introuvable.")
        return

    # Initialisation des variables
    journal_modifs = []
    journal_ignores = []
    stats = {'reformatees_forcee': 0, 'toujours_ignorees': 0, 'deja_propres': 0, 'vides': 0}
    total_lignes = len(df)
    
    print("\n--- Application des règles ciblées (Debug Console) ---\n")
    
    # 3. Lancement du traitement
    df[nom_colonne] = df.apply(
        lambda row: forcer_euro_estimation(row, nom_colonne, journal_modifs, journal_ignores, stats), 
        axis=1
    )

    # 4. Enregistrement final des modifications
    print(" Enregistrement des modifications dans le fichier CSV...")
    df.to_csv(CSV_PATH, sep=CSV_SEPARATOR, index=False, encoding='utf-8')

    # 5. Écriture du journal de ce script
    with open(LOG_MODIF_PATH, 'w', encoding='utf-8') as f_mod:
        f_mod.write("=====================================================================\n")
        f_mod.write("       JOURNAL DES MODIFICATIONS COMPLÉMENTAIRES (FORÇAGE EURO)       \n")
        f_mod.write("=====================================================================\n\n")
        for log in journal_modifs:
            f_mod.write(log + "\n")

    # 6. Écriture du journal final de TOUS les cas restants non-propres du fichier
    with open(LOG_IGNORE_PATH, 'w', encoding='utf-8') as f_ign:
        f_ign.write("=====================================================================\n")
        f_ign.write("         JOURNAL DE SYNTHÈSE DES DERNIERS ÉLÉMENTS NON NETTOYÉS       \n")
        f_ign.write("=====================================================================\n")
        f_ign.write("Voici la liste complète des lignes qui restent 'brutes' dans votre fichier final.\n\n")
        for log in journal_ignores:
            if "Hors cible" not in log:
                f_ign.write(log + "\n")

    # 7. Bilan statistique final

    print(f" Total des lignes analysées        : {total_lignes}")
    print(f" Lignes déjà propres (Scripts 1&2) : {stats['deja_propres']}")
    print(f" Lignes vides ou manquantes        : {stats['vides']}")
    print(f" Lignes reformatées en € (Ciblées) : {stats['reformatees_forcee']}")
    print(f" Journal des corrections € : '{LOG_MODIF_PATH}'")
    print(f" Rapport final des cas restants : '{LOG_IGNORE_PATH}'")
    print("--- Fin du programme finalisé avec succès ! ---")

if __name__ == "__main__":
    main()