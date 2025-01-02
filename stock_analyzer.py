import requests
from bs4 import BeautifulSoup
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime
import logging
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
from typing import List, Dict
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler('stock_analyzer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def safe_float(value, default=0):
    try:
        result = float(value)
        if pd.isna(result) or np.isnan(result) or np.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default

def round_if_number(value, decimal_places=2):
    try:
        float_val = float(value)
        if pd.isna(float_val) or np.isnan(float_val) or np.isinf(float_val):
            return None
        return round(float_val, decimal_places)
    except (TypeError, ValueError):
        return None

class StockAnalyzer:
    def __init__(self):
        self.chrome_options = Options()
        self.chrome_options.add_argument('--headless')
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.chrome_options.add_argument('--disable-extensions')
        self.service = Service(ChromeDriverManager().install())
    
    # Your existing get_zacks_data method stays the same

    def get_stock_data(self, ticker):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            if not info or len(info) == 0:
                return {'error': f"Ticker '{ticker}' not found. No valid data.", 'symbol': ticker}

            # Get today's trading data
            try:
                price = safe_float(info.get('currentPrice', 0))
                previous_close = safe_float(info.get('previousClose', 0))
                
                if price == 0 and previous_close == 0:
                    return {'error': f"Ticker '{ticker}' not found. No price data.", 'symbol': ticker}
                
                if price and previous_close:
                    price_change = price - previous_close
                    price_change_percent = (price_change / previous_close) * 100 if previous_close != 0 else 0
                else:
                    price = safe_float(info.get('regularMarketPrice', 0))
                    previous_close = safe_float(info.get('regularMarketPreviousClose', 0))
                    if price == 0 or previous_close == 0:
                        return {'error': f"Ticker '{ticker}' not found. No regularMarketPrice data.", 'symbol': ticker}
                    price_change = price - previous_close
                    price_change_percent = (price_change / previous_close) * 100 if previous_close != 0 else 0
            except Exception as e:
                return {'error': f"Error processing price data: {str(e)}", 'symbol': ticker}

            # Handle earnings dates
            earnings_dates = stock.calendar.get('Earnings Date')
            next_earnings_str = None
            if isinstance(earnings_dates, list) and earnings_dates:
                try:
                    next_earnings_str = earnings_dates[0].strftime('%A, %B %d, %Y')
                except:
                    next_earnings_str = None
            elif earnings_dates:
                try:
                    next_earnings_str = earnings_dates.strftime('%A, %B %d, %Y')
                except:
                    next_earnings_str = None

            # Handle recommendations
            try:
                recommendations_df = stock.recommendations
                recommendations = {
                    'strong_buy': int(safe_float(recommendations_df.iloc[0]['strongBuy'])) if recommendations_df is not None and not recommendations_df.empty else 0,
                    'buy': int(safe_float(recommendations_df.iloc[0]['buy'])) if recommendations_df is not None and not recommendations_df.empty else 0,
                    'hold': int(safe_float(recommendations_df.iloc[0]['hold'])) if recommendations_df is not None and not recommendations_df.empty else 0,
                    'sell': int(safe_float(recommendations_df.iloc[0]['sell'])) if recommendations_df is not None and not recommendations_df.empty else 0,
                    'strong_sell': int(safe_float(recommendations_df.iloc[0]['strongSell'])) if recommendations_df is not None and not recommendations_df.empty else 0
                }
            except:
                recommendations = {
                    'strong_buy': 0, 'buy': 0, 'hold': 0, 'sell': 0, 'strong_sell': 0
                }

            # Get balance sheet data and calculate debt ratios
            try:
                balance_sheet = stock.balancesheet
                if not balance_sheet.empty:
                    most_recent_date = balance_sheet.columns[0]
                    
                    total_debt = safe_float(balance_sheet.loc['Total Debt', most_recent_date])
                    long_term_debt = safe_float(balance_sheet.loc['Long Term Debt', most_recent_date])
                    total_equity = safe_float(info.get('bookValue', 0)) * safe_float(info.get('sharesOutstanding', 0))
                    
                    total_debt_to_equity = round_if_number(info.get('debtToEquity', 0))
                    long_term_debt_to_equity = round_if_number((long_term_debt / total_equity * 100)) if total_equity and long_term_debt else None

                    debt_ratios = {
                        'total': total_debt_to_equity,
                        'long_term': long_term_debt_to_equity,
                        'raw': {
                            'total_debt': total_debt,
                            'long_term_debt': long_term_debt,
                            'total_equity': total_equity
                        }
                    }
                else:
                    debt_ratios = {
                        'total': round_if_number(info.get('debtToEquity', 0)),
                        'long_term': None,
                        'raw': None
                    }
            except Exception as debt_error:
                debt_ratios = {
                    'total': round_if_number(info.get('debtToEquity', 0)),
                    'long_term': None,
                    'raw': None
                }

            # Build result object
            result = {
                'symbol': ticker,
                'company_name': info.get('longName'),
                'description': info.get('longBusinessSummary'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'price': round_if_number(price),
                'price_change': round_if_number(price_change),
                'price_change_percent': round_if_number(price_change_percent),
                'fifty_two_week_low': round_if_number(info.get('fiftyTwoWeekLow')),
                'fifty_two_week_high': round_if_number(info.get('fiftyTwoWeekHigh')),
                'profit_margin': round_if_number(safe_float(info.get('profitMargins', 0)) * 100),
                'dividend_yield': round_if_number(safe_float(info.get('dividendYield', 0)) * 100),
                'debt_ratios': debt_ratios,
                'next_earnings_date': next_earnings_str,
                'analyst_count': info.get('numberOfAnalystOpinions'),
                'price_targets': {
                    'low': round_if_number(info.get('targetLowPrice')),
                    'mean': round_if_number(info.get('targetMeanPrice')),
                    'median': round_if_number(info.get('targetMedianPrice')),
                    'high': round_if_number(info.get('targetHighPrice'))
                },
                'recommendations': recommendations
            }
            return result
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return {'error': f"Error processing {ticker}: {str(e)}", 'symbol': ticker}