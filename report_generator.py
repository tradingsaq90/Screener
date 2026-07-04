import os
from fpdf import FPDF
import datetime
import pandas as pd

class StockScreenerPDF(FPDF):
    def __init__(self, parameters=None):
        super().__init__()
        self.parameters = parameters or {}
        
    def header(self):
        # Draw a premium header banner
        self.set_fill_color(18, 24, 36) # dark navy/blue
        self.rect(0, 0, 210, 38, 'F')
        
        # Glow cyan title
        self.set_text_color(0, 242, 254) # Cyan glow
        self.set_font("helvetica", "B", 18)
        self.cell(0, 15, "AG-US STOCK SCREENER RESULTS", align="C", new_x="LMARGIN", new_y="NEXT")
        
        # Sub-header meta info
        self.set_text_color(160, 174, 192) # light slate grey
        self.set_font("helvetica", "I", 10)
        time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cell(0, 5, f"Scan Execution Report | Generated: {time_str}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(12)

    def footer(self):
        # Bottom page numbering
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

def generate_pdf_report(passed_df, parameters, filepath):
    """
    Generates a structured PDF report from screener parameters and passed stocks.
    """
    pdf = StockScreenerPDF(parameters)
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # 1. PARAMETERS & SCAN DETAILS (GRID)
    pdf.set_fill_color(248, 250, 252) # Slate-50 background for metrics block
    pdf.rect(10, 42, 190, 42, 'DF')
    
    pdf.set_font("helvetica", "B", 10)
    pdf.set_text_color(18, 24, 36)
    
    # Left column of stats grid
    pdf.set_xy(15, 45)
    pdf.cell(90, 6, f"Universe Scanned: {parameters.get('Universe', 'N/A')}")
    pdf.cell(90, 6, f"Timeframe: {parameters.get('Timeframe', 'N/A')}", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(15)
    pdf.cell(90, 6, f"Price Condition: Price > SMA(20)")
    pdf.cell(90, 6, f"RSI Bound: {parameters.get('RSI_Min', 55)} to {parameters.get('RSI_Max', 65)} [Target Range)", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(15)
    vol_mode_str = "10d Avg" if parameters.get('Vol_Mode', '').startswith('10-Day') else "Current"
    pdf.cell(90, 6, f"Volume Condition: {vol_mode_str} > {parameters.get('Vol_Threshold', 5000000):,}")
    pdf.cell(90, 6, f"Min Price: > ${parameters.get('Min_Price', 30.0):.2f}", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(15)
    pdf.cell(90, 6, f"Momentum: Positive (Close > Prev Close)")
    pdf.cell(90, 6, f"Scanned Count: {parameters.get('Scanned_Count', 0)} stocks", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(15)
    
    # 2. MATCHED STOCKS HEADER
    pdf.set_font("helvetica", "B", 13)
    pdf.set_text_color(18, 24, 36)
    pdf.cell(0, 10, f"Passed Stocks ({len(passed_df)} matched)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    
    # Check if empty
    if passed_df.empty:
        pdf.set_font("helvetica", "I", 11)
        pdf.set_text_color(100, 110, 120)
        pdf.cell(0, 15, "No stocks matched the screening criteria during this scan run.", align="C", new_x="LMARGIN", new_y="NEXT")
    else:
        # 3. RESULTS TABLE
        # Widths: Ticker=15, Company=45, Price=20, Change=25, RSI=20, SMA=20, Vol=22, AvgVol=23 -> Total = 190
        col_widths = [15, 45, 20, 25, 20, 20, 22, 23]
        headers = ["Ticker", "Company Name", "Price ($)", "Change (%)", "RSI (14)", "SMA (20) ($)", "Volume", "10d Avg Vol"]
        
        # Header Row
        pdf.set_fill_color(18, 24, 36) # Dark header
        pdf.set_text_color(255, 255, 255) # White text
        pdf.set_font("helvetica", "B", 9)
        
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 8, h, border=1, align="C", fill=True)
        pdf.ln()
        
        # Alternating rows
        pdf.set_text_color(51, 65, 85) # dark grey/blue text
        pdf.set_font("helvetica", "", 9)
        
        alt_row = False
        for _, row in passed_df.iterrows():
            if alt_row:
                pdf.set_fill_color(241, 245, 249) # light grey highlight
            else:
                pdf.set_fill_color(255, 255, 255) # white
            
            # Formatted string extractions
            ticker = str(row['Ticker'])
            company = str(row.get('Company', ticker))[:22] # truncate to fit 45mm width
            price = f"{row['Price']:.2f}"
            change = f"{row['Daily Change %']:+.2f}%"
            rsi = f"{row['RSI(14)']:.2f}"
            sma = f"{row['SMA(20)']:.2f}"
            volume = f"{row['Volume']:,.0f}"
            avg_vol = f"{row['10d Avg Volume']:,.0f}"
            
            # Print row cells
            pdf.cell(15, 8, ticker, border=1, align="C", fill=True)
            pdf.cell(45, 8, company, border=1, align="L", fill=True)
            pdf.cell(20, 8, price, border=1, align="R", fill=True)
            
            # Color coding for Daily Change in PDF
            if row['Daily Change %'] >= 0:
                pdf.set_text_color(22, 101, 52) # Dark green
            else:
                pdf.set_text_color(153, 27, 27) # Dark red
            pdf.cell(25, 8, change, border=1, align="R", fill=True)
            
            pdf.set_text_color(51, 65, 85) # restore normal text color
            pdf.cell(20, 8, rsi, border=1, align="R", fill=True)
            pdf.cell(20, 8, sma, border=1, align="R", fill=True)
            pdf.cell(22, 8, volume, border=1, align="R", fill=True)
            pdf.cell(23, 8, avg_vol, border=1, align="R", fill=True)
            pdf.ln()
            
            alt_row = not alt_row
            
    # Output to disk
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    pdf.output(filepath)
