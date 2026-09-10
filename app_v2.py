import os
from io import BytesIO
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from google.cloud import bigquery, storage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Configuration de la page Streamlit
st.set_page_config(layout="wide", page_title="Constats d'erreurs - UVE Tibi")

# --- MASQUER LA BARRE DE NAVIGATION MULTIPAGE AUTOMATIQUE ---
st.markdown("""
    <style>
    [data-testid="stSidebarNav"] {
        display: none;
    }
    div.metric-card {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 15px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        margin-bottom: 15px;
    }
    .main-header {
        font-size: 24px;
        font-weight: 700;
        color: #1f2937;
    }
    .sub-header {
        font-size: 13px;
        color: #6b7280;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# --- CHARGEMENT DES DONNÉES DEPUIS BIGQUERY ---
@st.cache_data(ttl=10)
def charger_donnees_bq():
    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "tibi-credentials.json"
        )
        client = bigquery.Client()
        query = "SELECT horodatage, type, count, score_confiance, plaque FROM `fastai-cours.alert_local.erreur_alerts` ORDER BY horodatage DESC"
        df = client.query(query).to_dataframe()
        return df, "En ligne (BigQuery)"
    except Exception as e:
        try:
            if os.path.exists("suivi_dechet_formate.xlsx"):
                df = pd.read_excel("suivi_dechet_formate.xlsx")
                df = df.rename(columns={'hortodatage': 'horodatage', 'score_de_confiance': 'score_confiance'})
                return df, "Fichier local (Excel)"
        except Exception:
            pass
        return pd.DataFrame(columns=["horodatage", "type", "count", "score_confiance", "plaque"]), f"Erreur : {e}"

df, source_info = charger_donnees_bq()

if not df.empty:
    df['horodatage'] = pd.to_datetime(df['horodatage'], errors='coerce')
    df['date'] = df['horodatage'].dt.date

    st.markdown('<div class="main-header">Stats et Bilan des erreurs de tri</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">Source : {source_info}</div>', unsafe_allow_html=True)

    # --- BARRE DE FILTRAGE ---
    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 2])
    with col_f1:
        options_temps = ["Semaine", "Aujourd'hui", "Choisir un jour précis", "Tout afficher"]
        choix_temps = st.selectbox("Période", options_temps, key="app_v2_periode")
    with col_f2:
        tournee_filtre = st.selectbox("Tournées", ["Toutes les tournées"], key="app_v2_tournee")
    with col_f3:
        types_disponibles = ["Tous les types"] + list(df['type'].dropna().unique())
        type_filtre = st.selectbox("Types d'erreurs", types_disponibles, key="app_v2_type")
    with col_f4:
        plaques_disponibles = ["Toutes les plaques"] + sorted(list(df['plaque'].dropna().unique()))
        plaque_filtre = st.selectbox("Plaque véhicule", plaques_disponibles, key="app_v2_plaque")

    # --- APPLICATION DES FILTRES ---
    df_filtered = df.copy()
    maintenant = datetime.now()
    aujourd_hui = maintenant.date()

    if choix_temps == "Aujourd'hui":
        df_filtered = df_filtered[df_filtered['date'] == aujourd_hui]
    elif choix_temps == "Semaine":
        limite_7d = aujourd_hui - timedelta(days=7)
        df_filtered = df_filtered[df_filtered['date'] >= limite_7d]
    elif choix_temps == "Choisir un jour précis":
        jour_choisi = st.date_input("Sélectionnez le jour précis", aujourd_hui, key="app_v2_date_precis")
        df_filtered = df_filtered[df_filtered['date'] == jour_choisi]

    if type_filtre != "Tous les types":
        df_filtered = df_filtered[df_filtered['type'] == type_filtre]

    if plaque_filtre != "Toutes les plaques":
        df_filtered = df_filtered[df_filtered['plaque'] == plaque_filtre]

    # --- CALCULS DES KPIS ---
    total_erreurs = len(df_filtered)
    try:
        total_count_sum = pd.to_numeric(df_filtered['count'], errors='coerce').sum()
    except Exception:
        total_count_sum = len(df_filtered)
        
    plaques_distinctes = df_filtered['plaque'].nunique() if not df_filtered.empty else 0
    nb_jours = df_filtered['date'].nunique() if not df_filtered.empty else 1
    
    if not df_filtered.empty:
        type_counts = df_filtered['type'].value_counts()
        type_dominant = type_counts.index[0]
        val_dominant = type_counts.iloc[0]
    else:
        type_dominant = "Aucun"
        val_dominant = 0

    st.markdown("---")

    # --- BLOCS MÉTRIQUES ---
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="metric-card"><span style="color: #6c757d; font-size: 13px;">Erreurs constatées</span><h2 style="margin: 0; color: #111827; font-weight: 700;">{total_erreurs}</h2></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card"><span style="color: #6c757d; font-size: 13px;">Cumul Count total</span><h2 style="margin: 0; color: #111827; font-weight: 700;">{int(total_count_sum)}</h2></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><span style="color: #6c757d; font-size: 13px;">Plaques distinctes</span><h2 style="margin: 0; color: #111827; font-weight: 700;">{plaques_distinctes}</h2></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card"><span style="color: #6c757d; font-size: 13px;">Type dominant</span><h2 style="margin: 0; color: #111827; font-weight: 700;">{val_dominant}</h2></div>', unsafe_allow_html=True)

    # --- GRAPHIQUE EMPILÉ ---
    st.markdown("#### Erreurs par jour et par type")
    if not df_filtered.empty:
        df_grouped = df_filtered.groupby([df_filtered['horodatage'].dt.strftime('%Y-%m-%d'), 'type']).size().reset_index(name='nombre')
        df_grouped.columns = ['jour', 'type', 'nombre']

        fig = px.bar(
            df_grouped, x="jour", y="nombre", color="type",
            color_discrete_map={
                "PMC": "#3b82f6", "sac_non_conforme": "#ea580c",
                "Sac_non_bio": "#ea580c", "Carton": "#f59e0b",
                "Inerte / métal": "#10b981", "Autre": "#6b7280"
            },
            template="simple_white"
        )
        fig.update_layout(
            barmode="stack",
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0),
            margin=dict(t=20, b=10, l=10, r=10),
            xaxis_title="", yaxis_title=""
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- TABLEAU ET SUPPRESSION ---
        st.markdown("---")
        st.markdown("#### Détail des constats d'erreurs & Suppression")
        colonnes_disponibles = [c for c in ['horodatage', 'count', 'type', 'score_confiance', 'plaque'] if c in df_filtered.columns]
        df_affichage = df_filtered[colonnes_disponibles].sort_values(by='horodatage', ascending=False)
        st.dataframe(df_affichage, use_container_width=True, hide_index=True)

        st.markdown("##### 🗑️ Supprimer une ligne spécifique")
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1:
            options_lignes = []
            ligne_mapping = {}
            for idx, row in df_affichage.iterrows():
                libelle = f"{row['horodatage']} | Plaque: {row['plaque']} | Type: {row['type']} | Count: {row['count']}"
                options_lignes.append(libelle)
                ligne_mapping[libelle] = row
            ligne_selectionnee = st.selectbox("Sélectionnez la ligne à supprimer", options_lignes, key="select_ligne_suppression_v2")
            
        with col_del2:
            st.write("") 
            st.write("")
            if st.button("🗑️ Supprimer la ligne", type="primary", key="btn_del_v2"):
                if ligne_selectionnee:
                    row_data = ligne_mapping[ligne_selectionnee]
                    try:
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)), "tibi-credentials.json"
                        )
                        client = bigquery.Client()
                        delete_query = f"""
                            DELETE FROM `fastai-cours.alert_local.erreur_alerts`
                            WHERE CAST(horodatage AS STRING) = '{str(row_data['horodatage'])}' 
                            AND plaque = '{str(row_data['plaque'])}' 
                            AND type = '{str(row_data['type'])}'
                        """
                        client.query(delete_query).result()
                        st.success("Ligne supprimée avec succès de BigQuery !")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur lors de la suppression : {e}")

        # --- SECTION RAPPORT PDF CLOUD STORAGE ---
        st.markdown("---")
        st.markdown("#### 📄 Génération du Rapport PDF Neurogreen")
        col_pdf1, col_pdf2 = st.columns([2, 2])
        with col_pdf1:
            pdf_date_input = st.date_input("Date du rapport PDF", maintenant.date(), key="pdf_date_fixe_v2")
        with col_pdf2:
            plaques_dispo_pdf = sorted(list(df_filtered['plaque'].dropna().unique()))
            pdf_plaque_input = st.selectbox("Plaque pour le PDF", plaques_dispo_pdf if plaques_dispo_pdf else ["Aucune plaque"], key="pdf_plaque_select_v2")

        if st.button("📥 Générer et télécharger le PDF", type="secondary", key="btn_pdf_v2"):
            if pdf_plaque_input and pdf_plaque_input != "Aucune plaque":
                date_str = pdf_date_input.strftime("%Y-%m-%d")
                try:
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), "tibi-credentials.json"
                    )
                    storage_client = storage.Client()
                    bucket = storage_client.bucket("uvetibi")
                    prefix = f"tibilevel_test_isapi/Galerie_erreur/{date_str}/{pdf_plaque_input}/"
                    
                    blobs = list(bucket.list_blobs(prefix=prefix))
                    image_blobs = [b for b in blobs if b.name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
                    image_blobs = sorted(image_blobs, key=lambda x: x.name)
                    
                    if not image_blobs:
                        st.warning(f"Aucune image trouvée dans le Cloud pour la plaque '{pdf_plaque_input}' à la date '{date_str}'.")
                    else:
                        pdf_buffer = BytesIO()
                        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
                        styles = getSampleStyleSheet()
                        title_style = ParagraphStyle('CoverTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, leading=20, textColor=colors.HexColor('#1a365d'))
                        caption_style = ParagraphStyle('CaptionStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=13, textColor=colors.HexColor('#333333'))
                        
                        story = [
                            Paragraph("Rapport sur l'exploitabilité des images captées par Neurogreen", title_style),
                            Paragraph(f"<b>Site :</b> UVE de Tibi (Pont-de-Loup) | <b>Date :</b> {date_str} | <b>Plaque :</b> {pdf_plaque_input}", styles['Normal']),
                            Spacer(1, 15)
                        ]
                        
                        for idx, blob in enumerate(image_blobs, start=1):
                            img = RLImage(BytesIO(blob.download_as_bytes()), width=480, height=270)
                            img.hAlign = 'CENTER'
                            story.append(img)
                            story.append(Spacer(1, 6))
                            story.append(Paragraph(f"<b>Figure {idx}:</b> Extraction galerie - Fichier : {os.path.basename(blob.name)} (Plaque : {pdf_plaque_input})", caption_style))
                            story.append(Spacer(1, 15))
                            if idx % 2 == 0 and idx < len(image_blobs):
                                story.append(PageBreak())
                                
                        doc.build(story)
                        st.download_button(
                            label="💾 Cliquer ici pour télécharger le PDF généré",
                            data=pdf_buffer.getvalue(),
                            file_name=f"Rapport_Neurogreen_{pdf_plaque_input}_{date_str}.pdf",
                            mime="application/pdf",
                            type="primary",
                            key="download_pdf_btn_v2"
                        )
                        st.success("Rapport PDF généré avec succès !")
                except Exception as e:
                    st.error(f"Erreur lors de la génération du PDF : {e}")
            else:
                st.warning("Veuillez sélectionner une plaque valide.")
    else:
        st.info("Aucune donnée disponible pour les filtres sélectionnés.")
else:
    st.warning("Aucune donnée d'alerte trouvée dans la table BigQuery.")