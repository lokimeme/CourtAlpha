import pandas as pd
import numpy as np

class CBAEngine:
    
    def __init__(self, season="2025-26"):
        self.season = season
        self.SALARY_CAP = 155000000
        self.LUXURY_TAX_LEVEL = 188328000
        self.FIRST_APRON = 195000000
        self.SECOND_APRON = 208000000
        
    def calculate_tax_bill(self, total_salary):
        
        if total_salary <= self.LUXURY_TAX_LEVEL:
            return 0
        
        excess = total_salary - self.LUXURY_TAX_LEVEL
        tax = 0
        
        brackets = [
            (5000000, 1.50),
            (5000000, 1.75),
            (5000000, 2.50),
            (5000000, 3.25),
            (float('inf'), 3.75)
        ]
        
        remaining = excess
        for limit, rate in brackets:
            taxable = min(remaining, limit)
            tax += taxable * rate
            remaining -= taxable
            if remaining <= 0:
                break
        return tax

    def check_trade_legality(self, outgoing_salaries, incoming_salaries, team_total_salary):
        
        status = {"legal": True, "notes": [], "hard_cap_triggered": False}
        
        outgoing_total = sum(outgoing_salaries)
        incoming_total = sum(incoming_salaries)
        
        if team_total_salary > self.SECOND_APRON:
            status["notes"].append("Team is over the Second Apron.")
            if len(outgoing_salaries) > 1:
                status["legal"] = False
                status["notes"].append("BLOCK: Second Apron teams cannot aggregate salaries in trades.")
            if incoming_total > outgoing_total:
                status["legal"] = False
                status["notes"].append(f"BLOCK: Second Apron teams cannot acquire more than 100% of outgoing salary (${outgoing_total:,.0f}).")
        
        elif team_total_salary > self.FIRST_APRON:
            status["notes"].append("Team is over the First Apron.")
            if incoming_total > outgoing_total:
                status["legal"] = False
                status["notes"].append(f"BLOCK: First Apron teams cannot acquire more than 100% of outgoing salary.")
        
        else:
            if outgoing_total <= 6525000:
                max_incoming = outgoing_total * 2.0 + 100000
            elif outgoing_total <= 19600000:
                max_incoming = outgoing_total + 5000000
            else:
                max_incoming = outgoing_total * 1.25 + 100000
                
            if incoming_total > max_incoming:
                status["legal"] = False
                status["notes"].append(f"BLOCK: Incoming salary (${incoming_total:,.0f}) exceeds matching limit (${max_incoming:,.0f}).")

        return status

    def get_apron_exposure(self, team_salary, projection_years=3):
        
        projections = []
        current_salary = team_salary
        for i in range(1, projection_years + 1):
            year_cap = self.SALARY_CAP * (1.10 ** i)
            year_first = self.FIRST_APRON * (1.10 ** i)
            year_second = self.SECOND_APRON * (1.10 ** i)
            
            est_salary = current_salary * (1.08 ** i)
            
            state = "Healthy"
            if est_salary > year_second: state = "Second Apron Danger"
            elif est_salary > year_first: state = "First Apron Danger"
            
            projections.append({
                "year": f"{2025+i}-{26+i}",
                "est_salary": est_salary,
                "first_apron": year_first,
                "second_apron": year_second,
                "status": state
            })
        return projections

    def explain_repeater_tax(self, team_history):
        
        if sum(team_history) >= 3:
            return "Repeater status active. Tax rates increased by $1.00 per bracket."
        return "Non-repeater status."

if __name__ == "__main__":
    cba = CBAEngine()
    print(f"Tax for $200M salary: ${cba.calculate_tax_bill(200000000):,.0f}")
    trade = cba.check_trade_legality([20000000], [26000000], 170000000)
    print(f"Trade legality: {trade}")