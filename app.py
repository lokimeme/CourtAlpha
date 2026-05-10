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
                SELECT PLAYER_NAME, TEAM, POSITION, 1 as priority FROM player_teams
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
        
    # 3. Spatial Intelligence (4-Zone Distribution)
    spatial_metrics = con.execute("""
        SELECT 
            PLAYER_NAME,
            SUM(CASE WHEN (SQRT(BIN_X*BIN_X + BIN_Y*BIN_Y) < 80) THEN SHOT_COUNT ELSE 0 END)::FLOAT / SUM(SHOT_COUNT) as RIM_FREQ,
            SUM(CASE WHEN (SQRT(BIN_X*BIN_X + BIN_Y*BIN_Y) BETWEEN 80 AND 235) THEN SHOT_COUNT ELSE 0 END)::FLOAT / SUM(SHOT_COUNT) as MID_FREQ,
            SUM(CASE WHEN (ABS(BIN_X) >= 220 AND BIN_Y <= 92) THEN SHOT_COUNT ELSE 0 END)::FLOAT / SUM(SHOT_COUNT) as CORNER_3_FREQ,
            SUM(CASE WHEN (SQRT(BIN_X*BIN_X + BIN_Y*BIN_Y) > 235 AND BIN_Y > 92) THEN SHOT_COUNT ELSE 0 END)::FLOAT / SUM(SHOT_COUNT) as WING_3_FREQ
        FROM player_shot_density
        GROUP BY PLAYER_NAME
    """).df()
    df = df.merge(spatial_metrics, on='PLAYER_NAME', how='left')
    
    # Fill spatial metrics specifically with 0
    for col in ['RIM_FREQ', 'MID_FREQ', 'CORNER_3_FREQ', 'WING_3_FREQ']:
        df[col] = df[col].fillna(0)
    
    # Legacy aliases for UI compatibility
    df['RIM_PRESSURE'] = df['RIM_FREQ']
    df['SPACING_RATING'] = df['CORNER_3_FREQ'] + df['WING_3_FREQ']
    
    df['TEAM'] = df['TEAM'].fillna("Unknown")
    df['POSITION'] = df['POSITION'].fillna("N/A")
    df['PPG'] = df['PPG'].fillna(0.0)
    
    # 4. Positional Inference Fallback
    def infer_position(row):
        if row['POSITION'] != 'N/A':
            return row['POSITION']
        arch_map = {
            "Rim Protector": "C",
            "Post Specialist": "C",
            "Defensive Specialist": "C",
            "Two-Way Connector": "PF",
            "Interior Finisher": "PF",
            "Movement Shooter": "SG",
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

@st.cache_data
def load_lineup_shot_data(player_names):
    from pathlib import Path
    db_path = Path(__file__).parent / "data" / DB_NAME
    con = duckdb.connect(str(db_path), read_only=True)
    
    query = """
        SELECT BIN_X, BIN_Y, SUM(SHOT_COUNT) as SHOT_COUNT
        FROM player_shot_density 
        WHERE PLAYER_NAME IN ({})
        GROUP BY 1, 2
    """.format(','.join(['?'] * len(player_names)))
    
    data = con.execute(query, player_names).df()
    con.close()
    return data

st.sidebar.title("CourtAlpha")
st.sidebar.markdown("*Executive Intelligence Suite*")
st.sidebar.markdown("---")
nav = st.sidebar.radio("Navigation", ["Executive Summary", "Player Intelligence", "Lineup Optimizer", "Trade Simulator", "Economic Layer"])

df = load_data()

def optimize_lineup(star_name, players_df, strategy="Win Now"):
    star = players_df[players_df['PLAYER_NAME'] == star_name].iloc[0]
    others = players_df[players_df['PLAYER_NAME'] != star_name].copy()
    
    # 1. Base Scoring logic
    if strategy == "Cap-Balanced":
        others['BASE_SCORE'] = others['META_IMPACT'] + (others['SURPLUS_VALUE'] / 20_000_000)
    elif strategy == "Budget Build":
        others['BASE_SCORE'] = others['SURPLUS_VALUE'] / 1_000_000
    else:
        others['BASE_SCORE'] = others['META_IMPACT']

    # 2. Geometry Complementarity Engine
    # We want to fill the "gaps" in the star's shooting profile
    star_zones = np.array([star['RIM_FREQ'], star['MID_FREQ'], star['CORNER_3_FREQ'], star['WING_3_FREQ']])
    
    def calculate_geometry_fit(row):
        candidate_zones = np.array([row['RIM_FREQ'], row['MID_FREQ'], row['CORNER_3_FREQ'], row['WING_3_FREQ']])
        
        # Complementarity Score: High bonus when candidate excels where star is absent
        fit_vector = (1.0 - star_zones) * candidate_zones
        fit_bonus = np.sum(fit_vector) * 15.0 # Weight for spatial diversity
        
        # Special Archetype Synergy
        s_arch = star['ARCHETYPE_NAME']
        r_arch = row['ARCHETYPE_NAME']
        if s_arch == "Floor General" and r_arch in ["Interior Finisher", "Rim Protector"]: fit_bonus += 5.0
        if s_arch == "Two-Way Connector" and r_arch == "Self-Created Scorer": fit_bonus += 6.0
        if s_arch == "Interior Finisher" and r_arch == "Floor General": fit_bonus += 7.0
        
        return fit_bonus

    others['FIT_SCORE'] = others.apply(calculate_geometry_fit, axis=1)
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
        "SF": ["Two-Way Connector", "Movement Shooter"],
        "PF": ["Interior Finisher", "Two-Way Connector"],
        "C": ["Rim Protector", "Defensive Specialist", "Post Specialist"]
    }
    
    # 4. Fill remaining slots deterministically
    for i in range(5):
        if lineup[i] is not None: continue
        
        target_pos = standard_pos[i]
        possible = others[others['INFERRED_POSITION'] == target_pos].copy()
        
        # Dynamic Spacing Check: Ensure the unit isn't too crowded
        current_spacing = sum([p['SPACING_RATING'] for p in lineup if p is not None])
        if current_spacing < 0.6: 
            possible['OPT_SCORE'] += possible['SPACING_RATING'] * 15.0

        if not possible.empty:
            best_fit = possible.sort_values(by='OPT_SCORE', ascending=False).iloc[0]
            lineup[i] = best_fit
            others = others[others['PLAYER_NAME'] != best_fit['PLAYER_NAME']]
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
        
        # 1. Injury Simulation Sub-Engine
        with st.sidebar:
            st.markdown("---")
            st.subheader("🏥 Next-Man-Up Simulator")
            deactivate_player = st.selectbox("Simulate Injury (Deactivate)", ["None"] + sorted(df['PLAYER_NAME'].unique()))
            
        if deactivate_player != "None":
            p_injured = df[df['PLAYER_NAME'] == deactivate_player].iloc[0]
            team_name = p_injured['TEAM']
            st.warning(f"⚠️ **INJURY REPORT:** {deactivate_player} is out for the season. Analyzing {team_name} roster depth...")
            
            # Calculate team loss
            team_roster = df[df['TEAM'] == team_name].sort_values(by='META_IMPACT', ascending=False)
            healthy_roster = team_roster[team_roster['PLAYER_NAME'] != deactivate_player]
            
            loss_pct = (p_injured['META_IMPACT'] / team_roster['META_IMPACT'].sum()) if team_roster['META_IMPACT'].sum() > 0 else 0
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Impact Lost", f"{p_injured['META_IMPACT']:.2f}")
            with c2:
                st.metric("Relative Team Loss", f"{loss_pct:.1%}")
            with c3:
                st.metric("Replacement Candidate", healthy_roster.iloc[4]['PLAYER_NAME'] if len(healthy_roster) > 4 else "None")
            
            st.info(f"**Strategic Consequence:** {team_name} loses its primary '{p_injured['ARCHETYPE_NAME']}'. Rotation shifts toward higher-usage for the bench unit.")

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
            st.subheader("Official Performance Data")
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Rebounds", f"{p['REB']:.1f}")
                st.metric("Assists", f"{p['AST']:.1f}")
                st.metric("FG%", f"{p['FG_PCT']:.1%}")
            with c2:
                st.metric("Steals", f"{p['STL']:.1f}")
                st.metric("Blocks", f"{p['BLK']:.1f}")
                st.metric("3PT%", f"{p['FG3_PCT']:.1%}")

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
            # Action Log (PBP Linking)
            with st.expander("🎥 Full Season Play-by-Play Tape", expanded=False):
                st.info(f"Retrieving all recorded play-by-play events for {player_name} in the 2025-26 Season...")
                from pathlib import Path
                db_path = Path(__file__).parent / "data" / "courtalpha.duckdb" # Use main DB for full PBP
                if db_path.exists():
                    con_pbp = duckdb.connect(str(db_path), read_only=True)
                    pbp_data = con_pbp.execute("""
                        SELECT PERIOD, CLOCK, ACTION_TYPE, SUB_TYPE, DESCRIPTION 
                        FROM play_by_play 
                        WHERE PLAYER_NAME = ? AND SEASON = '2025-26'
                        ORDER BY GAME_ID, PERIOD, ACTION_NUMBER
                    """, [player_name]).df()
                    con_pbp.close()
                    if not pbp_data.empty:
                        st.dataframe(pbp_data, use_container_width=True, height=250)
                    else:
                        st.warning("No detailed PBP events found for this player in the current season.")
                else:
                    st.error("Deep Intelligence Storage (Source DB) not found. Detailed PBP logs are unavailable in this environment.")

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

        # 5. Roster Geometry Visualizer
        st.markdown("---")
        st.subheader("📐 Unit Floor Geometry")
        st.info("Analyzing the spatial overlap and gravitational centers of this 5-man unit.")
        
        lineup_names = rec_lineup['PLAYER_NAME'].tolist()
        combined_spatial_data = load_lineup_shot_data(lineup_names)
        
        from scripts.visual_engine import ShotChartEngine
        viz = ShotChartEngine()
        heatmap_fig = viz.create_lineup_heatmap(combined_spatial_data, title=f"Floor Gravity: {star_player}'s Unit")
        st.plotly_chart(heatmap_fig, use_container_width=True)

    elif nav == "Trade Simulator":
        st.title("Strategic Trade Simulator")
        cba = CBAEngine()
        
        st.info("Simulate trades and analyze the 'Butterfly Effect' on your team's identity.")
        
        # 1. Team Context
        sim_team = st.selectbox("Select Your Team", sorted(df['TEAM'].unique()), index=0)
        current_roster = df[df['TEAM'] == sim_team].sort_values(by='META_IMPACT', ascending=False).head(12)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Outgoing Assets")
            outgoing = st.multiselect("Select Players to Trade Away", current_roster['PLAYER_NAME'].unique(), key="out")
            out_df = df[df['PLAYER_NAME'].isin(outgoing)]
            st.table(out_df[['PLAYER_NAME', 'CONTRACT_COST', 'META_IMPACT']])
            total_out = out_df['CONTRACT_COST'].sum()
            
        with col2:
            st.subheader("Incoming Assets")
            incoming = st.multiselect("Select Players to Acquire", df[df['TEAM'] != sim_team]['PLAYER_NAME'].unique(), key="in")
            in_df = df[df['PLAYER_NAME'].isin(incoming)]
            st.table(in_df[['PLAYER_NAME', 'CONTRACT_COST', 'META_IMPACT']])
            total_in = in_df['CONTRACT_COST'].sum()

        st.markdown("---")
        
        # 2. Legality Check
        team_salary = df[df['TEAM'] == sim_team]['CONTRACT_COST'].sum()
        legality = cba.check_trade_legality(out_df['CONTRACT_COST'].tolist(), in_df['CONTRACT_COST'].tolist(), team_salary)
        
        if legality['legal']:
            st.success("✅ TRADE IS LEGAL")
        else:
            st.error("❌ TRADE BLOCKED")
            for note in legality['notes']:
                st.write(f"- {note}")
                
        # 3. Butterfly Effect (Identity Analysis)
        st.subheader("🦋 Strategic Butterfly Effect")
        
        # Calculate Baseline
        base_impact = current_roster['META_IMPACT'].mean()
        base_spacing = current_roster['SPACING_RATING'].mean()
        base_rim = current_roster['RIM_PRESSURE'].mean()
        base_age = current_roster['AGE'].mean()
        
        # Calculate New Identity
        new_roster = pd.concat([current_roster[~current_roster['PLAYER_NAME'].isin(outgoing)], in_df]).head(12)
        new_impact = new_roster['META_IMPACT'].mean()
        new_spacing = new_roster['SPACING_RATING'].mean()
        new_rim = new_roster['RIM_PRESSURE'].mean()
        new_age = new_roster['AGE'].mean()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Net Impact", f"{new_impact - base_impact:+.2f}", delta=f"{new_impact - base_impact:+.2f}")
        m2.metric("Spacing Change", f"{new_spacing - base_spacing:+.1%}", delta=f"{(new_spacing - base_spacing):.1%}")
        m3.metric("Rim Gravity", f"{new_rim - base_rim:+.1%}", delta=f"{(new_rim - base_rim):.1%}")
        m4.metric("Avg Age Change", f"{new_age - base_age:+.1f}", delta=f"{new_age - base_age:+.1f}", delta_color="inverse")
        
        # Heuristic Insight Engine
        st.markdown("#### **Front Office Scouting Notes**")
        if new_spacing > base_spacing + 0.05:
            st.write("🎯 **Spacing Surge:** Acquire elite shooting depth. Your slashers will have significantly more room to operate.")
        if new_rim > base_rim + 0.05:
            st.write("🛡️ **Paint Fortress:** This trade bolsters your interior integrity and rim-running gravity.")
        if new_age < base_age - 2:
            st.write("⏳ **Window Expansion:** You've significantly lowered the team's average age, extending your competitive timeline.")
        if new_impact > base_impact + 0.5:
            st.write("📈 **Competitive Leap:** On-court impact suggests this team moves into a higher tier of championship contention.")
        elif new_impact < base_impact - 0.5:
            st.write("⚠️ **Asset Liquidation:** You are sacrificing immediate on-court production, likely to prioritize future draft assets or cap space.")
        
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
 
