"""Administration des constats - acces reserve.

Cette page porte les operations d'ecriture retirees de la vue client :
consultation de la table complete et suppression de lignes dans BigQuery.
L'acces est protege par un mot de passe stocke dans .streamlit/secrets.toml.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from google.cloud import bigquery

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402

st.set_page_config(layout="wide", page_title="Administration - UVE Tibi")

st.title("Administration des constats")
st.caption(f"{cfg.SITE} · table {cfg.TABLE_REF}")

# --------------------------------------------------------------------------
# Authentification
# --------------------------------------------------------------------------

MOT_DE_PASSE = st.secrets.get("admin_password")

if not MOT_DE_PASSE:
    st.error(
        "Aucun mot de passe administrateur n'est configure. "
        "Ajoutez `admin_password` dans .streamlit/secrets.toml pour ouvrir cette page."
    )
    st.stop()

st.session_state.setdefault("admin_ouvert", False)

if not st.session_state.admin_ouvert:
    saisie = st.text_input("Mot de passe", type="password")
    if st.button("Ouvrir la session", type="primary"):
        if saisie == MOT_DE_PASSE:
            st.session_state.admin_ouvert = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()

col_titre, col_sortie = st.columns([6, 1])
with col_sortie:
    if st.button("Fermer la session", use_container_width=True):
        st.session_state.admin_ouvert = False
        st.rerun()

# --------------------------------------------------------------------------
# Donnees
# --------------------------------------------------------------------------

try:
    df = cfg.charger_constats()
except Exception as exc:  # noqa: BLE001
    st.error("La lecture de BigQuery a echoue.")
    st.exception(exc)
    st.stop()

if df.empty:
    st.info("La table ne contient aucun constat.")
    st.stop()

debut, fin = cfg.periode(df)
st.markdown(
    f"**{len(df)} constats** du {cfg.libelle_long(debut)} au {cfg.libelle_long(fin)} · "
    f"{df['plaque'].nunique()} vehicules · {df['type'].nunique()} types d'erreur"
)

couples = cfg.couples_avec_images()
sans_image = len(df) - sum(
    (jour.isoformat(), str(plaque)) in couples
    for jour, plaque in zip(df["date"], df["plaque"])
)
if sans_image:
    st.caption(
        f"Table brute : {sans_image} de ces constats n'ont plus aucune image en "
        "stockage et sont donc masques dans la vue client, dont les compteurs "
        "sont plus bas que ceux-ci."
    )

col_jour, col_plaque, col_type = st.columns(3)
jours = ["Tous les jours"] + [str(j) for j in sorted(df["date"].unique(), reverse=True)]
filtre_jour = col_jour.selectbox("Jour", jours)
plaques = ["Toutes les plaques"] + sorted(df["plaque"].dropna().unique().tolist())
filtre_plaque = col_plaque.selectbox("Plaque", plaques)
types = ["Tous les types"] + sorted(df["type"].dropna().unique().tolist())
filtre_type = col_type.selectbox("Type", types)

vue = df.copy()
if filtre_jour != "Tous les jours":
    vue = vue[vue["date"].astype(str) == filtre_jour]
if filtre_plaque != "Toutes les plaques":
    vue = vue[vue["plaque"] == filtre_plaque]
if filtre_type != "Tous les types":
    vue = vue[vue["type"] == filtre_type]

st.dataframe(
    vue[["horodatage", "plaque", "type", "count", "score_confiance"]],
    use_container_width=True,
    hide_index=True,
)

# --------------------------------------------------------------------------
# Suppression
# --------------------------------------------------------------------------

st.divider()
st.subheader("Supprimer un constat")
st.caption(
    "La suppression est definitive et s'applique directement a BigQuery. "
    "Une ligne inseree il y a moins de 30 minutes peut encore se trouver dans le "
    "tampon de streaming : BigQuery refusera alors de la supprimer."
)

if vue.empty:
    st.info("Aucune ligne ne correspond aux filtres.")
    st.stop()

options = {
    f"{ligne.horodatage} · {ligne.plaque} · {ligne.type} · count {ligne.count}": ligne
    for ligne in vue.itertuples()
}
choix = st.selectbox("Ligne a supprimer", list(options.keys()))
ligne = options[choix]

confirme = st.checkbox("Je confirme la suppression definitive de cette ligne")

if st.button("Supprimer la ligne", type="primary", disabled=not confirme):
    requete = f"""
        DELETE FROM `{cfg.TABLE_REF}`
        WHERE horodatage = @horodatage
          AND plaque = @plaque
          AND type = @type
    """
    parametres = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("horodatage", "TIMESTAMP", ligne.horodatage.to_pydatetime()),
            bigquery.ScalarQueryParameter("plaque", "STRING", str(ligne.plaque)),
            bigquery.ScalarQueryParameter("type", "STRING", str(ligne.type)),
        ]
    )
    try:
        travail = cfg.client_bigquery().query(requete, job_config=parametres)
        travail.result()
        cfg.vider_caches()
        st.success(f"{travail.num_dml_affected_rows} ligne(s) supprimee(s).")
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error("La suppression a echoue.")
        st.exception(exc)
