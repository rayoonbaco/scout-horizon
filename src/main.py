import argparse
from pathlib import Path
from src.radar_engine import run_engine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='', help='Question Mode (exact label from config/question_modes.yaml)')
    ap.add_argument('--lookback-hours', type=int, default=24, help='How far back to search (discovery windows)')
    ap.add_argument('--include-text', default='', help='Comma-separated include terms; supports quoted phrases')
    ap.add_argument('--exclude-text', default='', help='Comma-separated exclude terms; supports quoted phrases')
    args = ap.parse_args()
    mode = args.mode.strip() or None
    proj = Path(__file__).resolve().parents[1]
    summary = run_engine(
        proj,
        mode=mode,
        lookback_hours=args.lookback_hours,
        include_text=args.include_text,
        exclude_text=args.exclude_text,
    )
    print(f"Done. Events: {summary['total_events']}  Mode: {summary.get('mode','') or 'default'}")
    print("Outputs: outputs/radar_signals.json and outputs/radar_summary.json")


if __name__ == '__main__':
    main()
