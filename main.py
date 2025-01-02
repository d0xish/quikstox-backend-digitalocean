from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from stock_analyzer import StockAnalyzer

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  
        "https://quikstox.netlify.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

analyzer = StockAnalyzer()

@app.get("/stock/{ticker}")
async def get_stock_data(ticker: str, include_zacks: bool = False):
    try:
        # Get yfinance data
        stock_data = analyzer.get_stock_data(ticker)
        
        # If stock_data has an error field, return it directly
        if isinstance(stock_data, dict) and 'error' in stock_data:
            return stock_data  # This will be JSON with error and symbol fields
        
        # Get Zacks data if requested
        if include_zacks:
            zacks_data = analyzer.get_zacks_data(ticker)
            stock_data.update(zacks_data)
        
        return stock_data
    except Exception as e:
        # Always return both error message and symbol
        return {"error": str(e), "symbol": ticker}

@app.get("/")
async def read_root():
    return {"status": "ready"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)