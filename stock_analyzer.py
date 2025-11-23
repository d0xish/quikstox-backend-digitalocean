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
from dotenv import load_dotenv

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

def send_pushover_notification(ticker, success=True):
    user_key = os.getenv('PUSHOVER_USER_KEY')
    app_token = os.getenv('PUSHOVER_APP_TOKEN')
    
    if not user_key or not app_token:
        print("Pushover credentials not configured")
        return
        
    message = f"{'✅' if success else '❌'} Stock lookup: {ticker}"
    
    try:
        requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": app_token,
                "user": user_key,
                "message": message,
                "title": "QuikStox Alert"
            },
            timeout=5
        )
    except Exception as e:
        print(f"Failed to send Pushover notification: {str(e)}")

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
                send_pushover_notification(ticker, success=False)
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

            # Get cash flow data and calculate Free Cash Flow to Firm (TTM)
            fcf_result = {'value': None, 'note': None, 'error': None}
            try:
                quarterly_cashflow = stock.quarterly_cashflow
                annual_cashflow = stock.cashflow

                fcf_values = []
                data_source = None

                # First, try to use pre-calculated "Free Cash Flow" field from quarterly data
                if not quarterly_cashflow.empty and len(quarterly_cashflow.columns) > 0:
                    if 'Free Cash Flow' in quarterly_cashflow.index:
                        # Get up to 4 most recent quarters for TTM
                        num_quarters = min(4, len(quarterly_cashflow.columns))
                        for i in range(num_quarters):
                            fcf = safe_float(quarterly_cashflow.loc['Free Cash Flow', quarterly_cashflow.columns[i]])
                            if fcf != 0 or i == 0:  # Include zero values except skip trailing zeros
                                fcf_values.append(fcf)

                        if len(fcf_values) > 0:
                            data_source = 'quarterly'
                            if len(fcf_values) < 4:
                                fcf_result['note'] = f'Calculated from {len(fcf_values)} quarter{"s" if len(fcf_values) > 1 else ""} of data'

                # If pre-calculated FCF not available, try manual calculation from quarterly data
                if not fcf_values and not quarterly_cashflow.empty and len(quarterly_cashflow.columns) > 0:
                    # Possible names for Operating Cash Flow
                    ocf_keys = ['Operating Cash Flow', 'Total Cash From Operating Activities',
                                'Cash Flow From Operating Activities']
                    # Possible names for Capital Expenditures
                    capex_keys = ['Capital Expenditures', 'Capital Expenditure',
                                  'Purchase Of Property Plant And Equipment']

                    # Find the correct keys
                    ocf_key = None
                    capex_key = None
                    for key in ocf_keys:
                        if key in quarterly_cashflow.index:
                            ocf_key = key
                            break
                    for key in capex_keys:
                        if key in quarterly_cashflow.index:
                            capex_key = key
                            break

                    if ocf_key and capex_key:
                        # Get up to 4 most recent quarters
                        num_quarters = min(4, len(quarterly_cashflow.columns))
                        for i in range(num_quarters):
                            ocf = safe_float(quarterly_cashflow.loc[ocf_key, quarterly_cashflow.columns[i]])
                            capex = safe_float(quarterly_cashflow.loc[capex_key, quarterly_cashflow.columns[i]])
                            # CapEx is typically negative, so we add them
                            fcf = ocf + capex
                            fcf_values.append(fcf)

                        if len(fcf_values) > 0:
                            data_source = 'quarterly'
                            if len(fcf_values) < 4:
                                fcf_result['note'] = f'Calculated from {len(fcf_values)} quarter{"s" if len(fcf_values) > 1 else ""} of data'

                # Fall back to annual data if quarterly didn't work
                if not fcf_values and not annual_cashflow.empty and len(annual_cashflow.columns) > 0:
                    # Try pre-calculated FCF first
                    if 'Free Cash Flow' in annual_cashflow.index:
                        most_recent = annual_cashflow.columns[0]
                        fcf = safe_float(annual_cashflow.loc['Free Cash Flow', most_recent])
                        if fcf != 0:
                            fcf_values = [fcf]
                            data_source = 'annual'
                            fcf_result['note'] = 'Annual data'
                    else:
                        # Manual calculation from annual data
                        ocf_keys = ['Operating Cash Flow', 'Total Cash From Operating Activities',
                                    'Cash Flow From Operating Activities']
                        capex_keys = ['Capital Expenditures', 'Capital Expenditure',
                                      'Purchase Of Property Plant And Equipment']

                        ocf_key = None
                        capex_key = None
                        for key in ocf_keys:
                            if key in annual_cashflow.index:
                                ocf_key = key
                                break
                        for key in capex_keys:
                            if key in annual_cashflow.index:
                                capex_key = key
                                break

                        if ocf_key and capex_key:
                            most_recent = annual_cashflow.columns[0]
                            ocf = safe_float(annual_cashflow.loc[ocf_key, most_recent])
                            capex = safe_float(annual_cashflow.loc[capex_key, most_recent])
                            fcf = ocf + capex
                            fcf_values = [fcf]
                            data_source = 'annual'
                            fcf_result['note'] = 'Annual data'

                # Calculate total FCF if we have data
                if fcf_values:
                    total_fcf = sum(fcf_values)
                    # Convert to millions
                    fcf_result['value'] = round_if_number(total_fcf / 1_000_000)
                else:
                    fcf_result['error'] = 'Cash flow data not available'

            except Exception as fcf_error:
                fcf_result['error'] = f'Error calculating FCF: {str(fcf_error)}'

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
                'fcf_to_firm': fcf_result,
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
            send_pushover_notification(ticker, success=True)
            return result
            
        except Exception as e:
            send_pushover_notification(ticker, success=False)
            import traceback
            print(traceback.format_exc())
            return {'error': f"Error processing {ticker}: {str(e)}", 'symbol': ticker}