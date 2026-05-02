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
    from pathlib import Path
    base_dir = Path(__file__).parent
    db_path = base_dir / "data" / "courtalpha.duckdb"
    
    if not db_path.exists():
        st.error(f"DB not found at: {db_path.absolute()}")
        st.write("Root files:", [f.name for f in base_dir.iterdir()])
        data_dir = base_dir / "data"
        if data_dir.exists():
            st.write("Data folder files:", [f.name for f in data_dir.iterdir()])
        return pd.DataFrame()
    
    size_mb = db_path.stat().st_size / (1024 * 1024)
    if size_mb < 1:
        st.error(f"⚠️ DATABASE ERROR: Found a 1KB pointer file ({size_mb:.2f}MB). GitHub LFS did not sync the real data to Streamlit.")
        return pd.DataFrame()

    con = duckdb.connect(str(db_path), read_only=True)
    
    # 1. Base Metrics
    df = con.execute("SELECT * FROM player_metrics").df()
    
    # 2. Robust Team & Position Mapping
    try:
        mapping_query = """
            SELECT PLAYER_NAME, TEAM, POSITION FROM (
                SELECT PLAYER_NAME, TEAM, 'N/A' as POSITION, 1 as priority FROM player_teams
                UNION ALL
                SELECT PLAYER_NAME, TEAM, POSITION, 2 as priority FROM contracts
            ) 
            QUALIFY ROW_NUMBER() OVER(PARTITION BY PLAYER_NAME ORDER BY priority DESC) = 1
        """
        meta = con.execute(mapping_query).df()
        df = df.merge(meta, on='PLAYER_NAME', how='left')
    except Exception as e:
        df['TEAM'] = "Unknown"
        df['POSITION'] = "N/A"
        
    df['TEAM'] = df['TEAM'].fillna("Unknown")
    df['POSITION'] = df['POSITION'].fillna("N/A")
    
    con.close()
    return df

@st.cache_data
def load_shot_data(player_name):
    base_dir = os.path.dirname(__file__)
    db_path = os.path.join(base_dir, 'data/courtalpha.duckdb')
    con = duckdb.connect(db_path, read_only=True)
    
    query = """
        SELECT LOC_X, LOC_Y, SHOT_MADE_FLAG 
        FROM play_by_play 
        WHERE PLAYER_NAME = ? 
          AND LOC_X IS NOT NULL 
          AND ACTION_TYPE IN ('Made Shot', 'Missed Shot')
    """
    shots = con.execute(query, [player_name]).df()
    con.close()
    return shots

st.sidebar.title("🏀 CourtAlpha v2.5")
st.sidebar.markdown("*Executive Intelligence Suite*")
st.sidebar.markdown("---")
nav = st.sidebar.radio("Navigation", ["Executive Summary", "Player Intelligence", "Lineup Optimizer", "Trade Simulator", "Economic Layer"])

df = load_data()

def optimize_lineup(star_name, players_df):
    star = players_df[players_df['PLAYER_NAME'] == star_name].iloc[0]
    others = players_df[players_df['PLAYER_NAME'] != star_name]
    
    # 1. Initialize Lineup with Star in their slot
    # Map raw positions to standard 5
    pos_map = {'PG': 0, 'SG': 1, 'SF': 2, 'PF': 3, 'C': 4}
    standard_pos = ['PG', 'SG', 'SF', 'PF', 'C']
    
    lineup = [None] * 5
    star_pos_idx = pos_map.get(star['POSITION'], 2) # SF default if unknown
    lineup[star_pos_idx] = star
    
    # 2. Strategic Fit Analysis
    # We want complementary archetypes for the remaining slots
    roles = {
        "PG": ["Floor General", "High-Usage Slasher"],
        "SG": ["Movement Shooter", "3&D Wing"],
        "SF": ["3&D Wing", "Versatile Forward"],
        "PF": ["Versatile Forward", "Connector / High-IQ Big"],
        "C": ["Elite Rim Protector", "Connector / High-IQ Big"]
    }
    
    # 3. Fill remaining slots with highest Meta-Impact for that position
    for i in range(5):
        if lineup[i] is not None: continue
        
        target_pos = standard_pos[i]
        possible = others[others['POSITION'] == target_pos]
        
        # Prefer specific archetypes for that position
        preferred = possible[possible['ARCHETYPE_NAME'].isin(roles[target_pos])]
        
        if not preferred.empty:
            best_fit = preferred.sort_values(by='META_IMPACT', ascending=False).iloc[0]
        elif not possible.empty:
            best_fit = possible.sort_values(by='META_IMPACT', ascending=False).iloc[0]
        else:
            # Emergency fallback: highest impact remaining player
            best_fit = others.sort_values(by='META_IMPACT', ascending=False).iloc[0]
            
        lineup[i] = best_fit
        others = others[others['PLAYER_NAME'] != best_fit['PLAYER_NAME']]
        
    return pd.DataFrame(lineup)

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
            st.dataframe(top_pillars[['PLAYER_NAME', 'TEAM', 'META_IMPACT', 'MARKET_VALUE', 'STRATEGIC_OUTLOOK']], use_container_width=True)
            
        with c2:
            st.subheader("Efficiency Engines")
            top_surplus = df.sort_values(by='SURPLUS_VALUE', ascending=False).head(10)
            st.dataframe(top_surplus[['PLAYER_NAME', 'TEAM', 'SURPLUS_VALUE', 'STRATEGIC_OUTLOOK']], use_container_width=True)

        with c3:
            st.subheader("Efficiency Risks")
            bottom_surplus = df.sort_values(by='SURPLUS_VALUE', ascending=True).head(10)
            st.dataframe(bottom_surplus[['PLAYER_NAME', 'TEAM', 'SURPLUS_VALUE', 'STRATEGIC_OUTLOOK']], use_container_width=True)

    elif nav == "Player Intelligence":
        st.title("Player Intelligence Report")
        
        player_name = st.selectbox("Select Player", sorted(df['PLAYER_NAME'].unique()))
        p = df[df['PLAYER_NAME'] == player_name].iloc[0]
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader(f"Profile: {player_name}")
            st.write(f"**Team:** {p['TEAM']} | **Position:** {p['POSITION']} | **Age:** {p['AGE']}")
            
            color = "#00ffcc" if "Pillar" in p['STRATEGIC_OUTLOOK'] else "#ffcc00" if "Engine" in p['STRATEGIC_OUTLOOK'] else "#ffffff"
            st.markdown(f"### Outlook: <span style='color:{color}'>{p['STRATEGIC_OUTLOOK']}</span>", unsafe_allow_html=True)
            
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
            tab1, tab2, tab3 = st.tabs(["Metric Decomposition", "Skill DNA", "Shot Heat Map"])
            
            with tab1:
                st.subheader("Metric Decomposition")
                bench_data = pd.DataFrame({
                    'Metric': ['Internal RAPM', 'LEBRON', 'EPM', 'DARKO'],
                    'Value': [p['SHRUNK_IMPACT']*100, p['EXTERNAL_LEBRON'], p['EXTERNAL_EPM'], p['EXTERNAL_DARKO']]
                })
                chart = alt.Chart(bench_data).mark_bar().encode(
                    x=alt.X('Value:Q'),
                    y=alt.Y('Metric:N', sort='-x'),
                    color=alt.condition(alt.datum.Value > 0, alt.value("#00ffcc"), alt.value("#ff4b4b"))
                ).properties(height=350)
                st.altair_chart(chart, use_container_width=True)
            
            with tab2:
                st.subheader("Skill DNA (Playstyle Frequencies)")
                dna_data = pd.DataFrame({
                    'Action': ['Logo', 'Floater', 'Post', 'Spot-up', 'Isolation', 'Rim Prot'],
                    'Freq': [p['LOGO_FREQ'], p['FLOATER_FREQ'], p['POST_FREQ'], p['SPOTUP_FREQ'], p['ISOLATION_FREQ'], p['RIM_PROT_FREQ']]
                })
                dna_chart = alt.Chart(dna_data).mark_bar(color="#ffcc00").encode(
                    x=alt.X('Freq:Q', axis=alt.Axis(format='%')),
                    y=alt.Y('Action:N', sort='-x')
                ).properties(height=350)
                st.altair_chart(dna_chart, use_container_width=True)

            with tab3:
                st.subheader("Shot Location Heat Map")
                shot_df = load_shot_data(player_name)
                if not shot_df.empty:
                    heatmap = alt.Chart(shot_df).mark_rect().encode(
                        x=alt.X('LOC_X:Q', bin=alt.Bin(maxbins=30), title="Court Width"),
                        y=alt.Y('LOC_Y:Q', bin=alt.Bin(maxbins=30), title="Court Length"),
                        color=alt.Color('count():Q', scale=alt.Scale(scheme='inferno'), title="Shot Density")
                    ).properties(height=400)
                    st.altair_chart(heatmap, use_container_width=True)
                else:
                    st.info("No spatial shot data available for this player.")

    # --- LINEUP OPTIMIZER ---
    elif nav == "Lineup Optimizer":
        st.title("Strategic Lineup Optimizer")
        st.info("Select a team and one of their top 3 impact players to build a complementary 5-man unit.")
        
        # 1. Select Team
        team_list = sorted(df[df['TEAM'] != 'Unknown']['TEAM'].unique())
        selected_team = st.selectbox("Select Team", team_list)
        
        # 2. Select from Top 3 Stars
        team_stars = df[df['TEAM'] == selected_team].sort_values(by='META_IMPACT', ascending=False).head(3)
        star_player = st.selectbox("Select Star Player (The Anchor)", team_stars['PLAYER_NAME'].unique())
        
        if star_player:
            rec_lineup = optimize_lineup(star_player, df)
            
            st.subheader(f"Balanced Lineup built around {star_player}")
            
            # Position labels for display
            pos_labels = ['PG', 'SG', 'SF', 'PF', 'C']
            
            cols = st.columns(5)
            for i, (_, p) in enumerate(rec_lineup.iterrows()):
                with cols[i]:
                    st.markdown(f"**{pos_labels[i]}**")
                    st.markdown(f"**{'🌟 ' if p['PLAYER_NAME'] == star_player else ''}{p['PLAYER_NAME']}**")
                    st.write(f"*{p['ARCHETYPE_NAME']}*")
                    st.metric("Impact", f"{p['META_IMPACT']:.2f}")
                    
            st.markdown("---")
            st.subheader("Unit Composition Analysis")
            
            total_unit_impact = rec_lineup['META_IMPACT'].sum()
            avg_age = rec_lineup['AGE'].mean()
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Total Lineup Meta-Impact", f"{total_unit_impact:.2f} Pts/100")
            with c2:
                st.metric("Average Unit Age", f"{avg_age:.1f}")
            with c3:
                total_cost = rec_lineup['CONTRACT_COST'].sum()
                st.metric("Total Unit Salary", format_currency(total_cost))
            
            st.dataframe(rec_lineup[['PLAYER_NAME', 'POSITION', 'ARCHETYPE_NAME', 'META_IMPACT', 'MARKET_VALUE', 'STRATEGIC_OUTLOOK']], use_container_width=True)

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
