using System;
using System.Linq;
using System.Text;
using System.Xml;
using System.IO;
using System.Globalization;
using System.Collections.Generic;
using cAlgo.API;
using HorizontalAlignment = cAlgo.API.HorizontalAlignment;

namespace cAlgo.Robots
{
    public enum AccountRole { BiasAccount, HedgeAccount, Manual }
    public enum TradeDirection { Buy, Sell }

    internal class NewsEventInfo
    {
        public DateTime EventTime { get; set; }
        public string Title { get; set; }
        public string Currency { get; set; }
    }

    [Robot(TimeZone = TimeZones.SouthAfricaStandardTime, AccessRights = AccessRights.FullAccess)]
    public class NewsTraderEA : Robot
    {
        private const string Label = "News Trader AI";
        private const string Comment = "Autonomous Straddle EA";

        #region Parameters

        [Parameter("Account Role", Group = "AI & Strategy", DefaultValue = AccountRole.BiasAccount)]
        public AccountRole Role { get; set; }

        [Parameter("AI Bias File Path", Group = "AI & Strategy", DefaultValue = @"C:\news_bias.txt")]
        public string BiasFilePath { get; set; }

        [Parameter("Manual Direction", Group = "AI & Strategy", DefaultValue = TradeDirection.Buy)]
        public TradeDirection ManualDirection { get; set; }

        [Parameter("Trade Holy Trinity Only", Group = "AI & Strategy", DefaultValue = true)]
        public bool HolyTrinityOnly { get; set; }

        [Parameter("Risk Capital ($)", Group = "Risk Management", DefaultValue = 1000)]
        public double RiskCapital { get; set; }

        [Parameter("Take Profit (points)", Group = "Execution", DefaultValue = 1000)]
        public int TakeProfitPoints { get; set; }

        [Parameter("Stop Loss (points)", Group = "Execution", DefaultValue = 250)]
        public int StopLossPoints { get; set; }

        [Parameter("Seconds Before", Group = "Execution", DefaultValue = 3)]
        public int SecondsBefore { get; set; }

        [Parameter("Trailing Stop", Group = "Trailing", DefaultValue = true)]
        public bool IncludeTrailingStop { get; set; }

        [Parameter("Trailing Trigger (points)", Group = "Trailing", DefaultValue = 500)]
        public double TrailingStopTrigger { get; set; }

        [Parameter("Trailing Step (points)", Group = "Trailing", DefaultValue = 200)]
        public double TrailingStopStep { get; set; }

        #endregion

        #region Fields

        private DateTime _triggerTime = DateTime.MaxValue;
        private NewsEventInfo _activeEvent = null;
        private bool _ordersPlaced;
        private TradeType? _resolvedDirection;
        private Border _dashboardPanel;
        
        private readonly string _feedUrl = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml";
        private static readonly TimeZoneInfo _pretoriaZone = TimeZoneInfo.FindSystemTimeZoneById("South Africa Standard Time");
        private List<NewsEventInfo> _newsEvents = new List<NewsEventInfo>();

        #endregion

        protected override void OnStart()
        {
            Timer.Start(1);
            LoadNewsEvents();
            UpdateDashboard();
            Print($"[INIT] Started as {Role}. Risk Capital: ${RiskCapital}");
        }

        protected override void OnTick()
        {
            if (IncludeTrailingStop)
                UpdateTrailingStops();

            if (Positions.FindAll(Label, SymbolName).Any())
            {
                if (_dashboardPanel != null)
                {
                    Chart.RemoveControl(_dashboardPanel);
                    _dashboardPanel = null;
                }
            }
        }

        protected override void OnTimer()
        {
            try
            {
                if (Positions.FindAll(Label, SymbolName).Any()) return;

                DateTime now = Server.Time;

                // Reload calendar every hour
                if (now.Minute == 0 && now.Second == 0)
                    LoadNewsEvents();

                // Find next event
                _activeEvent = _newsEvents.FirstOrDefault(e => e.EventTime > now);
                if (_activeEvent != null)
                {
                    _triggerTime = _activeEvent.EventTime;
                    ResolveDirection(now);
                    PrepareOrders(now);
                }

                UpdateDashboard();
            }
            catch (Exception ex)
            {
                Print("[OnTimer] " + ex);
            }
        }

        private void ResolveDirection(DateTime now)
        {
            if ((_triggerTime - now).TotalMinutes > 60)
            {
                _resolvedDirection = null; // Wait until 1 hour before news to lock in bias
                return;
            }

            if (_resolvedDirection != null) return; // Already resolved

            if (Role == AccountRole.Manual)
            {
                _resolvedDirection = ManualDirection == TradeDirection.Buy ? TradeType.Buy : TradeType.Sell;
                Print($"[AI] Manual direction set: {_resolvedDirection}");
                return;
            }

            // Autonomous Mode: Read AI Bias File
            try
            {
                if (File.Exists(BiasFilePath))
                {
                    string content = File.ReadAllText(BiasFilePath).Trim().ToUpper();
                    TradeType aiBias = content.Contains("BUY") ? TradeType.Buy : TradeType.Sell;
                    
                    if (Role == AccountRole.HedgeAccount)
                    {
                        _resolvedDirection = aiBias == TradeType.Buy ? TradeType.Sell : TradeType.Buy;
                        Print($"[AI] HEDGE Mode: AI predicted {aiBias}, we will execute {_resolvedDirection}");
                    }
                    else
                    {
                        _resolvedDirection = aiBias;
                        Print($"[AI] BIAS Mode: AI predicted {aiBias}, we will execute {_resolvedDirection}");
                    }
                }
                else
                {
                    Print($"[AI WARNING] Bias file not found at {BiasFilePath}. Waiting...");
                }
            }
            catch (Exception ex)
            {
                Print("[AI Error] " + ex.Message);
            }
        }

        private void PrepareOrders(DateTime now)
        {
            if (now > _triggerTime || _resolvedDirection == null) return;
            if ((_triggerTime - now).TotalSeconds > SecondsBefore) return;
            if (_ordersPlaced) return;

            _ordersPlaced = true;
            
            // Lot size math based on audited straddle: 0.01 lots per $4 risk
            // 250 point SL = 25 pips = $2.50 risk per 0.01 lot + slippage buffer
            double lots = (RiskCapital / 4.0) * 0.01;
            double volume = Symbol.NormalizeVolumeInUnits(Symbol.QuantityToVolumeInUnits(lots), RoundingMode.ToNearest);

            Print($"[EXECUTE] Triggering {_resolvedDirection} at {volume} volume.");

            ExecuteMarketOrderAsync(_resolvedDirection.Value, SymbolName, volume, Label, StopLossPoints / 10.0, TakeProfitPoints / 10.0, Comment, result =>
            {
                if (result.IsSuccessful)
                    Print($"[Order] Success — Position {result.Position.Id}");
                else
                    Print("[Order] Failed: " + result.Error);
            });
        }

        private void LoadNewsEvents()
        {
            try
            {
                HttpResponse response = Http.Get(_feedUrl);
                if (!response.IsSuccessful) return;

                var doc = new XmlDocument();
                doc.LoadXml(response.Body);
                _newsEvents.Clear();

                foreach (XmlNode node in doc.GetElementsByTagName("event"))
                {
                    if (!(node["impact"]?.InnerText.Trim() ?? "").Equals("High", StringComparison.OrdinalIgnoreCase)) continue;

                    string title = node["title"]?.InnerText.Trim() ?? "";
                    string currency = node["country"]?.InnerText.Trim().ToUpper() ?? "";
                    string dateStr = node["date"]?.InnerText.Trim() ?? "";
                    string timeStr = node["time"]?.InnerText.Trim() ?? "";

                    if (!DateTime.TryParse($"{dateStr} {timeStr}", out DateTime eventDt)) continue;
                    
                    DateTime eventLocal = TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(eventDt, DateTimeKind.Utc), _pretoriaZone);

                    if (eventLocal < Server.Time) continue;
                    if (string.IsNullOrEmpty(currency) || !SymbolName.ToUpper().Contains(currency)) continue;

                    if (HolyTrinityOnly)
                    {
                        bool isTrinity = title.Contains("Non-Farm") || title.Contains("CPI") || title.Contains("Retail Sales");
                        if (!isTrinity) continue;
                    }

                    _newsEvents.Add(new NewsEventInfo { EventTime = eventLocal, Title = title, Currency = currency });
                }
                
                _newsEvents = _newsEvents.OrderBy(e => e.EventTime).ToList();
            }
            catch (Exception ex)
            {
                Print("[News Load Error] " + ex.Message);
            }
        }

        private void UpdateTrailingStops()
        {
            foreach (var pos in Positions.FindAll(Label, SymbolName))
            {
                if (pos.TradeType == TradeType.Buy)
                {
                    double distance = Symbol.Bid - pos.EntryPrice;
                    if (distance < TrailingStopTrigger * Symbol.TickSize) continue;
                    
                    double newSL = Symbol.Bid - TrailingStopStep * Symbol.TickSize;
                    if (pos.StopLoss == null || newSL > pos.StopLoss.Value + Symbol.TickSize)
                        ModifyPosition(pos, newSL, pos.TakeProfit, ProtectionType.Absolute);
                }
                else
                {
                    double distance = pos.EntryPrice - Symbol.Ask;
                    if (distance < TrailingStopTrigger * Symbol.TickSize) continue;
                    
                    double newSL = Symbol.Ask + TrailingStopStep * Symbol.TickSize;
                    if (pos.StopLoss == null || newSL < pos.StopLoss.Value - Symbol.TickSize)
                        ModifyPosition(pos, newSL, pos.TakeProfit, ProtectionType.Absolute);
                }
            }
        }

        private void UpdateDashboard()
        {
            if (_dashboardPanel != null) Chart.RemoveControl(_dashboardPanel);

            _dashboardPanel = new Border
            {
                BorderColor = Color.DodgerBlue,
                BorderThickness = new Thickness(1),
                BackgroundColor = Color.FromArgb(220, 15, 15, 15),
                CornerRadius = 5,
                HorizontalAlignment = HorizontalAlignment.Right,
                VerticalAlignment = VerticalAlignment.Top,
                Margin = new Thickness(0, 50, 10, 0),
                Padding = new Thickness(10)
            };

            var panel = new StackPanel { Orientation = Orientation.Vertical };
            panel.AddChild(new TextBlock { Text = "News Trader AI", ForegroundColor = Color.DodgerBlue, FontWeight = FontWeight.ExtraBold, HorizontalAlignment = HorizontalAlignment.Center });
            
            panel.AddChild(new Border { BorderColor = Color.DodgerBlue, BorderThickness = new Thickness(0, 0, 0, 1), Margin = new Thickness(0, 4, 0, 4) });
            
            string roleColor = Role == AccountRole.BiasAccount ? "LimeGreen" : (Role == AccountRole.HedgeAccount ? "Orange" : "White");
            panel.AddChild(CreateRow("Account Role:", Role.ToString(), roleColor));
            
            string dirTxt = _resolvedDirection.HasValue ? _resolvedDirection.Value.ToString().ToUpper() : "WAITING FOR AI...";
            panel.AddChild(CreateRow("AI Direction:", dirTxt, _resolvedDirection == TradeType.Buy ? "LimeGreen" : "Red"));
            
            string nextEvent = _activeEvent != null ? $"{_activeEvent.Title} ({_activeEvent.EventTime:HH:mm})" : "NONE";
            panel.AddChild(CreateRow("Next Target:", nextEvent, "Cyan"));
            
            if (_activeEvent != null)
            {
                TimeSpan t = _activeEvent.EventTime - Server.Time;
                string tStr = t.TotalSeconds > 0 ? $"{t.Hours:D2}:{t.Minutes:D2}:{t.Seconds:D2}" : "EXECUTION IMMINENT";
                panel.AddChild(CreateRow("Countdown:", tStr, "Yellow"));
            }

            _dashboardPanel.Child = panel;
            Chart.AddControl(_dashboardPanel);
        }

        private StackPanel CreateRow(string label, string value, string colorHex)
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 2, 0, 2) };
            row.AddChild(new TextBlock { Text = label, Width = 100, ForegroundColor = Color.LightGray });
            row.AddChild(new TextBlock { Text = value, ForegroundColor = Color.FromName(colorHex), FontWeight = FontWeight.Bold });
            return row;
        }
    }
}