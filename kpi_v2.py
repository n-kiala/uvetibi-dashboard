# kpi_v2.py
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from google.cloud import bigquery

def afficher_page_kpi_v2():
    # --- STYLE CSS PERSONNALISÉ ---
    st.markdown("""
        <style>
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
    @st.cache_data(ttl=60)
    def charger_donnees_bq():
        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "tibi-credentials.json"
            client = bigquery.Client()
            # Requête ciblant la table avec count à la place de l'ID
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

        # En-tête de la page style interface pro
        st.markdown('<div class="main-header">Constats d’erreurs de tri — FFOM (UVE Pont-de-Loup)</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="sub-header">Source : {source_info} · Suivi via colonnes count</div>', unsafe_allow_html=True)

        # --- BARRE DE FILTRAGE ---
        col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
        with col_f1:
            options_temps = ["Semaine", "Aujourd'hui", "Choisir un jour précis", "Tout afficher"]
            choix_temps = st.selectbox("Période", options_temps, key="kpi_v2_periode")
        with col_f2:
            tournee_filtre = st.selectbox("Tournées", ["Toutes les tournées"], key="kpi_v2_tournee")
        with col_f3:
            types_disponibles = ["Tous les types"] + list(df['type'].dropna().unique())
            type_filtre = st.selectbox("Types d'erreurs", types_disponibles, key="kpi_v2_type")

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
            jour_choisi = st.date_input("Sélectionnez le jour précis", aujourd_hui, key="kpi_v2_date_precis")
            df_filtered = df_filtered[df_filtered['date'] == jour_choisi]

        if type_filtre != "Tous les types":
            df_filtered = df_filtered[df_filtered['type'] == type_filtre]

        # --- CALCULS DES KPIS (Remplacement ID par count) ---
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

        # --- AFFICHAGE DES BLOCS MÉTRIQUES ---
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.markdown(f"""
                <div class="metric-card">
                    <span style="color: #6c757d; font-size: 13px;">Erreurs constatées</span>
                    <h2 style="margin: 0; color: #111827; font-weight: 700;">{total_erreurs}</h2>
                    <span style="color: #6c757d; font-size: 11px;">sur {nb_jours} jours</span>
                </div>
            """, unsafe_allow_html=True)

        with c2:
            st.markdown(f"""
                <div class="metric-card">
                    <span style="color: #6c757d; font-size: 13px;">Cumul Count total</span>
                    <h2 style="margin: 0; color: #111827; font-weight: 700;">{int(total_count_sum)}</h2>
                    <span style="color: #6c757d; font-size: 11px;">quantité cumulée</span>
                </div>
            """, unsafe_allow_html=True)

        with c3:
            st.markdown(f"""
                <div class="metric-card">
                    <span style="color: #6c757d; font-size: 13px;">Plaques distinctes</span>
                    <h2 style="margin: 0; color: #111827; font-weight: 700;">{plaques_distinctes}</h2>
                    <span style="color: #6c757d; font-size: 11px;">véhicules identifiés</span>
                </div>
            """, unsafe_allow_html=True)

        with c4:
            st.markdown(f"""
                <div class="metric-card">
                    <span style="color: #6c757d; font-size: 13px;">Type dominant</span>
                    <h2 style="margin: 0; color: #111827; font-weight: 700;">{val_dominant}</h2>
                    <span style="color: #6c757d; font-size: 11px;">{type_dominant}</span>
                </div>
            """, unsafe_allow_html=True)

        # --- GRAPHIQUE EMPILÉ (BAR CHART) ---
        st.markdown("#### Erreurs par jour et par type")
        st.markdown("<span style='color: #6b7280; font-size: 12px;'>Cliquez sur les éléments de la légende pour filtrer par catégorie.</span>", unsafe_allow_html=True)

        if not df_filtered.empty:
            df_grouped = df_filtered.groupby([df_filtered['horodatage'].dt.strftime('%Y-%m-%d'), 'type']).size().reset_index(name='nombre')
            df_grouped.columns = ['jour', 'type', 'nombre']

            fig = px.bar(
                df_grouped,
                x="jour",
                y="nombre",
                color="type",
                color_discrete_map={
                    "PMC": "#3b82f6",
                    "sac_non_conforme": "#ea580c",
                    "Sac_non_bio": "#ea580c",
                    "Carton": "#f59e0b",
                    "Inerte / métal": "#10b981",
                    "Autre": "#6b7280"
                },
                template="simple_white"
            )
            fig.update_layout(
                barmode="stack",
                legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0),
                margin=dict(t=20, b=10, l=10, r=10),
                xaxis_title="",
                yaxis_title=""
            )
            st.plotly_chart(fig, use_container_width=True)

            # --- TABLEAU DÉTAILLÉ (AVEC COUNT À LA PLACE D'ID) ---
            st.markdown("---")
            st.markdown("#### Détail des constats d'erreurs")
            
            colonnes_disponibles = [c for c in ['horodatage', 'count', 'type', 'score_confiance', 'plaque'] if c in df_filtered.columns]
            df_affichage = df_filtered[colonnes_disponibles].sort_values(by='horodatage', ascending=False)
            
            st.dataframe(
                df_affichage,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Aucune donnée disponible pour les filtres sélectionnés.")
    else:
        st.warning("Aucune donnée d'alerte trouvée dans la table BigQuery.")