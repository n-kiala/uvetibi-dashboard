"""Genere les miniatures des images de la galerie deja publiees (M4).
Pour chaque image sous GALERIE_PREFIX qui n'a pas encore de miniature, telecharge l'original, le reduit avec 
cfg.reduire_image() (comme l'affichage) et range le resultat sous cfg.nom_miniature(). Les originaux ne sont
jamais modifiés. Relancable: les miniatures existantes sont sautees.

Usage:
    python generer_miniatures.py               # a blanc: compte ce qui serait fait, n'écrit rien
    python generer_miniatures.py --execute     # ecrit les miniatures dans le bucket
"""

from __future__ import annotations

import argparse
import time

import config as cfg

def main() -> None:
    parseur = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parseur.add_argument("--execute", action="store_true")
    args = parseur.parse_args()

    bucket = cfg.client_storage().bucket(cfg.BUCKET)
    originaux = [
        b.name for b in bucket.list_blobs(prefix=f"{cfg.GALERIE_PREFIX}/")
        if b.name.lower().endswith(cfg.EXTENSIONS_IMAGE)
    ]
    existantes = {b.name for b in bucket.list_blobs(prefix=f"{cfg.PREFIXE_MINIATURES}/")}
    a_faire = [nom for nom in originaux if cfg.nom_miniature(nom) not in existantes]

    print(f"Images de la galerie   : {len(originaux)}")
    print(f"Miniatures existantes  : {len(existantes)}")
    print(f"Miniatures a generer   : {len(a_faire)}")

    if not args.execute:
        print("\nA blanc : rien n'a ete ecrit. Relancer avec --execute pour generer les miniatures.")
        return

    debut = time.perf_counter()
    octets_originaux = octets_miniatures = 0
    for i, nom in enumerate(a_faire, start=1):
        brut = bucket.blob(nom).download_as_bytes()
        miniature = cfg.reduire_image(brut)
        bucket.blob(cfg.nom_miniature(nom)).upload_from_string(miniature, content_type="image/jpeg")
        octets_originaux += len(brut)
        octets_miniatures += len(miniature)
        if i % 50 == 0 or i == len(a_faire):
            print(f"  {i}/{len(a_faire)}")

    duree = time.perf_counter() - debut
    print(f"\nTermine en {duree:.0f} s")
    print(f"Originaux lus     : {octets_originaux / 2**20:.1f} Mio")
    print(f"Miniatures ecrites: {octets_miniatures / 2**20:.1f} Mio")
    

if __name__ == "__main__":
    main()