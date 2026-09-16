# News Trader AI

## Architectural Overview

News Trader AI is a high-frequency, autonomous straddle execution engine engineered specifically to exploit extreme market volatility during Tier-1 macroeconomic events (NFP, CPI, Retail Sales). 

The primary problem solved by this system is **Sequence of Returns Risk (SoRR)** and **Whipsaw Liquidation** during news events. Traditional retail news trading fails because predictive accuracy rarely exceeds 70%, and when predictions fail, slippage destroys account equity. This architecture mitigates failure through a mathematically audited **Asymmetrical Straddle Strategy** coupled with a strict path-dependent compounding protocol.

For developers and quantitative engineers, this repository provides a full-stack solution: a Python-based data ingestion and heuristic prediction pipeline, bridged to a C# cTrader execution node that handles sub-second latency order routing.

## Core Features & Capabilities

- **Autonomous Heuristic Prediction Engine**: Analyzes real-time calendar data against historical correlations (e.g., ADP predicting NFP, Wages predicting CPI) to generate an immediate directional bias.
- **Asymmetric Risk Straddle**: Routes a heavy `BiasAccount` order ($1000 base) in the direction of the AI's prediction, and a smaller `HedgeAccount` order ($500 base) in the exact opposite direction.
- **Whipsaw Isolation & Compounding**: Mathematically proven to survive double-whipsaw volatility by limiting drawdowns while leaving the winning side uncapped with aggressive trailing stops.
- **Zero-Latency Execution IPC**: Bypasses heavy ML overhead on the execution client by using lightweight flat-file IPC (`news_bias.txt`), ensuring the C# cBot executes flawlessly without HTTP latency.

## Component & Tech Stack

### Data & Prediction Layer
- **Language**: Python 3.12+
- **Data Processing**: `polars==1.6.0`, `pyarrow==17.0.0`
- **Analytics & Reporting**: `plotly==5.24.1`, `kaleido==0.2.1`
- **Event Feeds**: HuggingFace `datasets==3.0.0` & ForexFactory XML

### Execution Layer
- **Platform**: cTrader Automate API
- **Language**: C# / .NET 6.0
- **Latency Optimization**: Direct flat-file observer for bias fetching; pre-calculated lot sizing.

## Environment Configuration & Quick Start

Ensure you have Python 3.12+ and cTrader installed on your Windows machine. 

```powershell
# 1. Clone the repository
git clone https://github.com/your-org/news-trader-ai.git
cd news-trader-ai

# 2. Setup Python Environment
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Download the necessary Datasets
python data/download_calendar.py

# 4. Generate the Baseline Backtest Reports
python generate_reports.py
```

### cTrader Deployment
1. Copy `News Trader EA.cs` from the repository into your `Documents\cAlgo\Sources\Robots\News Trader EA` directory.
2. Build the robot in cTrader Automate.
3. Attach to **two** separate XAUUSD M1 charts.
4. Set Instance 1 `Role` parameter to `BiasAccount` (Risk: $1000).
5. Set Instance 2 `Role` parameter to `HedgeAccount` (Risk: $500).

## Core API / Integration Contracts

The Python prediction engine communicates with the C# execution layer via a simple flat-file IPC contract. 

**Python Execution Contract (Bias Generator)**
```python
# The python engine will write the predicted direction to the local file 60 seconds before the event
def write_bias(prediction: str, path: str = "C:\\news_bias.txt"):
    """
    prediction: 'BUY' or 'SELL'
    """
    with open(path, "w") as f:
        f.write(prediction)
```

**C# Consumer Contract**
```csharp
// The C# bot reads the file locally and resolves the execution direction autonomously
string content = File.ReadAllText(@"C:\news_bias.txt").Trim().ToUpper();
TradeType aiBias = content.Contains("BUY") ? TradeType.Buy : TradeType.Sell;

if (Role == AccountRole.HedgeAccount)
{
    _resolvedDirection = aiBias == TradeType.Buy ? TradeType.Sell : TradeType.Buy;
}
else
{
    _resolvedDirection = aiBias;
}
```
