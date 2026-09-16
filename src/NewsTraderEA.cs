using System;
using System.Linq;
using System.Net;
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
        public string Title     { get; set; }
        public string Currency  { get; set; }
        public double? Actual   { get; set; }
        public double? Forecast { get; set; }
    }

    [Robot(TimeZone = TimeZones.SouthAfricaStandardTime, AccessRights = AccessRights.FullAccess)]
    public class NewsTraderEA : Robot
    {
        private const string Label   = "News Trader AI";
        private const string Comment = "by Tinotenda Bumhira";

        #region Parameters

        // ── Setup ────────────────────────────────────────────────────────────────────
        [Parameter("Account Role",        Group = "News",    DefaultValue = AccountRole.BiasAccount)]
        public AccountRole Role { get; set; }

        [Parameter("News Hour",           Group = "News",    DefaultValue = 15, MinValue = 0, MaxValue = 23)]
        public int NewsHour { get; set; }

        [Parameter("News Minute",         Group = "News",    DefaultValue = 30, MinValue = 0, MaxValue = 59)]
        public int NewsMinute { get; set; }

        [Parameter("Seconds Before",      Group = "News",    DefaultValue = 3,  MinValue = 1)]
        public int SecondsBefore { get; set; }

        // ── Risk Management ──────────────────────────────────────────────────────────
        [Parameter("Risk Capital ($)",    Group = "Risk Management", DefaultValue = 1000)]
        public double RiskCapital { get; set; }

        // ── Trade Settings (Backtested M1 Scalp Defaults) ────────────────────────────
        // No Take Profit — the trailing stop manages the full exit
        [Parameter("Stop Loss (pips)",    Group = "Trading", DefaultValue = 300)]
        public int StopLoss { get; set; }

        // ── Trailing Stop ─────────────────────────────────────────────────────────────
        [Parameter("Trailing Stop",       Group = "Trailing", DefaultValue = true)]
        public bool IncludeTrailingStop { get; set; }

        [Parameter("Trail Trigger (pips)", Group = "Trailing", DefaultValue = 500)]
        public double TrailingStopTrigger { get; set; }

        [Parameter("Trail Step (pips)",    Group = "Trailing", DefaultValue = 200)]
        public double TrailingStopStep { get; set; }

        #endregion

        #region Constants

        private const int    NewsTimeToleranceMinutes = 5;
        private const double MinMarginLevel           = 20.0;
        private readonly string _feedUrl = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml";
        private static readonly TimeZoneInfo _pretoriaZone =
            TimeZoneInfo.FindSystemTimeZoneById("South Africa Standard Time");

        #endregion

        #region Fields

        private DateTime  _triggerTime;
        private bool      _ordersPlaced;
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

            // Match News Trader Pro: set trigger time on startup so countdown works immediately
            var today = Server.Time;
            _triggerTime = new DateTime(today.Year, today.Month, today.Day, NewsHour, NewsMinute, 0);

            Print("[INIT] Fetching ForexFactory calendar and running AI analysis...");
            LoadAndAnalyse();
            DrawDashboard();

            Print($"[INIT] Account Balance: {Account.Balance:C} | Equity: {Account.Equity:C} | Role: {Role}");
        }

        protected override void OnTick()
        {
            // Margin guard — mirror News Trader Pro exactly
            if (Account.MarginLevel < MinMarginLevel)
            {
                foreach (var pos in Positions.FindAll(Label, SymbolName))
                {
                    Print($"[Safety] Margin {Account.MarginLevel:F1}% < {MinMarginLevel}% — closing position {pos.Id}");
                    ClosePosition(pos);
                }
            }

            if (IncludeTrailingStop)
                UpdateTrailingStops();

            if (Positions.FindAll(Label, SymbolName).Any())
                HideChartDisplays();
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

                // Rebuild trigger time daily (same as News Trader Pro)
                _triggerTime = new DateTime(now.Year, now.Month, now.Day, NewsHour, NewsMinute, 0);

                // Reset ordersPlaced flag after event window passes (5 min tolerance)
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
                    Print("[FF] Rate limited — will retry on next timer cycle");
                    return;
                }

                var doc = new XmlDocument();
                doc.LoadXml(xml);

                _weeklyEvents.Clear();

                foreach (XmlNode node in doc.GetElementsByTagName("event"))
                {
                    string currency = node["country"]?.InnerText.Trim().ToUpper() ?? "";
                    if (currency != "USD") continue;

                    string title   = node["title"]?.InnerText.Trim() ?? "";
                    string dateStr = node["date"]?.InnerText.Trim()  ?? "";
                    string timeStr = node["time"]?.InnerText.Trim()  ?? "";

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
                Print($"[FF] Loaded {_weeklyEvents.Count} USD events this week.");

                // Match user-configured time to an event
                _targetEvent = _weeklyEvents.FirstOrDefault(e =>
                    e.EventTime > Server.Time &&
                    e.EventTime.Hour   == NewsHour &&
                    e.EventTime.Minute == NewsMinute);

                if (_targetEvent == null)
                {
                    Print($"[FF] No USD event found at {NewsHour:D2}:{NewsMinute:D2}. Check ForexFactory.");
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

            double score     = 0;
            string title     = _targetEvent.Title.ToLower();

            // ─── NFP ────────────────────────────────────────────────────────────────
            if (title.Contains("farm") || title.Contains("nfp"))
            {
                var adp = _weeklyEvents.FirstOrDefault(e => e.Title.Contains("ADP Non-Farm") && e.Actual.HasValue);
                if (adp != null)
                {
                    double surprise = adp.Actual.Value - (adp.Forecast ?? adp.Actual.Value);
                    // Strong jobs = hawkish Fed = stronger USD = bearish gold
                    score -= Math.Sign(surprise) * 1.5;
                    Print($"[AI] NFP | ADP surprise: {surprise:+0.0;-0.0} → score {score:+0.0;-0.0}");
                }
                else Print("[AI] NFP | ADP precursor not yet published this week.");
            }
            // ─── CPI ────────────────────────────────────────────────────────────────
            else if (title.Contains("cpi"))
            {
                var ism = _weeklyEvents.FirstOrDefault(e => e.Title.Contains("ISM Services") && e.Actual.HasValue);
                if (ism != null)
                {
                    double surprise = ism.Actual.Value - (ism.Forecast ?? ism.Actual.Value);
                    score -= Math.Sign(surprise) * 1.0;
                    Print($"[AI] CPI | ISM Services surprise: {surprise:+0.0;-0.0} → score {score:+0.0;-0.0}");
                }
                else Print("[AI] CPI | ISM Services precursor not yet published this week.");
            }
            // ─── Retail Sales ───────────────────────────────────────────────────────
            else if (title.Contains("retail"))
            {
                var conf = _weeklyEvents.FirstOrDefault(e => e.Title.Contains("Consumer Confidence") && e.Actual.HasValue);
                if (conf != null)
                {
                    double surprise = conf.Actual.Value - (conf.Forecast ?? conf.Actual.Value);
                    score -= Math.Sign(surprise) * 1.5;
                    Print($"[AI] Retail | Conf surprise: {surprise:+0.0;-0.0} → score {score:+0.0;-0.0}");
                }
                else Print("[AI] Retail | Consumer Confidence not yet published this week.");
            }

            // Resolve AI directional bias
            if      (score > 0) _aiBias = TradeType.Buy;
            else if (score < 0) _aiBias = TradeType.Sell;
            else
            {
                Print("[AI] No precursor divergence. Defaulting to BUY for BiasAccount.");
                _aiBias = TradeType.Buy;
            }

            // Hedge account inverts the bias
            _executionDirection = Role == AccountRole.HedgeAccount
                ? (_aiBias == TradeType.Buy ? TradeType.Sell : TradeType.Buy)
                : _aiBias;

            Print($"[AI] AI Bias: {_aiBias} | Account: {Role} | Will Execute: {_executionDirection}");
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
                Print("[Orders] No direction resolved yet — rerunning analysis.");
                LoadAndAnalyse();
                if (_executionDirection == null) return;
            }

            _ordersPlaced = true;

            // Lot sizing — mirror blueprint: 0.01 lots per $4 risk capital
            double lots   = (RiskCapital / 4.0) * 0.01;
            double volume = Symbol.NormalizeVolumeInUnits(
                Symbol.QuantityToVolumeInUnits(lots), RoundingMode.ToNearest);

            Print($"[Orders] Placing {_executionDirection} | {lots:F2} lots | Balance: {Account.Balance:C} | Equity: {Account.Equity:C}");

            ExecuteMarketOrderAsync(_executionDirection.Value, SymbolName, volume,
                Label, StopLoss, null, Comment, result =>
                {
                    if (result.IsSuccessful)
                        Print($"[Order] Executed — Position {result.Position.Id} @ {result.Position.EntryPrice}");
                    else
                        Print("[Order] Failed: " + result.Error);
                });
        }

        #endregion

        #region Trailing Stop  (mirrored from News Trader Pro)

        private void UpdateTrailingStops()
        {
            UpdateTrailForType(TradeType.Buy,
                () => Symbol.Bid - TrailingStopStep * Symbol.PipSize);
            UpdateTrailForType(TradeType.Sell,
                () => Symbol.Ask + TrailingStopStep * Symbol.PipSize);
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

        #region UI  (mirrored from News Trader Pro)

        private void UpdateUI(DateTime now)
        {
            TimeSpan remaining = _triggerTime - now;
            string countdown   = "Time left to news: " + FormatTime(remaining);
            TimeSpan toOrders  = remaining - TimeSpan.FromSeconds(SecondsBefore);
            countdown += "\nTime left to place orders: " + (toOrders > TimeSpan.Zero ? FormatTime(toOrders) : "0s");
            countdown += "\n";
            DrawStaticText(CountdownLabel, countdown, VerticalAlignment.Top, HorizontalAlignment.Right, Color.Red);

            double lots      = (RiskCapital / 4.0) * 0.01;
            double margin001 = Symbol.GetEstimatedMargin(TradeType.Buy, Symbol.QuantityToVolumeInUnits(0.01));
            double reqMargin = (lots / 0.01) * margin001;
            DrawStaticText(LotSizeLabel,
                $"Lot Size: {lots:F2} | Margin: ${reqMargin:F0} | Balance: {Account.Balance:C} | Equity: {Account.Equity:C}",
                VerticalAlignment.Top, HorizontalAlignment.Center, Color.DeepSkyBlue);

            DrawDashboard();
        }

        private void DrawDashboard()
        {
            if (_dashboardPanel != null)
                Chart.RemoveControl(_dashboardPanel);

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
            panel.AddChild(Row("Account Role:", Role.ToString(),  roleColor));
            panel.AddChild(Row("Event:",        eventName,        Color.White));
            panel.AddChild(Row("AI Bias:",      biasText,         biasColor));
            panel.AddChild(Row("Executing:",    execText,         execColor));

            panel.AddChild(Divider());
            panel.AddChild(Row("SL:",     $"{StopLoss} pips  (trailing manages exit)", Color.White));
            panel.AddChild(Row("Trigger:", $"{TrailingStopTrigger} pips",              Color.White));
            panel.AddChild(Row("Trail:",   $"{TrailingStopStep} pips",                 Color.White));

            panel.AddChild(Divider());
            panel.AddChild(Row("Balance:", $"{Account.Balance:C}",  Color.White));
            panel.AddChild(Row("Equity:",  $"{Account.Equity:C}",   Account.Equity >= Account.Balance ? Color.LimeGreen : Color.OrangeRed));

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
            row.AddChild(new TextBlock { Text = label, Width = 95, ForegroundColor = Color.LightGray });
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