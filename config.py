"""Configuration partagee et acces aux donnees pour le dashboard UVE Tibi.

Ce module centralise :
  - les constantes de projet (table BigQuery, bucket, chemins),
  - la charte graphique Neurogreen / Tibi,
  - la creation des clients GCP (mise en cache pour toute la session),
  - les fonctions de lecture BigQuery et Cloud Storage (mises en cache).

Il est importe a la fois par app_v3.py (vue client) et par pages/1_Administration.py.
"""

from __future__ import annotations

import io
import os
from datetime import date

import pandas as pd
import streamlit as st
from google.cloud import bigquery, storage
from google.oauth2 import service_account
from PIL import Image

# --------------------------------------------------------------------------
# Chemins
# --------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "tibi-credentials.json")
ASSETS_DIR = BASE_DIR
LOGO_NEUROGREEN = os.path.join(ASSETS_DIR, "logo_neurogreen.png")
LOGO_TIBI = os.path.join(ASSETS_DIR, "logo_tibi.png")

# --------------------------------------------------------------------------
# Ressources GCP
# --------------------------------------------------------------------------

PROJECT_ID = "fastai-cours"
DATASET = "alert_local"
TABLE = "erreur_alerts"
TABLE_REF = f"{PROJECT_ID}.{DATASET}.{TABLE}"

BUCKET = "uvetibi"
GALERIE_PREFIX = "tibilevel_test_isapi/Galerie_erreur"

SITE = "UVE de Tibi - Pont-de-Loup"

# --------------------------------------------------------------------------
# Charte graphique (hex extraits des logos fournis)
# --------------------------------------------------------------------------

VERT_NG = "#169B68"        # vert NeuroGreen, porte l'interface
VERT_NG_CLAIR = "#E4F4EC"
VERT_NG_FONCE = "#0C5C3E"
VERT_TIBI = "#009C46"      # vert Tibi, reserve a l'identite du site
LIME = "#D1D600"           # accent NeuroGreen, jamais en couleur de texte

# Palette unique du tableau de bord : un type d'erreur porte la meme couleur
# partout - barres du graphique, badges, carres de legende et boites tracees
# sur les photos. Les teintes sont celles des labels CVAT, pour qu'un lecteur
# retrouve dans le graphique la couleur qu'il voit sur l'image.
#   [0] teinte de base : barres, carres de legende, boites CVAT
#   [1] texte lisible sur cette teinte : libelle des badges
COULEURS_TYPE = {
    "Sac_non_bio": ("#F0E14A", "#5C4E00"),
    "PMC": ("#79D7F5", "#0B4A61"),
    "Plastique_dur": ("#C9E7C7", "#2C5429"),
    "Textile": ("#EBBAC5", "#77304A"),
    "Autre": ("#FB6E6E", "#6B1111"),
    "Carton": ("#E8D3A9", "#5F4514"),
}
COULEUR_TYPE_DEFAUT = ("#E5E7EB", "#374151")

# Variantes de saisie (casse, orthographe) ramenees vers un type canonique
# ci-dessus, pour que chaque erreur ne soit comptee et coloree qu'une fois.
TYPES_CANONIQUES = {
    "sac_non_bio": "Sac_non_bio",
    "sac_non_conforme": "Sac_non_bio",
    "pmc": "PMC",
    "plastique_dur": "Plastique_dur",
    "carton": "Carton",
    "textile": "Textile",
    "textiles": "Textile",
    "autre": "Autre",
    "autres": "Autre",
}


# Legende des boites tracees SUR les images par l'outil d'annotation (CVAT) :
# le libelle tel qu'il apparait dans CVAT, le type canonique dont il tire sa
# couleur dans COULEURS_TYPE, et une glose quand le nom seul preterait a
# confusion. L'ordre est celui de la barre de labels CVAT.
LEGENDE_ANNOTATIONS = [
    ("sac_non_bio", "Sac_non_bio", "sacs plastique non commercialises par Tibi"),
    ("pmc", "PMC", "plastiques, metaux et cartons a boissons"),
    ("plastique_dur", "Plastique_dur", ""),
    ("textiles", "Textile", ""),
    ("autre", "Autre", ""),
]


def normaliser_type(nom_type: str) -> str:
    """Ramene un libelle de type vers sa forme canonique (casse/orthographe)."""
    nom = str(nom_type).strip()
    return TYPES_CANONIQUES.get(nom.lower(), nom)


def couleur_type(nom_type: str) -> tuple[str, str]:
    """Renvoie (fond, texte) pour un type d'erreur."""
    return COULEURS_TYPE.get(str(nom_type), COULEUR_TYPE_DEFAUT)


# --------------------------------------------------------------------------
# Clients GCP
# --------------------------------------------------------------------------


def _credentials():
    """Identifiants du service account.

    En ligne ils viennent des secrets Streamlit (rubrique gcp_service_account),
    en local du fichier JSON pose a cote de l'application. Ce fichier n'est
    jamais versionne : hors de la machine de developpement, seuls les secrets
    de l'hebergeur font foi.
    """
    try:
        rubriques = sorted(st.secrets.keys())
        secrets_gcp = st.secrets.get("gcp_service_account")
    except Exception:  # noqa: BLE001 - aucun secrets.toml : cas normal en local
        rubriques, secrets_gcp = [], None

    if secrets_gcp:
        return service_account.Credentials.from_service_account_info(dict(secrets_gcp))

    if os.path.exists(CREDENTIALS_PATH):
        return service_account.Credentials.from_service_account_file(CREDENTIALS_PATH)

    # Le detail des rubriques presentes (leurs noms seuls, jamais les valeurs)
    # distingue d'un coup d'oeil "aucun secret configure" de "secret present
    # mais mal nomme", les deux erreurs de deploiement les plus frequentes.
    raise FileNotFoundError(
        "Aucun identifiant GCP. Section [gcp_service_account] attendue dans les "
        f"secrets ; rubriques trouvees : {rubriques or 'aucune'}. "
        f"Aucun fichier local non plus : {CREDENTIALS_PATH}."
    )


@st.cache_resource(show_spinner=False)
def client_bigquery() -> bigquery.Client:
    return bigquery.Client(credentials=_credentials(), project=PROJECT_ID)


@st.cache_resource(show_spinner=False)
def client_storage() -> storage.Client:
    return storage.Client(credentials=_credentials(), project=PROJECT_ID)


# --------------------------------------------------------------------------
# Lecture BigQuery
# --------------------------------------------------------------------------


@st.cache_data(ttl=300, show_spinner="Lecture des constats...")
def charger_constats() -> pd.DataFrame:
    """Renvoie tous les constats, tries du plus recent au plus ancien.

    Les erreurs ne sont pas avalees : elles remontent a l'appelant, qui decide
    comment les afficher. Une exception silencieuse ici produirait un tableau
    vide impossible a diagnostiquer.
    """
    requete = f"""
        SELECT horodatage, type, count, score_confiance, plaque
        FROM `{TABLE_REF}`
        ORDER BY horodatage DESC
    """
    df = client_bigquery().query(requete).to_dataframe()

    if df.empty:
        return df

    df["horodatage"] = pd.to_datetime(df["horodatage"], errors="coerce", utc=True)
    df = df.dropna(subset=["horodatage"])
    df["date"] = df["horodatage"].dt.date
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(1).astype(int)
    df["type"] = df["type"].map(normaliser_type)
    return df


def periode(df: pd.DataFrame) -> tuple[date | None, date | None]:
    """Premiere et derniere date de collecte presentes dans les donnees."""
    if df.empty:
        return None, None
    return df["date"].min(), df["date"].max()


MOIS = {
    1: "janv.", 2: "fevr.", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juil.", 8: "aout", 9: "sept.", 10: "oct.", 11: "nov.", 12: "dec.",
}
JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


def libelle_long(d: date) -> str:
    return f"{d.day} {MOIS[d.month]} {d.year}"


def libelle_court(d: date) -> str:
    return f"{JOURS[d.weekday()]} {d.day:02d}/{d.month:02d}"


# --------------------------------------------------------------------------
# Lecture Cloud Storage
# --------------------------------------------------------------------------

EXTENSIONS_IMAGE = (".png", ".jpg", ".jpeg", ".webp")


@st.cache_data(ttl=300, show_spinner=False)
def couples_avec_images() -> set[tuple[str, str]]:
    """Couples (jour ISO, plaque) ayant au moins une image en stockage.

    Un seul listage du bucket suffit, la ou un appel par vehicule en couterait
    autant que de plaques : c'est ce qui permet de filtrer la totalite des
    constats des le chargement, et donc de garder tous les compteurs coherents.
    """
    prefixe = f"{GALERIE_PREFIX}/"
    couples = set()
    for blob in client_storage().bucket(BUCKET).list_blobs(prefix=prefixe):
        segments = blob.name[len(prefixe):].split("/")
        if len(segments) >= 3 and segments[2].lower().endswith(EXTENSIONS_IMAGE):
            couples.add((segments[0], segments[1]))
    return couples


@st.cache_data(ttl=300, show_spinner=False)
def lister_images(jour: date, plaque: str) -> list[str]:
    """Noms des blobs image pour un couple (jour, plaque)."""
    prefixe = f"{GALERIE_PREFIX}/{jour.isoformat()}/{plaque}/"
    bucket = client_storage().bucket(BUCKET)
    noms = [
        blob.name
        for blob in bucket.list_blobs(prefix=prefixe)
        if blob.name.lower().endswith(EXTENSIONS_IMAGE)
    ]
    return sorted(noms)


@st.cache_data(ttl=1800, show_spinner=False)
def telecharger_image(nom_blob: str) -> bytes:
    """Image pleine resolution, en octets."""
    return client_storage().bucket(BUCKET).blob(nom_blob).download_as_bytes()


def supprimer_image(nom_blob: str) -> None:
    """Supprime definitivement un fichier image du bucket Cloud Storage."""
    client_storage().bucket(BUCKET).blob(nom_blob).delete()


@st.cache_data(ttl=1800, show_spinner=False)
def vignette(nom_blob: str, largeur: int = 480) -> bytes:
    """Version reduite d'une image, generee a la volee.

    Le bucket ne contient pas de miniatures : on telecharge donc l'original
    une fois, on le reduit, et le cache evite les appels reseau suivants.
    """
    brut = telecharger_image(nom_blob)
    image = Image.open(io.BytesIO(brut))
    image = image.convert("RGB")
    ratio = largeur / image.width
    if ratio < 1:
        image = image.resize((largeur, int(image.height * ratio)), Image.LANCZOS)
    tampon = io.BytesIO()
    image.save(tampon, format="JPEG", quality=82, optimize=True)
    return tampon.getvalue()


def vider_caches() -> None:
    """A appeler apres toute ecriture dans BigQuery ou Cloud Storage."""
    charger_constats.clear()
    lister_images.clear()
    couples_avec_images.clear()
