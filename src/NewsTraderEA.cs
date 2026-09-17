using System;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Globalization;
using System.Collections.Generic;
using cAlgo.API;
using HorizontalAlignment = cAlgo.API.HorizontalAlignment;

namespace cAlgo.Robots
{
    public enum AccountRole { BiasAccount, HedgeAccount }

    public enum TradeLogicOption { SingleOrder, OrderSplitting }

    public enum BiasOverride { Auto, Buy, Sell, Skip }

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

    internal class ContextDecision
    {
        [JsonPropertyName("decision")]
        public string Decision { get; set; }

        [JsonPropertyName("event")]
        public string Event { get; set; }

        [JsonPropertyName("reason")]
        public string Reason { get; set; }
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

        [Parameter("Manual Override Bias",    Group = "AI Override (Last Week Data)", DefaultValue = BiasOverride.Auto)]
        public BiasOverride ManualBias { get; set; }

        #endregion

        #region Constants

        private const int    NewsUpdateIntervalSeconds = 300;
        private const int    NewsTimeToleranceMinutes  = 5;
        private const double MinMarginLevel            = 20.0;
        private const double LotSizeLogThreshold       = 0.02;

        private readonly string _apiUrl = "http://127.0.0.1:8001/api/v1/decision";

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
                private string _targetEventName = "Unknown";

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
                // Always run trailing stop first on every tick
                if (IncludeTrailingStop)
                    UpdateTrailingStops();

                // Margin safety check â€” MUST run before returning
                if (Account.MarginLevel < MinMarginLevel)
                {
                    foreach (var pos in Positions.FindAll(Label, SymbolName))
                    {
                        Print($"[Safety] Margin < {MinMarginLevel}% â€” closing position {pos.Id}");
                        ClosePosition(pos);
                    }
                }

                bool hasPositions = Positions.FindAll(Label, SymbolName).Any();

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
                    Print($"[Order] Executed â€” Position {result.Position.Id} @ {result.Position.EntryPrice}");
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

        

        #region News Feed

        private void LoadNewsEvents()
        {
            try
            {
                DateTime today = Server.Time.Date;
                _triggerTime = new DateTime(today.Year, today.Month, today.Day, NewsHour, NewsMinute, 0);

                // Convert server trigger time to UTC ISO format
                DateTime triggerUtc = TimeZoneInfo.ConvertTimeToUtc(_triggerTime, _pretoriaZone);
                string targetTimeIso = triggerUtc.ToString("yyyy-MM-ddTHH:mm:ssZ");

                string url = $"{_apiUrl}?target_time={targetTimeIso}&symbol={SymbolName}";
                HttpResponse response = Http.Get(url);

                if (!response.IsSuccessful)
                {
                    Print($"[Context API] Request failed — HTTP {response.StatusCode}");
                    SetSkipBias();
                    return;
                }

                var decision = JsonSerializer.Deserialize<ContextDecision>(response.Body);
                if (decision == null)
                {
                    Print("[Context API] Failed to parse JSON response");
                    SetSkipBias();
                    return;
                }

                _targetEventName = decision.Event;
                
                if (ManualBias != BiasOverride.Auto)
                {
                    Print($"[AI] Using Manual Override: {ManualBias}");
                    if (ManualBias == BiasOverride.Skip)
                    {
                        SetSkipBias();
                    }
                    else
                    {
                        _aiBias = ManualBias == BiasOverride.Buy ? TradeType.Buy : TradeType.Sell;
                        _executionDirection = (Role == AccountRole.BiasAccount) ? _aiBias : (_aiBias == TradeType.Buy ? TradeType.Sell : TradeType.Buy);
                    }
                    return;
                }

                if (decision.Decision == "BUY") _aiBias = TradeType.Buy;
                else if (decision.Decision == "SELL") _aiBias = TradeType.Sell;
                else _aiBias = null;

                _executionDirection = Role == AccountRole.HedgeAccount
                    ? (_aiBias == TradeType.Buy ? TradeType.Sell : TradeType.Buy)
                    : _aiBias;

                Print($"[Context API] Target: {decision.Event}");
                Print($"[Context API] Reason: {decision.Reason}");
                Print($"[Context API] Bias: {_aiBias} | Role: {Role} | Executing: {_executionDirection}");
            }
            catch (Exception ex)
            {
                Print("[Context API] Error: " + ex.Message);
                SetSkipBias();
            }
        }

        private void SetSkipBias()
        {
            _aiBias = null;
            _executionDirection = null;
            _targetEventName = "Unknown or Error";
        }

        private void DisplayNewsEvents()
        {
            var sb = new StringBuilder();

            sb.AppendLine($"Target: {_targetEventName}");
            sb.AppendLine($"AI Bias: {(_aiBias.HasValue ? _aiBias.Value.ToString().ToUpper() : "SKIP (No Trade)")}");
            sb.AppendLine($"Executing: {(_executionDirection.HasValue ? _executionDirection.Value.ToString().ToUpper() : "---")}");

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

            string biasText  = _aiBias.HasValue ? (_aiBias == TradeType.Buy ? "BUY  â–²" : "SELL  â–¼") : "SKIP";
            string execText  = _executionDirection.HasValue ? (_executionDirection == TradeType.Buy ? "BUY  â–²" : "SELL  â–¼") : "---";
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