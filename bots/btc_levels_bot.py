import ccxt
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import time
from datetime import datetime
import asyncio

# Parameters
EXCHANGE = "binance"
PAIR = "BTC/USDT"
TIMEFRAME = "1h"
LOOKBACK = 200
TOLERANCE = 0.005  # 0.5% tolerance for level clustering
TOUCHES_MIN = 2    # Minimum touches
REFRESH_INTERVAL = 3  # seconds

exchange = getattr(ccxt, EXCHANGE)()

def fetch_ohlcv():
    ohlcv = exchange.fetch_ohlcv(PAIR, timeframe=TIMEFRAME, limit=LOOKBACK)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df

def is_level_touched(level, price):
    return abs(level - price) / price < TOLERANCE

def detect_levels(df):
    highs = df["high"]
    lows = df["low"]
    levels = []

    for i in range(2, len(df) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            level = highs[i]
        elif lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            level = lows[i]
        else:
            continue

        if not any(is_level_touched(existing, level) for existing in levels):
            levels.append(level)

    grouped = {}
    for lvl in levels:
        touch_count = (
            df["high"].apply(lambda x: is_level_touched(lvl, x)).sum() +
            df["low"].apply(lambda x: is_level_touched(lvl, x)).sum()
        )
        if touch_count >= TOUCHES_MIN:
            grouped[round(lvl, 2)] = int(touch_count)

    return grouped

def get_data():
    
        print(f"\n🔄 Fetching new data... {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        df = fetch_ohlcv()
        result = detect_levels(df)

        return result
