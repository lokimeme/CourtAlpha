from fpdf import FPDF
from datetime import datetime

class CourtAlphaPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'CourtAlpha | Executive Intelligence Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()} | Generated on {datetime.now().strftime("%Y-%m-%d %H:%M")}', 0, 0, 'C')

def generate_player_pdf(p_data):
    pdf = CourtAlphaPDF()
    pdf.add_page()

    # 1. Executive Summary Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, f"Player Intelligence Brief: {p_data['PLAYER_NAME']}", ln=True, border='B')
    pdf.ln(5)

    # 2. Vital Stats Grid
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(40, 8, "TEAM:", border=0)
    pdf.set_font("Arial", '', 11)
    pdf.cell(50, 8, str(p_data['TEAM']), ln=True)

    pdf.set_font("Arial", 'B', 11)
    pdf.cell(40, 8, "POSITION:", border=0)
    pdf.set_font("Arial", '', 11)
    pdf.cell(50, 8, str(p_data['POSITION']), ln=True)

    pdf.set_font("Arial", 'B', 11)
    pdf.cell(40, 8, "OUTLOOK:", border=0)
    pdf.set_font("Arial", '', 11)
    pdf.cell(50, 8, str(p_data['STRATEGIC_OUTLOOK']), ln=True)
    pdf.ln(5)

    # 3. Dynamic Narrative Scouting Report
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Executive Scouting Report", ln=True)
    pdf.set_font("Arial", 'I', 11)

    # Generate Narrative Logic
    arch = p_data['ARCHETYPE_NAME']
    impact = p_data['META_IMPACT']
    ppg = p_data['PPG']

    narrative = ""
    if arch == "Floor General":
        narrative = f"{p_data['PLAYER_NAME']} functions as a primary offensive engine, leveraging elite range and play-initiation skills to manipulate opposing defenses. "
    elif arch == "Rim Protector":
        narrative = f"{p_data['PLAYER_NAME']} provides elite interior structural integrity, serving as a high-gravity defensive anchor and vertical spacer. "
    elif arch == "Movement Shooter":
        narrative = f"{p_data['PLAYER_NAME']} is a premier floor-stretcher whose perimeter gravity creates significant operating windows for interior slashers. "
    elif arch == "Self-Created Scorer":
        narrative = f"{p_data['PLAYER_NAME']} excels as an isolation-heavy bucket-getter, capable of generating high-value looks under defensive duress. "
    else:
        narrative = f"{p_data['PLAYER_NAME']} serves as a versatile {arch}, providing balanced contributions across multiple phases of play. "

    if impact > 1.5:
        narrative += "Statistically, they rank as a top-tier impact outlier, driving winning across almost every lineup combination."
    elif impact > 0:
        narrative += f"With a positive meta-impact of {impact:.2f}, they function as a highly efficient rotation piece."
    else:
        narrative += "While their current impact is neutral, their specific playstyle fingerprint provides strategic utility in targeted matchups."

    pdf.multi_cell(0, 8, narrative, border=1)
    pdf.ln(10)

    # 4. Economic Valuation
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Economic Valuation & Market Projection", ln=True)
    pdf.set_font("Arial", '', 11)

    valuation_data = [
        ("Current PPG", f"{ppg:.1f}"),
        ("Meta-Impact", f"{impact:.2f} Pts/100"),
        ("Projected Market Value", f"${p_data['MARKET_VALUE']:,.0f}"),
        ("Actual Contract Cost", f"${p_data['CONTRACT_COST']:,.0f}"),
        ("Annual Surplus Value", f"${p_data['SURPLUS_VALUE']:,.0f}")
    ]

    for label, val in valuation_data:
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(60, 8, label + ":", border=0)
        pdf.set_font("Arial", '', 11)
        pdf.cell(40, 8, val, ln=True)

    pdf.ln(10)

    # 5. Strategic Offseason Value
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Strategic Offseason Value & Trade Utility", ln=True)
    pdf.set_font("Arial", '', 11)

    surplus = p_data['SURPLUS_VALUE']
    if surplus > 10000000:
        utility = "ELITE ASSET: Highly positive surplus value makes this player a premier trade chip or foundational pillar."
    elif surplus > 0:
        utility = "EFFICIENT ROTATION: Value exceeds contract cost; providing high-level production relative to cap hit."
    elif surplus > -10000000:
        utility = "NEUTRAL VALUE: Market value is aligned with contract. Primarily a matching-salary piece in larger deals."
    else:
        utility = "DISTRESSED ASSET: Contract significantly exceeds current production. May require sweeteners for offloading."

    pdf.multi_cell(0, 8, utility, border=1)
    pdf.ln(5)

    # 6. Skill-DNA Breakdown
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Skill-DNA Fingerprint (Micro-Action Freq)", ln=True)
    pdf.set_font("Arial", '', 11)

    dna_metrics = [
        ('LOGO_FREQ', 'Logo Range'), ('FLOATER_FREQ', 'Floater/Touch'),
        ('POST_FREQ', 'Post-Up'), ('SPOTUP_FREQ', 'Spot-Up'),
        ('ISOLATION_FREQ', 'Isolation'), ('RIM_PROT_FREQ', 'Rim Protection')
    ]

    for key, label in dna_metrics:
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(60, 8, label + ":", border=0)
        pdf.set_font("Arial", '', 11)
        pdf.cell(40, 8, f"{p_data[key]:.1%}", ln=True)

    return bytes(pdf.output())
