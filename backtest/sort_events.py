import re
from collections import defaultdict

def main():
    with open('backtest/breakdown.txt', 'r') as f:
        lines = f.readlines()

    trades = []
    # Pattern to match the output lines
    # 2024-01-05 15:30 | NFP          | Acct A (Bias): $     2,800.00 | Acct B (Hedge): $    -375.00 | Net Walkaway: $   2,425.00 | Pot: $  7,425.00
    pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+\|\s+([^|]+?)\s+\|\s+Acct A \(Bias\):\s+\$\s*([-\d,.]+)\s+\|\s+Acct B \(Hedge\):\s+\$\s*([-\d,.]+)\s+\|\s+Net Walkaway:\s+\$\s*([-\d,.]+)\s+\|')

    for line in lines:
        match = pattern.search(line)
        if match:
            date_str = match.group(1)
            event = match.group(2).strip()
            net_str = match.group(5).replace(',', '')
            net_val = float(net_str)
            
            trades.append({
                'date': date_str,
                'event': event,
                'net': net_val,
                'line': line.strip()
            })

    # Group by event
    events_grouped = defaultdict(list)
    for t in trades:
        events_grouped[t['event']].append(t)

    print("=== PERFORMANCE SUMMARY BY EVENT ===")
    print(f"{'EVENT':<15} | {'TOTAL':<5} | {'WINS':<5} | {'LOSSES':<6} | {'WIN RATE':<8}")
    print("-" * 50)
    
    for event, t_list in events_grouped.items():
        total = len(t_list)
        wins = sum(1 for t in t_list if t['net'] > 0)
        losses = total - wins
        win_rate = (wins / total) * 100
        print(f"{event:<15} | {total:<5} | {wins:<5} | {losses:<6} | {win_rate:.1f}%")
        
    print("\n\n=== EXACT TRADES SORTED BY EVENT ===")
    for event, t_list in events_grouped.items():
        print(f"\n--- {event.upper()} ---")
        for t in t_list:
            # We strip out the "Pot: $..." part to keep it clean and focused on the event itself, 
            # since Pot compounding makes comparing early vs late trades visually confusing.
            clean_line = t['line'].split('| Pot:')[0].strip()
            print(clean_line)

if __name__ == "__main__":
    main()
