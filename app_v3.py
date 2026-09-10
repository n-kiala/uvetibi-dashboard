"""Dashboard des constats d'erreurs de tri - UVE de Tibi.

Vue destinee au client : consultation jour par jour, puis par vehicule,
avec les images annotees correspondantes. La suppression de constats vit
normalement dans pages/1_Administration.py ; le drapeau AUTORISER_SUPPRESSION
ci-dessous permet, si besoin, d'exposer aussi un bouton de suppression ici.
"""

from __future__ import annotations

import base64
import os
from io import BytesIO

import altair as alt
import streamlit as st
from google.cloud import bigquery
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image as RLImage
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import config as cfg

# Active/desactive le bouton "Supprimer ce constat" dans la vue client.
# A basculer ici uniquement, sans toucher au reste du code.
AUTORISER_SUPPRESSION = False

st.set_page_config(
    layout="wide",
    page_title="Suivi des indésirables — collecte FFOM - UVE Tibi",
    page_icon=cfg.LOGO_NEUROGREEN if os.path.exists(cfg.LOGO_NEUROGREEN) else None,
)

# --------------------------------------------------------------------------
# Styles
# --------------------------------------------------------------------------

st.markdown(
    f"""
    <style>
    .bandeau {{
        border-top: 3px solid {cfg.VERT_NG};
        border-bottom: 1px solid #e9ecef;
        padding: 14px 4px 16px 4px;
        margin-bottom: 8px;
    }}
    .bandeau-titre {{ font-size: 22px; font-weight: 600; color: #1f2937; }}
    .bandeau-site {{ font-size: 13px; color: #6b7280; margin-top: 2px; }}
    .bandeau-periode-label {{ font-size: 11px; color: #9ca3af; text-align: right; }}
    .bandeau-periode {{ font-size: 14px; font-weight: 600; color: {cfg.VERT_NG}; text-align: right; }}
    .carte {{
        background: #f8f9fa; border-radius: 10px; padding: 14px 16px; margin-bottom: 6px;
    }}
    .carte-active {{ background: {cfg.VERT_NG_CLAIR}; }}
    .carte-label {{ font-size: 13px; color: #6c757d; }}
    .carte-valeur {{ font-size: 26px; font-weight: 700; color: #111827; margin: 0; }}
    .carte-valeur-texte {{ font-size: 17px; font-weight: 600; color: #111827; margin: 6px 0 0 0; }}
    .badge {{
        display: inline-block; font-size: 12px; padding: 3px 10px;
        border-radius: 8px; font-weight: 500;
    }}
    .legende {{ font-size: 13px; color: #6b7280; margin-bottom: 10px; }}
    .bloc-legende {{
        background: #f8f9fa; border-radius: 10px; padding: 10px 14px 12px 14px;
        margin-bottom: 14px; line-height: 2;
    }}
    .bloc-legende-titre {{
        font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
        color: #9ca3af; margin-bottom: 4px;
    }}
    .annotation {{ font-size: 13px; color: #374151; margin-right: 18px; white-space: nowrap; }}
    .carre-annotation {{
        display: inline-block; width: 11px; height: 11px; border-radius: 3px;
        border: 1px solid rgba(0, 0, 0, .18); margin-right: 6px; vertical-align: middle;
    }}
    .annotation-glose {{ color: #6b7280; }}
    .pastille {{
        display: inline-block; width: 8px; height: 8px; border-radius: 2px;
        background: {cfg.LIME}; margin-right: 7px; vertical-align: middle;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


def _logo_base64(chemin: str) -> str:
    with open(chemin, "rb") as fichier:
        return base64.b64encode(fichier.read()).decode()


def bloc_legende(titre: str, entrees) -> str:
    """Legende en carres de couleur, partagee par le graphique et la galerie.

    `entrees` : suite de (libelle, couleur, glose), la glose restant facultative.
    """
    corps = "".join(
        f'<span class="annotation">'
        f'<span class="carre-annotation" style="background:{couleur};"></span>'
        f"{libelle}"
        + (f' <span class="annotation-glose">&mdash; {glose}</span>' if glose else "")
        + "</span>"
        for libelle, couleur, glose in entrees
    )
    return f'<div class="bloc-legende"><div class="bloc-legende-titre">{titre}</div>{corps}</div>'


# --------------------------------------------------------------------------
# Donnees
# --------------------------------------------------------------------------

try:
    df = cfg.charger_constats()
    erreur_chargement = None
except Exception as exc:  # noqa: BLE001
    df, erreur_chargement = None, exc

if erreur_chargement is not None:
    st.error("La connexion à BigQuery a échoué. Le détail technique :")
    st.exception(erreur_chargement)
    st.stop()

if df.empty:
    st.info(
        f"La table `{cfg.TABLE_REF}` ne contient aucun constat. "
        "Vérifiez que la remontée depuis le site alimente bien BigQuery."
    )
    st.stop()

df = df[~df["type"].isin(cfg.TYPES_MASQUES)]

# Un vehicule dont toutes les images ont ete supprimees n'a plus rien a montrer
# au client : ses constats sortent du jeu de donnees des le chargement. Filtrer
# ici plutot qu'a l'affichage garantit que tous les compteurs de la page (jour
# selectionne, graphique, total sur la periode) parlent des memes constats.
try:
    couples = cfg.couples_avec_images()
    df = df[
        [
            (jour.isoformat(), str(plaque)) in couples
            for jour, plaque in zip(df["date"], df["plaque"])
        ]
    ]
except Exception as exc:  # noqa: BLE001
    st.warning(
        "Impossible de vérifier les images disponibles ; les constats sans "
        "image restent affichés."
    )

if df.empty:
    st.info(
        "Aucun constat ne dispose encore d'image consultable. "
        "Les constats dont les images ont été supprimées ne sont plus affichés."
    )
    st.stop()

debut, fin = cfg.periode(df)

# --------------------------------------------------------------------------
# Bandeau
# --------------------------------------------------------------------------

st.markdown('<div class="bandeau">', unsafe_allow_html=True)
col_logo_ng, col_titre, col_periode, col_logo_tibi = st.columns([1, 8, 3, 1])
with col_logo_ng:
    if os.path.exists(cfg.LOGO_NEUROGREEN):
        st.image(cfg.LOGO_NEUROGREEN, width=54)
with col_titre:
    st.markdown(
        '<div class="bandeau-titre">Suivi des indésirables &mdash; collecte FFOM</div>'
        f'<div class="bandeau-site">{cfg.SITE} &middot; surveillance automatisée NeuroGreen</div>',
        unsafe_allow_html=True,
    )
with col_periode:
    st.markdown(
        '<div class="bandeau-periode-label">Période analysée</div>'
        f'<div class="bandeau-periode">{cfg.libelle_long(debut)} &rarr; {cfg.libelle_long(fin)}</div>',
        unsafe_allow_html=True,
    )
with col_logo_tibi:
    if os.path.exists(cfg.LOGO_TIBI):
        st.image(cfg.LOGO_TIBI, width=60)
st.markdown("</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Selection du jour
# --------------------------------------------------------------------------

jours = sorted(df["date"].unique())
volumes = df.groupby("date").size().to_dict()

if "jour" not in st.session_state or st.session_state.jour not in jours:
    st.session_state.jour = jours[-1]

st.markdown("##### Jour de collecte")

repartition_jour = (
    df.groupby(["date", "type"])
    .agg(constats=("type", "size"))
    .reset_index()
)
repartition_jour["jour"] = repartition_jour["date"].map(cfg.libelle_court)
repartition_jour["actif"] = repartition_jour["date"] == st.session_state.jour

libelles_ordonnes = [cfg.libelle_court(jour) for jour in jours]
types_presents = sorted(repartition_jour["type"].unique())

graphique = (
    alt.Chart(repartition_jour)
    # Contour discret : sans lui, les aplats pastel se fondent dans le fond blanc.
    .mark_bar(stroke="#9CA3AF", strokeWidth=0.6, cursor="pointer")
    .encode(
        x=alt.X(
            "jour:N",
            sort=libelles_ordonnes,
            title=None,
            axis=alt.Axis(labelAngle=0, labelPadding=8, domainColor="#d1d5db", ticks=False),
        ),
        y=alt.Y(
            "constats:Q",
            title="Constats",
            axis=alt.Axis(tickMinStep=1, grid=True, gridColor="#eef0f2", domain=False, ticks=False),
        ),
        color=alt.Color(
            "type:N",
            scale=alt.Scale(
                domain=types_presents,
                range=[cfg.couleur_type(t)[0] for t in types_presents],
            ),
            # Legende rendue en HTML sous le graphique, dans le meme habillage
            # que celle de la galerie.
            legend=None,
        ),
        # Le jour selectionne reste en pleine couleur, les autres s'estompent
        # a peine : les teintes CVAT etant pastel, les estomper davantage les
        # ramenerait au blanc. Le bouton actif porte deja le signal principal.
        opacity=alt.condition(alt.datum.actif, alt.value(1), alt.value(0.75)),
        # Volontairement sans le nombre d'objets : cote client, deux compteurs
        # voisins aux valeurs differentes pretaient a confusion.
        tooltip=[
            alt.Tooltip("jour:N", title="Jour"),
            alt.Tooltip("type:N", title="Type"),
            alt.Tooltip("constats:Q", title="Constats"),
        ],
    )
    .properties(height=240)
    .configure_view(strokeWidth=0)
    .configure_axis(labelColor="#4b5563", titleColor="#6b7280", labelFontSize=12, titleFontSize=11)
)

st.altair_chart(graphique, use_container_width=True)

st.markdown(
    bloc_legende(
        "Types d'erreur",
        [
            (str(type_nom).replace("_", " "), cfg.couleur_type(type_nom)[0], "")
            for type_nom in types_presents
        ],
    ),
    unsafe_allow_html=True,
)

colonnes = st.columns(min(len(jours), 8))
for index, jour in enumerate(jours):
    with colonnes[index % len(colonnes)]:
        if st.button(
            f"{cfg.libelle_court(jour)}  ·  {volumes[jour]}",
            key=f"jour_{jour}",
            use_container_width=True,
            type="primary" if jour == st.session_state.jour else "secondary",
        ):
            st.session_state.jour = jour
            st.session_state.pop("plaque", None)
            st.session_state.zoom = None
            st.rerun()

jour_actif = st.session_state.jour
df_jour = df[df["date"] == jour_actif]

# --------------------------------------------------------------------------
# Indicateurs
# --------------------------------------------------------------------------

# Le type dominant se juge au nombre d'objets constates (colonne count) et non
# au nombre de lignes : un seul constat "Sac_non_bio count=12" pese plus que
# trois lignes a count=1.
type_dominant = df_jour.groupby("type")["count"].sum().idxmax()
indicateurs = [
    ("Constats du jour", str(len(df_jour)), True),
    ("Véhicules concernés", str(df_jour["plaque"].nunique()), False),
    ("Type dominant", str(type_dominant).replace("_", " "), False),
    ("Total sur la période", str(len(df)), False),
]

st.write("")
for colonne, (label, valeur, accent) in zip(st.columns(4), indicateurs):
    classe_valeur = "carte-valeur" if valeur.isdigit() else "carte-valeur-texte"
    colonne.markdown(
        f'<div class="carte {"carte-active" if accent else ""}">'
        f'<div class="carte-label">{label}</div>'
        f'<p class="{classe_valeur}">{valeur}</p></div>',
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------
# Vehicules du jour
# --------------------------------------------------------------------------

st.write("")
st.markdown("##### Véhicules concernés ce jour")

type_dominant_par_plaque = (
    df_jour.groupby(["plaque", "type"])["count"]
    .sum()
    .reset_index()
    .sort_values("count", ascending=False)
    .drop_duplicates("plaque")
    .set_index("plaque")["type"]
)

resume_plaques = (
    df_jour.groupby("plaque")
    .agg(constats=("plaque", "size"))
    .join(type_dominant_par_plaque.rename("type_dominant"))
    .sort_values("constats", ascending=False)
    .reset_index()
)

if "plaque" not in st.session_state or st.session_state.plaque not in set(resume_plaques["plaque"]):
    st.session_state.plaque = resume_plaques.iloc[0]["plaque"]

for ligne in resume_plaques.itertuples():
    actif = ligne.plaque == st.session_state.plaque
    fond, texte = cfg.couleur_type(ligne.type_dominant)
    col_bouton, col_badge, col_nombre = st.columns([5, 3, 1])
    with col_bouton:
        if st.button(
            f"{'▸' if actif else '  '}  {ligne.plaque}",
            key=f"plaque_{ligne.plaque}",
            use_container_width=True,
            type="primary" if actif else "secondary",
        ):
            st.session_state.plaque = ligne.plaque
            st.session_state.zoom = None
            st.rerun()
    with col_badge:
        st.markdown(
            f'<div style="padding-top:8px;"><span class="badge" '
            f'style="background:{fond}; color:{texte};">'
            f'{str(ligne.type_dominant).replace("_", " ")}</span></div>',
            unsafe_allow_html=True,
        )
    with col_nombre:
        st.markdown(
            f'<div style="padding-top:8px; text-align:right; font-weight:600;">'
            f'{ligne.constats}</div>',
            unsafe_allow_html=True,
        )

plaque_active = st.session_state.plaque

# --------------------------------------------------------------------------
# Galerie
# --------------------------------------------------------------------------

st.divider()

try:
    images = cfg.lister_images(jour_actif, plaque_active)
    erreur_images = None
except Exception as exc:  # noqa: BLE001
    images, erreur_images = [], exc

st.markdown(
    f'<div class="legende"><span class="pastille"></span>'
    f"{cfg.libelle_court(jour_actif)} &middot; plaque {plaque_active}</div>",
    unsafe_allow_html=True,
)

if erreur_images is not None:
    st.warning("Les images n'ont pas pu être listées dans Cloud Storage.")
    st.exception(erreur_images)
elif not images:
    st.info("Aucune image archivée pour ce véhicule ce jour-là.")
else:
    st.markdown(
        bloc_legende(
            "Couleurs des annotations sur les images",
            [
                (libelle.replace("_", " "), cfg.couleur_type(canonique)[0], glose)
                for libelle, canonique, glose in cfg.LEGENDE_ANNOTATIONS
                if canonique not in cfg.TYPES_MASQUES
            ],
        ),
        unsafe_allow_html=True,
    )

    st.session_state.setdefault("zoom", None)

    if st.session_state.zoom is not None:
        index = st.session_state.zoom % len(images)
        st.image(cfg.telecharger_image(images[index]), use_container_width=True)
        col_info, col_prec, col_suiv, col_fermer = st.columns([6, 1, 1, 1])
        col_info.markdown(f"**Figure {index + 1} sur {len(images)}**")
        if col_prec.button("←", key="prec", use_container_width=True):
            st.session_state.zoom = (index - 1) % len(images)
            st.rerun()
        if col_suiv.button("→", key="suiv", use_container_width=True):
            st.session_state.zoom = (index + 1) % len(images)
            st.rerun()
        if col_fermer.button("Fermer", key="fermer", use_container_width=True):
            st.session_state.zoom = None
            st.rerun()

        if AUTORISER_SUPPRESSION:
            constats_vehicule = df_jour[df_jour["plaque"] == plaque_active][
                ["horodatage", "type", "count", "score_confiance"]
            ].sort_values("horodatage")
            st.divider()
            if constats_vehicule.empty:
                st.info("Aucun constat associé à ce véhicule pour ce jour.")
            else:
                st.caption(
                    "Supprime définitivement ce fichier image du stockage ainsi que le constat "
                    "choisi ci-dessous dans BigQuery. Un constat inséré il y a moins de 30 minutes "
                    "peut encore être dans le tampon de streaming et refuser d'être supprimé."
                )
                options_suppression = {
                    f"{ligne.horodatage} · {ligne.type} · count {ligne.count}": ligne
                    for ligne in constats_vehicule.itertuples()
                }
                choix_suppression = st.selectbox(
                    "Constat correspondant à cette image", list(options_suppression.keys()),
                    key="choix_suppression",
                )
                confirme_suppression = st.checkbox(
                    "Je confirme la suppression définitive de cette image et de ce constat",
                    key="confirme_suppression",
                )
                if st.button(
                    "Supprimer cette image et le constat",
                    type="primary",
                    disabled=not confirme_suppression,
                    key="bouton_suppression",
                ):
                    ligne = options_suppression[choix_suppression]
                    nom_image = images[index]
                    try:
                        cfg.supprimer_image(nom_image)
                    except Exception as exc:  # noqa: BLE001
                        st.error("La suppression du fichier image a échoué.")
                        st.exception(exc)
                        st.stop()

                    requete = f"""
                        DELETE FROM `{cfg.TABLE_REF}`
                        WHERE horodatage = @horodatage
                          AND plaque = @plaque
                          AND type = @type
                    """
                    parametres = bigquery.QueryJobConfig(
                        query_parameters=[
                            bigquery.ScalarQueryParameter(
                                "horodatage", "TIMESTAMP", ligne.horodatage.to_pydatetime()
                            ),
                            bigquery.ScalarQueryParameter("plaque", "STRING", str(plaque_active)),
                            bigquery.ScalarQueryParameter("type", "STRING", str(ligne.type)),
                        ]
                    )
                    try:
                        travail = cfg.client_bigquery().query(requete, job_config=parametres)
                        travail.result()
                    except Exception as exc:  # noqa: BLE001
                        st.warning(
                            "L'image a été supprimée, mais la suppression du constat BigQuery a échoué."
                        )
                        st.exception(exc)
                        st.stop()

                    cfg.vider_caches()
                    st.session_state.zoom = None
                    st.success("Image et constat supprimes.")
                    st.rerun()
    else:
        for depart in range(0, len(images), 3):
            for colonne, position in zip(st.columns(3), range(depart, min(depart + 3, len(images)))):
                with colonne:
                    st.image(cfg.vignette(images[position]), use_container_width=True)
                    st.markdown(f"**Figure {position + 1}**")
                    if st.button("Agrandir", key=f"zoom_{position}", use_container_width=True):
                        st.session_state.zoom = position
                        st.rerun()

# --------------------------------------------------------------------------
# Export PDF
# --------------------------------------------------------------------------


def construire_pdf(jour, plaque, noms_blobs) -> bytes:
    """Assemble le rapport des constats d'un vehicule pour une journee."""
    tampon = BytesIO()
    document = SimpleDocTemplate(
        tampon, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
    )
    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        "TitreRapport",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor(cfg.VERT_NG_FONCE),
    )
    style_legende = ParagraphStyle(
        "Legende",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#333333"),
    )

    # Legende des boites tracees sur les images : sans elle, le lecteur du
    # rapport n'a aucun moyen de savoir ce que chaque couleur designe. La liste
    # est figee ici : les deux boucles qui suivent doivent parcourir les memes
    # entrees dans le meme ordre, sinon couleurs et libelles se decalent.
    entrees_legende = [
        entree for entree in cfg.LEGENDE_ANNOTATIONS if entree[1] not in cfg.TYPES_MASQUES
    ]
    cellules = [
        ["", Paragraph(
            f"<b>{libelle.replace('_', ' ')}</b>" + (f" - {glose}" if glose else ""),
            style_legende,
        )]
        for libelle, _, glose in entrees_legende
    ]

    tableau_legende = Table(cellules, colWidths=[12, 468], rowHeights=[14] * len(cellules))
    styles_legende = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 0),
        ("LEFTPADDING", (1, 0), (1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]
    for rang, (_, canonique, _) in enumerate(entrees_legende):
        couleur = cfg.couleur_type(canonique)[0]
        styles_legende.append(("BACKGROUND", (0, rang), (0, rang), colors.HexColor(couleur)))
        styles_legende.append(("BOX", (0, rang), (0, rang), 0.5, colors.HexColor("#9CA3AF")))
    tableau_legende.setStyle(TableStyle(styles_legende))

    contenu = [
        Paragraph("Suivi des indésirables — collecte FFOM par Neurogreen", style_titre),
        Paragraph(
            f"<b>Site :</b> {cfg.SITE} | <b>Date :</b> {cfg.libelle_long(jour)} "
            f"| <b>Plaque :</b> {plaque}",
            styles["Normal"],
        ),
        Spacer(1, 12),
        Paragraph("<b>Couleurs des annotations sur les images</b>", style_legende),
        Spacer(1, 4),
        tableau_legende,
        Spacer(1, 15),
    ]

    for numero, nom_blob in enumerate(noms_blobs, start=1):
        image = RLImage(BytesIO(cfg.telecharger_image(nom_blob)), width=480, height=270)
        image.hAlign = "CENTER"
        contenu.extend([
            image,
            Spacer(1, 6),
            Paragraph(
                f"<b>Figure {numero} :</b> extraction galerie - "
                f"{os.path.basename(nom_blob)} (plaque : {plaque})",
                style_legende,
            ),
            Spacer(1, 15),
        ])
        if numero % 2 == 0 and numero < len(noms_blobs):
            contenu.append(PageBreak())

    document.build(contenu)
    return tampon.getvalue()


if images:
    st.write("")
    if st.button("Préparer le rapport PDF de ce véhicule", type="secondary"):
        with st.spinner("Assemblage du rapport..."):
            st.session_state.pdf = construire_pdf(jour_actif, plaque_active, images)

    if st.session_state.get("pdf"):
        st.download_button(
            "Télécharger le rapport PDF",
            data=st.session_state.pdf,
            file_name=f"Rapport_NeuroGreen_{plaque_active}_{jour_actif.isoformat()}.pdf",
            mime="application/pdf",
            type="primary",
        )
