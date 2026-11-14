import os
import pandas as pd
import talib
import numpy as np
import time
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from ai_trading_crew.config import settings
from ai_trading_crew.utils.twelve_data_manager import twelve_data_manager
from ai_trading_crew.models import IndicatorPoint, IndicatorSnapshot, PriceBar

from dotenv import load_dotenv


# Load environment variables
load_dotenv()

class TwelveTI:
    def __init__(self, symbol: str, interval: str) -> None:
        self.symbol = symbol
        self.interval = interval
        self._data = None
        self._quote_data = None
        
        # Map interval from Twelve Data format to yfinance format
        self.yf_interval_map = {
            "1min": "1m",
            "5min": "5m",
            "15min": "15m",
            "30min": "30m",
            "45min": "45m",
            "1h": "1h",
            "2h": "2h",
            "4h": "4h",
            "1day": "1d",
            "1week": "1wk",
            "1month": "1mo"
        }
        
    def _get_data(self, period="4mo"):
        # Use the centralized data manager
        self._data = twelve_data_manager.get_time_series_data(self.symbol, self.interval, period)
        
        # Ensure consistent column naming to handle any data source variations
        column_mapping = {
            'open': 'Open',
            'high': 'High', 
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }
        
        # Only rename columns that exist and need renaming
        for old_name, new_name in column_mapping.items():
            if old_name in self._data.columns and new_name not in self._data.columns:
                self._data = self._data.rename(columns={old_name: new_name})
        
        return self._data
    


    def _get_latest_date(self):
        data = self._get_data()
        last_date = data.index[-1]
        return last_date.strftime('%Y-%m-%d')
    
    def _get_column_data(self, data, column_name):
        """Safely get column data with proper error handling"""
        if column_name not in data.columns:
            available_columns = list(data.columns)
            raise KeyError(f"Column '{column_name}' not found in data. Available columns: {available_columns}. "
                          f"Symbol: {self.symbol}, Interval: {self.interval}")
        return data[column_name].astype(float).to_numpy().flatten()

    def fetch_adx(self, time_period: int = 14):
        data = self._get_data()
        tp = time_period if time_period is not None else 14

        high = self._get_column_data(data, 'High')
        low = self._get_column_data(data, 'Low')
        close = self._get_column_data(data, 'Close')
        adx = talib.ADX(high, low, close, timeperiod=tp)
        latest = adx[-1]
        last_date = self._get_latest_date()
        return f"ADX with time_period of {tp} days has a latest value of {round(latest, 4)} on {last_date}."

    def fetch_bbands(self, time_period: int = 20):
        data = self._get_data()
        tp = time_period if time_period is not None else 20

        close = data['Close'].astype(float).to_numpy().flatten()
        upper, middle, lower = talib.BBANDS(close, timeperiod=tp, nbdevup=2.0, nbdevdn=2.0, matype=0)
        u, m, l = upper[-1], middle[-1], lower[-1]
        last_date = self._get_latest_date()
        return (f"BBANDS with time_period of {tp} days, sd of 2.0 and ma_type sma "
                f"has an upper_band value of {round(u, 4)}, middle_band value of {round(m, 4)}, "
                f"and lower_band value of {round(l, 4)} on {last_date}.")

    def fetch_ema(self, time_period: int = 9):
        data = self._get_data()
        tp = time_period if time_period is not None else 9

        close = data['Close'].astype(float).to_numpy().flatten()
        ema = talib.EMA(close, timeperiod=tp)
        value = ema[-1]
        last_date = self._get_latest_date()
        return f"EMA with time_period of {tp} days has a value of {round(value, 4)} on {last_date}."

    def fetch_macd(self, macd_fast_period: int = 12, macd_slow_period: int = 26):
        data = self._get_data()
        fp = macd_fast_period if macd_fast_period is not None else 12
        sp = macd_slow_period if macd_slow_period is not None else 26
        sig = 9

        close = data['Close'].astype(float).to_numpy().flatten()
        macd, macdsignal, macdhist = talib.MACD(close, fastperiod=fp, slowperiod=sp, signalperiod=sig)
        v, s, h = macd[-1], macdsignal[-1], macdhist[-1]
        last_date = self._get_latest_date()
        return (f"MACD with fast_period {fp}, slow_period {sp} and signal_period {sig} "
                f"has a macd value of {round(v, 4)}, macd_signal of {round(s, 4)} "
                f"and macd_hist of {round(h, 4)} on {last_date}.")

    def fetch_percent_b(self, time_period: int = 20):
        data = self._get_data()
        tp = time_period if time_period is not None else 20

        close_arr = data['Close'].astype(float).to_numpy().flatten()
        upper, middle, lower = talib.BBANDS(close_arr, timeperiod=tp, nbdevup=2.0, nbdevdn=2.0, matype=0)
        c = close_arr[-1]
        u, l = upper[-1], lower[-1]
        percent_b_value = (c - l) / (u - l)
        last_date = self._get_latest_date()
        return (f"PERCENT_B with time_period of {tp} days, sd of 2.0 and ma_type sma "
                f"has a value of {round(percent_b_value, 4)} on {last_date}.")

    def fetch_rsi(self, time_period: int = 14):
        data = self._get_data()
        tp = time_period if time_period is not None else 14

        close = data['Close'].astype(float).to_numpy().flatten()
        rsi = talib.RSI(close, timeperiod=tp)
        value = rsi[-1]
        last_date = self._get_latest_date()
        return f"RSI with time_period of {tp} days has a value of {round(value, 4)} on {last_date}."

    def fetch_sma(self, time_period: int = 20):
        data = self._get_data()
        tp = time_period if time_period is not None else 20

        close = data['Close'].astype(float).to_numpy().flatten()
        sma = talib.SMA(close, timeperiod=tp)
        value = sma[-1]
        last_date = self._get_latest_date()
        return f"SMA with time_period of {tp} days has a value of {round(value, 4)} on {last_date}."

    def fetch_stoch(self, fast_k_period: int = 14, slow_k_period: int = 3, slow_d_period: int = 3):
        data = self._get_data()
        fk = fast_k_period if fast_k_period is not None else 14
        sk = slow_k_period if slow_k_period is not None else 3
        sd = slow_d_period if slow_d_period is not None else 3

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        close = data['Close'].astype(float).to_numpy().flatten()
        slowk, slowd = talib.STOCH(high, low, close, fastk_period=fk, slowk_period=sk, slowk_matype=0, slowd_period=sd, slowd_matype=0)
        k_val, d_val = slowk[-1], slowd[-1]
        last_date = self._get_latest_date()
        return (f"STOCH with fast_k_period {fk}, slow_k_period {sk} and slow_d_period {sd} "
                f"has slow_k value of {round(k_val, 4)} and slow_d value of {round(d_val, 4)} on {last_date}.")

    def fetch_cci(self, time_period: int = 20):
        data = self._get_data()
        tp = time_period if time_period is not None else 20

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        close = data['Close'].astype(float).to_numpy().flatten()
        cci = talib.CCI(high, low, close, timeperiod=tp)
        value = cci[-1]
        last_date = self._get_latest_date()
        return f"CCI with time_period of {tp} days has a value of {round(value, 4)} on {last_date}."

    def fetch_sar(self):
        data = self._get_data()

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        sar = talib.SAR(high, low, acceleration=0.02, maximum=0.2)
        value = sar[-1]
        last_date = self._get_latest_date()
        return f"SAR has a value of {round(value, 4)} on {last_date}."

    def fetch_stochrsi(self, rsi_length: int = 14, stoch_length: int = 14, k_period: int = 3, d_period: int = 3):
        data = self._get_data()
        rl = rsi_length if rsi_length is not None else 14
        sl = stoch_length if stoch_length is not None else 14
        kp = k_period if k_period is not None else 3
        dp = d_period if d_period is not None else 3

        close = data['Close'].astype(float).to_numpy().flatten()
        fastk, fastd = talib.STOCHRSI(close, timeperiod=rl, fastk_period=kp, fastd_period=dp, fastd_matype=0)
        k_val, d_val = fastk[-1], fastd[-1]
        last_date = self._get_latest_date()
        return (f"STOCHRSI with rsi_length {rl}, stoch_length {sl}, "
                f"k_period {kp} and d_period {dp} has values of k: {round(k_val, 4)} and d: {round(d_val, 4)} on {last_date}.")

    def fetch_ichimoku(self, tenkan_period: int = 9, kijun_period: int = 26, senkou_span_b_period: int = 52):
        data = self._get_data(period="12mo")
        tp = tenkan_period if tenkan_period is not None else 9
        kp = kijun_period if kijun_period is not None else 26
        sb = senkou_span_b_period if senkou_span_b_period is not None else 52

        high = data['High'].astype(float)
        low = data['Low'].astype(float)
        close = data['Close'].astype(float)
        conv_line = (high.rolling(tp).max() + low.rolling(tp).min()) / 2
        base_line = (high.rolling(kp).max() + low.rolling(kp).min()) / 2
        senkou_a = ((conv_line + base_line) / 2).shift(kp)
        senkou_b = ((high.rolling(sb).max() + low.rolling(sb).min()) / 2).shift(kp)
        if len(senkou_a) < kp + 1 or len(senkou_b) < kp + 1:
            print(f"Not enough data for Ichimoku calculation with current periods for {self.symbol}")
            sys.exit(1)
        spanA = senkou_a.iloc[-1]
        spanB = senkou_b.iloc[-1]
        last_date = self._get_latest_date()
        return (f"ICHIMOKU with conversion_line_period {tp}, base_line_period {kp}, "
                f"leading_span_b_period {sb}, lagging_span_period 26 has "
                f"senkou_span_a of {round(spanA, 4)}, senkou_span_b of {round(spanB, 4)} on {last_date}.")

    def fetch_mfi(self, time_period: int = 14):
        data = self._get_data()
        tp = time_period if time_period is not None else 14

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        close = data['Close'].astype(float).to_numpy().flatten()
        volume = data['Volume'].astype(float).to_numpy().flatten()
        mfi = talib.MFI(high, low, close, volume, timeperiod=tp)
        value = mfi[-1]
        last_date = self._get_latest_date()
        return f"MFI with time_period of {tp} days has a value of {round(value, 4)} on {last_date}."

    def fetch_obv(self):
        data = self._get_data()

        close = data['Close'].astype(float).to_numpy().flatten()
        volume = data['Volume'].astype(float).to_numpy().flatten()
        obv = talib.OBV(close, volume)
        value = obv[-1]
        last_date = self._get_latest_date()
        return f"OBV has a value of {round(float(value), 4)} on {last_date}."

    def fetch_mom(self, time_period: int = 10):
        data = self._get_data()
        tp = time_period if time_period is not None else 10

        close = data['Close'].astype(float).to_numpy().flatten()
        mom = talib.MOM(close, timeperiod=tp)
        value = mom[-1]
        last_date = self._get_latest_date()
        return f"MOM with time_period of {tp} days has a value of {round(value, 4)} on {last_date}."

    def fetch_willr(self, time_period: int = 14):
        data = self._get_data()
        tp = time_period if time_period is not None else 14

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        close = data['Close'].astype(float).to_numpy().flatten()
        willr = talib.WILLR(high, low, close, timeperiod=tp)
        value = willr[-1]
        last_date = self._get_latest_date()
        return f"WILLR with time_period of {tp} days has a value of {round(value, 4)} on {last_date}."

    def fetch_historical_prices(self, days: int = 30):
        """
        Fetch historical price data for the symbol.
        
        Args:
            days (int): Number of days of historical data to retrieve
            
        Returns:
            pd.DataFrame: DataFrame with historical price data
        """
        data = self._get_data()
        
        # Get the last 'days' entries
        historical_data = data.tail(days).copy()
        
        # Calculate daily percentage change
        historical_data['pct_change'] = historical_data['Close'].pct_change() * 100
        
        # Sort by date descending (most recent first)
        historical_data = historical_data.sort_index(ascending=False)
        
        return historical_data
    
    def fetch_historical_adx(self, time_period: int = 14, days: int = 30):
        """Fetch historical ADX values"""
        data = self._get_data()
        tp = time_period if time_period is not None else 14

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        close = data['Close'].astype(float).to_numpy().flatten()
        adx = talib.ADX(high, low, close, timeperiod=tp)
        
        # Create DataFrame with dates and ADX values
        df = pd.DataFrame({
            'date': data.index,
            'value': adx
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp

    def fetch_historical_bbands(self, time_period: int = 20, days: int = 30):
        """Fetch historical Bollinger Bands values"""
        data = self._get_data()
        tp = time_period if time_period is not None else 20

        close = data['Close'].astype(float).to_numpy().flatten()
        upper, middle, lower = talib.BBANDS(close, timeperiod=tp, nbdevup=2.0, nbdevdn=2.0, matype=0)
        
        # Create DataFrame with dates and BBANDS values (using middle band as main value)
        df = pd.DataFrame({
            'date': data.index,
            'value': middle,
            'upper': upper,
            'lower': lower
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp

    def fetch_historical_ema(self, time_period: int = 9, days: int = 30):
        """Fetch historical EMA values"""
        data = self._get_data()
        tp = time_period if time_period is not None else 9

        close = data['Close'].astype(float).to_numpy().flatten()
        ema = talib.EMA(close, timeperiod=tp)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': ema
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp

    def fetch_historical_macd(self, macd_fast_period: int = 12, macd_slow_period: int = 26, days: int = 30):
        """Fetch historical MACD values"""
        data = self._get_data()
        fp = macd_fast_period if macd_fast_period is not None else 12
        sp = macd_slow_period if macd_slow_period is not None else 26
        sig = 9

        close = data['Close'].astype(float).to_numpy().flatten()
        macd, macdsignal, macdhist = talib.MACD(close, fastperiod=fp, slowperiod=sp, signalperiod=sig)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': macd,
            'signal': macdsignal,
            'hist': macdhist
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, fp, sp, sig

    def fetch_historical_percent_b(self, time_period: int = 20, days: int = 30):
        """Fetch historical Percent B values"""
        data = self._get_data()
        tp = time_period if time_period is not None else 20

        close_arr = data['Close'].astype(float).to_numpy().flatten()
        upper, middle, lower = talib.BBANDS(close_arr, timeperiod=tp, nbdevup=2.0, nbdevdn=2.0, matype=0)
        
        percent_b_values = (close_arr - lower) / (upper - lower)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': percent_b_values
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp

    def fetch_historical_rsi(self, time_period: int = 14, days: int = 30):
        """Fetch historical RSI values"""
        data = self._get_data()
        tp = time_period if time_period is not None else 14

        close = data['Close'].astype(float).to_numpy().flatten()
        rsi = talib.RSI(close, timeperiod=tp)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': rsi
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp

    def fetch_historical_sma(self, time_period: int = 20, days: int = 30):
        """Fetch historical SMA values"""
        data = self._get_data()
        tp = time_period if time_period is not None else 20

        close = data['Close'].astype(float).to_numpy().flatten()
        sma = talib.SMA(close, timeperiod=tp)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': sma
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp

    def fetch_historical_stoch(self, fast_k_period: int = 14, slow_k_period: int = 3, slow_d_period: int = 3, days: int = 30):
        """Fetch historical Stochastic values"""
        data = self._get_data()
        fk = fast_k_period if fast_k_period is not None else 14
        sk = slow_k_period if slow_k_period is not None else 3
        sd = slow_d_period if slow_d_period is not None else 3

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        close = data['Close'].astype(float).to_numpy().flatten()
        slowk, slowd = talib.STOCH(high, low, close, fastk_period=fk, slowk_period=sk, slowk_matype=0, slowd_period=sd, slowd_matype=0)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': slowk,
            'slowd': slowd
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, fk, sk, sd

    def fetch_historical_cci(self, time_period: int = 20, days: int = 30):
        """Fetch historical CCI values"""
        data = self._get_data()
        tp = time_period if time_period is not None else 20

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        close = data['Close'].astype(float).to_numpy().flatten()
        cci = talib.CCI(high, low, close, timeperiod=tp)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': cci
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp

    def fetch_historical_sar(self, days: int = 30):
        """Fetch historical SAR values"""
        data = self._get_data()

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        sar = talib.SAR(high, low, acceleration=0.02, maximum=0.2)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': sar
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df

    def fetch_historical_stochrsi(self, rsi_length: int = 14, stoch_length: int = 14, k_period: int = 3, d_period: int = 3, days: int = 30):
        """Fetch historical StochRSI values"""
        data = self._get_data()
        rl = rsi_length if rsi_length is not None else 14
        sl = stoch_length if stoch_length is not None else 14
        kp = k_period if k_period is not None else 3
        dp = d_period if d_period is not None else 3

        close = data['Close'].astype(float).to_numpy().flatten()
        fastk, fastd = talib.STOCHRSI(close, timeperiod=rl, fastk_period=kp, fastd_period=dp, fastd_matype=0)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': fastk,
            'fastd': fastd
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, rl, sl, kp, dp

    def fetch_historical_ichimoku(self, tenkan_period: int = 9, kijun_period: int = 26, senkou_span_b_period: int = 52, days: int = 30):
        """Fetch historical Ichimoku values"""
        data = self._get_data(period="12mo")
        tp = tenkan_period if tenkan_period is not None else 9
        kp = kijun_period if kijun_period is not None else 26
        sb = senkou_span_b_period if senkou_span_b_period is not None else 52

        high = data['High'].astype(float)
        low = data['Low'].astype(float)
        close = data['Close'].astype(float)
        conv_line = (high.rolling(tp).max() + low.rolling(tp).min()) / 2
        base_line = (high.rolling(kp).max() + low.rolling(kp).min()) / 2
        senkou_a = ((conv_line + base_line) / 2).shift(kp)
        senkou_b = ((high.rolling(sb).max() + low.rolling(sb).min()) / 2).shift(kp)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': senkou_a,
            'senkou_b': senkou_b
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp, kp, sb

    def fetch_historical_mfi(self, time_period: int = 14, days: int = 30):
        """Fetch historical MFI values"""
        data = self._get_data()
        tp = time_period if time_period is not None else 14

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        close = data['Close'].astype(float).to_numpy().flatten()
        volume = data['Volume'].astype(float).to_numpy().flatten()
        mfi = talib.MFI(high, low, close, volume, timeperiod=tp)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': mfi
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp

    def fetch_historical_obv(self, days: int = 30):
        """Fetch historical OBV values"""
        data = self._get_data()

        close = data['Close'].astype(float).to_numpy().flatten()
        volume = data['Volume'].astype(float).to_numpy().flatten()
        obv = talib.OBV(close, volume)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': obv
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df

    def fetch_historical_mom(self, time_period: int = 10, days: int = 30):
        """Fetch historical Momentum values"""
        data = self._get_data()
        tp = time_period if time_period is not None else 10

        close = data['Close'].astype(float).to_numpy().flatten()
        mom = talib.MOM(close, timeperiod=tp)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': mom
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp

    def fetch_historical_willr(self, time_period: int = 14, days: int = 30):
        """Fetch historical Williams %R values"""
        data = self._get_data()
        tp = time_period if time_period is not None else 14

        high = data['High'].astype(float).to_numpy().flatten()
        low = data['Low'].astype(float).to_numpy().flatten()
        close = data['Close'].astype(float).to_numpy().flatten()
        willr = talib.WILLR(high, low, close, timeperiod=tp)
        
        df = pd.DataFrame({
            'date': data.index,
            'value': willr
        })
        df.set_index('date', inplace=True)
        df = df.dropna()
        df = df.tail(days)
        df['pct_change'] = df['value'].pct_change() * 100
        df = df.sort_index(ascending=False)
        
        return df, tp

    def _format_historical_data(self, df, indicator_name, params_str, days):
        """
        Format historical data similar to VIX format.
        
        Args:
            df (pd.DataFrame): DataFrame with historical data
            indicator_name (str): Name of the indicator
            params_str (str): String describing the parameters
            days (int): Number of days requested
            
        Returns:
            str: Formatted historical data
        """
        actual_days = len(df)
        result = ""
        
        if actual_days < days:
            result = f"WARNING: Only {actual_days} days of {indicator_name} data available instead of requested {days} days.\n\n"
        
        result += f"{indicator_name} {params_str} values for the last {actual_days} days:\n"
        
        # Sort by date ascending for display
        df_sorted = df.sort_index(ascending=True)
        latest_date = df.index[0].strftime('%Y-%m-%d') if len(df) > 0 else ""
        
        for date, row in df_sorted.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            value = "No data available" if pd.isna(row['value']) else round(float(row['value']), 4)
            
            if date_str == latest_date:
                result += f"* {date_str}: {value} (LATEST {indicator_name.upper()} VALUE)\n"
            else:
                result += f"* {date_str}: {value}\n"
        
        return result

    def _format_price_historical_data(self, df, symbol, days):
        """
        Format historical price data similar to VIX format.
        
        Args:
            df (pd.DataFrame): DataFrame with historical price data
            symbol (str): Symbol name
            days (int): Number of days requested
            
        Returns:
            str: Formatted historical price data
        """
        actual_days = len(df)
        result = ""
        
        if actual_days < days:
            result = f"WARNING: Only {actual_days} days of {symbol} price data available instead of requested {days} days.\n\n"
        
        result += f"{symbol} closing price values for the last {actual_days} days:\n"
        
        # Sort by date ascending for display
        df_sorted = df.sort_index(ascending=True)
        latest_date = df.index[0].strftime('%Y-%m-%d') if len(df) > 0 else ""
        
        for date, row in df_sorted.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            value = "No data available" if pd.isna(row['Close']) else round(float(row['Close']), 4)
            
            if date_str == latest_date:
                daily_change = row['pct_change'] if not pd.isna(row['pct_change']) else "N/A"
                daily_change_str = f"{daily_change:.2f}%" if isinstance(daily_change, (int, float)) else daily_change
                result += f"* {date_str}: {value} (LATEST PRICE VALUE, Daily change from previous day: {daily_change_str})\n"
            else:
                result += f"* {date_str}: {value}\n"
        
        return result

    def _get_quote_data(self):
        # Use the centralized data manager
        self._quote_data = twelve_data_manager.get_quote_data(self.symbol)
        return self._quote_data



    def fetch_quote(self):
        return _format_quote(self._get_quote_data())

    def fetch_current_price(self):
        return _format_current_price(self._get_quote_data())

    def fetch_all(
        self,
        adx_time_period: int = None,
        bbands_time_period: int = None,
        ema_time_period: int = None,
        macd_fast_period: int = None,
        macd_slow_period: int = None,
        percent_b_time_period: int = None,
        rsi_time_period: int = None,
        sma_time_period: int = None,
        stoch_fast_period: int = None,
        stoch_slow_period: int = None,
        stoch_d_period: int = None,
        cci_time_period: int = None,
        mom_time_period: int = None,
        willr_time_period: int = None,
        mfi_time_period: int = None,
        rsi_length: int = None,
        stoch_length: int = None,
        k_period: int = None,
        d_period: int = None,
        tenkan_period: int = None,
        kijun_period: int = None,
        senkou_span_b_period: int = None,
    ):
        # Get the latest date for technical indicators
        last_date = self._get_latest_date()
        
        # Create the technical indicators section header
        technical_indicators = f"\n\nTechnical Indicators as of {last_date}:"
        
        return {
            "price": self.fetch_current_price(),
            "quote": self.fetch_quote(),
            "technical_indicators": technical_indicators,
            "adx": self.fetch_adx(time_period=adx_time_period),
            "bbands": self.fetch_bbands(time_period=bbands_time_period),
            "ema": self.fetch_ema(time_period=ema_time_period),
            "macd": self.fetch_macd(macd_fast_period=macd_fast_period, macd_slow_period=macd_slow_period),
            "percent_b": self.fetch_percent_b(time_period=percent_b_time_period),
            "rsi": self.fetch_rsi(time_period=rsi_time_period),
            "sma": self.fetch_sma(time_period=sma_time_period),
            "stoch": self.fetch_stoch(fast_k_period=stoch_fast_period,
                                        slow_k_period=stoch_slow_period,
                                        slow_d_period=stoch_d_period),
            "cci": self.fetch_cci(time_period=cci_time_period),
            "sar": self.fetch_sar(),
            "stochrsi": self.fetch_stochrsi(rsi_length=rsi_length, stoch_length=stoch_length,
                                            k_period=k_period, d_period=d_period),
            "ichimoku": self.fetch_ichimoku(tenkan_period=tenkan_period, kijun_period=kijun_period,
                                            senkou_span_b_period=senkou_span_b_period),
            "mfi": self.fetch_mfi(time_period=mfi_time_period),
            "obv": self.fetch_obv(),
            "mom": self.fetch_mom(time_period=mom_time_period),
            "willr": self.fetch_willr(time_period=willr_time_period),
        }

    def fetch_company_name(self, exchange: str = "NASDAQ"):
        # Use the Quote endpoint from Twelve Data API (available in free tier)
        # The quote endpoint provides the company name and is available for all plans
        quote_data = self._get_quote_data()
        return quote_data.get("name", self.symbol)


# --- A4: fetch_* / format_* split ---------------------------------------------
#
# fetch_technical_data computes every indicator once into the A2 records
# (IndicatorSnapshot and PriceBar); format_ti_context turns them back into the
# prompt text that get_ti_context has always produced. The golden test
# tests/test_golden_context.py pins that text byte for byte, so the rounding
# below copies the original code: the "current" sentences rounded numpy
# scalars (np.round semantics) and the history tables rounded Python floats.

# Period defaults of the individual TwelveTI.fetch_* methods, keyed like
# settings.TECHNICAL_INDICATOR_DEFAULTS.
TI_PARAM_DEFAULTS = {
    "adx_time_period": 14,
    "bbands_time_period": 20,
    "ema_time_period": 9,
    "macd_fast_period": 12,
    "macd_slow_period": 26,
    "percent_b_time_period": 20,
    "rsi_time_period": 14,
    "sma_time_period": 20,
    "stoch_fast_period": 14,
    "stoch_slow_period": 3,
    "stoch_d_period": 3,
    "cci_time_period": 20,
    "mom_time_period": 10,
    "willr_time_period": 14,
    "mfi_time_period": 14,
    "rsi_length": 14,
    "stoch_length": 14,
    "k_period": 3,
    "d_period": 3,
    "tenkan_period": 9,
    "kijun_period": 26,
    "senkou_span_b_period": 52,
}
MACD_SIGNAL_PERIOD = 9


@dataclass(frozen=True)
class TechnicalData:
    """What ``fetch_technical_data`` returns.

    ``snapshot`` (every non-NaN value of every indicator series) and ``bars``
    are the A2 records the run store saves. ``quote`` is the raw Twelve Data
    quote payload, which A2 does not model; the prompt text prints it as is.
    ``params`` holds the resolved indicator periods.
    """

    snapshot: IndicatorSnapshot
    bars: tuple[PriceBar, ...]
    quote: dict
    params: dict


def _resolve_ti_params(indicator_params: Optional[dict]) -> dict:
    given = dict(indicator_params or {})
    unknown = sorted(set(given) - set(TI_PARAM_DEFAULTS))
    if unknown:
        raise ValueError(f"unknown technical indicator parameters: {unknown}")
    return {
        key: given[key] if given.get(key) is not None else default
        for key, default in TI_PARAM_DEFAULTS.items()
    }


def _price_bars(symbol: str, data: pd.DataFrame) -> list[PriceBar]:
    has_volume = "Volume" in data.columns
    bars = []
    for ts, row in data.iterrows():
        volume = float(row["Volume"]) if has_volume and not pd.isna(row["Volume"]) else None
        bars.append(
            PriceBar(
                symbol=symbol,
                ts=pd.Timestamp(ts).to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=volume,
            )
        )
    return bars


def fetch_technical_data(
    symbol: str,
    indicator_params: dict = settings.TECHNICAL_INDICATOR_DEFAULTS,
    interval: str = "1day",
) -> TechnicalData:
    """Fetch prices and the quote from Twelve Data and compute every indicator."""
    p = _resolve_ti_params(indicator_params)
    ti = TwelveTI(symbol, interval)
    quote = ti._get_quote_data()
    data = ti._get_data()

    high = ti._get_column_data(data, "High")
    low = ti._get_column_data(data, "Low")
    close = ti._get_column_data(data, "Close")

    points: list[IndicatorPoint] = []

    def add(indicator: str, series: str, params: str, values, index) -> None:
        for ts, value in zip(index, np.asarray(values, dtype=float)):
            if not np.isnan(value):
                points.append(
                    IndicatorPoint(
                        symbol=symbol,
                        indicator=indicator,
                        series=series,
                        params=params,
                        ts=pd.Timestamp(ts).to_pydatetime(),
                        value=float(value),
                    )
                )

    idx = data.index

    tp = p["adx_time_period"]
    add("adx", "adx", f"time_period={tp}", talib.ADX(high, low, close, timeperiod=tp), idx)

    tp = p["bbands_time_period"]
    upper, middle, lower = talib.BBANDS(close, timeperiod=tp, nbdevup=2.0, nbdevdn=2.0, matype=0)
    for series, values in (("bbands_upper", upper), ("bbands_middle", middle), ("bbands_lower", lower)):
        add("bbands", series, f"time_period={tp},sd=2.0", values, idx)

    tp = p["ema_time_period"]
    add("ema", "ema", f"time_period={tp}", talib.EMA(close, timeperiod=tp), idx)

    fp, sp, sig = p["macd_fast_period"], p["macd_slow_period"], MACD_SIGNAL_PERIOD
    macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=fp, slowperiod=sp, signalperiod=sig)
    for series, values in (("macd", macd), ("macd_signal", macd_signal), ("macd_hist", macd_hist)):
        add("macd", series, f"fast={fp},slow={sp},signal={sig}", values, idx)

    tp = p["percent_b_time_period"]
    pb_upper, _pb_middle, pb_lower = talib.BBANDS(close, timeperiod=tp, nbdevup=2.0, nbdevdn=2.0, matype=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        percent_b = (close - pb_lower) / (pb_upper - pb_lower)
    add("percent_b", "percent_b", f"time_period={tp},sd=2.0", percent_b, idx)

    tp = p["rsi_time_period"]
    add("rsi", "rsi", f"time_period={tp}", talib.RSI(close, timeperiod=tp), idx)

    tp = p["sma_time_period"]
    add("sma", "sma", f"time_period={tp}", talib.SMA(close, timeperiod=tp), idx)

    fk, sk, sd = p["stoch_fast_period"], p["stoch_slow_period"], p["stoch_d_period"]
    slowk, slowd = talib.STOCH(
        high, low, close, fastk_period=fk, slowk_period=sk, slowk_matype=0, slowd_period=sd, slowd_matype=0
    )
    for series, values in (("stoch_slowk", slowk), ("stoch_slowd", slowd)):
        add("stoch", series, f"fast_k={fk},slow_k={sk},slow_d={sd}", values, idx)

    tp = p["cci_time_period"]
    add("cci", "cci", f"time_period={tp}", talib.CCI(high, low, close, timeperiod=tp), idx)

    add("sar", "sar", "acceleration=0.02,maximum=0.2", talib.SAR(high, low, acceleration=0.02, maximum=0.2), idx)

    rl, sl, kp, dp = p["rsi_length"], p["stoch_length"], p["k_period"], p["d_period"]
    fastk, fastd = talib.STOCHRSI(close, timeperiod=rl, fastk_period=kp, fastd_period=dp, fastd_matype=0)
    for series, values in (("stochrsi_fastk", fastk), ("stochrsi_fastd", fastd)):
        add("stochrsi", series, f"rsi_length={rl},stoch_length={sl},k={kp},d={dp}", values, idx)

    # Ichimoku uses a longer history, as TwelveTI.fetch_ichimoku does.
    tk, kj, sb = p["tenkan_period"], p["kijun_period"], p["senkou_span_b_period"]
    data_12mo = ti._get_data(period="12mo")
    high_12 = data_12mo["High"].astype(float)
    low_12 = data_12mo["Low"].astype(float)
    conv_line = (high_12.rolling(tk).max() + low_12.rolling(tk).min()) / 2
    base_line = (high_12.rolling(kj).max() + low_12.rolling(kj).min()) / 2
    senkou_a = ((conv_line + base_line) / 2).shift(kj)
    senkou_b = ((high_12.rolling(sb).max() + low_12.rolling(sb).min()) / 2).shift(kj)
    if len(senkou_a) < kj + 1 or len(senkou_b) < kj + 1:
        # Kept from TwelveTI.fetch_ichimoku; exiting here bypasses per-symbol
        # error handling (ROADMAP X10).
        print(f"Not enough data for Ichimoku calculation with current periods for {symbol}")
        sys.exit(1)
    for series, values in (("ichimoku_senkou_a", senkou_a), ("ichimoku_senkou_b", senkou_b)):
        add("ichimoku", series, f"tenkan={tk},kijun={kj},senkou_b={sb}", values.to_numpy(), data_12mo.index)

    tp = p["mfi_time_period"]
    volume = ti._get_column_data(data, "Volume")
    add("mfi", "mfi", f"time_period={tp}", talib.MFI(high, low, close, volume, timeperiod=tp), idx)
    add("obv", "obv", "", talib.OBV(close, volume), idx)

    tp = p["mom_time_period"]
    add("mom", "mom", f"time_period={tp}", talib.MOM(close, timeperiod=tp), idx)

    tp = p["willr_time_period"]
    add("willr", "willr", f"time_period={tp}", talib.WILLR(high, low, close, timeperiod=tp), idx)

    bars = _price_bars(symbol, data)
    snapshot = IndicatorSnapshot(symbol=symbol, as_of=bars[-1].ts, interval=interval, points=points)
    return TechnicalData(snapshot=snapshot, bars=tuple(bars), quote=quote, params=p)


def _format_quote(data: dict) -> str:
    current_date = datetime.strptime(data['datetime'], '%Y-%m-%d')
    previous_day_str = (current_date - timedelta(days=1)).strftime('%Y-%m-%d')
    return (f"Quote Summary for {data['symbol']} - {data['name']}:"
            f"\n• Exchange: {data['exchange']} ({data['mic_code']})"
            f"\n• Currency: {data['currency']}"
            f"\n\nDaily Statistics on {previous_day_str} :"
            f"\n• Open: {data['open']}"
            f"\n• High: {data['high']}"
            f"\n• Low: {data['low']}"
            f"\n• Close: {data['close']}"
            f"\n• Previous Close: {data['previous_close']}"
            f"\n• Change: {data['change']} ({data['percent_change']}%)"
            f"\n\nVolume Information:"
            f"\n• Current Volume: {data['volume']}"
            f"\n• Average Volume: {data['average_volume']}"
            f"\n\n52-Week Performance:"
            f"\n• Low: {data['fifty_two_week']['low']}"
            f"\n• High: {data['fifty_two_week']['high']}"
            f"\n• Low Change: {data['fifty_two_week']['low_change']} ({data['fifty_two_week']['low_change_percent']}%)"
            f"\n• High Change: {data['fifty_two_week']['high_change']} ({data['fifty_two_week']['high_change_percent']}%)"
            f"\n• Range: {data['fifty_two_week']['range']}")


def _format_current_price(data: dict) -> str:
    return f'The current price for {data["name"]} is {data["close"]}'


def _r4(value: float):
    """Round like the original sentences did: numpy scalar rounding, ``nan`` kept."""
    return round(np.float64(value), 4)


def _current_sentences(td: TechnicalData) -> list[str]:
    p = td.params
    last_ts = td.bars[-1].ts
    last_date = last_ts.strftime('%Y-%m-%d')

    def cur(series: str) -> float:
        # The value on the last bar; NaN (printed "nan") when the series has
        # none there, as indexing [-1] on the raw array gave before.
        points = td.snapshot.series(series)
        return points[-1].value if points and points[-1].ts == last_ts else float("nan")

    pb_tp = p["percent_b_time_period"]
    fk, sk, sd = p["stoch_fast_period"], p["stoch_slow_period"], p["stoch_d_period"]
    rl, sl, kp, dp = p["rsi_length"], p["stoch_length"], p["k_period"], p["d_period"]
    tk, kj, sb = p["tenkan_period"], p["kijun_period"], p["senkou_span_b_period"]
    sentences = {
        "adx": f"ADX with time_period of {p['adx_time_period']} days has a latest value of {_r4(cur('adx'))} on {last_date}.",
        "bbands": (f"BBANDS with time_period of {p['bbands_time_period']} days, sd of 2.0 and ma_type sma "
                   f"has an upper_band value of {_r4(cur('bbands_upper'))}, middle_band value of {_r4(cur('bbands_middle'))}, "
                   f"and lower_band value of {_r4(cur('bbands_lower'))} on {last_date}."),
        "ema": f"EMA with time_period of {p['ema_time_period']} days has a value of {_r4(cur('ema'))} on {last_date}.",
        "macd": (f"MACD with fast_period {p['macd_fast_period']}, slow_period {p['macd_slow_period']} and signal_period {MACD_SIGNAL_PERIOD} "
                 f"has a macd value of {_r4(cur('macd'))}, macd_signal of {_r4(cur('macd_signal'))} "
                 f"and macd_hist of {_r4(cur('macd_hist'))} on {last_date}."),
        "percent_b": (f"PERCENT_B with time_period of {pb_tp} days, sd of 2.0 and ma_type sma "
                      f"has a value of {_r4(cur('percent_b'))} on {last_date}."),
        "rsi": f"RSI with time_period of {p['rsi_time_period']} days has a value of {_r4(cur('rsi'))} on {last_date}.",
        "sma": f"SMA with time_period of {p['sma_time_period']} days has a value of {_r4(cur('sma'))} on {last_date}.",
        "stoch": (f"STOCH with fast_k_period {fk}, slow_k_period {sk} and slow_d_period {sd} "
                  f"has slow_k value of {_r4(cur('stoch_slowk'))} and slow_d value of {_r4(cur('stoch_slowd'))} on {last_date}."),
        "cci": f"CCI with time_period of {p['cci_time_period']} days has a value of {_r4(cur('cci'))} on {last_date}.",
        "sar": f"SAR has a value of {_r4(cur('sar'))} on {last_date}.",
        "stochrsi": (f"STOCHRSI with rsi_length {rl}, stoch_length {sl}, "
                     f"k_period {kp} and d_period {dp} has values of k: {_r4(cur('stochrsi_fastk'))} and d: {_r4(cur('stochrsi_fastd'))} on {last_date}."),
        "ichimoku": (f"ICHIMOKU with conversion_line_period {tk}, base_line_period {kj}, "
                     f"leading_span_b_period {sb}, lagging_span_period 26 has "
                     f"senkou_span_a of {_r4(cur('ichimoku_senkou_a'))}, senkou_span_b of {_r4(cur('ichimoku_senkou_b'))} on {last_date}."),
        "mfi": f"MFI with time_period of {p['mfi_time_period']} days has a value of {_r4(cur('mfi'))} on {last_date}.",
        "obv": f"OBV has a value of {round(float(cur('obv')), 4)} on {last_date}.",
        "mom": f"MOM with time_period of {p['mom_time_period']} days has a value of {_r4(cur('mom'))} on {last_date}.",
        "willr": f"WILLR with time_period of {p['willr_time_period']} days has a value of {_r4(cur('willr'))} on {last_date}.",
    }
    return [f"• {key}: {text}" for key, text in sentences.items()]


def _history_rows(snapshot: IndicatorSnapshot, series: list[str], days: int) -> list[tuple[datetime, float]]:
    """Last ``days`` bars on which every one of ``series`` has a value, oldest first.

    Matches the old DataFrame path: one row per bar, dropna across all
    columns, then tail(days). The first series is the displayed value.
    """
    by_series = [{p.ts: p.value for p in snapshot.series(name)} for name in series]
    common = set(by_series[0]).intersection(*by_series[1:])
    rows = [(ts, by_series[0][ts]) for ts in sorted(common)]
    return rows[-days:] if days > 0 else []


def _format_history(rows: list[tuple[datetime, float]], indicator_name: str, params_str: str, days: int) -> str:
    actual_days = len(rows)
    result = ""
    if actual_days < days:
        result = f"WARNING: Only {actual_days} days of {indicator_name} data available instead of requested {days} days.\n\n"
    result += f"{indicator_name} {params_str} values for the last {actual_days} days:\n"
    latest_date = rows[-1][0].strftime('%Y-%m-%d') if rows else ""
    for ts, value in rows:
        date_str = ts.strftime('%Y-%m-%d')
        value = round(float(value), 4)
        if date_str == latest_date:
            result += f"* {date_str}: {value} (LATEST {indicator_name.upper()} VALUE)\n"
        else:
            result += f"* {date_str}: {value}\n"
    return result


def _format_price_history(bars: tuple[PriceBar, ...], symbol: str, days: int) -> str:
    recent = list(bars[-days:]) if days > 0 else []
    actual_days = len(recent)
    result = ""
    if actual_days < days:
        result = f"WARNING: Only {actual_days} days of {symbol} price data available instead of requested {days} days.\n\n"
    result += f"{symbol} closing price values for the last {actual_days} days:\n"
    latest_date = recent[-1].ts.strftime('%Y-%m-%d') if recent else ""
    for i, bar in enumerate(recent):
        date_str = bar.ts.strftime('%Y-%m-%d')
        value = round(float(bar.close), 4)
        if date_str == latest_date:
            if i > 0:
                # Same arithmetic as pandas pct_change() * 100.
                daily_change_str = f"{(bar.close / recent[i - 1].close - 1) * 100:.2f}%"
            else:
                daily_change_str = "N/A"
            result += f"* {date_str}: {value} (LATEST PRICE VALUE, Daily change from previous day: {daily_change_str})\n"
        else:
            result += f"* {date_str}: {value}\n"
    return result


def format_ti_context(td: TechnicalData, days: int = 30) -> str:
    """Render fetched technical data as the technical-analysis prompt text."""
    p = td.params
    snap = td.snapshot
    symbol = snap.symbol
    last_date = td.bars[-1].ts.strftime('%Y-%m-%d')

    output = f"{_format_current_price(td.quote)}\n{_format_quote(td.quote)}"
    output += f"\n\nTechnical Indicators as of {last_date}:\n"
    output += "\n".join(_current_sentences(td)) + "\n"
    output += "\n" + "=" * 50 + "\nHISTORICAL DATA\n" + "=" * 50 + "\n\n"
    output += _format_price_history(td.bars, symbol, days) + "\n\n"

    histories = [
        (["adx"], "ADX", f"with time_period of {p['adx_time_period']} days"),
        (["bbands_middle", "bbands_upper", "bbands_lower"], "BBANDS (Middle Band)",
         f"with time_period of {p['bbands_time_period']} days"),
        (["ema"], "EMA", f"with time_period of {p['ema_time_period']} days"),
        (["macd", "macd_signal", "macd_hist"], "MACD",
         f"with fast_period {p['macd_fast_period']}, slow_period {p['macd_slow_period']} and signal_period {MACD_SIGNAL_PERIOD}"),
        (["rsi"], "RSI", f"with time_period of {p['rsi_time_period']} days"),
        (["sma"], "SMA", f"with time_period of {p['sma_time_period']} days"),
        (["cci"], "CCI", f"with time_period of {p['cci_time_period']} days"),
        (["mfi"], "MFI", f"with time_period of {p['mfi_time_period']} days"),
    ]
    for series, name, params_str in histories:
        output += _format_history(_history_rows(snap, series, days), name, params_str, days) + "\n\n"
    return output


def get_ti_context(symbol: str, indicator_params: dict = settings.TECHNICAL_INDICATOR_DEFAULTS, interval: str = "1day", days: int = 30) -> str:
    return format_ti_context(fetch_technical_data(symbol, indicator_params, interval), days)
