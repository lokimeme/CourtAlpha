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

DB_NAME = 'courtalpha_deploy.duckdb'

@st.cache_data
def load_data():
    from pathlib import Path
    base_dir = Path(__file__).parent
    db_path = base_dir / "data" / DB_NAME
    
    if not db_path.exists():
        st.error(f"DB not found at: {db_path.absolute()}")
        return pd.DataFrame()
        
    con = duckdb.connect(str(db_path), read_only=True)
    
    # 1. Base Metrics
    df = con.execute("""
        SELECT * FROM player_metrics 
        WHERE PLAYER_NAME NOT LIKE '%Putback%' 
          AND PLAYER_NAME NOT LIKE '%Reverse%'
          AND PLAYER_NAME NOT LIKE '%Tip%'
    """).df()
    
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
        # Ensure we don't have duplicate TEAM/POSITION columns before merging
        cols_to_use = [c for c in meta.columns if c not in df.columns or c == 'PLAYER_NAME']
        df = df.merge(meta[cols_to_use], on='PLAYER_NAME', how='left')
    except Exception as e:
        st.error(f"Mapping error: {e}")
        if 'TEAM' not in df.columns: df['TEAM'] = "Unknown"
        if 'POSITION' not in df.columns: df['POSITION'] = "N/A"
        
    # 3. Spatial Intelligence (Spacing & Rim Gravity)
    spatial_metrics = con.execute("""
        SELECT 
            PLAYER_NAME,
            SUM(CASE WHEN (SQRT(BIN_X*BIN_X + BIN_Y*BIN_Y) < 80) THEN SHOT_COUNT ELSE 0 END)::FLOAT / SUM(SHOT_COUNT) as RIM_PRESSURE,
            SUM(CASE WHEN (SQRT(BIN_X*BIN_X + BIN_Y*BIN_Y) > 230 OR (ABS(BIN_X) >= 220 AND BIN_Y <= 140)) THEN SHOT_COUNT ELSE 0 END)::FLOAT / SUM(SHOT_COUNT) as SPACING_RATING
        FROM player_shot_density
        GROUP BY PLAYER_NAME
    """).df()
    df = df.merge(spatial_metrics, on='PLAYER_NAME', how='left')
    
    # Fill spatial metrics specifically with 0, not the whole dataframe
    df['RIM_PRESSURE'] = df['RIM_PRESSURE'].fillna(0)
    df['SPACING_RATING'] = df['SPACING_RATING'].fillna(0)
    
    df['TEAM'] = df['TEAM'].fillna("Unknown")
    df['POSITION'] = df['POSITION'].fillna("N/A")
    df['PPG'] = df['PPG'].fillna(0.0)
    
    # 4. Positional Inference Fallback
    def infer_position(row):
        if row['POSITION'] != 'N/A':
            return row['POSITION']
        arch_map = {
            "Rim Protector": "C",
            "Post Specialist": "PF",
            "Defensive Specialist": "SF",
            "Two-Way Connector": "SF",
            "Movement Shooter": "SG",
            "Interior Finisher": "PF",
            "Self-Created Scorer": "SG",
            "Floor General": "PG"
        }
        return arch_map.get(row['ARCHETYPE_NAME'], 'SF')
    
    df['INFERRED_POSITION'] = df.apply(infer_position, axis=1)
    
    con.close()
    return df

@st.cache_data
def load_shot_data(player_name):
    from pathlib import Path
    base_dir = Path(__file__).parent
    db_path = base_dir / "data" / DB_NAME
    con = duckdb.connect(str(db_path), read_only=True)
    
    query = """
        SELECT BIN_X as LOC_X, BIN_Y as LOC_Y, SHOT_COUNT 
        FROM player_shot_density 
        WHERE PLAYER_NAME = ?
    """
    shots = con.execute(query, [player_name]).df()
    con.close()
    return shots

st.sidebar.title("CourtAlpha")
st.sidebar.markdown("*Executive Intelligence Suite*")
st.sidebar.markdown("---")
nav = st.sidebar.radio("Navigation", ["Executive Summary", "Player Intelligence", "Lineup Optimizer", "Trade Simulator", "Economic Layer"])

df = load_data()

def optimize_lineup(star_name, players_df, strategy="Win Now"):
    star = players_df[players_df['PLAYER_NAME'] == star_name].iloc[0]
    others = players_df[players_df['PLAYER_NAME'] != star_name].copy()
    
    # 1. Base Scoring logic based on strategy
    if strategy == "Cap-Balanced":
        others['BASE_SCORE'] = others['META_IMPACT'] + (others['SURPLUS_VALUE'] / 20_000_000)
    elif strategy == "Budget Build":
        others['BASE_SCORE'] = others['SURPLUS_VALUE'] / 1_000_000
    else:
        others['BASE_SCORE'] = others['META_IMPACT']

    # 2. Spatial Fit Logic
    star_rim = star['RIM_PRESSURE']
    star_space = star['SPACING_RATING']
    
    def calculate_fit(row):
        fit_bonus = 0
        # Complementary logic: Slashers need Spacers, Spacers need Rim Gravity
        if star_rim > 0.4:
            fit_bonus += row['SPACING_RATING'] * 8.0  # High priority on spacing
        if star_space > 0.4:
            fit_bonus += row['RIM_PRESSURE'] * 5.0   # High priority on rim pressure/gravity
            
        # Archetype Synergy
        if star['ARCHETYPE_NAME'] == "Floor General" and row['ARCHETYPE_NAME'] in ["Movement Shooter", "Elite Rim Protector"]:
            fit_bonus += 3.0
        return fit_bonus

    others['FIT_SCORE'] = others.apply(calculate_fit, axis=1)
    others['OPT_SCORE'] = others['BASE_SCORE'] + others['FIT_SCORE']

    # 3. Initialize Lineup
    pos_map = {'PG': 0, 'SG': 1, 'SF': 2, 'PF': 3, 'C': 4}
    standard_pos = ['PG', 'SG', 'SF', 'PF', 'C']
    lineup = [None] * 5
    
    star_pos = star['INFERRED_POSITION']
    star_pos_idx = pos_map.get(star_pos, 2)
    lineup[star_pos_idx] = star
    
    roles = {
        "PG": ["Floor General", "Self-Created Scorer"],
        "SG": ["Movement Shooter", "Self-Created Scorer"],
        "SF": ["Defensive Specialist", "Two-Way Connector"],
        "PF": ["Post Specialist", "Interior Finisher"],
        "C": ["Rim Protector", "Post Specialist"]
    }
    
    # 4. Fill remaining slots
    for i in range(5):
        if lineup[i] is not None: continue
        
        target_pos = standard_pos[i]
        possible = others[others['INFERRED_POSITION'] == target_pos].copy()
        
        # Dynamic Spacing Check: If current lineup is clogged, prioritize spacers
        current_spacing = sum([p['SPACING_RATING'] for p in lineup if p is not None])
        if current_spacing < 0.8:
            possible['OPT_SCORE'] += possible['SPACING_RATING'] * 12.0

        preferred = possible[possible['ARCHETYPE_NAME'].isin(roles[target_pos])]
        
        # Variety Logic: Add tiny random noise to break ties and rotate similar fits
        noise = np.random.normal(0, 0.05, size=len(possible))
        possible['OPT_SCORE'] += noise

        if not preferred.empty:
            best_fit = preferred.sort_values(by='OPT_SCORE', ascending=False).iloc[0]
        elif not possible.empty:
            best_fit = possible.sort_values(by='OPT_SCORE', ascending=False).iloc[0]
        else:
            best_fit = others.sort_values(by='OPT_SCORE', ascending=False).iloc[0]
            
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
            st.subheader("Spatial Profile")
            st.progress(min(max(p['RIM_PRESSURE'], 0.0), 1.0), text=f"Rim Pressure: {p['RIM_PRESSURE']:.1%}")
            st.progress(min(max(p['SPACING_RATING'], 0.0), 1.0), text=f"Spacing Rating: {p['SPACING_RATING']:.1%}")
            
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
                        x=alt.X('LOC_X:Q', title="Court Width"),
                        y=alt.Y('LOC_Y:Q', title="Court Length"),
                        color=alt.Color('SHOT_COUNT:Q', scale=alt.Scale(scheme='inferno'), title="Shot Density")
                    ).properties(height=400)
                    st.altair_chart(heatmap, use_container_width=True)
                else:
                    st.info("No spatial shot data available for this player.")

    # --- LINEUP OPTIMIZER ---
    elif nav == "Lineup Optimizer":
        st.title("Strategic Lineup Optimizer")
        st.info("Select a team and one of their top 3 impact players to build a complementary 5-man unit.")
        
        c1, c2 = st.columns(2)
        with c1:
            team_list = sorted([str(t) for t in df[df['TEAM'] != 'Unknown']['TEAM'].unique() if pd.notnull(t)])
            selected_team = st.selectbox("Select Team", team_list)
        with c2:
            opt_strategy = st.selectbox("Cap Strategy", ["Win Now", "Cap-Balanced", "Budget Build"], help="Win Now maximizes impact. Cap-Balanced finds efficient high-impact players. Budget Build prioritizes low-cost engines.")
        
        # 2. Select from Top 3 Stars (By PPG)
        team_stars = df[df['TEAM'] == selected_team].sort_values(by='PPG', ascending=False).head(3)
        star_player = st.selectbox("Select Star Player (The Anchor)", team_stars['PLAYER_NAME'].unique())
        
        if star_player:
            rec_lineup = optimize_lineup(star_player, df, strategy=opt_strategy)
            
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
                lineup_spacing = rec_lineup['SPACING_RATING'].mean()
                st.metric("Lineup Spacing Index", f"{lineup_spacing:.2f}")
            with c2:
                st.metric("Average Unit Age", f"{avg_age:.1f}")
                lineup_rim = rec_lineup['RIM_PRESSURE'].mean()
                st.metric("Lineup Rim Gravity", f"{lineup_rim:.2f}")
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
 
