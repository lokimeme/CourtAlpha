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
    pdf.set_font("Arial", size=12)
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Player Profile: {p_data['PLAYER_NAME']}", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.ln(5)
    
    pdf.cell(50, 10, "Team:", border=1)
    pdf.cell(100, 10, str(p_data['TEAM']), border=1, ln=True)
    pdf.cell(50, 10, "Strategic Outlook:", border=1)
    pdf.cell(100, 10, str(p_data['STRATEGIC_OUTLOOK']), border=1, ln=True)
    pdf.cell(50, 10, "Archetype:", border=1)
    pdf.cell(100, 10, str(p_data['ARCHETYPE_NAME']), border=1, ln=True)
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Economic Valuation", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(50, 10, "Meta-Impact:", border=0)
    pdf.cell(50, 10, f"{p_data['META_IMPACT']:.2f} Pts/100", ln=True)
    pdf.cell(50, 10, "Market Value:", border=0)
    pdf.cell(50, 10, f"${p_data['MARKET_VALUE']:,.0f}", ln=True)
    pdf.cell(50, 10, "Contract Cost:", border=0)
    pdf.cell(50, 10, f"${p_data['CONTRACT_COST']:,.0f}", ln=True)
    pdf.cell(50, 10, "Surplus Value:", border=0)
    pdf.cell(50, 10, f"${p_data['SURPLUS_VALUE']:,.0f}", ln=True)
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Skill DNA (Frequencies)", ln=True)
    pdf.set_font("Arial", size=12)
    dna_metrics = ['LOGO_FREQ', 'FLOATER_FREQ', 'POST_FREQ', 'SPOTUP_FREQ', 'ISOLATION_FREQ', 'RIM_PROT_FREQ']
    for m in dna_metrics:
        pdf.cell(50, 10, f"{m.replace('_', ' ')}:", border=0)
        pdf.cell(50, 10, f"{p_data[m]:.1%}", ln=True)
    
    return bytes(pdf.output())
