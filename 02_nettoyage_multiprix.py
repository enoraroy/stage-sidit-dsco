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

BACKUP_PATH = os.path.join(DIR_NAME, f"backup_2_{BASE_NAME}")
LOG_MODIF_PATH = os.path.join(DIR_NAME, "journal_nettoyage_multi.txt")
LOG_IGNORE_PATH = os.path.join(DIR_NAME, "journal_elements_ignores_finaux.txt")

CSV_SEPARATOR = '\t'

# FONCTION DE TRAITEMENT DES BLOCS MULTI-PRIX
def normaliser_multi_estimation(row, nom_colonne, journal_modifs, journal_ignores, stats):
    """
    Détecte, découpe et normalise les cellules contenant plusieurs prix/monnaies.
    Affiche des prints de débug dans la console pour validation humaine.
    """
    valeur = row[nom_colonne]
    
    # Extraction des métadonnées pour le suivi
    titre_vente = str(row.get('Titre_vente', 'Vente inconnue')).strip()
    num_lot = str(row.get('Numero_lot', 'Lot inconnu')).strip()
    titre_lot = str(row.get('Titre_lot', 'Titre inconnu')).strip()
    titre_lot_court = (titre_lot[:47] + '...') if len(titre_lot) > 50 else titre_lot
    id_lot = f"[Vente: {titre_vente} | Lot n°{num_lot} ({titre_lot_court})]"

    if pd.isna(valeur):
        return valeur
    
    texte_original = str(valeur).strip()
    if not texte_original:
        return valeur

    # RÈGLE DE SÉCURITÉ : Si la cellule a déjà été nettoyée au format simple par le script 1,
    # on n'y touche pas (Ex: "€3,500 - €4,500" ou "£12,000")
    pattern_deja_propre = r'^\s*(?:HK\$|US\$|[$£€])\d{1,3}(?:\,\d{3})*(?:\s*-\s*(?:HK\$|US\$|[$£€])\d{1,3}(?:\,\d{3})*)?\s*$'
    if re.match(pattern_deja_propre, texte_original):
        stats['deja_propres'] += 1
        return texte_original

    # 1. Nettoyage des séparateurs de milliers (bruit) pour coller les chiffres
    texte_nettoye = texte_original
    for _ in range(3):  
        texte_nettoye = re.sub(r'(\d)[,\.\s](\d{3})(?!\d)', r'\1\2', texte_nettoye)

    # 2. Extraction des blocs de prix via une Expressions Régulière Avancée
    # Elle capture la monnaie, un 1er nombre, et optionnellement un 2e nombre (intervalle)
    pattern_bloc = r'(?i)(hk\$|us\$|\$|£|gbp|€|eur(?:o)?s?)\s*(\d+)(?:\s*[\-\/–—;,\s\(\)]+\s*(?:hk\$|us\$|\$|£|gbp|€|eur(?:o)?s?)?\s*(\d+))?'
    matches = re.findall(pattern_bloc, texte_nettoye)

    # Si aucun bloc monnaie + chiffre n'est extrait, la cellule est considérée comme bruit total
    if not matches:
        journal_ignores.append(f"{id_lot} - TOUJOURS IGNORÉ : Aucun bloc de prix exploitable détecté dans '{texte_original}'")
        stats['toujours_ignorees'] += 1
        return texte_original

    # Fonction de correspondance pour standardiser les symboles monétaires
    def map_currency(c_str):
        c_str = c_str.lower()
        if 'hk$' in c_str: return 'HK$'
        if 'us$' in c_str: return 'US$'
        if '$' in c_str: return '$'
        if '£' in c_str or 'gbp' in c_str: return '£'
        if '€' in c_str or 'eur' in c_str or 'euro' in c_str: return '€'
        return c_str

    intervalles_normalises = []
    
    # 3. Reconstruction normée de chaque bloc trouvé
    for match in matches:
        monnaie_brute, num1, num2 = match
        symbole = map_currency(monnaie_brute)
        
        val1 = int(num1)
        if num2:  # C'est un intervalle (ex: 1,000 - 1,500)
            val2 = int(num2)
            intervalles_normalises.append(f"{symbole}{val1:,} - {symbole}{val2:,}")
        else:     # C'est un prix fixe (ex: €1,400)
            intervalles_normalises.append(f"{symbole}{val1:,}")

    # 4. Assemblage final séparé par un point-virgule
    if intervalles_normalises:
        texte_normalise = " ; ".join(intervalles_normalises)
        
        # --- PRINTS DE DEBUG EN CONSOLE ---
        print(f"DEBUG {id_lot}")
        print(f"   • Avant : {texte_original}")
        print(f"   • Après : {texte_normalise}\n")
        
        journal_modifs.append(f"{id_lot} - REFORMATÉE MULTI : '{texte_original}' -> '{texte_normalise}'")
        stats['reformatees_multi'] += 1
        return texte_normalise
    else:
        journal_ignores.append(f"{id_lot} - TOUJOURS IGNORÉ : Échec du reformatage des blocs extraits dans '{texte_original}'")
        stats['toujours_ignorees'] += 1
        return texte_original


def main():
    print("--- Début du processus de nettoyage des prix multiples ---")
    
    # 1. Vérification et création de la sauvegarde de niveau 2
    if not os.path.exists(CSV_PATH):
        print(f"Erreur : Le fichier CSV est introuvable à l'adresse relative : '{CSV_PATH}'")
        print("Vérifiez que le fichier est bien placé dans le dossier parent de 'Programmes'.")
        return

    try:
        shutil.copy2(CSV_PATH, BACKUP_PATH)
        print(f" Sauvegarde 'backup_2' créée avec succès : '{BACKUP_PATH}'")
    except Exception as e:
        print(f"Erreur critique lors de la création du backup_2 : {e}")
        return

    # 2. Lecture du fichier CSV
    print(" Lecture du fichier CSV...")
    try:
        df = pd.read_csv(CSV_PATH, sep=CSV_SEPARATOR, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, sep=CSV_SEPARATOR, encoding='latin-1')

    # Ciblage de la colonne
    nom_colonne = None
    for col in df.columns:
        if col.strip().lower() == 'estimation_lot':
            nom_colonne = col
            break

    if not nom_colonne:
        print(f"Erreur : La colonne 'Estimation_lot' n'existe pas dans ce fichier.")
        return

    # Initialisation des structures de données
    journal_modifs = []
    journal_ignores = []
    stats = {'reformatees_multi': 0, 'toujours_ignorees': 0, 'deja_propres': 0}
    total_lignes = len(df)
    
    print("\n--- Analyse et Découpage des cellules complexes (Debug Console) ---\n")
    
    # 3. Lancement du traitement ligne par ligne
    df[nom_colonne] = df.apply(
        lambda row: normaliser_multi_estimation(row, nom_colonne, journal_modifs, journal_ignores, stats), 
        axis=1
    )

    # 4. Sauvegarde des données écrasées dans le CSV principal
    print(" Enregistrement des modifications dans le fichier CSV...")
    df.to_csv(CSV_PATH, sep=CSV_SEPARATOR, index=False, encoding='utf-8')

    # 5. Écriture du journal des modifications multi-prix
    with open(LOG_MODIF_PATH, 'w', encoding='utf-8') as f_mod:
        f_mod.write("=====================================================================\n")
        f_mod.write("       JOURNAL DES MODIFICATIONS COMPLEXES (SCRIPT MULTI-PRIX)        \n")
        f_mod.write("=====================================================================\n\n")
        for log in journal_modifs:
            f_mod.write(log + "\n")

    # 6. Écriture du journal d'exclusion final (Bruit persistant)
    with open(LOG_IGNORE_PATH, 'w', encoding='utf-8') as f_ign:
        f_ign.write("=====================================================================\n")
        f_ign.write("       JOURNAL FINAL DES CELLULES INUTILISABLES / IGNORÉES            \n")
        f_ign.write("=====================================================================\n")
        f_ign.write("Ces lignes n'ont pu être nettoyées ni par le script 1, ni par le script 2.\n\n")
        for log in journal_ignores:
            f_ign.write(log + "\n")

    # 7. Bilan statistique final
    print(f" Total des lignes analysées        : {total_lignes}")
    print(f" Lignes déjà nettoyées (Script 1)  : {stats['deja_propres']}")
    print(f" Lignes reformatées (Multi-prix)   : {stats['reformatees_multi']}")
    print(f" Lignes définitivement ignorées   : {stats['toujours_ignorees']}")
    print(f" Fichier d'audit des modifs : '{LOG_MODIF_PATH}'")
    print(f" Fichier des cas insolubles : '{LOG_IGNORE_PATH}'")
    print("--- Fin du programme avec succès ! ---")

if __name__ == "__main__":
    main()