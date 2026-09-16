using System;
using System.Linq;
using System.Xml;
using System.Collections.Generic;
using cAlgo.API;
using HorizontalAlignment = cAlgo.API.HorizontalAlignment;

namespace cAlgo.Robots
{
    public enum AccountRole { BiasAccount, HedgeAccount }

    internal class FxEvent
    {
        public DateTime EventTime { get; set; }
        public string   Title     { get; set; }
        public string   Currency  { get; set; }
        public double?  Actual    { get; set; }
        public double?  Forecast  { get; set; }
    }

    [Robot(TimeZone = TimeZones.SouthAfricaStandardTime, AccessRights = AccessRights.FullAccess)]
    public class NewsTraderEA : Robot
    {
        private const string Label   = "News Trader AI";
        private const string Comment = "by Tinotenda Bumhira";

        #region Parameters

        [Parameter("Account Role",         Group = "News",     DefaultValue = AccountRole.BiasAccount)]
        public AccountRole Role { get; set; }

        [Parameter("News Hour",            Group = "News",     DefaultValue = 15, MinValue = 0, MaxValue = 23)]
        public int NewsHour { get; set; }

        [Parameter("News Minute",          Group = "News",     DefaultValue = 30, MinValue = 0, MaxValue = 59)]
        public int NewsMinute { get; set; }

        [Parameter("Seconds Before",       Group = "News",     DefaultValue = 3,  MinValue = 1)]
        public int SecondsBefore { get; set; }

        // Mirrors News Trader Pro exactly
        [Parameter("Risk Percentage",      Group = "Risk Management", DefaultValue = 80, MinValue = 1, MaxValue = 100)]
        public double RiskPercentage { get; set; }

        [Parameter("Stop Loss (pips)",     Group = "Trading",  DefaultValue = 300)]
        public int StopLoss { get; set; }

        // No Take Profit — trailing stop is the sole exit mechanism
        [Parameter("Trailing Stop",        Group = "Trailing", DefaultValue = true)]
        public bool IncludeTrailingStop { get; set; }

        [Parameter("Trail Trigger (pips)", Group = "Trailing", DefaultValue = 500)]
        public double TrailingStopTrigger { get; set; }

        [Parameter("Trail Step (pips)",    Group = "Trailing", DefaultValue = 200)]
        public double TrailingStopStep { get; set; }

        #endregion

        #region Constants & Fields

        private const int    NewsTimeToleranceMinutes = 5;
        private const double MinMarginLevel           = 20.0;
        private const double LotSizeLogThreshold      = 0.02;
        private readonly string _feedUrl = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml";
        private static readonly TimeZoneInfo _pretoriaZone =
            TimeZoneInfo.FindSystemTimeZoneById("South Africa Standard Time");

        // Lot size cache — mirrors News Trader Pro
        private DateTime _lastLotSizeCalcTime = DateTime.MinValue;
        private double   _cachedLotSize;
        private double   _lastLoggedLotSize;
        private double   _currentVolume;

        private DateTime   _triggerTime;
        private bool       _ordersPlaced;
        private TradeType? _aiBias            = null;
        private TradeType? _executionDirection = null;

        private List<FxEvent> _weeklyEvents = new List<FxEvent>();
        private FxEvent       _targetEvent  = null;
        private Border        _dashboardPanel;

        private const string CountdownLabel = "countdown";
        private const string LotSizeLabel   = "lotsize";

        #endregion

        #region Lifecycle

        protected override void OnStart()
        {
            Timer.Start(1);
            _currentVolume = CalculateLotSize();
            var today = Server.Time;
            _triggerTime  = new DateTime(today.Year, today.Month, today.Day, NewsHour, NewsMinute, 0);

            Print("[INIT] Fetching ForexFactory & running AI analysis...");
            LoadAndAnalyse();
            DrawDashboard();
        }

        protected override void OnTick()
        {
            try
            {
                // Always trail first — mirrors News Trader Pro
                if (IncludeTrailingStop)
                    UpdateTrailingStops();

                bool hasPositions = Positions.FindAll(Label, SymbolName).Any();

                if (hasPositions)
                {
                    HideChartDisplays();
                    return;
                }

                // Margin safety check — mirrors News Trader Pro
                if (Account.MarginLevel < MinMarginLevel)
                {
                    foreach (var pos in Positions.FindAll(Label, SymbolName))
                    {
                        Print($"[Safety] Margin < {MinMarginLevel}% — closing position {pos.Id}");
                        ClosePosition(pos);
                    }
                }
            }
            catch (Exception ex)
            {
                Print("[OnTick] " + ex);
            }
        }

        protected override void OnTimer()
        {
            try
            {
                if (Positions.FindAll(Label, SymbolName).Any())
                {
                    HideChartDisplays();
                    return;
                }

                DateTime now = Server.Time;
                _triggerTime   = new DateTime(now.Year, now.Month, now.Day, NewsHour, NewsMinute, 0);
                _currentVolume = CalculateLotSize();

                if (now > _triggerTime.AddMinutes(NewsTimeToleranceMinutes))
                    _ordersPlaced = false;

                UpdateUI(now);
                PrepareOrders(now);
            }
            catch (Exception ex)
            {
                Print("[OnTimer] " + ex);
            }
        }

        #endregion

        #region Lot Size — mirrors News Trader Pro exactly

        private double CalculateLotSize()
        {
            if (Account.Balance <= 0)
                return Symbol.VolumeInUnitsMin;

            if (_cachedLotSize > 0 && (Server.Time - _lastLotSizeCalcTime).TotalSeconds < 2)
                return _cachedLotSize;

            _lastLotSizeCalcTime = Server.Time;

            double riskAmount      = Account.Balance * (RiskPercentage / 100.0);
            double marginPer001Lot = Symbol.GetEstimatedMargin(TradeType.Buy, Symbol.QuantityToVolumeInUnits(0.01));
            if (marginPer001Lot <= 0) return Symbol.VolumeInUnitsMin;

            double lots   = (riskAmount / marginPer001Lot) * 0.01;
            double volume = Symbol.NormalizeVolumeInUnits(Symbol.QuantityToVolumeInUnits(lots), RoundingMode.ToNearest);

            _cachedLotSize = volume;

            if (_lastLoggedLotSize == 0.0 || Math.Abs(volume - _lastLoggedLotSize) / _lastLoggedLotSize > LotSizeLogThreshold)
            {
                _lastLoggedLotSize = volume;
                double lotQty = Symbol.VolumeInUnitsToQuantity(volume);
                Print($"[LotSize] Balance: {Account.Balance:F2} | Risk: {RiskPercentage}% | Lots: {lotQty:F2}");
            }

            return volume;
        }

        #endregion

        #region ForexFactory + AI Heuristics

        private void LoadAndAnalyse()
        {
            try
            {
                HttpResponse response = Http.Get(_feedUrl);
                if (!response.IsSuccessful)
                {
                    Print($"[FF] Feed failed — HTTP {response.StatusCode}");
                    return;
                }

                string xml = response.Body;
                if (!xml.TrimStart().StartsWith("<") || xml.Contains("<html"))
                {
                    Print("[FF] Rate limited — will retry");
                    return;
                }

                var doc = new XmlDocument();
                doc.LoadXml(xml);
                _weeklyEvents.Clear();

                foreach (XmlNode node in doc.GetElementsByTagName("event"))
                {
                    // Load ALL currencies — we need precursors from any country
                    string title    = node["title"]?.InnerText.Trim()             ?? "";
                    string currency = node["country"]?.InnerText.Trim().ToUpper() ?? "";
                    string dateStr  = node["date"]?.InnerText.Trim()              ?? "";
                    string timeStr  = node["time"]?.InnerText.Trim()              ?? "";

                    if (!DateTime.TryParse($"{dateStr} {timeStr}", out DateTime utcDt)) continue;
                    DateTime localDt = TimeZoneInfo.ConvertTimeFromUtc(
                        DateTime.SpecifyKind(utcDt, DateTimeKind.Utc), _pretoriaZone);

                    _weeklyEvents.Add(new FxEvent
                    {
                        EventTime = localDt,
                        Title     = title,
                        Currency  = currency,
                        Actual    = ParseValue(node["actual"]?.InnerText),
                        Forecast  = ParseValue(node["forecast"]?.InnerText)
                    });
                }

                _weeklyEvents = _weeklyEvents.OrderBy(e => e.EventTime).ToList();
                Print($"[FF] Loaded {_weeklyEvents.Count} total events this week.");

                // Lock onto whatever event the user has pointed us at — no filtering
                _targetEvent = _weeklyEvents.FirstOrDefault(e =>
                    e.EventTime > Server.Time &&
                    e.EventTime.Hour   == NewsHour &&
                    e.EventTime.Minute == NewsMinute);

                if (_targetEvent == null)
                {
                    Print($"[FF] No event found at {NewsHour:D2}:{NewsMinute:D2}. Check ForexFactory and re-enter the time.");
                    return;
                }

                Print($"[FF] Target locked: '{_targetEvent.Title}' @ {_targetEvent.EventTime:HH:mm}");
                RunAiHeuristics();
            }
            catch (Exception ex)
            {
                Print("[FF] Error: " + ex.Message);
            }
        }

        private void RunAiHeuristics()
        {
            if (_targetEvent == null) return;

            double score = 0;
            string title = _targetEvent.Title.ToLower();

            // ── NFP ──────────────────────────────────────────────────────────
            if (title.Contains("non-farm") || title.Contains("nfp"))
            {
                var adp = FindPrecursor("ADP Non-Farm");
                if (adp != null) score += Surprise(adp) * -1.5; // Strong jobs = bearish gold
                Print($"[AI] NFP | ADP score contribution: {score:+0.0;-0.0}");
            }
            // ── CPI ──────────────────────────────────────────────────────────
            else if (title.Contains("cpi") || title.Contains("consumer price"))
            {
                var ism = FindPrecursor("ISM Services");
                if (ism != null) score += Surprise(ism) * -1.0;
                Print($"[AI] CPI | ISM score contribution: {score:+0.0;-0.0}");
            }
            // ── PPI ──────────────────────────────────────────────────────────
            else if (title.Contains("ppi") || title.Contains("producer price"))
            {
                var cpi = FindPrecursor("CPI"); // CPI leads PPI trend
                if (cpi != null) score += Surprise(cpi) * -1.0;
                Print($"[AI] PPI | CPI precursor score contribution: {score:+0.0;-0.0}");
            }
            // ── Retail Sales ─────────────────────────────────────────────────
            else if (title.Contains("retail"))
            {
                var conf = FindPrecursor("Consumer Confidence");
                if (conf != null) score += Surprise(conf) * -1.5;
                Print($"[AI] Retail | Confidence score contribution: {score:+0.0;-0.0}");
            }
            // ── FOMC / Fed Rate ──────────────────────────────────────────────
            else if (title.Contains("fomc") || title.Contains("federal funds") || title.Contains("interest rate"))
            {
                var cpi = FindPrecursor("CPI");
                if (cpi != null) score += Surprise(cpi) * -1.0; // Hotter CPI = more hawkish = bearish gold
                Print($"[AI] FOMC | CPI precursor score contribution: {score:+0.0;-0.0}");
            }
            // ── GDP ──────────────────────────────────────────────────────────
            else if (title.Contains("gdp"))
            {
                var ism = FindPrecursor("ISM Manufacturing");
                if (ism != null) score += Surprise(ism) * -1.0;
                Print($"[AI] GDP | ISM Mfg score contribution: {score:+0.0;-0.0}");
            }
            // ── Generic fallback for anything else (PCE, Housing, etc.) ─────
            else
            {
                Print($"[AI] '{_targetEvent.Title}' — no specific precursor model. Defaulting bias to BUY.");
                score = 0;
            }

            if      (score > 0) _aiBias = TradeType.Buy;
            else if (score < 0) _aiBias = TradeType.Sell;
            else
            {
                _aiBias = TradeType.Buy;
                Print("[AI] Neutral score or no precursor data. Defaulting to BUY.");
            }

            _executionDirection = Role == AccountRole.HedgeAccount
                ? (_aiBias == TradeType.Buy ? TradeType.Sell : TradeType.Buy)
                : _aiBias;

            Print($"[AI] Final Bias: {_aiBias} | Role: {Role} | Executing: {_executionDirection}");
        }

        // Find the most recent published precursor event by keyword
        private FxEvent FindPrecursor(string keyword)
        {
            var match = _weeklyEvents
                .Where(e => e.Title.Contains(keyword, StringComparison.OrdinalIgnoreCase)
                         && e.Actual.HasValue
                         && e.EventTime < _targetEvent.EventTime)
                .OrderByDescending(e => e.EventTime)
                .FirstOrDefault();

            if (match == null)
                Print($"[AI] Precursor '{keyword}' not yet published this week.");

            return match;
        }

        // Returns +1 if actual beat forecast (hawkish/strong), -1 if missed, 0 if flat
        private static double Surprise(FxEvent e)
        {
            if (!e.Actual.HasValue || !e.Forecast.HasValue) return 0;
            return Math.Sign(e.Actual.Value - e.Forecast.Value);
        }

        #endregion

        #region Trading

        private void PrepareOrders(DateTime now)
        {
            if (now > _triggerTime) return;
            if ((_triggerTime - now).TotalSeconds > SecondsBefore) return;
            if (_ordersPlaced) return;
            if (_executionDirection == null)
            {
                Print("[Orders] Direction not resolved — retrying analysis.");
                LoadAndAnalyse();
                if (_executionDirection == null) return;
            }

            _ordersPlaced = true;

            double volume = _currentVolume;
            double lotQty = Symbol.VolumeInUnitsToQuantity(volume);
            Print($"[Orders] {_executionDirection} | {lotQty:F2} lots | Balance: {Account.Balance:C}");

            // No Take Profit — trailing stop manages the exit
            ExecuteMarketOrderAsync(_executionDirection.Value, SymbolName, volume,
                Label, StopLoss, null, Comment, result =>
                {
                    if (result.IsSuccessful)
                        Print($"[Order] Executed — {result.Position.Id} @ {result.Position.EntryPrice}");
                    else
                        Print("[Order] Failed: " + result.Error);
                });
        }

        #endregion

        #region Trailing Stop — mirrors News Trader Pro

        private void UpdateTrailingStops()
        {
            UpdateTrailForType(TradeType.Buy,  () => Symbol.Bid - TrailingStopStep * Symbol.PipSize);
            UpdateTrailForType(TradeType.Sell, () => Symbol.Ask + TrailingStopStep * Symbol.PipSize);
        }

        private void UpdateTrailForType(TradeType type, Func<double> calcSL)
        {
            foreach (var pos in Positions.FindAll(Label, SymbolName, type))
            {
                double distance = type == TradeType.Buy
                    ? Symbol.Bid - pos.EntryPrice
                    : pos.EntryPrice - Symbol.Ask;

                if (distance < TrailingStopTrigger * Symbol.PipSize) continue;

                double newSL     = calcSL();
                double tolerance = Symbol.PipSize;

                bool shouldModify = pos.StopLoss == null || (type == TradeType.Buy
                    ? newSL > pos.StopLoss.Value + tolerance
                    : newSL < pos.StopLoss.Value - tolerance);

                if (!shouldModify) continue;

                ModifyPosition(pos, newSL, pos.TakeProfit, ProtectionType.Absolute);
            }
        }

        #endregion

        #region UI — mirrors News Trader Pro

        private void UpdateUI(DateTime now)
        {
            TimeSpan remaining = _triggerTime - now;
            string countdown   = "Time left to news: " + FormatTime(remaining);
            TimeSpan toOrders  = remaining - TimeSpan.FromSeconds(SecondsBefore);
            countdown += "\nTime left to place orders: " + (toOrders > TimeSpan.Zero ? FormatTime(toOrders) : "0s");
            countdown += "\n";
            DrawStaticText(CountdownLabel, countdown, VerticalAlignment.Top, HorizontalAlignment.Right, Color.Red);

            double lotQty    = Symbol.VolumeInUnitsToQuantity(_currentVolume);
            double margin001 = Symbol.GetEstimatedMargin(TradeType.Buy, Symbol.QuantityToVolumeInUnits(0.01));
            double reqMargin = (lotQty / 0.01) * margin001;
            DrawStaticText(LotSizeLabel,
                $"Calculated Lot Size: {lotQty:F2} lots | Required Margin: ${reqMargin:F2}",
                VerticalAlignment.Top, HorizontalAlignment.Center, Color.Blue);

            DrawDashboard();
        }

        private void DrawDashboard()
        {
            if (_dashboardPanel != null) Chart.RemoveControl(_dashboardPanel);

            string eventName = _targetEvent != null ? _targetEvent.Title : $"No event at {NewsHour:D2}:{NewsMinute:D2}";
            string biasText  = _aiBias.HasValue ? _aiBias.Value.ToString().ToUpper() + (_aiBias == TradeType.Buy ? " ▲" : " ▼") : "Analysing...";
            string execText  = _executionDirection.HasValue ? _executionDirection.Value.ToString().ToUpper() : "---";
            Color  biasColor = _aiBias == TradeType.Buy ? Color.LimeGreen : (_aiBias == TradeType.Sell ? Color.Red : Color.Gray);
            Color  execColor = _executionDirection == TradeType.Buy ? Color.LimeGreen : Color.OrangeRed;
            Color  roleColor = Role == AccountRole.BiasAccount ? Color.DodgerBlue : Color.Orange;

            _dashboardPanel = new Border
            {
                BorderColor         = Color.DarkGoldenrod,
                BorderThickness     = new Thickness(1),
                BackgroundColor     = Color.FromArgb(220, 15, 15, 15),
                CornerRadius        = 5,
                HorizontalAlignment = HorizontalAlignment.Right,
                VerticalAlignment   = VerticalAlignment.Top,
                Margin              = new Thickness(0, 110, 10, 0),
                Padding             = new Thickness(10)
            };

            var panel = new StackPanel { Orientation = Orientation.Vertical };

            panel.AddChild(new TextBlock
            {
                Text                = "News Trader AI",
                ForegroundColor     = Color.DarkGoldenrod,
                FontWeight          = FontWeight.ExtraBold,
                HorizontalAlignment = HorizontalAlignment.Center,
                Margin              = new Thickness(0, 0, 0, 5)
            });

            panel.AddChild(Divider());
            panel.AddChild(Row("Role:",    Role.ToString(), roleColor));
            panel.AddChild(Row("Event:",   eventName,       Color.White));
            panel.AddChild(Row("AI Bias:", biasText,        biasColor));
            panel.AddChild(Row("Execute:", execText,        execColor));

            panel.AddChild(Divider());
            panel.AddChild(Row("Risk:",    $"{RiskPercentage}%",       Color.White));
            panel.AddChild(Row("SL:",      $"{StopLoss} pips",         Color.White));
            panel.AddChild(Row("Trigger:", $"{TrailingStopTrigger} pips", Color.White));
            panel.AddChild(Row("Trail:",   $"{TrailingStopStep} pips", Color.White));

            panel.AddChild(Divider());
            panel.AddChild(Row("Balance:", $"{Account.Balance:C}", Color.White));
            panel.AddChild(Row("Equity:",  $"{Account.Equity:C}",
                Account.Equity >= Account.Balance ? Color.LimeGreen : Color.OrangeRed));

            _dashboardPanel.Child = panel;
            Chart.AddControl(_dashboardPanel);
        }

        private static Border Divider() => new Border
        {
            BorderColor     = Color.DarkGoldenrod,
            BorderThickness = new Thickness(0, 0, 0, 1),
            Margin          = new Thickness(0, 4, 0, 4)
        };

        private static StackPanel Row(string label, string value, Color valueColor)
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 2, 0, 2) };
            row.AddChild(new TextBlock { Text = label, Width = 90, ForegroundColor = Color.LightGray });
            row.AddChild(new TextBlock { Text = value, ForegroundColor = valueColor, FontWeight = FontWeight.Bold });
            return row;
        }

        private void HideChartDisplays()
        {
            try { Chart.RemoveObject(CountdownLabel); } catch { }
            try { Chart.RemoveObject(LotSizeLabel);   } catch { }
            if (_dashboardPanel != null)
            {
                Chart.RemoveControl(_dashboardPanel);
                _dashboardPanel = null;
            }
        }

        private void DrawStaticText(string name, string text, VerticalAlignment va, HorizontalAlignment ha, Color color)
        {
            try { Chart.RemoveObject(name); } catch { }
            dynamic obj = Chart.DrawStaticText(name, text, va, ha, color);
            try { obj.FontSize = 15; obj.IsBold = true; } catch { }
        }

        #endregion

        #region Helpers

        private static double? ParseValue(string s)
        {
            if (string.IsNullOrWhiteSpace(s)) return null;
            s = s.Replace("%", "").Replace("K", "").Replace("M", "").Replace("B", "").Replace(",", "").Trim();
            return double.TryParse(s, out double val) ? val : (double?)null;
        }

        private static string FormatTime(TimeSpan t)
        {
            var sb = new System.Text.StringBuilder();
            if (t.TotalHours >= 1) sb.Append($"{(int)t.TotalHours}h ");
            if (t.Minutes    >= 1) sb.Append($"{t.Minutes}m ");
            if (t.Seconds    >  0) sb.Append($"{t.Seconds}s");
            return sb.ToString();
        }

        #endregion
    }
}