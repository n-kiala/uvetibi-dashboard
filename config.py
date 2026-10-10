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
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

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

# Journees verifiees mais pas encore publiees (version locale uniquement) : un
# dossier par jour (JJ-MM-AAAA) avec le tableur de suivi et un sous-dossier
# d'images par plaque. Elles ne sont lues que si ce dossier existe sur la
# machine ; il est exclu du depot (.gitignore), donc la version en ligne ne les
# voit jamais. Rien n'est ecrit dans BigQuery ni dans Cloud Storage : pour
# publier une journee, passer son dossier a ingerer_suivi.py.
LOTS_LOCAUX_DIR = os.environ.get("TIBI_LOTS_LOCAUX") or os.path.join(BASE_DIR, "lots_locaux")
PREFIXE_LOCAL = "local:"

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
    "Incertain": ("#B48CE6", "#3B1260"),   # violet des boites CVAT (#cc00ff) ; distinct des autres teintes, daltonisme compris
    "Carton": ("#E8D3A9", "#5F4514"),
}
COULEUR_TYPE_DEFAUT = ("#E5E7EB", "#374151")

# Types ecartes de la vue client : ils restent en base et visibles dans la page
# Administration, mais ne sont ni comptes ni affiches cote client. Le filtre
# s'applique au chargement, pour que compteurs, graphique et legendes portent
# tous sur le meme jeu de constats.
# Incertain est affiche (decision du 10/10) : voir sa definition dans DEFINITIONS_TYPES.
TYPES_MASQUES = {"Textile"}

# Variantes de saisie (casse, orthographe) ramenees vers un type canonique
# ci-dessus, pour que chaque erreur ne soit comptee et coloree qu'une fois.
TYPES_CANONIQUES = {
    "sac_non_bio": "Sac_non_bio",
    "sac _non_bio": "Sac_non_bio",
    "sac-non_bio": "Sac_non_bio",
    "sac_non_conforme": "Sac_non_bio",
    "pmc": "PMC",
    "plastique_dur": "Plastique_dur",
    "plastique dur": "Plastique_dur",
    "carton": "Carton",
    "textile": "Textile",
    "textiles": "Textile",
    "autre": "Autre",
    "autres": "Autre",
    "incertain": "Incertain",
}


# Legende des boites tracees SUR les images par l'outil d'annotation (CVAT) :
# le libelle tel qu'il apparait dans CVAT, le type canonique dont il tire sa
# couleur dans COULEURS_TYPE, et une glose quand le nom seul preterait a
# confusion. L'ordre est celui de la barre de labels CVAT.
LEGENDE_ANNOTATIONS = [
    ("sac_non_bio", "Sac_non_bio", "sacs plastique non commercialisés par Tibi"),
    ("pmc", "PMC", "plastiques, métaux et cartons à boissons"),
    ("plastique_dur", "Plastique_dur", "objet en plastique rigide"),
    ("textiles", "Textile", ""),
    ("autre", "Autre", "indésirable hors des trois catégories (verre, carton...)"),
    ("incertain", "Incertain", "catégorie non tranchée, très probablement pas un déchet organique"),
]

# Definition des categories, affichee aux clients sous le graphique. Autre et Incertain : formulations du 10/10.
DEFINITIONS_TYPES = [
    ("Sac_non_bio", "Sac non bio", "sac en plastique qui n'est pas un sac commercialisé par Tibi."),
    ("PMC", "PMC", "emballages en plastique, emballages métalliques et cartons à boissons (bouteilles, canettes, "
                   "sachets de chips...)."),
    ("Plastique_dur", "Plastique dur", "objet en plastique rigide qui n'est pas un emballage (seau, caisse...)."),
    ("Autre", "Autre", "indésirable dont la nature ne rentre dans aucune des trois catégories précédentes "
                       "(PMC, sac non bio, plastique dur) : une bouteille en verre, un carton, etc."),
    ("Incertain", "Incertain", "le modèle n'identifie pas de catégorie précise, contrairement à « Autre », mais "
                               "suspecte fortement que le déchet n'est pas un déchet organique."),
]


_PLAQUE_RE = re.compile(r"[A-Z]{3}-?\d{3}|\d{3}-?[A-Z]{3}")


def plaque_identifiee(plaque) -> bool:
    """Vrai si la plaque contient une immatriculation lisible (format 1-ABC-234, 123-ABC ou ABC-123).
    Les constats sans plaque (« X », vide, « ? ») sont ecartes de la vue client : un camion non identifie ne peut
    pas etre presente au client."""
    return bool(_PLAQUE_RE.search(str(plaque or "").upper()))


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


# --------------------------------------------------------------------------
# Journees locales (non publiees)
# --------------------------------------------------------------------------


def _tableur_local(dossier: str) -> str | None:
    for nom in sorted(os.listdir(dossier)):
        if "suivi" in nom.lower() and nom.lower().endswith(".xlsx") and not nom.startswith("~$"):   # suivi_dechet_..., 2026_09_17_suivi_dechet
            return os.path.join(dossier, nom)
    return None


def jours_locaux() -> dict[str, str]:
    """{jour ISO : dossier} des journees locales presentes sur cette machine."""
    if not os.path.isdir(LOTS_LOCAUX_DIR):
        return {}
    resultat = {}
    for nom in sorted(os.listdir(LOTS_LOCAUX_DIR)):
        chemin = os.path.join(LOTS_LOCAUX_DIR, nom)
        try:
            jour = datetime.strptime(nom, "%d-%m-%Y").date()
        except ValueError:
            continue
        if os.path.isdir(chemin) and _tableur_local(chemin):
            resultat[jour.isoformat()] = chemin
    return resultat


@st.cache_data(ttl=300, show_spinner="Lecture des journées locales...")
def charger_constats_locaux() -> pd.DataFrame:
    """Constats des journees locales, sous la forme exacte que leur donnera
    ingerer_suivi.py une fois publies : une ligne par (plaque, type), counts
    sommes, horodatage du premier constat, score_confiance = 100."""
    jours = jours_locaux()
    lignes = []
    if jours:  # en ligne il n'y en a jamais : openpyxl n'y est pas installe
        import openpyxl

        import ingerer_suivi as ing  # importe ici : ingerer_suivi importe lui-meme ce module
    for jour, dossier in jours.items():
        tableur = _tableur_local(dossier)
        feuille = openpyxl.load_workbook(tableur, read_only=True).sheetnames[0]
        try:
            lus = ing.lire_constats(Path(tableur), feuille)
            ignorees = lignes_ignorees().get(jour, set())        # saisies en double (fenetre de decision)
            lus = [ligne for ligne in lus if ligne["ligne"] not in ignorees]
            ing.recaler_sur_dossier(lus, Path(dossier))   # date du dossier, plaque du dossier de l'image
            constats = ing.agreger(lus)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - SystemExit : erreurs de lecture d'ingerer_suivi
            raise RuntimeError(f"Journée locale {jour} illisible ({tableur}) : {exc}") from None
        lignes += [dict(c, source="local") for c in constats]
    df = pd.DataFrame(lignes, columns=["horodatage", "type", "count", "score_confiance", "plaque", "source"])
    if df.empty:
        return df
    df["horodatage"] = pd.to_datetime(df["horodatage"], errors="coerce", utc=True)
    df = df.dropna(subset=["horodatage"])
    df["date"] = df["horodatage"].dt.date
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(1).astype(int)
    df["type"] = df["type"].map(normaliser_type)
    return df


def ajouter_constats_locaux(df: pd.DataFrame) -> tuple[pd.DataFrame, list[date]]:
    """Ajoute aux constats BigQuery les journees locales qui n'y sont pas encore.

    Une journee deja publiee n'est jamais comptee deux fois : sa version
    BigQuery l'emporte. Renvoie aussi la liste des journees ajoutees.
    """
    locaux = charger_constats_locaux()
    if locaux.empty:
        return df, []
    if not df.empty:
        locaux = locaux[~locaux["date"].isin(set(df["date"]))]
    if locaux.empty:
        return df, []
    fusion = pd.concat([df, locaux], ignore_index=True) if not df.empty else locaux
    return fusion.sort_values("horodatage", ascending=False), sorted(locaux["date"].unique())


def periode(df: pd.DataFrame) -> tuple[date | None, date | None]:
    """Premiere et derniere date de collecte presentes dans les donnees."""
    if df.empty:
        return None, None
    return df["date"].min(), df["date"].max()


MOIS = {
    1: "janv.", 2: "févr.", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juil.", 8: "août", 9: "sept.", 10: "oct.", 11: "nov.", 12: "déc.",
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


# --------------------------------------------------------------------------
# Corrections de plaque (decisions prises dans cvat-export\decisions_plaques.py)
# --------------------------------------------------------------------------

# Plaque mal saisie (un chiffre ou une lettre de travers) : la decision est enregistree ici et appliquee a l'affichage,
# sans toucher aux tableurs ni a BigQuery. Les images restent dans le dossier de la plaque saisie.
CORRECTIONS_PLAQUES = os.path.join(BASE_DIR, "corrections_plaques.json")


def _decisions() -> dict:
    """Decisions prises dans la fenetre de decision (fichier absent : aucune)."""
    try:
        with open(CORRECTIONS_PLAQUES, encoding="utf-8") as fichier:
            return json.load(fichier)
    except FileNotFoundError:
        return {}


def corrections_plaques() -> dict[tuple[str, str], dict]:
    """{(jour ISO, plaque saisie) : decision} des corrections validees (decision « corriger »)."""
    return {
        (e["jour"], e["plaque"]): e
        for e in _decisions().get("corrections", [])
        if e.get("decision") == "corriger" and e.get("plaque_corrigee")
    }


def lignes_ignorees() -> dict[str, set[int]]:
    """{jour ISO : numeros de ligne du tableur a ignorer} : saisies en double tranchees dans la fenetre de decision
    (le tableur n'est pas modifie)."""
    resultat: dict[str, set[int]] = {}
    for e in _decisions().get("decisions_donnees", []):
        if e.get("lignes_ignorees"):
            resultat.setdefault(e["jour"], set()).update(int(n) for n in e["lignes_ignorees"])
    return resultat


def images_masquees() -> dict[tuple[str, str], set[str]]:
    """{(jour ISO, dossier) : fichiers retires de la galerie} : image rangee aussi chez un autre camion, ou version
    en double d'une meme image. Les fichiers ne sont pas supprimes."""
    resultat: dict[tuple[str, str], set[str]] = {}
    for e in _decisions().get("decisions_donnees", []):
        for dossier, noms in (e.get("images_masquees") or {}).items():
            resultat.setdefault((e["jour"], dossier), set()).update(noms)
    return resultat


def appliquer_corrections(df: pd.DataFrame) -> pd.DataFrame:
    """Plaque corrigee (et heure, quand le constat publie portait une heure fictive) pour chaque constat concerne."""
    corrections = corrections_plaques()
    if df.empty or not corrections:
        return df
    df = df.copy()
    cles = [(jour.isoformat(), str(plaque)) for jour, plaque in zip(df["date"], df["plaque"])]
    df["plaque"] = [corrections[c]["plaque_corrigee"] if c in corrections else p for c, p in zip(cles, df["plaque"])]
    heures = [corrections[c].get("heure") if c in corrections else None for c in cles]
    if any(heures):
        df["horodatage"] = [
            pd.Timestamp(f"{c[0]} {h}", tz="UTC") if h else t for c, h, t in zip(cles, heures, df["horodatage"])
        ]
    return df


def dossiers_images(jour_iso: str, plaque: str) -> list[str]:
    """Dossiers de galerie d'un camion affiche : le sien, plus ceux des plaques saisies corrigees vers lui."""
    return [plaque] + [
        saisie for (jour, saisie), e in corrections_plaques().items()
        if jour == jour_iso and e["plaque_corrigee"] == plaque and saisie != plaque
    ]


# --------------------------------------------------------------------------
# Inventaire de la galerie
# --------------------------------------------------------------------------


@st.cache_data(ttl=300, show_spinner=False)
def _inventaire_galerie() -> dict[tuple[str, str], bool]:
    """{(jour ISO, dossier de plaque) : le dossier contient-il la photo de la plaque ?} pour chaque dossier ayant au
    moins une image, publie (Cloud Storage) ou local.

    Un seul listage du bucket suffit, la ou un appel par vehicule en couterait
    autant que de plaques : c'est ce qui permet de filtrer la totalite des
    constats des le chargement, et donc de garder tous les compteurs coherents.
    """
    prefixe = f"{GALERIE_PREFIX}/"
    inventaire: dict[tuple[str, str], bool] = {}
    for blob in client_storage().bucket(BUCKET).list_blobs(prefix=prefixe):
        segments = blob.name[len(prefixe):].split("/")
        if len(segments) >= 3 and segments[2].lower().endswith(EXTENSIONS_IMAGE):
            cle = (segments[0], segments[1])
            inventaire[cle] = inventaire.get(cle, False) or est_photo_plaque(segments[2])
    for jour, dossier in jours_locaux().items():
        for plaque in os.listdir(dossier):
            images = _images_locales(os.path.join(dossier, plaque))
            if images:
                inventaire[(jour, plaque)] = any(est_photo_plaque(nom) for nom in images)
    return inventaire


def _couples_affiches(avec_photo_plaque: bool) -> set[tuple[str, str]]:
    corrections = corrections_plaques()
    couples = set()
    for (jour, dossier), photo in _inventaire_galerie().items():
        if photo or not avec_photo_plaque:
            couples.add((jour, dossier))
            if (jour, dossier) in corrections:
                couples.add((jour, corrections[(jour, dossier)]["plaque_corrigee"]))
    return couples


def couples_avec_images() -> set[tuple[str, str]]:
    """Couples (jour ISO, plaque affichee) ayant au moins une image en stockage."""
    return _couples_affiches(avec_photo_plaque=False)


def couples_avec_photo_plaque() -> set[tuple[str, str]]:
    """Couples (jour ISO, plaque affichee) dont la galerie contient la photo de la plaque. Sans elle, le client ne
    peut pas identifier le camion (plaque illisible dans toutes ses videos) : il sort de la vue, comme un « X »."""
    return _couples_affiches(avec_photo_plaque=True)


def _images_locales(dossier: str) -> list[str]:
    """Images d'un dossier de plaque local (les dossiers _corbeille, _sauvegardes... sont ignores)."""
    if os.path.basename(dossier).startswith("_") or not os.path.isdir(dossier):
        return []
    return sorted(
        PREFIXE_LOCAL + os.path.join(dossier, nom)
        for nom in os.listdir(dossier)
        if nom.lower().endswith(EXTENSIONS_IMAGE)
    )


@st.cache_data(ttl=300, show_spinner=False)
def _lister_dossier(jour: date, dossier: str) -> list[str]:
    """Noms des blobs image d'un dossier de galerie ; a defaut, images de la journee locale (chemins prefixes par
    PREFIXE_LOCAL)."""
    prefixe = f"{GALERIE_PREFIX}/{jour.isoformat()}/{dossier}/"
    bucket = client_storage().bucket(BUCKET)
    noms = [
        blob.name
        for blob in bucket.list_blobs(prefix=prefixe)
        if blob.name.lower().endswith(EXTENSIONS_IMAGE)
    ]
    if not noms and jour.isoformat() in jours_locaux():
        noms = _images_locales(os.path.join(jours_locaux()[jour.isoformat()], dossier))
    return noms


def lister_images(jour: date, plaque: str) -> list[str]:
    """Images d'un camion pour un jour, photo de plaque en tete (dossiers des plaques corrigees vers lui compris)."""
    masquees = images_masquees()
    noms = [
        nom
        for dossier in dossiers_images(jour.isoformat(), plaque)
        for nom in _lister_dossier(jour, dossier)
        if os.path.basename(nom) not in masquees.get((jour.isoformat(), dossier), set())
    ]
    return sorted(dict.fromkeys(noms), key=cle_galerie)


def est_photo_plaque(nom: str) -> bool:
    """Photo de la plaque d'immatriculation du camion : fichier prefixe « plaque_ », ou nom contenant « Plaque_immat »
    (galerie publiee, parfois precede du chemin du dataset : « datasets_..._Plaque_immat_f000036_... »)."""
    base = os.path.basename(nom).lower()
    return base.startswith("plaque_") or "plaque_immat" in base


def cle_galerie(nom: str):
    """Ordre de la galerie : la photo de plaque d'abord, puis les images dans l'ordre du nom (donc de la video)."""
    return (0 if est_photo_plaque(nom) else 1, os.path.basename(nom).lower())


@st.cache_data(ttl=1800, show_spinner=False)
def telecharger_image(nom_blob: str) -> bytes:
    """Image pleine resolution, en octets (Cloud Storage, ou disque pour une journee locale)."""
    if nom_blob.startswith(PREFIXE_LOCAL):
        with open(nom_blob[len(PREFIXE_LOCAL):], "rb") as fichier:
            return fichier.read()
    return client_storage().bucket(BUCKET).blob(nom_blob).download_as_bytes()


def supprimer_image(nom_blob: str) -> None:
    """Supprime definitivement un fichier image du bucket Cloud Storage."""
    if nom_blob.startswith(PREFIXE_LOCAL):
        raise PermissionError(
            "Image d'une journée locale : la retirer avec verif_suivi_tri.py, qui met aussi le tableur à jour."
        )
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
    charger_constats_locaux.clear()
    _lister_dossier.clear()
    _inventaire_galerie.clear()
