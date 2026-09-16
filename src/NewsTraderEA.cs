using System;
using System.Linq;
using System.Text;
using System.Xml;
using System.Globalization;
using System.Collections.Generic;
using cAlgo.API;
using HorizontalAlignment = cAlgo.API.HorizontalAlignment;

namespace cAlgo.Robots
{
    public enum AccountRole { BiasAccount, HedgeAccount }

    public enum TradeLogicOption { SingleOrder, OrderSplitting }

    public interface ITradeStrategy
    {
        List<double> CalculateOrderVolumes(double initialLotSize, Random random);
    }

    public class SingleOrderStrategy : ITradeStrategy
    {
        public List<double> CalculateOrderVolumes(double initialLotSize, Random random)
            => new List<double> { Math.Round(initialLotSize, 2) };
    }

    public class OrderSplittingStrategy : ITradeStrategy
    {
        public List<double> CalculateOrderVolumes(double initialLotSize, Random random)
        {
            if (initialLotSize <= 1.0)
                return new List<double> { Math.Round(initialLotSize, 2) };

            var    volumes          = new List<double>();
            int    splitFactor      = random.Next(10, 21);
            double rawBase          = initialLotSize / splitFactor;
            double normalizedBase   = Math.Round(rawBase, 2);

            if ((normalizedBase * (splitFactor - 1)) > initialLotSize)
                normalizedBase = Math.Floor(rawBase / 0.01) * 0.01;

            for (int i = 0; i < splitFactor - 1; i++)
                volumes.Add(normalizedBase);

            volumes.Add(initialLotSize - volumes.Sum());
            return volumes;
        }
    }

    internal class NewsEventInfo
    {
        public DateTime EventTime { get; set; }
        public string   Title     { get; set; }
        public string   Currency  { get; set; }
        public double?  Actual    { get; set; }
        public double?  Forecast  { get; set; }
    }

    [Robot(TimeZone = TimeZones.SouthAfricaStandardTime, AccessRights = AccessRights.None)]
    public class NewsTraderEA : Robot
    {
        private const string Label   = "News Trader AI";
        private const string Comment = "by Tinotenda Bumhira";

        #region Parameters

        [Parameter("News Hour",               Group = "News",            DefaultValue = 15,  MinValue = 0,   MaxValue = 23)]
        public int NewsHour { get; set; }

        [Parameter("News Minute",             Group = "News",            DefaultValue = 30,  MinValue = 0,   MaxValue = 59)]
        public int NewsMinute { get; set; }

        [Parameter("Account Role",            Group = "News")]
        public AccountRole Role { get; set; }

        [Parameter("Stop Loss (pips)",        Group = "News",            DefaultValue = 300)]
        public int StopLoss { get; set; }

        [Parameter("Risk Percentage",         Group = "Risk Management", DefaultValue = 80,  MinValue = 1,   MaxValue = 100)]
        public double RiskPercentage { get; set; }

        [Parameter("Seconds Before",          Group = "News",            DefaultValue = 3,   MinValue = 1)]
        public int SecondsBefore { get; set; }

        [Parameter("Trailing Stop",           Group = "Trailing",        DefaultValue = true)]
        public bool IncludeTrailingStop { get; set; }

        [Parameter("Trailing Trigger (pips)", Group = "Trailing",        DefaultValue = 500)]
        public double TrailingStopTriggerPip { get; set; }

        [Parameter("Trailing Step (pips)",    Group = "Trailing",        DefaultValue = 200)]
        public double TrailingStopStepPip { get; set; }

        [Parameter("Trade Logic",             Group = "Trading Options", DefaultValue = TradeLogicOption.SingleOrder)]
        public TradeLogicOption TradeLogic { get; set; }

        #endregion

        #region Constants

        private const int    NewsUpdateIntervalSeconds = 300;
        private const int    NewsTimeToleranceMinutes  = 5;
        private const double MinMarginLevel            = 20.0;
        private const double LotSizeLogThreshold       = 0.02;

        private readonly string _feedUrl = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml";

        private static readonly TimeZoneInfo _pretoriaZone =
            TimeZoneInfo.FindSystemTimeZoneById("South Africa Standard Time");

        #endregion

        #region Fields

        private DateTime       _triggerTime;
        private double         _currentLotSize;
        private double         _previousCalculatedLots = -1;
        private Random         _random;
        private DateTime       _lastNewsUpdate      = DateTime.MinValue;
        private DateTime       _lastLotSizeCalcTime = DateTime.MinValue;
        private double         _cachedLotSize;
        private double         _lastLoggedLotSize;
        private bool           _ordersPlaced;
        private List<double>   _orderVolumes;
        private ITradeStrategy _tradeStrategy;
        private Border         _dashboardPanel;

        // AI-specific fields
        private TradeType?         _aiBias            = null;
        private TradeType?         _executionDirection = null;
        private List<NewsEventInfo> _allWeeklyEvents   = new List<NewsEventInfo>();
        private NewsEventInfo       _targetEvent        = null;

        // Display labels
        private const string CountdownLabel = "countdown";
        private const string LotSizeLabel   = "lotsize";
        private const string NewsLabel      = "NewsEventsLabel";

        #endregion

        #region Lifecycle

        protected override void OnStart()
        {
            Timer.Start(1);
            _random         = new Random();
            _currentLotSize = CalculateLotSize();

            _tradeStrategy = TradeLogic switch
            {
                TradeLogicOption.SingleOrder    => new SingleOrderStrategy(),
                TradeLogicOption.OrderSplitting => new OrderSplittingStrategy(),
                _                               => throw new ArgumentOutOfRangeException()
            };

            UpdateOrderVolumesIfChanged();

            LoadNewsEvents();
            DisplayNewsEvents();
            _lastNewsUpdate = Server.Time;
        }

        protected override void OnTick()
        {
            try
            {
                // 1. Trail stops first
                if (IncludeTrailingStop)
                    UpdateTrailingStops();

                bool hasPositions = Positions.FindAll(Label, SymbolName).Any();

                // 2. Margin safety check MUST happen BEFORE the early return
                if (hasPositions && Account.MarginLevel < MinMarginLevel)
                {
                    foreach (var pos in Positions.FindAll(Label, SymbolName))
                    {
                        Print($"[Safety] Margin < {MinMarginLevel}% — closing position {pos.Id}");
                        ClosePosition(pos);
                    }
                    hasPositions = false; // Reset since we just closed them
                }

                // 3. Early return to hide UI while in a trade
                if (hasPositions)
                {
                    HideChartDisplays();
                    return;
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
                CheckEventTime(now);
                UpdateUI(now);

                _currentLotSize = CalculateLotSize();
                UpdateOrderVolumesIfChanged();

                PrepareOrders(now);
            }
            catch (Exception ex)
            {
                Print("[OnTimer] " + ex);
            }
        }

        #endregion

        #region Trading

        private void CheckEventTime(DateTime now)
        {
            if (now > _triggerTime.AddMinutes(NewsTimeToleranceMinutes))
                _ordersPlaced = false;

            _triggerTime = new DateTime(now.Year, now.Month, now.Day, NewsHour, NewsMinute, 0);
        }

        private void UpdateOrderVolumesIfChanged()
        {
            double updatedLots = Symbol.VolumeInUnitsToQuantity(_currentLotSize);
            if (Math.Abs(updatedLots - _previousCalculatedLots) > 0.001)
            {
                _orderVolumes = _tradeStrategy.CalculateOrderVolumes(updatedLots, _random);
                _previousCalculatedLots = updatedLots;
                if (TradeLogic != TradeLogicOption.SingleOrder)
                    Print($"[Strategy] Order splits regenerated: {string.Join(", ", _orderVolumes.Select(v => v.ToString("F2")))} lots");
            }
        }

        private void PrepareOrders(DateTime now)
        {
            if (now > _triggerTime) return;
            if ((_triggerTime - now).TotalSeconds > SecondsBefore) return;
            if (_ordersPlaced) return;
            if (_executionDirection == null)
            {
                Print("[Orders] AI direction is SKIP/Unresolved. Standing down.");
                _ordersPlaced = true; // Prevent spamming logs, we've decided not to trade this cycle
                return;
            }

            _ordersPlaced = true;

            Print($"[Orders] Placing {TradeLogic} orders as {Role}: {string.Join(", ", _orderVolumes.Select(v => v.ToString("F2")))} lots | Direction: {_executionDirection}");

            foreach (double lot in _orderVolumes)
            {
                double volume = Symbol.NormalizeVolumeInUnits(Symbol.QuantityToVolumeInUnits(lot), RoundingMode.ToNearest);
                PlaceOrder(_executionDirection.Value, volume);
            }
        }

        private void PlaceOrder(TradeType type, double volume)
        {
            ExecuteMarketOrderAsync(type, SymbolName, volume, Label, StopLoss, null, Comment, result =>
            {
                if (result.IsSuccessful)
                    Print($"[Order] Executed — Position {result.Position.Id} @ {result.Position.EntryPrice}");
                else
                    Print("[Order] Failed: " + result.Error);
            });
        }

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

        #region Trailing Stop

        private void UpdateTrailingStops()
        {
            UpdateTrailingForType(TradeType.Buy,  () => Symbol.Bid - TrailingStopStepPip * Symbol.PipSize);
            UpdateTrailingForType(TradeType.Sell, () => Symbol.Ask + TrailingStopStepPip * Symbol.PipSize);
        }

        private void UpdateTrailingForType(TradeType type, Func<double> calcSL)
        {
            foreach (var pos in Positions.FindAll(Label, SymbolName, type))
            {
                double distance = type == TradeType.Buy
                    ? Symbol.Bid - pos.EntryPrice
                    : pos.EntryPrice - Symbol.Ask;

                if (distance < TrailingStopTriggerPip * Symbol.PipSize) continue;

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

        #region AI Heuristics

        private void RunAiHeuristics()
        {
            if (_targetEvent == null) return;

            double score = 0;
            string title = _targetEvent.Title.ToLower();
            bool hasPrecursor = false;

            if (title.Contains("non-farm") || title.Contains("nfp"))
            {
                var adp = FindPrecursor("ADP Non-Farm");
                if (adp != null) { score += Surprise(adp) * -1.5; hasPrecursor = true; Print($"[AI] NFP | ADP surprise → score {score:+0.0;-0.0}"); }
                else Print("[AI] NFP | ADP not yet published this week.");
            }
            else if (title.Contains("cpi") || title.Contains("consumer price"))
            {
                var ism = FindPrecursor("ISM Services");
                if (ism != null) { score += Surprise(ism) * -1.0; hasPrecursor = true; Print($"[AI] CPI | ISM Services surprise → score {score:+0.0;-0.0}"); }
                else Print("[AI] CPI | ISM Services not yet published this week.");
            }
            else if (title.Contains("ppi") || title.Contains("producer price"))
            {
                var cpi = FindPrecursor("CPI");
                if (cpi != null) { score += Surprise(cpi) * -1.0; hasPrecursor = true; Print($"[AI] PPI | CPI precursor → score {score:+0.0;-0.0}"); }
                else Print("[AI] PPI | CPI not yet published this week.");
            }
            else if (title.Contains("retail"))
            {
                var conf = FindPrecursor("Consumer Confidence");
                if (conf != null) { score += Surprise(conf) * -1.5; hasPrecursor = true; Print($"[AI] Retail | Confidence surprise → score {score:+0.0;-0.0}"); }
                else Print("[AI] Retail | Consumer Confidence not yet published this week.");
            }
            else if (title.Contains("fomc") || title.Contains("federal funds") || title.Contains("interest rate"))
            {
                var cpi = FindPrecursor("CPI");
                if (cpi != null) { score += Surprise(cpi) * -1.0; hasPrecursor = true; Print($"[AI] FOMC | CPI precursor → score {score:+0.0;-0.0}"); }
                else Print("[AI] FOMC | CPI not yet published this week.");
            }
            else if (title.Contains("gdp"))
            {
                var ism = FindPrecursor("ISM Manufacturing");
                if (ism != null) { score += Surprise(ism) * -1.0; hasPrecursor = true; Print($"[AI] GDP | ISM Mfg → score {score:+0.0;-0.0}"); }
                else Print("[AI] GDP | ISM Manufacturing not yet published this week.");
            }
            else
            {
                Print($"[AI] '{_targetEvent.Title}' — no specific precursor model. Skipping trade.");
            }

            if (!hasPrecursor || score == 0)
            {
                Print("[AI] No precursor data or neutral score. Bias is SKIP (No Trade).");
                _aiBias = null;
                _executionDirection = null;
                return;
            }

            if (score > 0) _aiBias = TradeType.Buy;
            if (score < 0) _aiBias = TradeType.Sell;

            _executionDirection = Role == AccountRole.HedgeAccount
                ? (_aiBias == TradeType.Buy ? TradeType.Sell : TradeType.Buy)
                : _aiBias;

            Print($"[AI] Bias: {_aiBias} | Role: {Role} | Executing: {_executionDirection}");
        }

        private NewsEventInfo FindPrecursor(string keyword)
        {
            return _allWeeklyEvents
                .Where(e => e.Title.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0
                         && e.Actual.HasValue
                         && e.EventTime < _targetEvent.EventTime)
                .OrderByDescending(e => e.EventTime)
                .FirstOrDefault();
        }

        private static double Surprise(NewsEventInfo e)
        {
            if (!e.Actual.HasValue || !e.Forecast.HasValue) return 0;
            return Math.Sign(e.Actual.Value - e.Forecast.Value);
        }

        #endregion

        #region News Feed

        private void LoadNewsEvents()
        {
            try
            {
                HttpResponse response = Http.Get(_feedUrl);

                if (!response.IsSuccessful)
                {
                    Print($"[News] Feed failed — HTTP {response.StatusCode}");
                    return;
                }

                string xml = response.Body;

                if (!xml.TrimStart().StartsWith("<") || xml.Contains("<html"))
                {
                    Print("[News] Rate limited — will retry next cycle");
                    return;
                }

                var doc = new XmlDocument();
                doc.LoadXml(xml);

                DateTime today = Server.Time.Date;
                _triggerTime = new DateTime(today.Year, today.Month, today.Day, NewsHour, NewsMinute, 0);

                _allWeeklyEvents.Clear();
                _targetEvent = null;

                foreach (XmlNode node in doc.GetElementsByTagName("event"))
                {
                    string title    = node["title"]?.InnerText.Trim()             ?? "";
                    string currency = node["country"]?.InnerText.Trim().ToUpper() ?? "";
                    string dateStr  = node["date"]?.InnerText.Trim()              ?? "";
                    string timeStr  = node["time"]?.InnerText.Trim()              ?? "";

                    if (!DateTime.TryParseExact($"{dateStr} {timeStr}",
                            new[] { "MMM d, yyyy h:mmtt", "M/d/yyyy h:mmtt", "MM-dd-yyyy h:mmtt", "M-d-yyyy h:mmtt" },
                            CultureInfo.InvariantCulture, DateTimeStyles.None, out DateTime eventDt)
                        && !DateTime.TryParse($"{dateStr} {timeStr}", out eventDt))
                    {
                        continue;
                    }

                    DateTime eventLocal = TimeZoneInfo.ConvertTimeFromUtc(
                        DateTime.SpecifyKind(eventDt, DateTimeKind.Utc), _pretoriaZone);

                    _allWeeklyEvents.Add(new NewsEventInfo
                    {
                        EventTime = eventLocal,
                        Title     = title,
                        Currency  = currency,
                        Actual    = ParseValue(node["actual"]?.InnerText),
                        Forecast  = ParseValue(node["forecast"]?.InnerText)
                    });
                }

                _allWeeklyEvents = _allWeeklyEvents.OrderBy(e => e.EventTime).ToList();

                _targetEvent = _allWeeklyEvents.FirstOrDefault(e =>
                    e.EventTime.Date == today &&
                    e.EventTime.Hour   == NewsHour &&
                    e.EventTime.Minute == NewsMinute &&
                    !string.IsNullOrEmpty(e.Currency) &&
                    SymbolName.ToUpper().Contains(e.Currency));

                if (_targetEvent == null)
                    Print($"[News] No event found at {NewsHour:D2}:{NewsMinute:D2} for {SymbolName}. Check ForexFactory.");
                else
                {
                    Print($"[News] Target: '{_targetEvent.Title}' @ {_targetEvent.EventTime:HH:mm}");
                    RunAiHeuristics();
                }
            }
            catch (Exception ex)
            {
                Print("[News] Error: " + ex.Message);
            }
        }

        private void DisplayNewsEvents()
        {
            var sb = new StringBuilder();

            if (_targetEvent == null)
                sb.AppendLine($"No event found at {NewsHour:D2}:{NewsMinute:D2} for {SymbolName}");
            else
            {
                sb.AppendLine($"Target: {_targetEvent.Currency}: {_targetEvent.Title}");
                sb.AppendLine($"AI Bias: {(_aiBias.HasValue ? _aiBias.Value.ToString().ToUpper() : "SKIP (No Trade)")}");
                sb.AppendLine($"Executing: {(_executionDirection.HasValue ? _executionDirection.Value.ToString().ToUpper() : "---")}");
            }

            DrawStaticText(NewsLabel, sb.ToString(), VerticalAlignment.Top, HorizontalAlignment.Left, Color.White);
        }

        #endregion

        #region UI

        private void UpdateUI(DateTime now)
        {
            TimeSpan remaining = _triggerTime - now;

            string countdown  = "Time left to news: " + FormatTime(remaining);
            TimeSpan toOrders = remaining - TimeSpan.FromSeconds(SecondsBefore);
            countdown += "\nTime left to place orders: " + (toOrders > TimeSpan.Zero ? FormatTime(toOrders) : "0s");
            countdown += "\n";

            DrawStaticText(CountdownLabel, countdown, VerticalAlignment.Top, HorizontalAlignment.Right, Color.Red);

            double lots      = Symbol.VolumeInUnitsToQuantity(_currentLotSize);
            double margin001 = Symbol.GetEstimatedMargin(TradeType.Buy, Symbol.QuantityToVolumeInUnits(0.01));
            double reqMargin = (lots / 0.01) * margin001;
            DrawStaticText(LotSizeLabel,
                $"Calculated Lot Size: {lots:F2} lots | Required Margin: ${reqMargin:F2}",
                VerticalAlignment.Top, HorizontalAlignment.Center, Color.Blue);

            DrawDashboard();

            if ((now - _lastNewsUpdate).TotalSeconds >= NewsUpdateIntervalSeconds)
            {
                LoadNewsEvents();
                DisplayNewsEvents();
                _lastNewsUpdate = now;
            }
        }

        private void DrawDashboard()
        {
            if (_dashboardPanel != null)
                Chart.RemoveControl(_dashboardPanel);

            string biasText  = _aiBias.HasValue ? (_aiBias == TradeType.Buy ? "BUY  ▲" : "SELL  ▼") : "SKIP";
            string execText  = _executionDirection.HasValue ? (_executionDirection == TradeType.Buy ? "BUY  ▲" : "SELL  ▼") : "---";
            Color  biasColor = _aiBias == TradeType.Buy ? Color.LimeGreen : (_aiBias == TradeType.Sell ? Color.Red : Color.Gray);
            Color  execColor = _executionDirection == TradeType.Buy ? Color.LimeGreen : Color.Gray;
            Color  roleColor = Role == AccountRole.BiasAccount ? Color.DodgerBlue : Color.Orange;
            Color  trailColor = IncludeTrailingStop ? Color.LimeGreen : Color.Gray;

            string logicLabel = TradeLogic switch
            {
                TradeLogicOption.SingleOrder    => "Single Order",
                TradeLogicOption.OrderSplitting => "Order Split",
                _                               => TradeLogic.ToString()
            };

            _dashboardPanel = new Border
            {
                BorderColor         = Color.DarkGoldenrod,
                BorderThickness     = new Thickness(1),
                BackgroundColor     = Color.FromArgb(220, 15, 15, 15),
                CornerRadius        = 5,
                HorizontalAlignment = HorizontalAlignment.Right,
                VerticalAlignment   = VerticalAlignment.Top,
                Margin              = new Thickness(0, 105, 10, 0),
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

            // Group 1: AI Direction
            panel.AddChild(Divider());
            panel.AddChild(Row("Role:",         Role.ToString(), roleColor));
            panel.AddChild(Row("AI Bias:",      biasText,        biasColor));
            panel.AddChild(Row("Risk:",         $"{RiskPercentage}%",  Color.White));
            panel.AddChild(Row("Secs Before:",  $"{SecondsBefore}s",   Color.Yellow));

            // Group 2: Trailing
            panel.AddChild(Divider());
            panel.AddChild(Row("Trailing SL:", IncludeTrailingStop ? "ENABLED" : "DISABLED", trailColor));
            panel.AddChild(Row("Trigger:",     $"{TrailingStopTriggerPip} pips", Color.White));
            panel.AddChild(Row("Step:",        $"{TrailingStopStepPip} pips",    Color.White));
            panel.AddChild(Row("Stop Loss:",   $"{StopLoss} pips",               Color.White));

            // Group 3: Trade Logic
            panel.AddChild(Divider());
            panel.AddChild(Row("Trade Logic:", logicLabel, Color.Cyan));

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
            RemoveObj(CountdownLabel);
            RemoveObj(LotSizeLabel);
            RemoveObj(NewsLabel);

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

        private void RemoveObj(string name)
        {
            try { Chart.RemoveObject(name); } catch { }
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
            var sb = new StringBuilder();
            if (t.TotalHours >= 1) sb.Append($"{(int)t.TotalHours}h ");
            if (t.Minutes    >= 1) sb.Append($"{t.Minutes}m ");
            if (t.Seconds    >  0) sb.Append($"{t.Seconds}s");
            return sb.ToString();
        }

        #endregion
    }
}