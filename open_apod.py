#!/usr/bin/env python3
import json
import os
import webbrowser
from datetime import datetime

# Chemin vers le cache créé par le script d'overlay
CACHE_FILE = os.path.expanduser("~/dev/apod/pic/apod_data.json")

def open_apod():
    """
    Ouvre la page web de l'APOD du jour dans le navigateur.
    Utilise le cache local pour trouver la date exacte.
    """
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                date_str = data.get('date') # Format YYYY-MM-DD
                
                if date_str:
                    # Convertir YYYY-MM-DD en YYMMDD pour l'URL NASA
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    url = f"https://apod.nasa.gov/apod/ap{dt.strftime('%y%m%d')}.html"
                    print(f"🚀 Ouverture de la page APOD : {url}")
                    webbrowser.open(url)
                    return
        except Exception as e:
            print(f"Erreur lors de la lecture du cache : {e}")
    
    # Fallback si le cache est absent ou corrompu
    print("🚀 Cache non trouvé, ouverture de la page principale APOD...")
    webbrowser.open("https://apod.nasa.gov/apod/astropix.html")

if __name__ == "__main__":
    open_apod()
