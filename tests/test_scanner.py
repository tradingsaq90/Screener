import os
import sys
import unittest
import pandas as pd
import numpy as np
import pandas_ta as ta

# Add the parent directory to the system path to allow importing scanner
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scanner

class TestStockScreener(unittest.TestCase):
    
    def setUp(self):
        # Generate 35 days of dummy historical data
        self.dates = pd.date_range(start="2026-05-01", periods=35, freq="D")
        
    def generate_mock_data(self, price_series, volume_series):
        """Helper to create a standard OHLCV DataFrame."""
        df = pd.DataFrame({
            "Open": price_series,
            "High": [p * 1.01 for p in price_series],
            "Low": [p * 0.99 for p in price_series],
            "Close": price_series,
            "Volume": volume_series
        }, index=self.dates)
        return df

    def test_fetch_sp500_tickers(self):
        """Verify that Wikipedia S&P 500 scraping returns valid ticker list."""
        tickers = scanner.fetch_sp500_tickers()
        self.assertIsInstance(tickers, list)
        self.assertGreater(len(tickers), 0)
        # Ensure there are no dots in symbols (replaced with hyphens)
        self.assertTrue(all("." not in t for t in tickers))

    def test_stock_fails_insufficient_data(self):
        """Verify stocks with less than 20 rows are skipped (insufficient data for SMA20)."""
        df = pd.DataFrame({
            "Open": [50.0] * 10,
            "High": [51.0] * 10,
            "Low": [49.0] * 10,
            "Close": [50.0] * 10,
            "Volume": [1000000] * 10
        }, index=self.dates[:10])
        
        result_item, _ = scanner.process_single_stock("XYZ", df, 30.0, 55.0, 65.0, 5000000.0, True)
        self.assertIsNone(result_item)

    def test_stock_filter_passed(self):
        """Verify that a stock meeting all criteria successfully passes the filters."""
        # Create an oscillating price series with a slight upward slope
        # This keeps Close > SMA(20), Price > 30, upward momentum (Close > Prev Close),
        # and moderate RSI (around 55.6).
        prices = [50.0 + (i % 3 - 1) * 2.0 + i * 0.12 for i in range(35)]
        volumes = [6000000] * 35 # Exceeds 5M volume limit
        
        df = self.generate_mock_data(prices, volumes)
        
        # Verify RSI(14) calculated value falls inside our target window [55, 65)
        # to ensure the test itself is valid.
        calculated_rsi = ta.rsi(pd.Series(prices), length=14)
        latest_rsi = calculated_rsi.iloc[-1]
        
        # Assert that the dummy data generates an RSI in our desired range
        self.assertTrue(55.0 <= latest_rsi < 65.0, f"Setup error: mock data RSI is {latest_rsi:.2f}, not in [55, 65)")
        
        result_item, processed_df = scanner.process_single_stock(
            ticker="MOCK-PASS",
            ticker_data=df,
            min_price=30.0,
            rsi_min=55.0,
            rsi_max=65.0,
            volume_min=5000000.0,
            use_avg_volume=True
        )
        
        self.assertIsNotNone(result_item)
        self.assertEqual(result_item["Ticker"], "MOCK-PASS")
        self.assertGreater(result_item["Price"], 30.0)
        self.assertTrue(result_item["Price"] > result_item["SMA(20)"])
        self.assertTrue(55.0 <= result_item["RSI(14)"] < 65.0)
        self.assertGreaterEqual(result_item["10d Avg Volume"], 5000000.0)
        self.assertGreater(result_item["Daily Change %"], 0.0)

    def test_stock_filter_failed_price_below_min(self):
        """Verify that a stock with Close price below the minimum threshold fails."""
        # Clean moderate uptrend but below $30 (e.g. starting at 20)
        prices = [20.0 + i * 0.2 for i in range(35)] # Final price = 26.8 (< 30)
        volumes = [6000000] * 35
        df = self.generate_mock_data(prices, volumes)
        
        result_item, _ = scanner.process_single_stock(
            ticker="MOCK-LOWPRICE",
            ticker_data=df,
            min_price=30.0,
            rsi_min=55.0,
            rsi_max=65.0,
            volume_min=5000000.0,
            use_avg_volume=True
        )
        self.assertIsNone(result_item)

    def test_stock_filter_failed_negative_momentum(self):
        """Verify that a stock that closed down on the last day fails (negative momentum)."""
        # Moderate uptrend but last day close drops
        prices = [40.0 + i * 0.4 for i in range(34)]
        prices.append(prices[-1] - 1.0) # Drop last day's price by 1.0
        volumes = [6000000] * 35
        df = self.generate_mock_data(prices, volumes)
        
        result_item, _ = scanner.process_single_stock(
            ticker="MOCK-NEGMOMENTUM",
            ticker_data=df,
            min_price=30.0,
            rsi_min=55.0,
            rsi_max=65.0,
            volume_min=5000000.0,
            use_avg_volume=True
        )
        self.assertIsNone(result_item)

    def test_stock_filter_failed_volume_insufficient(self):
        """Verify that a stock with volume below the threshold fails."""
        prices = [40.0 + i * 0.4 for i in range(35)]
        volumes = [4000000] * 35 # 4M < 5M limit
        df = self.generate_mock_data(prices, volumes)
        
        result_item, _ = scanner.process_single_stock(
            ticker="MOCK-LOWVOL",
            ticker_data=df,
            min_price=30.0,
            rsi_min=55.0,
            rsi_max=65.0,
            volume_min=5000000.0,
            use_avg_volume=True
        )
        self.assertIsNone(result_item)

    def test_stock_filter_failed_rsi_out_of_bounds(self):
        """Verify that a stock with RSI outside [55, 65) fails."""
        # Strong uptrend price series -> RSI becomes overbought (>70)
        prices = [40.0 + i * 2.0 for i in range(35)] # Final price = 108.0
        volumes = [6000000] * 35
        df = self.generate_mock_data(prices, volumes)
        
        result_item, _ = scanner.process_single_stock(
            ticker="MOCK-HIGHRSI",
            ticker_data=df,
            min_price=30.0,
            rsi_min=55.0,
            rsi_max=65.0,
            volume_min=5000000.0,
            use_avg_volume=True
        )
        self.assertIsNone(result_item)

if __name__ == "__main__":
    unittest.main()
