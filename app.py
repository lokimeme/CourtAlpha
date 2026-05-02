import streamlit as st
import duckdb
import pandas as pd
import altair as alt
import numpy as np
from scripts.cba_engine import CBAEngine
from scripts.utils import format_currency
from scripts.narrative_generator import generate_player_pdf

st.set_page_config(page_title="CourtAlpha | Front Office Dashboard", layout="wide", page_icon="🏀")

st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #1e2130;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #3e4253;
    }
    .status-pillar { color: #00ffcc; font-weight: bold; }
    .status-engine { color: #ffcc00; font-weight: bold; }
    .status-risk { color: #ff4b4b; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data/courtalpha.duckdb')

@st.cache_data
def load_data():
    if not os.path.exists(DB_PATH):
        st.error(f"Database not found at {DB_PATH}. Current files: {os.listdir(os.path.dirname(DB_PATH)) if os.path.exists(os.path.dirname(DB_PATH)) else 'data/ dir missing'}")
        return pd.DataFrame()
        
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute("SELECT * FROM player_metrics").df()
    try:
        teams = con.execute("SELECT PLAYER_NAME, TEAM FROM contracts").df()
        df = df.merge(teams, on='PLAYER_NAME', how='left')
    except:
        df['TEAM'] = "Unknown"
    
    con.close()
    return df

st.sidebar.title("🏀 CourtAlpha v2.5")
st.sidebar.markdown("*Executive Intelligence Suite*")
st.sidebar.markdown("---")
nav = st.sidebar.radio("Navigation", ["Executive Summary", "Player Intelligence", "Trade Simulator", "Economic Layer"])

df = load_data()

if df.empty:
    st.error("No data found in database. Please run the ingestion and ML pipelines.")
else:
    if nav == "Executive Summary":
        st.title("Executive Front Office Dashboard")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Players Analyzed", len(df))
        with col2:
            st.metric("Avg Meta-Impact", f"{df['META_IMPACT'].mean():.2f}")
        with col3:
            pillars = len(df[df['STRATEGIC_OUTLOOK'] == "Championship Pillar"])
            st.metric("Championship Pillars", pillars)
        with col4:
            engines = len(df[df['STRATEGIC_OUTLOOK'] == "Efficiency Engine"])
            st.metric("Efficiency Engines", engines)

        st.markdown("---")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.subheader("Market Value Leaders")
            top_pillars = df.sort_values(by='MARKET_VALUE', ascending=False).head(10)
            st.dataframe(top_pillars[['PLAYER_NAME', 'META_IMPACT', 'MARKET_VALUE', 'STRATEGIC_OUTLOOK']], use_container_width=True)
            
        with c2:
            st.subheader("Efficiency Engines")
            top_surplus = df.sort_values(by='SURPLUS_VALUE', ascending=False).head(10)
            st.dataframe(top_surplus[['PLAYER_NAME', 'SURPLUS_VALUE', 'STRATEGIC_OUTLOOK']], use_container_width=True)

        with c3:
            st.subheader("Efficiency Risks")
            bottom_surplus = df.sort_values(by='SURPLUS_VALUE', ascending=True).head(10)
            st.dataframe(bottom_surplus[['PLAYER_NAME', 'SURPLUS_VALUE', 'STRATEGIC_OUTLOOK']], use_container_width=True)

    elif nav == "Player Intelligence":
        st.title("Player Intelligence Report")
        
        player_name = st.selectbox("Select Player", sorted(df['PLAYER_NAME'].unique()))
        p = df[df['PLAYER_NAME'] == player_name].iloc[0]
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader(f"Profile: {player_name}")
            st.write(f"**Team:** {p['TEAM']} | **Age:** {p['AGE']} | **Archetype:** {p['ARCHETYPE_NAME']}")
            
            color = "#00ffcc" if "Pillar" in p['STRATEGIC_OUTLOOK'] else "#ffcc00" if "Engine" in p['STRATEGIC_OUTLOOK'] else "#ffffff"
            st.markdown(f"### Outlook: <span style='color:{color}'>{p['STRATEGIC_OUTLOOK']}</span>", unsafe_allow_stdio=True)
            
            st.markdown("---")
            st.metric("Meta-Impact (Pts/100)", f"{p['META_IMPACT']:.2f}")
            st.metric("Market Value", format_currency(p['MARKET_VALUE']))
            st.metric("Contract Cost", format_currency(p['CONTRACT_COST']))
            st.metric("Surplus Value", format_currency(p['SURPLUS_VALUE']), delta=format_currency(p['SURPLUS_VALUE']))
            
            st.markdown("---")
            try:
                pdf_bytes = generate_player_pdf(p.to_dict())
                st.download_button(
                    label="📥 Download Executive PDF Report",
                    data=pdf_bytes,
                    file_name=f"{player_name}_Report.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.warning(f"PDF generation failed: {e}")
            
        with col2:
            st.subheader("Metric Decomposition")
            
            bench_data = pd.DataFrame({
                'Metric': ['Internal RAPM', 'LEBRON', 'EPM', 'DARKO'],
                'Value': [p['SHRUNK_IMPACT']*100, p['EXTERNAL_LEBRON'], p['EXTERNAL_EPM'], p['EXTERNAL_DARKO']]
            })
            
            chart = alt.Chart(bench_data).mark_bar().encode(
                x=alt.X('Value:Q'),
                y=alt.Y('Metric:N', sort='-x'),
                color=alt.condition(
                    alt.datum.Value > 0,
                    alt.value("#00ffcc"),  # Green for positive
                    alt.value("#ff4b4b")   # Red for negative
                )
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)
            
            st.subheader("Skill DNA (Playstyle Frequencies)")
            dna_data = pd.DataFrame({
                'Action': ['Logo', 'Floater', 'Post', 'Spot-up', 'Isolation', 'Rim Prot'],
                'Freq': [p['LOGO_FREQ'], p['FLOATER_FREQ'], p['POST_FREQ'], p['SPOTUP_FREQ'], p['ISOLATION_FREQ'], p['RIM_PROT_FREQ']]
            })
            
            dna_chart = alt.Chart(dna_data).mark_bar(color="#ffcc00").encode(
                x=alt.X('Freq:Q', axis=alt.Axis(format='%')),
                y=alt.Y('Action:N', sort='-x')
            ).properties(height=300)
            st.altair_chart(dna_chart, use_container_width=True)

    elif nav == "Trade Simulator":
        st.title("CBA Trade Simulator")
        cba = CBAEngine()
        
        st.info("Simulate trades and check legality under 2023 CBA rules.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Outgoing Assets")
            outgoing = st.multiselect("Select Players to Trade Away", df['PLAYER_NAME'].unique(), key="out")
            out_df = df[df['PLAYER_NAME'].isin(outgoing)]
            st.table(out_df[['PLAYER_NAME', 'CONTRACT_COST', 'META_IMPACT']])
            total_out = out_df['CONTRACT_COST'].sum()
            avg_impact_out = out_df['META_IMPACT'].mean() if not out_df.empty else 0
            
        with col2:
            st.subheader("Incoming Assets")
            incoming = st.multiselect("Select Players to Acquire", df['PLAYER_NAME'].unique(), key="in")
            in_df = df[df['PLAYER_NAME'].isin(incoming)]
            st.table(in_df[['PLAYER_NAME', 'CONTRACT_COST', 'META_IMPACT']])
            total_in = in_df['CONTRACT_COST'].sum()
            avg_impact_in = in_df['META_IMPACT'].mean() if not in_df.empty else 0

        st.markdown("---")
        
        team_salary = st.number_input("Your Team's Total Salary (Current)", value=170000000, step=1000000)
        
        legality = cba.check_trade_legality(out_df['CONTRACT_COST'].tolist(), in_df['CONTRACT_COST'].tolist(), team_salary)
        
        if legality['legal']:
            st.success("✅ TRADE IS LEGAL")
        else:
            st.error("❌ TRADE BLOCKED")
            for note in legality['notes']:
                st.write(f"- {note}")
                
        st.subheader("Net Impact Change")
        net_impact = (avg_impact_in * len(in_df)) - (avg_impact_out * len(out_df))
        st.metric("Net Meta-Impact Change", f"{net_impact:+.2f} Pts/100")
        
        net_salary = total_in - total_out
        st.metric("Net Salary Change", format_currency(net_salary), delta=format_currency(net_salary), delta_color="inverse")

    elif nav == "Economic Layer":
        st.title("Economic Layer & Market Projections")
        
        st.write("Full league analysis of surplus value and strategic outlook.")
        
        f_outlook = st.multiselect("Filter by Outlook", df['STRATEGIC_OUTLOOK'].unique(), default=df['STRATEGIC_OUTLOOK'].unique())
        f_arch = st.multiselect("Filter by Archetype", df['ARCHETYPE_NAME'].unique(), default=df['ARCHETYPE_NAME'].unique())
        
        display_df = df[(df['STRATEGIC_OUTLOOK'].isin(f_outlook)) & (df['ARCHETYPE_NAME'].isin(f_arch))]
        
        st.dataframe(
            display_df[['PLAYER_NAME', 'TEAM', 'AGE', 'ARCHETYPE_NAME', 'META_IMPACT', 'CONTRACT_COST', 'MARKET_VALUE', 'SURPLUS_VALUE', 'STRATEGIC_OUTLOOK', 'FLAGS']],
            use_container_width=True,
            height=800
        )
