#!/usr/bin/env python3
"""
指標預計算腳本 - 離線批量計算常用技術指標

用法：
    python scripts/warmup_indicators.py --all --workers 8
    python scripts/warmup_indicators.py --codes 2330.TW 2454.TW --indicators sma macd rsi
"""
import argparse
import json
import sys
import os

# 添加專案根目錄到 PATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="指標預計算工具")
    parser.add_argument("--codes", nargs="+", help="股票代碼清單")
    parser.add_argument("--all", action="store_true", help="處理所有股票")
    parser.add_argument("--indicators", nargs="+", help="指定指標名稱 (sma/ema/macd/rsi/atr/bollinger/kdj/obv/vma)")
    parser.add_argument("--workers", type=int, default=4, help="worker 數量", choices=range(1, 17))
    parser.add_argument("--output", "-o", help="輸出結果到 JSON 文件")
    
    args = parser.parse_args()
    
    from src.core.indicators.precomputed_indicators import warmup_indicators
    
    codes = args.codes if args.codes else None
    if args.all and not codes:
        print("正在獲取所有股票代碼...")
        from src.core.stock_universe import get_all_codes
        codes = get_all_codes()
        print(f"找到 {len(codes)} 支股票")
    
    if not codes:
        print("❌ 錯誤：沒有指定股票代碼")
        parser.print_help()
        sys.exit(1)
    
    print(f"\n開始預熱指標:")
    print(f"  股票數量：{len(codes)}")
    print(f"  指標類型：{args.indicators or '全部'}")
    print(f"  Worker 數量：{args.workers}")
    print()
    
    result = warmup_indicators(
        codes=codes,
        subset_indicators=args.indicators,
        max_workers=args.workers,
    )
    
    # 輸出結果
    print("\n" + "="*60)
    print("預計算完成!")
    print("="*60)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n結果已儲存至：{args.output}")
    
    # 返回狀態碼
    if result.get("status") == "completed":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
