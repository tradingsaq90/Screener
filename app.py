import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import scanner
import requests
import traceback
import os
import io

# 1. Page Config
st.set_page_config(
    page_title="AG-US Stock Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Premium Custom CSS Inject
st.markdown("""
    <style>
        /* Main background & fonts */
        .main {
            background-color: #0A0D14;
            color: #E6EDF3;
        }
        
        /* Metric cards styling */
        div[data-testid="stMetric"] {
            background-color: #121824;
            border: 1px solid #1E293B;
            border-radius: 12px;
            padding: 15px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            transition: all 0.3s ease;
        }
        div[data-testid="stMetric"]:hover {
            border-color: #00F2FE;
            box-shadow: 0 4px 20px rgba(0, 242, 254, 0.15);
            transform: translateY(-2px);
        }
        
        /* Glowing main header */
        .glowing-header {
            font-size: 2.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, #00F2FE 0%, #4FACFE 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        
        /* Subheaders */
        .section-header {
            font-size: 1.5rem;
            font-weight: 600;
            color: #E6EDF3;
            border-bottom: 2px solid #1E293B;
            padding-bottom: 5px;
            margin-top: 1.5rem;
            margin-bottom: 1rem;
        }
        
        /* Custom card */
        .custom-card {
            background-color: #121824;
            border: 1px solid #1E293B;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 1.5rem;
        }
        
        /* Sidebar styling */
        section[data-testid="stSidebar"] {
            background-color: #0E131F;
            border-right: 1px solid #1E293B;
        }
        
        /* Custom buttons styling */
        div.stButton > button {
            background: linear-gradient(135deg, #00F2FE 0%, #4FACFE 100%);
            color: #0A0D14;
            font-weight: 700;
            border: none;
            border-radius: 8px;
            padding: 10px 24px;
            width: 100%;
            transition: all 0.3s ease;
        }
        div.stButton > button:hover {
            box-shadow: 0 0 15px rgba(0, 242, 254, 0.6);
            transform: scale(1.02);
            color: #0A0D14;
        }
        
        /* Table enhancements */
        .dataframe {
            background-color: #121824 !important;
            border: 1px solid #1E293B !important;
        }
    </style>
""", unsafe_allow_html=True)

# 3. Cache Nasdaq 100 Tickers
@st.cache_data(ttl=86400)
def fetch_nasdaq100_tickers():
    """Scrapes Nasdaq 100 tickers from Wikipedia as a secondary option."""
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        # Usually index 4 contains the component table on the page
        for t in tables:
            if 'Ticker' in t.columns or 'Symbol' in t.columns:
                col = 'Ticker' if 'Ticker' in t.columns else 'Symbol'
                company_col = 'Company' if 'Company' in t.columns else ('Security' if 'Security' in t.columns else None)
                tickers = []
                for _, row in t.iterrows():
                    sym = str(row[col]).replace('.', '-')
                    tickers.append(sym)
                    if company_col:
                        scanner.TICKER_COMPANY_MAP[sym] = row[company_col]
                return tickers
        # Fallback if table parsed incorrectly
        return ["AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST", "PEP", "ADBE"]
    except Exception as e:
        print(f"Error scraping Nasdaq 100: {e}")
        return ["AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST"]

# Initialize Session State
if 'scan_run' not in st.session_state:
    st.session_state.scan_run = False
if 'passed_df' not in st.session_state:
    st.session_state.passed_df = pd.DataFrame()
if 'passed_dfs' not in st.session_state:
    st.session_state.passed_dfs = {}
if 'failed_tickers' not in st.session_state:
    st.session_state.failed_tickers = []
if 'last_universe' not in st.session_state:
    st.session_state.last_universe = ""
if 'scanned_timeframe' not in st.session_state:
    st.session_state.scanned_timeframe = "Daily"

# --- MAIN APP LAYOUT ---

st.markdown('<div class="glowing-header">🤖 AG-US Stock Scanner</div>', unsafe_allow_html=True)
st.markdown("<p style='color: #8A99AD; margin-top: -10px;'>Sophisticated algorithmic filtering for US base equities.</p>", unsafe_allow_html=True)

# --- SIDEBAR: SCAN SETTINGS & PRESETS ---
st.sidebar.markdown("### ⚙️ Scan Parameters")

timeframe = st.sidebar.selectbox(
    "Scan Timeframe",
    options=["Daily", "Weekly", "Monthly"],
    index=0,
    help="Select the bar resolution for price and technical indicators."
)

# Discrepancy Solution: Default to 30.0 but easily slider-adjustable to 100.0 or more
min_price = st.sidebar.slider(
    "Minimum Share Price ($)",
    min_value=1.0,
    max_value=300.0,
    value=30.0,
    step=5.0,
    help="Default is $30 as per text requirements, but can be set to $100 as in the reference screenshot."
)

rsi_min = st.sidebar.slider(
    "RSI(14) Range - Lower Bound (Inclusive)",
    min_value=0.0,
    max_value=100.0,
    value=55.0,
    step=1.0
)

rsi_max = st.sidebar.slider(
    "RSI(14) Range - Upper Bound (Exclusive)",
    min_value=0.0,
    max_value=100.0,
    value=65.0,
    step=1.0
)

vol_mode = st.sidebar.selectbox(
    "Volume Filter Mode",
    options=["10-Day Average Volume", "Current Day's Volume"],
    index=0
)

volume_threshold = st.sidebar.number_input(
    "Significant Volume Threshold (Shares)",
    min_value=100000,
    max_value=50000000,
    value=5000000,
    step=500000,
    format="%d"
)

# Universe selection
universe_option = st.sidebar.selectbox(
    "Scan Universe",
    options=["S&P 500 (Auto-Fetched)", "Nasdaq 100 (Auto-Fetched)", "Custom List (Comma-Separated)", "CSV Upload"],
    index=0
)

tickers_to_scan = []

if universe_option == "S&P 500 (Auto-Fetched)":
    st.sidebar.info("Automatically downloads S&P 500 list from Wikipedia (~503 stocks).")
    if st.sidebar.button("Fetch & Scan S&P 500"):
        tickers_to_scan = scanner.fetch_sp500_tickers()
        st.session_state.last_universe = "S&P 500"
elif universe_option == "Nasdaq 100 (Auto-Fetched)":
    st.sidebar.info("Automatically downloads Nasdaq 100 list from Wikipedia (~101 stocks).")
    if st.sidebar.button("Fetch & Scan Nasdaq 100"):
        tickers_to_scan = fetch_nasdaq100_tickers()
        st.session_state.last_universe = "Nasdaq 100"
elif universe_option == "Custom List (Comma-Separated)":
    custom_input = st.sidebar.text_area("Enter Tickers", "AAPL, MSFT, TSLA, GOOGL, NVDA, AMZN", help="Separate by commas.")
    if st.sidebar.button("Scan Custom List"):
        tickers_to_scan = [t.strip().upper().replace('.', '-') for t in custom_input.split(",") if t.strip()]
        st.session_state.last_universe = "Custom Tickers"
elif universe_option == "CSV Upload":
    uploaded_file = st.sidebar.file_uploader("Upload CSV", type=["csv"], help="Must contain a column named 'Symbol' or 'Ticker'.")
    if uploaded_file is not None:
        try:
            df_uploaded = pd.read_csv(uploaded_file)
            col_name = None
            for c in df_uploaded.columns:
                if c.lower() in ['symbol', 'ticker', 'symbol/ticker', 'code']:
                    col_name = c
                    break
            if col_name:
                tickers_uploaded = df_uploaded[col_name].dropna().astype(str).tolist()
                tickers_to_scan = [t.strip().upper().replace('.', '-') for t in tickers_uploaded if t.strip()]
                st.sidebar.success(f"Loaded {len(tickers_to_scan)} tickers successfully!")
            else:
                st.sidebar.error("Could not find a Ticker or Symbol column in the CSV.")
        except Exception as e:
            st.sidebar.error(f"Error loading CSV: {e}")
            
    if len(tickers_to_scan) > 0 and st.sidebar.button("Scan Uploaded Tickers"):
        st.session_state.last_universe = "Uploaded CSV Tickers"

# --- RUNNING THE SCAN ---
if len(tickers_to_scan) > 0:
    st.session_state.scan_run = False  # Reset
    
    # Progress Display
    progress_bar = st.progress(0.0)
    status_text = st.empty()
    
    def update_progress(pct, text):
        progress_bar.progress(pct)
        status_text.text(text)
        
    try:
        passed_df, passed_dfs, failed_tickers = scanner.scan_stocks(
            tickers=tickers_to_scan,
            min_price=min_price,
            rsi_min=rsi_min,
            rsi_max=rsi_max,
            volume_min=volume_threshold,
            use_avg_volume=(vol_mode == "10-Day Average Volume"),
            timeframe=timeframe,
            progress_callback=update_progress
        )
        
        # Save to state
        st.session_state.passed_df = passed_df
        st.session_state.passed_dfs = passed_dfs
        st.session_state.failed_tickers = failed_tickers
        st.session_state.scanned_timeframe = timeframe
        st.session_state.scan_run = True
        
        # Clear progress indicators
        progress_bar.empty()
        status_text.empty()
        st.success("Scan completed successfully!")
        
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"An error occurred during scan execution: {e}")
        st.code(traceback.format_exc())

# --- DISPLAYING RESULTS ---
if st.session_state.scan_run:
    passed_df = st.session_state.passed_df
    passed_dfs = st.session_state.passed_dfs
    
    # Top Level Metrics
    total_scanned = len(passed_dfs) + len(st.session_state.failed_tickers)
    total_passed = len(passed_df)
    hit_rate = (total_passed / total_scanned * 100) if total_scanned > 0 else 0.0
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Universe / Total Scanned", f"{st.session_state.last_universe} / {total_scanned} Stocks")
    col2.metric("Stocks Passed Filters", f"{total_passed} Stocks")
    col3.metric("Hit Rate", f"{hit_rate:.2f}%")
    
    st.markdown('<div class="section-header">🔍 Filter Screening Results</div>', unsafe_allow_html=True)
    
    if passed_df.empty:
        st.info("No stocks matched all criteria based on the latest daily prices. Try modifying parameters in the sidebar.")
    else:
        # Show table of results
        col_desc, col_dl_csv, col_dl_pdf = st.columns([2, 1, 1])
        with col_desc:
            st.markdown(f"The following **{total_passed}** stocks passed all filtering conditions:")
        with col_dl_csv:
            csv_data = passed_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV",
                data=csv_data,
                file_name="screener_results.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col_dl_pdf:
            try:
                temp_pdf_path = "temp_report.pdf"
                params = {
                    "Universe": st.session_state.last_universe,
                    "Timeframe": st.session_state.scanned_timeframe,
                    "RSI_Min": rsi_min,
                    "RSI_Max": rsi_max,
                    "Vol_Threshold": volume_threshold,
                    "Vol_Mode": vol_mode,
                    "Min_Price": min_price,
                    "Scanned_Count": total_scanned
                }
                import report_generator
                report_generator.generate_pdf_report(passed_df, params, temp_pdf_path)
                with open(temp_pdf_path, "rb") as f:
                    pdf_data = f.read()
                if os.path.exists(temp_pdf_path):
                    os.remove(temp_pdf_path)
                
                st.download_button(
                    label="📄 Download PDF Report",
                    data=pdf_data,
                    file_name=f"screener_report_{st.session_state.scanned_timeframe.lower()}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            except Exception as e:
                st.error("Error generating PDF Report")
                print(f"PDF generation error: {e}")
        
        # Setup styled display of DataFrame
        styled_df = passed_df.copy()
        
        # Render clean interactive table
        st.dataframe(
            styled_df.style.format({
                'Price': '${:.2f}',
                'Daily Change %': '{:+.2f}%',
                'RSI(14)': '{:.2f}',
                'SMA(20)': '${:.2f}',
                'Volume': '{:,.0f}',
                '10d Avg Volume': '{:,.0f}'
            }),
            use_container_width=True,
            column_config={
                "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                "Company": st.column_config.TextColumn("Company Name", width="medium"),
                "Price": st.column_config.NumberColumn("Price", format="$%.2f"),
                "Daily Change %": st.column_config.NumberColumn("Daily Change", format="%+.2f%%"),
                "RSI(14)": st.column_config.NumberColumn("RSI (14)", format="%.2f"),
                "SMA(20)": st.column_config.NumberColumn("20-Day SMA", format="$%.2f"),
                "Volume": st.column_config.NumberColumn("Current Volume", format="%d"),
                "10d Avg Volume": st.column_config.NumberColumn("10-Day Avg Volume", format="%d"),
            }
        )
        
        # --- DETAILS & CHARTING ---
        st.markdown('<div class="section-header">📊 Interactive Stock Analysis Chart</div>', unsafe_allow_html=True)
        
        # Setup columns for ticker selector and indicators toggle
        chart_col1, chart_col2 = st.columns([3, 1])
        with chart_col1:
            selected_ticker = st.selectbox("Select a stock to inspect details & charts:", options=passed_df['Ticker'].tolist())
        with chart_col2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True) # Spacer to align with selectbox
            show_bb = st.checkbox("Show Bollinger Bands (20, 2)", value=False)
        
        if selected_ticker and selected_ticker in passed_dfs:
            df_selected = passed_dfs[selected_ticker]
            
            # Print quick stats cards for selected stock
            ticker_row = passed_df[passed_df['Ticker'] == selected_ticker].iloc[0]
            
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Current Price", f"${ticker_row['Price']:.2f}", f"{ticker_row['Daily Change %']:+.2f}%")
            sc2.metric(f"RSI (14) - {st.session_state.scanned_timeframe}", f"{ticker_row['RSI(14)']:.2f}", help="Target range is 55 to 65")
            sc3.metric(f"20-Period SMA - {st.session_state.scanned_timeframe}", f"${ticker_row['SMA(20)']:.2f}", f"{(ticker_row['Price'] - ticker_row['SMA(20)']):+.2f} above SMA")
            sc4.metric(f"Volume (10-Period Avg) - {st.session_state.scanned_timeframe}", f"{ticker_row['10d Avg Volume']:,.0f}", help=f"Current: {ticker_row['Volume']:,.0f}")
            
            # Create Plotly subplots (Row 1: Price + SMA, Row 2: Volume, Row 3: RSI)
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.06, 
                row_heights=[0.55, 0.18, 0.27],
                subplot_titles=(
                    f"{selected_ticker} Price & SMA(20) ({st.session_state.scanned_timeframe})", 
                    f"Volume ({st.session_state.scanned_timeframe})", 
                    f"RSI(14) Oscillator ({st.session_state.scanned_timeframe})"
                )
            )
            
            # Bollinger Bands (rendered below price candles for neatness)
            if show_bb and 'BB_Upper' in df_selected.columns and 'BB_Lower' in df_selected.columns:
                # Add Upper Band trace first
                fig.add_trace(
                    go.Scatter(
                        x=df_selected.index,
                        y=df_selected['BB_Upper'],
                        line=dict(color='rgba(0, 242, 254, 0.3)', width=1, dash='dash'),
                        name="BB Upper (2.0 std)"
                    ),
                    row=1, col=1
                )
                # Add Lower Band trace second, filling the region up to BB_Upper
                fig.add_trace(
                    go.Scatter(
                        x=df_selected.index,
                        y=df_selected['BB_Lower'],
                        line=dict(color='rgba(0, 242, 254, 0.3)', width=1, dash='dash'),
                        fill='tonexty',
                        fillcolor='rgba(0, 242, 254, 0.03)',
                        name="BB Lower (2.0 std)"
                    ),
                    row=1, col=1
                )

            # Candlestick chart
            fig.add_trace(
                go.Candlestick(
                    x=df_selected.index,
                    open=df_selected['Open'],
                    high=df_selected['High'],
                    low=df_selected['Low'],
                    close=df_selected['Close'],
                    name="Price"
                ),
                row=1, col=1
            )
            
            # SMA(20) line
            fig.add_trace(
                go.Scatter(
                    x=df_selected.index,
                    y=df_selected['SMA_20'],
                    line=dict(color='#00F2FE', width=2),
                    name="SMA(20) / BB Mid"
                ),
                row=1, col=1
            )
            
            # Volume bar chart (Row 2)
            vol_colors = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(df_selected['Close'], df_selected['Open'])]
            fig.add_trace(
                go.Bar(
                    x=df_selected.index,
                    y=df_selected['Volume'],
                    marker_color=vol_colors,
                    name="Volume"
                ),
                row=2, col=1
            )
            
            # RSI line (Row 3)
            fig.add_trace(
                go.Scatter(
                    x=df_selected.index,
                    y=df_selected['RSI_14'],
                    line=dict(color='#FFA500', width=2),
                    name="RSI(14)"
                ),
                row=3, col=1
            )
            
            # Highlight RSI target bounds 55 - 65
            fig.add_hrect(
                y0=55.0, y1=65.0, 
                fillcolor="rgba(0, 255, 0, 0.1)", 
                line_width=0, 
                annotation_text="Target Range [55, 65)",
                annotation_position="top left",
                annotation_font=dict(color="rgba(0, 255, 0, 0.6)", size=10),
                row=3, col=1
            )
            
            # Reference lines for RSI (30 oversold, 70 overbought)
            fig.add_hline(y=70, line_dash="dash", line_color="red", line_width=1, row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", line_width=1, row=3, col=1)
            fig.update_yaxes(range=[10, 90], row=3, col=1)
            
            # Layout updates
            fig.update_layout(
                height=750,
                template="plotly_dark",
                plot_bgcolor="#0E131F",
                paper_bgcolor="#0A0D14",
                xaxis_rangeslider_visible=False,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                margin=dict(t=50, b=50, l=50, r=50)
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
else:
    # Landing page instructions / explanation of filters
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown("### 📋 Screener Filtering Conditions Explained")
    st.markdown("""
    This scanner is set up with precise algorithmic conditions to select high-momentum, stable US equities:
    
    1. **Price > SMA(20)**: The closing price must be strictly above its 20-day Simple Moving Average (confirming a medium-term uptrend).
    2. **RSI(14) in [55, 65)**: The 14-day Relative Strength Index must be between 55 (inclusive) and 65 (exclusive). This targets stocks entering strong momentum zones but not yet overbought (>70).
    3. **Volume > 5,000,000**: Supports filtering by average 10-day volume or current volume to ensure highly liquid names and avoid micro-caps.
    4. **Price > $30 (Configurable)**: Restricts results to solid mid-to-large-cap stock prices.
    5. **Upward Momentum (Close > Prev Close)**: Confirms the stock is currently active and closed higher on the scanning day.
    
    **To get started, select your Universe (e.g. S&P 500) and click the scan button in the sidebar!**
    """)
    st.markdown('</div>', unsafe_allow_html=True)
