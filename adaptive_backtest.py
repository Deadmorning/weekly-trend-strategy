"""
WTS + 自适应周五清仓策略
========================
规则：
  入场：WTS=1 → 周一开盘买入（纯WTS入场逻辑）
  持仓：WTS=1 期间持有
  出场（双重）：
    1. WTS 转 0 → 当日开盘平仓
    2. 每周五收盘时判断：当周上涨天数（收≥开）< 3 → 收盘强制清仓
                         当周上涨天数 ≥ 3 → 不清仓，持仓延续到下周
  逻辑：当周势头不足时（<3天上涨），不愿意持仓过周末；势头好时让利润奔跑

对比：纯WTS / 自适应 / 非对称DTS / BNH
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

UPLOADS = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/uploads")
OUTPUT  = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/outputs")

W_FLAT=0.015; W_SAME=0.90; W_REV=0.45
D_FLAT=0.005
COST_BPS=15
UP=1; DOWN=-1; FLAT=0
UP_DAYS_THR = 3

OPT_PARAMS = {
    "上证50ETF":  (0.75, 0.60),
    "沪深300ETF": (2.50, 2.00),
    "中证500ETF": (2.50, 2.00),
    "科创50ETF":  (2.50, 1.50),
    "深证100ETF": (3.00, 2.00),
    "创业板ETF":  (4.00, 1.00),
}
ETF_FILES = {
    "上证50ETF":  "510050_上证_50ETF.csv",
    "沪深300ETF": "510300_沪深_300ETF.csv",
    "中证500ETF": "510500_中证_500ETF.csv",
    "科创50ETF":  "588080_科创_50ETF.csv",
    "深证100ETF": "159901_深证_100ETF.csv",
    "创业板ETF":  "159915_创业板_ETF.csv",
}
PERIODS = [
    ("全程", "2023-04-17", "2026-04-15"),
    ("P1",   "2025-01-01", "2025-08-31"),
    ("P2",   "2025-08-01", "2026-01-31"),
    ("P3",   "2025-08-01", "2026-03-31"),
]

def load_etf(name):
    df = pd.read_csv(UPLOADS/ETF_FILES[name], encoding='utf-8-sig')
    df = df.rename(columns={'日期':'date','开盘':'open','收盘':'close',
                             '最高':'high','最低':'low','成交量':'volume'})
    df['date'] = pd.to_datetime(df['date'])
    return df[['date','open','high','low','close']].sort_values('date').reset_index(drop=True)

def classify(row, thr):
    amp = (row['high'] - row['low']) / row['open']
    if amp < thr: return FLAT
    return UP if row['close'] >= row['open'] else DOWN

def amp_pct(row):
    return (row['high'] - row['low']) / row['open'] * 100.0

def seven_rules(dp, dc, ap, ac, prev_pos, st, rt):
    raw = None; rule = None
    if   dp==UP   and dc==UP:   rule, raw = 1,  1
    elif dp==DOWN and dc==DOWN: rule, raw = 2, -1
    elif dp==UP   and dc==DOWN: rule, raw = 3, -1
    elif dp==DOWN and dc==UP:   rule, raw = 4,  1
    elif (dp==FLAT or dp==UP)   and (dc==UP   or dc==FLAT): return 1, 5, False
    elif (dp==FLAT or dp==DOWN) and (dc==DOWN or dc==FLAT): return 0, 6, False
    elif dp==FLAT and dc==FLAT: return prev_pos, 7, False
    else: return prev_pos, None, False
    diff = abs(ac - ap); thr = st if (dp > 0) == (dc > 0) else rt
    if diff < thr: return prev_pos, rule, True
    return max(raw, 0), rule, False

def build_signals(daily, d_same, d_rev):
    d = daily.copy()

    # ── 周线 WTS + 当周上涨天数 ──────────────────────────────────────────────
    d['wk'] = d['date'].dt.to_period('W')

    def agg_w(g):
        g = g.sort_values('date')
        up_days = int((g['close'] >= g['open']).sum())
        return pd.Series({
            'we': g['date'].iloc[-1],
            'open': g['open'].iloc[0], 'high': g['high'].max(),
            'low': g['low'].min(),     'close': g['close'].iloc[-1],
            'up_days': up_days,
        })

    wk = d.groupby('wk').apply(agg_w).reset_index().dropna()
    wk['st'] = wk.apply(lambda r: classify(r, W_FLAT), axis=1)
    wk['am'] = wk.apply(amp_pct, axis=1)

    pos = 0; ws = [0]
    for i in range(1, len(wk)):
        p, c = wk.iloc[i-1], wk.iloc[i]
        np_, _, _ = seven_rules(p['st'], c['st'], p['am'], c['am'], pos, W_SAME, W_REV)
        ws.append(np_); pos = np_
    wk['wts'] = ws

    wk_list  = wk['wk'].tolist()
    wts_list = wk['wts'].tolist()
    # 上周上涨天数（用于 updays 过滤策略参考）
    upd_list = wk['up_days'].tolist()

    week_to_perm   = {str(wk_list[i+1]): wts_list[i] for i in range(len(wk_list)-1)}
    week_to_prev_up = {str(wk_list[i+1]): upd_list[i] for i in range(len(wk_list)-1)}

    d['wp']      = d['wk'].apply(lambda w: week_to_perm.get(str(w), 0))
    d['prev_up'] = d['wk'].apply(lambda w: week_to_prev_up.get(str(w), 0))

    # 当周上涨天数（收盘时才知道全貌，但我们只在每周五用它）
    curr_updays = d.groupby('wk').apply(
        lambda g: pd.Series((g['close'] >= g['open']).sum(), index=g.index)
    ).reset_index(level=0, drop=True)
    d['curr_up'] = curr_updays

    # ── 日线 DTS（非对称策略用） ───────────────────────────────────────────────
    d['ds'] = d.apply(lambda r: classify(r, D_FLAT), axis=1)
    d['da'] = d.apply(amp_pct, axis=1)
    pos = 0; dsigs = [0]
    for i in range(1, len(d)):
        p, c = d.iloc[i-1], d.iloc[i]
        np_, _, _ = seven_rules(p['ds'], c['ds'], p['da'], c['da'], pos, d_same, d_rev)
        dsigs.append(np_); pos = np_
    d['dts'] = dsigs
    d['dts_s'] = d['dts'].shift(1).fillna(0).astype(int)

    # ── 策略1：纯 WTS ──────────────────────────────────────────────────────────
    d['pos_wts'] = d['wp']

    # ── 策略2：非对称 WTS+DTS（状态机） ───────────────────────────────────────
    asym = []; pos_a = 0; prev_wp = 0
    for i, row in d.iterrows():
        wp = int(row['wp']); dts = int(row['dts_s'])
        if wp == 0: pos_a = 0
        elif prev_wp == 0 and wp == 1: pos_a = 1
        else:
            if   pos_a == 1 and dts == 0: pos_a = 0
            elif pos_a == 0 and dts == 1: pos_a = 1
        asym.append(pos_a); prev_wp = wp
    d['pos_asym'] = asym

    # ── 策略3：自适应周五清仓（核心新策略） ────────────────────────────────────
    # 入场：WTS=1 → 周一开盘（纯WTS入场）
    # 持仓：维持到WTS=0 或 周五弱势（curr_up<3）
    # 强持：当周涨天≥3 → 不清仓，跨周持仓
    adapt = []; pos_ad = 0
    for i, row in d.iterrows():
        wd      = row['date'].weekday()   # 0=Mon, 4=Fri
        wp      = int(row['wp'])
        curr_up = int(row['curr_up'])

        # WTS=0：强制空仓
        if wp == 0:
            pos_ad = 0
        # WTS=1：
        elif wd == 0 and pos_ad == 0:
            # 周一且未持仓 → 入场
            pos_ad = 1
        # 其他（Tue-Thu 或已持仓的 Mon）：维持

        adapt.append(pos_ad)

        # 周五收盘：判断是否清仓
        if wd == 4 and pos_ad == 1:
            if curr_up < UP_DAYS_THR:
                pos_ad = 0   # 弱势周 → 收盘清仓
            # else: 强势周 → 持仓过周末

    d['pos_adaptive'] = adapt

    # 标记哪些周五需要在收盘时平仓
    d['fri_close'] = (d['date'].dt.weekday == 4) & (d['curr_up'] < UP_DAYS_THR)

    return d, wk


def backtest_seg(daily_full, pos_col, start, end, init=1_000_000.0,
                 fri_close_col=None):
    """
    fri_close_col: 列名，该列为 True 时在当日收盘强制平仓（用于自适应策略）
    """
    d = daily_full[
        (daily_full['date'] >= start) & (daily_full['date'] <= end)
    ].copy().reset_index(drop=True)
    if len(d) < 5:
        return None

    cash = init; shares = 0.0; pos = 0; trades = []
    ep = 0.0; ed = None; equity = []

    for i, row in d.iterrows():
        np_    = int(row[pos_col])
        o      = row['open']; c = row['close']
        do_fri = bool(row[fri_close_col]) if fri_close_col else False

        # 开盘执行信号变化
        if np_ != pos:
            if pos == 1 and shares > 0:
                cash   = shares * o * (1 - COST_BPS / 10000)
                pnl    = (o * (1 - COST_BPS / 10000) - ep) / ep * 100
                trades.append({
                    'entry_date':  str(ed.date()),
                    'exit_date':   str(row['date'].date()),
                    'entry_price': round(ep, 4), 'exit_price': round(o, 4),
                    'pnl_pct':     round(pnl, 2),
                    'hold_days':   (row['date'] - ed).days,
                })
                shares = 0.0
            if np_ == 1:
                shares = (cash * (1 - COST_BPS / 10000)) / o
                cash   = 0.0; ep = o * (1 + COST_BPS / 10000); ed = row['date']

        pos = np_
        equity.append(cash + shares * c)

        # 收盘时自适应强制清仓（弱势周五）
        if do_fri and pos == 1 and shares > 0:
            cash   = shares * c * (1 - COST_BPS / 10000)
            pnl    = (c * (1 - COST_BPS / 10000) - ep) / ep * 100
            trades.append({
                'entry_date':  str(ed.date()),
                'exit_date':   str(row['date'].date()),
                'entry_price': round(ep, 4), 'exit_price': round(c, 4),
                'pnl_pct':     round(pnl, 2),
                'hold_days':   (row['date'] - ed).days,
            })
            shares = 0.0; pos = 0; ep = 0.0; ed = None
            equity[-1] = cash

    # 期末持仓
    if pos == 1 and shares > 0:
        last = d.iloc[-1]
        pnl  = (last['close'] * (1 - COST_BPS / 10000) - ep) / ep * 100
        trades.append({
            'entry_date':  str(ed.date()),
            'exit_date':   str(last['date'].date()),
            'entry_price': round(ep, 4), 'exit_price': round(last['close'], 4),
            'pnl_pct':     round(pnl, 2),
            'hold_days':   (last['date'] - ed).days,
        })

    eq  = pd.Series(equity)
    bnh = init * d['close'] / d['close'].iloc[0]
    n   = len(eq)
    tr  = (eq.iloc[-1] / init - 1) * 100
    br  = (bnh.iloc[-1] / init - 1) * 100
    dr  = eq.pct_change().dropna()
    sh  = dr.mean() / dr.std() * np.sqrt(252) if dr.std() > 0 else 0
    mdd = ((eq - eq.cummax()) / eq.cummax()).min() * 100
    wins = [t for t in trades if t['pnl_pct'] > 0]

    return {
        'dates':   [str(x.date()) for x in d['date']],
        'close':   d['close'].round(4).tolist(),
        'equity':  eq.round(2).tolist(), 'bnh': bnh.round(2).tolist(),
        'cum_ret': ((eq / init - 1) * 100).round(2).tolist(),
        'bnh_ret': ((bnh / init - 1) * 100).round(2).tolist(),
        'pos':     d[pos_col].tolist(), 'trades': trades,
        'metrics': {
            'total_return': round(tr, 2),  'bnh_return':   round(br, 2),
            'alpha':        round(tr - br, 2), 'sharpe':   round(sh, 2),
            'max_drawdown': round(mdd, 2),
            'win_rate':     round(len(wins) / len(trades) * 100, 1) if trades else 0,
            'n_trades': len(trades),
            'long_pct': round((d[pos_col] == 1).sum() / n * 100, 1),
            'n_days': n,
            'start': str(d['date'].iloc[0].date()),
            'end':   str(d['date'].iloc[-1].date()),
        }
    }


# ── 主流程 ────────────────────────────────────────────────────────────────────
STRATS = [
    # (pos_col, label, fri_close_col)
    ('pos_adaptive', '自适应周五清仓', 'fri_close'),
    ('pos_wts',      '纯WTS',         None),
    ('pos_asym',     '非对称DTS',     None),
]

all_data = {}

print(f"{'标的':10s} {'阶段':8s}  "
      f"{'自适应':>14s}  {'纯WTS':>10s}  {'非对称DTS':>10s}  {'BNH':>8s}")
print("─" * 80)

for name in ETF_FILES:
    d_s, d_r = OPT_PARAMS[name]
    daily    = load_etf(name)
    dsig, wk = build_signals(daily, d_s, d_r)

    etf = {'opt': {'same': d_s, 'rev': d_r}, 'periods': {}}

    for plabel, ps, pe in PERIODS:
        results = {}
        for col, lbl, fri_col in STRATS:
            r = backtest_seg(dsig, col, ps, pe, fri_close_col=fri_col)
            results[col] = r

        etf['periods'][plabel] = results
        if results['pos_wts']:
            mw = results['pos_wts']['metrics']
            ma = results['pos_asym']['metrics']
            mad = results['pos_adaptive']['metrics']
            n_fri_close = sum(1 for t in (results['pos_adaptive']['trades'] or [])
                              if t['exit_date'] and
                              pd.Timestamp(t['exit_date']).weekday() == 4)
            print(f"{name:10s} {plabel:8s}  "
                  f"ADT {mad['total_return']:+6.1f}%(α{mad['alpha']:+.1f},T{mad['n_trades']})  "
                  f"WTS {mw['total_return']:+6.1f}%  "
                  f"ASY {ma['total_return']:+6.1f}%  "
                  f"BNH {mw['bnh_return']:+6.1f}%")

    all_data[name] = etf
    print()

out = OUTPUT / 'adaptive_results.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(all_data, f, ensure_ascii=False, default=str)
print(f"\n保存: {out}  ({out.stat().st_size // 1024} KB)")
