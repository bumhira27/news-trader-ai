using System;
using System.Linq;
using System.Net;
using System.Text;
using System.Xml;
using System.Collections.Generic;
using cAlgo.API;
using HorizontalAlignment = cAlgo.API.HorizontalAlignment;

namespace cAlgo.Robots
{
    public enum AccountRole { BiasAccount, HedgeAccount }

    internal class NewsEvent
    {
        public DateTime EventTime { get; set; }
        public string Title { get; set; }
        public string Currency { get; set; }
        public double? Actual { get; set; }
        public double? Forecast { get; set; }
    }

    [Robot(TimeZone = TimeZones.SouthAfricaStandardTime, AccessRights = AccessRights.FullAccess)]
    public class NewsTraderEA : Robot
    {
        private const string Label = "News Trader AI";
        
        #region Parameters

        [Parameter("Account Role", Group = "1. Setup", DefaultValue = AccountRole.BiasAccount)]
        public AccountRole Role { get; set; }

        [Parameter("Target News Hour", Group = "1. Setup", DefaultValue = 15, MinValue = 0, MaxValue = 23)]
        public int TargetHour { get; set; }

        [Parameter("Target News Minute", Group = "1. Setup", DefaultValue = 30, MinValue = 0, MaxValue = 59)]
        public int TargetMinute { get; set; }

        [Parameter("Risk Capital ($)", Group = "2. Risk", DefaultValue = 1000)]
        public double RiskCapital { get; set; }

        [Parameter("Seconds Before", Group = "2. Risk", DefaultValue = 3)]
        public int SecondsBefore { get; set; }

        #endregion

        private DateTime _targetTime = DateTime.MaxValue;
        private NewsEvent _targetEvent = null;
        private TradeType? _aiBias = null;
        private TradeType? _executionDirection = null;
        private bool _ordersPlaced = false;
        
        // Optimum Settings Holders
        private int _optimumSlPoints = 250;
        private int _optimumTpPoints = 1000;
        private double _optimumTrailTrigger = 500;
        private double _optimumTrailStep = 200;

        private List<NewsEvent> _weeklyEvents = new List<NewsEvent>();
        private Border _dashboard;
        private readonly string _ffUrl = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml";

        protected override void OnStart()
        {
            ServicePointManager.Expect100Continue = true;
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            
            Print("Initializing Autonomous C# Heuristic Engine...");
            LoadAndAnalyzeForexFactory();
            UpdateDashboard();
            
            Timer.Start(1);
        }

        protected override void OnTick()
        {
            UpdateTrailingStops();
        }

        protected override void OnTimer()
        {
            if (Positions.FindAll(Label, SymbolName).Any())
            {
                if (_dashboard != null) Chart.RemoveControl(_dashboard);
                return;
            }

            DateTime now = Server.Time;
            UpdateDashboard();

            if (_targetEvent != null && _executionDirection.HasValue && !_ordersPlaced)
            {
                if (now <= _targetTime && (_targetTime - now).TotalSeconds <= SecondsBefore)
                {
                    _ordersPlaced = true;
                    ExecuteStraddleOrder();
                }
            }
        }

        private void LoadAndAnalyzeForexFactory()
        {
            try
            {
                HttpResponse response = Http.Get(_ffUrl);
                if (!response.IsSuccessful)
                {
                    Print("Failed to fetch ForexFactory calendar.");
                    return;
                }

                var doc = new XmlDocument();
                doc.LoadXml(response.Body);
                _weeklyEvents.Clear();
                
                var pretoriaZone = TimeZoneInfo.FindSystemTimeZoneById("South Africa Standard Time");

                foreach (XmlNode node in doc.GetElementsByTagName("event"))
                {
                    string currency = node["country"]?.InnerText.Trim().ToUpper() ?? "";
                    if (currency != "USD") continue; // Only care about USD precursors and targets
                    
                    string title = node["title"]?.InnerText.Trim() ?? "";
                    string dateStr = node["date"]?.InnerText.Trim() ?? "";
                    string timeStr = node["time"]?.InnerText.Trim() ?? "";
                    
                    if (!DateTime.TryParse($"{dateStr} {timeStr}", out DateTime eventDtUtc)) continue;
                    DateTime localDt = TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(eventDtUtc, DateTimeKind.Utc), pretoriaZone);
                    
                    _weeklyEvents.Add(new NewsEvent
                    {
                        EventTime = localDt,
                        Title = title,
                        Currency = currency,
                        Actual = ParseDouble(node["actual"]?.InnerText),
                        Forecast = ParseDouble(node["forecast"]?.InnerText)
                    });
                }
                
                _weeklyEvents = _weeklyEvents.OrderBy(e => e.EventTime).ToList();

                // Find the Target Event based on user's inputted time
                _targetEvent = _weeklyEvents.FirstOrDefault(e => e.EventTime > Server.Time && e.EventTime.Hour == TargetHour && e.EventTime.Minute == TargetMinute);

                if (_targetEvent == null)
                {
                    Print($"[WARNING] No upcoming USD event found at {TargetHour:D2}:{TargetMinute:D2} this week.");
                    return;
                }

                Print($"[TARGET LOCKED] Found {_targetEvent.Title} at {_targetEvent.EventTime}");
                _targetTime = _targetEvent.EventTime;

                RunAiHeuristics(_targetEvent.Title);
            }
            catch (Exception ex)
            {
                Print("[API ERROR] " + ex.Message);
            }
        }

        private void RunAiHeuristics(string eventTitle)
        {
            double score = 0;
            string titleLower = eventTitle.ToLower();

            // AI MAGIC: Calculate bias natively based on precursor events in the same XML feed
            if (titleLower.Contains("farm") || titleLower.Contains("nfp"))
            {
                Print("[AI] Target is NFP. Scanning weekly feed for ADP precursor...");
                var adp = _weeklyEvents.FirstOrDefault(e => e.Title.Contains("ADP Non-Farm"));
                if (adp != null && adp.Actual.HasValue && adp.Forecast.HasValue)
                {
                    if (adp.Actual > adp.Forecast) { score -= 1.5; Print("[AI] ADP beat forecast. Bearish Gold."); }
                    else if (adp.Actual < adp.Forecast) { score += 1.5; Print("[AI] ADP missed forecast. Bullish Gold."); }
                }
                else Print("[AI] ADP precursor data not found or missing actuals.");
                
                // NFP Optimal Backtest Settings
                _optimumSlPoints = 250; _optimumTpPoints = 1500; _optimumTrailTrigger = 500; _optimumTrailStep = 200;
            }
            else if (titleLower.Contains("cpi") || titleLower.Contains("inflation"))
            {
                Print("[AI] Target is CPI. Scanning weekly feed for Services/Mfg precursor...");
                var ism = _weeklyEvents.FirstOrDefault(e => e.Title.Contains("ISM Services"));
                if (ism != null && ism.Actual.HasValue && ism.Forecast.HasValue)
                {
                    if (ism.Actual > ism.Forecast) { score -= 1.0; Print("[AI] ISM beat forecast. Bearish Gold."); }
                    else if (ism.Actual < ism.Forecast) { score += 1.0; Print("[AI] ISM missed forecast. Bullish Gold."); }
                }
                
                // CPI Optimal Backtest Settings (Wider SL for CPI whipsaws)
                _optimumSlPoints = 300; _optimumTpPoints = 1500; _optimumTrailTrigger = 600; _optimumTrailStep = 250;
            }
            else if (titleLower.Contains("retail"))
            {
                Print("[AI] Target is Retail Sales. Scanning weekly feed for Confidence precursor...");
                var conf = _weeklyEvents.FirstOrDefault(e => e.Title.Contains("Consumer Confidence"));
                if (conf != null && conf.Actual.HasValue && conf.Forecast.HasValue)
                {
                    if (conf.Actual > conf.Forecast) { score -= 1.5; Print("[AI] Confidence beat forecast. Bearish Gold."); }
                    else if (conf.Actual < conf.Forecast) { score += 1.5; Print("[AI] Confidence missed forecast. Bullish Gold."); }
                }
                
                // Retail Sales Optimal Backtest Settings (Tighter SL)
                _optimumSlPoints = 200; _optimumTpPoints = 1000; _optimumTrailTrigger = 400; _optimumTrailStep = 150;
            }
            else
            {
                // Fallback for unexpected events
                _optimumSlPoints = 250; _optimumTpPoints = 1000; _optimumTrailTrigger = 500; _optimumTrailStep = 200;
            }

            // Resolve Direction
            if (score > 0) _aiBias = TradeType.Buy;
            else if (score < 0) _aiBias = TradeType.Sell;
            else 
            {
                Print("[AI] Precursors flat or missing. Defaulting Bias to BUY. Use Hedge Account to cover.");
                _aiBias = TradeType.Buy;
            }

            _executionDirection = Role == AccountRole.HedgeAccount 
                ? (_aiBias == TradeType.Buy ? TradeType.Sell : TradeType.Buy) 
                : _aiBias;

            Print($"[AI] Final Bias: {_aiBias}. Account Role: {Role}. Executing: {_executionDirection}");
        }

        private void ExecuteStraddleOrder()
        {
            double lots = (RiskCapital / 4.0) * 0.01;
            double volume = Symbol.NormalizeVolumeInUnits(Symbol.QuantityToVolumeInUnits(lots), RoundingMode.ToNearest);

            Print($"[EXECUTE] Firing {_executionDirection} at {volume} Vol. SL: {_optimumSlPoints/10.0}pips");

            ExecuteMarketOrderAsync(_executionDirection.Value, SymbolName, volume, Label, _optimumSlPoints / 10.0, _optimumTpPoints / 10.0, "AI Auto", result =>
            {
                if (result.IsSuccessful) Print($"[Order] Fill: {result.Position.EntryPrice}");
                else Print("[Order] Failed: " + result.Error);
            });
        }

        private void UpdateTrailingStops()
        {
            foreach (var pos in Positions.FindAll(Label, SymbolName))
            {
                if (pos.TradeType == TradeType.Buy)
                {
                    double distance = Symbol.Bid - pos.EntryPrice;
                    if (distance < _optimumTrailTrigger * Symbol.TickSize) continue;
                    
                    double newSL = Symbol.Bid - _optimumTrailStep * Symbol.TickSize;
                    if (pos.StopLoss == null || newSL > pos.StopLoss.Value + Symbol.TickSize)
                        ModifyPosition(pos, newSL, pos.TakeProfit, ProtectionType.Absolute);
                }
                else
                {
                    double distance = pos.EntryPrice - Symbol.Ask;
                    if (distance < _optimumTrailTrigger * Symbol.TickSize) continue;
                    
                    double newSL = Symbol.Ask + _optimumTrailStep * Symbol.TickSize;
                    if (pos.StopLoss == null || newSL < pos.StopLoss.Value - Symbol.TickSize)
                        ModifyPosition(pos, newSL, pos.TakeProfit, ProtectionType.Absolute);
                }
            }
        }

        private double? ParseDouble(string s)
        {
            if (string.IsNullOrWhiteSpace(s)) return null;
            s = s.Replace("%", "").Replace("K", "").Replace("M", "").Replace("B", "").Replace(",", "").Trim();
            if (double.TryParse(s, out double val)) return val;
            return null;
        }

        private void UpdateDashboard()
        {
            if (_dashboard != null) Chart.RemoveControl(_dashboard);

            _dashboard = new Border
            {
                BorderColor = Color.Magenta, BorderThickness = new Thickness(2),
                BackgroundColor = Color.FromArgb(230, 15, 15, 15), CornerRadius = 5,
                HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Top,
                Margin = new Thickness(0, 50, 10, 0), Padding = new Thickness(15)
            };

            var panel = new StackPanel { Orientation = Orientation.Vertical };
            panel.AddChild(new TextBlock { Text = "News Trader AI (Native)", ForegroundColor = Color.Magenta, FontWeight = FontWeight.ExtraBold, HorizontalAlignment = HorizontalAlignment.Center });
            panel.AddChild(new Border { BorderColor = Color.Magenta, BorderThickness = new Thickness(0, 0, 0, 1), Margin = new Thickness(0, 5, 0, 5) });
            
            panel.AddChild(CreateRow("Role:", Role.ToString(), Role == AccountRole.BiasAccount ? "LimeGreen" : "Orange"));
            
            string eventName = _targetEvent != null ? _targetEvent.Title : $"Waiting for {TargetHour:D2}:{TargetMinute:D2}...";
            panel.AddChild(CreateRow("Event:", eventName, "White"));

            if (_targetEvent != null && _aiBias.HasValue)
            {
                panel.AddChild(CreateRow("AI Bias:", _aiBias.Value.ToString().ToUpper(), _aiBias.Value == TradeType.Buy ? "LimeGreen" : "Red"));
                panel.AddChild(CreateRow("Executing:", _executionDirection.Value.ToString().ToUpper(), _executionDirection.Value == TradeType.Buy ? "LimeGreen" : "Red"));
                panel.AddChild(CreateRow("Optimum SL:", $"{_optimumSlPoints} pts", "Cyan"));
                panel.AddChild(CreateRow("Optimum Trail:", $"{_optimumTrailTrigger}/{_optimumTrailStep}", "Cyan"));

                TimeSpan t = _targetTime - Server.Time;
                string countdown = t.TotalSeconds > 0 ? $"{t.Hours:D2}:{t.Minutes:D2}:{t.Seconds:D2}" : "FIRED";
                panel.AddChild(CreateRow("Countdown:", countdown, "Yellow"));
            }
            
            _dashboard.Child = panel;
            Chart.AddControl(_dashboard);
        }

        private StackPanel CreateRow(string label, string value, string colorHex)
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 3, 0, 3) };
            row.AddChild(new TextBlock { Text = label, Width = 100, ForegroundColor = Color.LightGray });
            row.AddChild(new TextBlock { Text = value, ForegroundColor = Color.FromName(colorHex), FontWeight = FontWeight.Bold });
            return row;
        }
    }
}