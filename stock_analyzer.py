import requests
from bs4 import BeautifulSoup
import yfinance as yf
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

# with open('stock_analyzer.log', 'w'):
#     pass

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler('stock_analyzer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class StockAnalyzer:
    def __init__(self):
        # self.logger = logging.getLogger(__name__)
        self.chrome_options = Options()
        self.chrome_options.add_argument('--headless')
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.chrome_options.add_argument('--disable-extensions')
        self.service = Service(ChromeDriverManager().install())
    
    def get_zacks_data(self, ticker):
        try:
            driver = webdriver.Chrome(service=self.service, options=self.chrome_options)
            wait = WebDriverWait(driver, 20)
            
            url = f'https://www.zacks.com/stock/quote/{ticker}'
            driver.get(url)
            
            try:
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "zr_rankbox")))
                time.sleep(2)
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Get Zacks Rank number
                rank_view = soup.find('div', class_='zr_rankbox').find('p', class_='rank_view')
                rank_text = rank_view.get_text().strip().split('\n')[0].strip() if rank_view else ''
                zacks_rank = int(rank_text.split('-')[0]) if rank_text else None
                
                # Get Style Scores
                style_scores = {}
                style_box = soup.find('div', {'class': 'zr_rankbox composite_group'})
                if style_box:
                    style_view = style_box.find('p', class_='rank_view')
                    if style_view:
                        score_spans = style_view.find_all('span', class_='composite_val')
                        score_text = style_view.get_text()
                        
                        if 'Value' in score_text:
                            style_scores['Value'] = score_spans[0].text.strip()
                        if 'Growth' in score_text:
                            style_scores['Growth'] = score_spans[1].text.strip()
                        if 'Momentum' in score_text:
                            style_scores['Momentum'] = score_spans[2].text.strip()
                        if 'VGM' in score_text:
                            style_scores['VGM'] = score_spans[3].text.strip()
                
                # Get earnings date from Zacks
                earnings_section = soup.find('section', id='stock_key_earnings')
                earnings_date = None
                if earnings_section:
                    for dl in earnings_section.find_all('dl', class_='abut_bottom'):
                        dt = dl.find('dt')
                        if dt and 'Earnings Date' in dt.text:
                            dd = dl.find('dd')
                            if dd:
                                earnings_date = dd.text.strip()
                
            finally:
                driver.quit()
            
            return {
                'zacks_rank': zacks_rank,
                'style_scores': style_scores,
                'earnings_date': earnings_date
            }
            
        except Exception as e:
            return {
                'zacks_rank': None,
                'style_scores': {},
                'earnings_date': None
            }
    
    def get_stock_data(self, ticker):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Check if we got valid data back
            if not info or len(info) == 0:
                return {'error': f"Ticker '{ticker}' not found. No valid data.", 'symbol': ticker}

            # self.logger.info(f"Raw stock info for {ticker}:")
            # self.logger.info(json.dumps(info, indent=2, default=str))

            # Get today's trading data
            try:
                price = float(info.get('currentPrice', 0))
                previous_close = float(info.get('previousClose', 0))
                
                # If we can't get current price data, the ticker probably doesn't exist
                if price == 0 and previous_close == 0:
                    return {'error': f"Ticker '{ticker}' not found. No price data.", 'symbol': ticker}
                
                if price and previous_close:
                    price_change = price - previous_close
                    price_change_percent = (price_change / previous_close) * 100
                else:
                    # Fallback to regularMarket values if available
                    price = float(info.get('regularMarketPrice', 0))
                    previous_close = float(info.get('regularMarketPreviousClose', 0))
                    if price == 0 or previous_close == 0:
                        return {'error': f"Ticker '{ticker}' not found. No regularMarketPrice data.", 'symbol': ticker}
                    price_change = price - previous_close
                    price_change_percent = (price_change / previous_close) * 100
            except (TypeError, ZeroDivisionError):
                return {'error': f"Ticker '{ticker}' not found. ZeroDivisionError.", 'symbol': ticker}

            earnings_dates = stock.calendar.get('Earnings Date')
            next_earnings_str = None
            if isinstance(earnings_dates, list) and earnings_dates:
                next_earnings_str = earnings_dates[0].strftime('%A, %B %d, %Y')
            elif earnings_dates:
                next_earnings_str = earnings_dates.strftime('%A, %B %d, %Y')

            try:
                recommendations_df = stock.recommendations
                recommendations = {
                    'strong_buy': int(recommendations_df.iloc[0]['strongBuy']) if recommendations_df is not None and not recommendations_df.empty else 0,
                    'buy': int(recommendations_df.iloc[0]['buy']) if recommendations_df is not None and not recommendations_df.empty else 0,
                    'hold': int(recommendations_df.iloc[0]['hold']) if recommendations_df is not None and not recommendations_df.empty else 0,
                    'sell': int(recommendations_df.iloc[0]['sell']) if recommendations_df is not None and not recommendations_df.empty else 0,
                    'strong_sell': int(recommendations_df.iloc[0]['strongSell']) if recommendations_df is not None and not recommendations_df.empty else 0
                }
            except:
                recommendations = {
                    'strong_buy': 0,
                    'buy': 0,
                    'hold': 0,
                    'sell': 0,
                    'strong_sell': 0
                }

            # Get balance sheet data
            try:
                balance_sheet = stock.balancesheet
            except Exception as bs_error:
                balance_sheet = pd.DataFrame()  # Empty DataFrame as fallback

            # if not balance_sheet.empty:
            #     print("\nAvailable Balance Sheet Metrics:")
            #     for idx in balance_sheet.index:
            #         print(f"  - {idx}")
            #     print("\n")

            # print("Processing balance sheet data...")
            # Calculate debt ratios
            try:
                if not balance_sheet.empty:
                    most_recent_date = balance_sheet.columns[0]
                    
                    # Get all relevant values
                    total_debt = float(balance_sheet.loc['Total Debt', most_recent_date])
                    long_term_debt = float(balance_sheet.loc['Long Term Debt', most_recent_date])
                    total_equity = float(info.get('bookValue', 0)) * float(info.get('sharesOutstanding', 0))
                    
                    # print(f"Debt values - Total: {total_debt:,.0f}, Long Term: {long_term_debt:,.0f}, Equity: {total_equity:,.0f}")
                    
                    # Calculate ratios
                    total_debt_to_equity = round(info.get('debtToEquity', 0), 2) if info.get('debtToEquity') else None
                    # total_debt_to_equity = round((total_debt / total_equity * 100), 2) if total_equity else None
                    long_term_debt_to_equity = round((long_term_debt / total_equity * 100), 2) if total_equity and long_term_debt else None

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
                        'total': round(float(info.get('debtToEquity', 0)), 2),
                        'long_term': None,
                        'raw': None
                    }
            except Exception as debt_error:
                debt_ratios = {
                    'total': round(float(info.get('debtToEquity', 0)), 2),
                    'long_term': None,
                    'raw': None
                }

            def round_if_number(value, decimal_places=2):
                try:
                    float_val = float(value)
                    if pd.isna(float_val) or np.isnan(float_val) or np.isinf(float_val):
                        return None
                    return round(float_val, decimal_places)
                except (TypeError, ValueError):
                    return None

            result = {
                'symbol': ticker,
                'company_name': info.get('longName'),
                'description': info.get('longBusinessSummary'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'price': round_if_number(price),
                'price_change': round_if_number(price_change),
                'price_change_percent': round_if_number(price_change_percent),
                'fifty_two_week_low': round_if_number(info.get('fiftyTwoWeekLow', 0)),
                'fifty_two_week_high': round_if_number((info.get('fiftyTwoWeekHigh', 0)),
                'profit_margin': round_if_number(info.get('profitMargins', 0) * 100) if info.get('profitMargins') else None,
                'dividend_yield': round_if_number(info.get('dividendYield', 0) * 100) if info.get('dividendYield') else None,
                'debt_ratios': {
                    'total': total_debt_to_equity,
                    'long_term': long_term_debt_to_equity,
                    'raw': {
                        'total_debt': total_debt if 'total_debt' in locals() else None,
                        'long_term_debt': long_term_debt if 'long_term_debt' in locals() else None,
                        'total_equity': total_equity if 'total_equity' in locals() else None
                    }
                },
                'next_earnings_date': next_earnings_str,
                'analyst_count': info.get('numberOfAnalystOpinions'),
                'price_targets': {
                    'low': round(info.get('targetLowPrice', 0), 2),
                    'mean': round(info.get('targetMeanPrice', 0), 2),
                    'median': round(info.get('targetMedianPrice', 0), 2),
                    'high': round(info.get('targetHighPrice', 0), 2)
                },
                'recommendations': recommendations
            }
            return result
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())  # This will print the full stack trace
            return {'error': f"Error processing {ticker}: {str(e)}", 'symbol': ticker}