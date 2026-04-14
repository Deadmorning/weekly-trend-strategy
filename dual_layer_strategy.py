"""
双层趋势策略回测
=============================================================
Layer 1（周线 WTS）：判断本周是否处于多头"许可区"
Layer 2（日线）：在许可区内精确择时，两种版本：
  A. DTS 完整规则（前日+当日方向组合，7条规则 + 振幅过滤）
  B. 简单 UP/DOWN 过滤（当日 close >= open → Long，否则 Cash）

合并逻辑：
  position = weekly_perm AND daily_signal
  执行时序：信号在当日收盘产生 → 次日开盘执行（T+1）
"""

import pandas as pd
import numpy as np
import json
import glob
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

UPLOADS = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/uploads")
OUTPUT  = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/outputs")
OUTPUT.mkdir(exist_ok=True)

# ── 参数 ──────────────────────────────────────────────────────────────────────
# 周线 WTS
W_FLAT  = 0.015   # 周振幅 < 1.5% → FLAT
W_SAME  = 0.90    # 同向过滤阈值 %
W_REV   = 0.45    # 反向过滤阈值 %
# 日线 DTS
D_FLAT  = 0.005   # 日振幅 < 0.5% → FLAT
D_SAME  = 0.30
D_REV   = 0.15

UP = 1; DOWN = -1; FLAT = 0

ETF_FILES = {
    "上证50ETF":  "sh_510050_上证 50ETF.csv",
    "沪深300ETF": "sh_510300_沪深 300ETF.csv",
    "中证500ETF": "sh_510500_中证 500ETF.csv",
    "科创50ETF":  "sh_588000_科创 50ETF.csv",
    "深证100ETF": "sz_159901_深证 100ETF.csv",
    "创业板ETF":  "sz_159915_创业板 ETF.csv",
}
NEW_DATA_MAP = {
    "上证50ETF":  ("510050", "sh_510050_上证 50ETF.csv"),
    "沪深300ETF": ("510300", "sh_510300_沪深 300ETF.csv"),
    "中证500ETF": ("510500", "sh_510500_中证 500ETF.csv"),
    "科创50ETF":  ("588000", "sh_588000_科创 50ETF.csv"),
    "深证100ETF": ("159901", "sz_159901_深证 100ETF.csv"),
    "创业板ETF":  ("159915", "sz_159915_创业板 ETF.csv"),
}

# ── 数据加载 ──────────────────────────────────────────────────────────────────

def load_daily_5min(path):
    df = pd.read_csv(path, encoding='utf-8-sig')
    df['date'] = pd.to_datetime(df['date'])
    return df.groupby('date').agg(
        open=('open','first'), high=('high','max'),
        low=('low','min'), close=('close','last'),
        volume=('volume','sum'), amount=('amount','sum'),
    ).reset_index().sort_values('date').reset_index(drop=True)

def load_daily_1min(pattern):
    files = sorted(glob.glob(pattern))
    if not files: return pd.DataFrame()
    dfs = []
    for f in files:
        df = pd.read_csv(f, encoding='utf-8-sig')
        df['datetime'] = pd.to_datetime(df['day'])
        df['date'] = df['datetime'].dt.date
        dfs.append(df)
    all_df = pd.concat(dfs, ignore_index=True)
    all_df['date'] = pd.to_datetime(all_df['date'])
    return all_df.groupby('date').agg(
        open=('open','first'), high=('high','max'),
        low=('low','min'), close=('close','last'),
        volume=('volume','sum'), amount=('amount','sum'),
    ).reset_index().sort_values('date').reset_index(drop=True)

def get_daily(name):
    if name in NEW_DATA_MAP:
        prefix, hist_file = NEW_DATA_MAP[name]
        hist  = load_daily_5min(UPLOADS / hist_file)
        new_d = load_daily_1min(str(UPLOADS / f"{prefix}_202604*_1min_akshare.csv"))
        if not new_d.empty:
            cutoff = new_d['date'].min()
            hist   = hist[hist['date'] < cutoff]
            return pd.concat([hist, new_d], ignore_index=True).sort_values('date').reset_index(drop=True)
    return load_daily_5min(UPLOADS / ETF_FILES[name])

# ── 分类器 ────────────────────────────────────────────────────────────────────

def classify(row, flat_thresh):
    amp = (row['high'] - row['low']) / row['open']
    if amp < flat_thresh: return FLAT
    return UP if row['close'] >= row['open'] else DOWN

def amp_pct(row):
    return (row['high'] - row['low']) / row['open'] * 100.0

# ── 通用 7 条规则信号函数 ─────────────────────────────────────────────────────

def seven_rules(dp, dc, amp_p, amp_c, prev_pos, same_thr, rev_thr):
    """返回 (new_pos, rule, filtered)，纯多头（空头→0）"""
    raw = None; rule = None
    if   dp==UP   and dc==UP:   rule,raw = 1, 1
    elif dp==DOWN and dc==DOWN: rule,raw = 2,-1
    elif dp==UP   and dc==DOWN: rule,raw = 3,-1
    elif dp==DOWN and dc==UP:   rule,raw = 4, 1
    elif (dp==FLAT or dp==UP)  and (dc==UP   or dc==FLAT): return 1,5,False
    elif (dp==FLAT or dp==DOWN)and (dc==DOWN or dc==FLAT): return 0,6,False
    elif dp==FLAT and dc==FLAT: return prev_pos,7,False
    else: return prev_pos,None,False

    amp_diff = abs(amp_c - amp_p)
    thr = same_thr if ((dp>0)==(dc>0)) else rev_thr
    if amp_diff < thr: return prev_pos,rule,True
    return max(raw,0),rule,False   # 空头 → 0（持现金）

# ── Layer 1：周线 WTS 信号序列 ────────────────────────────────────────────────

def build_weekly_signals(daily):
    """
    返回：每个交易日对应的"本周WTS许可"（0 或 1）
    许可在当周第一个交易日（周一）从上周五的信号切换生效。
    """
    daily = daily.copy()
    daily['week_key'] = daily['date'].dt.to_period('W')

    # 聚合周线
    def agg_w(g):
        g = g.sort_values('date')
        return pd.Series({
            'week_start': g['date'].iloc[0],
            'week_end':   g['date'].iloc[-1],
            'open': g['open'].iloc[0], 'high': g['high'].max(),
            'low':  g['low'].min(),    'close': g['close'].iloc[-1],
        })
    weekly = daily.groupby('week_key').apply(agg_w).reset_index().dropna()
    # reset_index 后 week_key 是一列，保留它

    # 生成周线信号
    weekly['state'] = weekly.apply(lambda r: classify(r, W_FLAT), axis=1)
    weekly['amp']   = weekly.apply(amp_pct, axis=1)
    pos = 0
    w_sigs = []
    for i in range(len(weekly)):
        if i == 0:
            w_sigs.append(0)
            continue
        prev, curr = weekly.iloc[i-1], weekly.iloc[i]
        new_pos, _, _ = seven_rules(
            prev['state'], curr['state'],
            prev['amp'],   curr['amp'],
            pos, W_SAME, W_REV)
        w_sigs.append(new_pos)
        pos = new_pos
    weekly['wts_signal'] = w_sigs

    # 映射回日线：本周的 wts_signal 在下周所有交易日生效
    wk_keys  = weekly['week_key'].tolist()
    wts_sigs = weekly['wts_signal'].tolist()
    week_to_perm = {}
    for i in range(len(wk_keys) - 1):
        week_to_perm[str(wk_keys[i + 1])] = wts_sigs[i]

    daily['weekly_perm'] = daily['week_key'].apply(
        lambda wk: week_to_perm.get(str(wk), 0))

    return daily, weekly

# ── Layer 2A：DTS 完整规则日线信号 ───────────────────────────────────────────

def build_dts_signals(daily):
    """
    返回 daily['dts_signal']：当日收盘产生，次日执行
    """
    daily = daily.copy()
    daily['state'] = daily.apply(lambda r: classify(r, D_FLAT), axis=1)
    daily['amp']   = daily.apply(amp_pct, axis=1)

    pos = 0
    sigs = [0]
    for i in range(1, len(daily)):
        prev, curr = daily.iloc[i-1], daily.iloc[i]
        new_pos, _, _ = seven_rules(
            prev['state'], curr['state'],
            prev['amp'],   curr['amp'],
            pos, D_SAME, D_REV)
        sigs.append(new_pos)
        pos = new_pos
    daily['dts_signal'] = sigs
    return daily

# ── Layer 2B：简单 UP/DOWN 日线信号 ──────────────────────────────────────────

def build_simple_signals(daily):
    """
    当日 close >= open → 明日做多
    当日 close <  open → 明日持现金
    """
    daily = daily.copy()
    # 今日形态 → 明日信号（shift(-1)即下一行使用今日的分类）
    today_up = (daily['close'] >= daily['open']).astype(int)
    daily['simple_signal'] = today_up.shift(1).fillna(0).astype(int)
    return daily

# ── 回测引擎（通用） ──────────────────────────────────────────────────────────

def backtest(daily, pos_col, init_cash=1_000_000.0):
    """
    pos_col: 每日持仓列名（0 或 1）
    P&L 以 open→close 计算（每日持有当天仓位）
    """
    d = daily.copy().reset_index(drop=True)
    equity = [init_cash]
    cash   = init_cash
    shares = 0.0
    pos    = 0
    trades = []
    entry_price = 0.0
    entry_date  = None

    for i, row in d.iterrows():
        new_pos = int(row[pos_col])
        price   = row['close']
        o_price = row['open']

        # 换仓（在当日开盘执行）
        if new_pos != pos:
            if pos == 1 and shares > 0:
                cash   = shares * o_price
                pnl    = (o_price - entry_price) / entry_price * 100
                trades.append({
                    'entry_date': str(entry_date.date()),
                    'exit_date':  str(row['date'].date()),
                    'entry_price': entry_price,
                    'exit_price':  round(o_price, 4),
                    'pnl_pct':     round(pnl, 2),
                    'hold_days':   (row['date'] - entry_date).days,
                })
                shares = 0.0
            if new_pos == 1:
                shares      = cash / o_price
                cash        = 0.0
                entry_price = o_price
                entry_date  = row['date']
        pos = new_pos

        # 当日收益（以 open→close 计）
        cur_equity = cash + shares * price
        equity.append(cur_equity)

    # 末日平仓
    if pos == 1 and shares > 0:
        last  = d.iloc[-1]
        cash  = shares * last['close']
        pnl   = (last['close'] - entry_price) / entry_price * 100
        trades.append({
            'entry_date': str(entry_date.date()),
            'exit_date':  str(last['date'].date()),
            'entry_price': entry_price,
            'exit_price':  round(last['close'], 4),
            'pnl_pct':     round(pnl, 2),
            'hold_days':   (last['date'] - entry_date).days,
        })

    eq = pd.Series(equity[1:], index=d.index)
    bnh = init_cash * d['close'] / d['close'].iloc[0]

    total_r = eq.iloc[-1] / init_cash - 1
    bnh_r   = bnh.iloc[-1] / init_cash - 1
    n       = len(eq)
    ann_r   = (1+total_r)**(252/max(n,1)) - 1

    daily_ret = eq.pct_change().dropna()
    sharpe    = daily_ret.mean()/daily_ret.std()*np.sqrt(252) if daily_ret.std()>0 else 0
    roll_mx   = eq.cummax()
    mdd       = ((eq - roll_mx)/roll_mx).min()

    sells  = trades
    wins   = [t for t in sells if t.get('pnl_pct',0)>0]
    wr     = len(wins)/len(sells) if sells else 0

    long_days = (d[pos_col]==1).sum()

    return {
        'equity':    eq.round(2).tolist(),
        'bnh':       bnh.round(2).tolist(),
        'cum_ret':   ((eq/init_cash-1)*100).round(2).tolist(),
        'bnh_ret':   ((bnh/init_cash-1)*100).round(2).tolist(),
        'trades':    trades,
        'metrics': {
            'total_return':  round(total_r*100, 2),
            'bnh_return':    round(bnh_r*100, 2),
            'alpha':         round((total_r-bnh_r)*100, 2),
            'annual_return': round(ann_r*100, 2),
            'sharpe':        round(sharpe, 2),
            'max_drawdown':  round(mdd*100, 2),
            'win_rate':      round(wr*100, 1),
            'n_trades':      len(sells),
            'long_days':     int(long_days),
            'long_pct':      round(long_days/n*100, 1),
        }
    }

# ── 主流程 ────────────────────────────────────────────────────────────────────

chart_data = {}

print(f"{'标的':12s} {'策略':8s} {'WTS':>8s} {'WTS+DTS':>9s} {'WTS+SIM':>9s} "
      f"{'BNH':>8s}  α(纯WTS) α(+DTS) α(+SIM)")
print("─"*90)

for name in ETF_FILES:
    daily = get_daily(name)

    # 生成各层信号
    daily, weekly = build_weekly_signals(daily)
    daily = build_dts_signals(daily)
    daily = build_simple_signals(daily)

    # 三种策略的合并持仓
    # 策略1：纯 WTS（周维度，周一切换信号后持整周）
    daily['pos_wts']     = daily['weekly_perm']

    # 策略2：WTS × DTS
    daily['pos_wts_dts'] = (daily['weekly_perm'] * daily['dts_signal']).clip(0,1)

    # 策略3：WTS × 简单UP/DOWN
    daily['pos_wts_sim'] = (daily['weekly_perm'] * daily['simple_signal']).clip(0,1)

    # 回测
    r_wts = backtest(daily, 'pos_wts')
    r_dts = backtest(daily, 'pos_wts_dts')
    r_sim = backtest(daily, 'pos_wts_sim')

    mw = r_wts['metrics']; md = r_dts['metrics']; ms = r_sim['metrics']

    print(f"{name:12s} "
          f"WTS {mw['total_return']:+6.2f}%  "
          f"DTS {md['total_return']:+6.2f}%  "
          f"SIM {ms['total_return']:+6.2f}%  "
          f"BNH {mw['bnh_return']:+6.2f}%  "
          f"α {mw['alpha']:+5.2f}% {md['alpha']:+5.2f}% {ms['alpha']:+5.2f}%")

    # 当前状态
    last = daily.iloc[-1]
    chart_data[name] = {
        'dates':        [str(d.date()) for d in daily['date']],
        'open':         daily['open'].round(4).tolist(),
        'high':         daily['high'].round(4).tolist(),
        'low':          daily['low'].round(4).tolist(),
        'close':        daily['close'].round(4).tolist(),
        'volume':       daily['volume'].tolist(),
        # 周线
        'weekly_dates': [str(w['week_end'].date()) for _,w in weekly.iterrows()],
        'weekly_open':  weekly['open'].round(4).tolist(),
        'weekly_high':  weekly['high'].round(4).tolist(),
        'weekly_low':   weekly['low'].round(4).tolist(),
        'weekly_close': weekly['close'].round(4).tolist(),
        'weekly_state': [str({1:'UP',-1:'DOWN',0:'FLAT'}[s]) for s in weekly['state']],
        'weekly_sig':   weekly['wts_signal'].tolist(),
        # 日线信号
        'weekly_perm':  daily['weekly_perm'].tolist(),
        'dts_signal':   daily['dts_signal'].tolist(),
        'simple_signal':daily['simple_signal'].tolist(),
        'dts_state':    daily['state'].tolist(),
        # 仓位
        'pos_wts':      daily['pos_wts'].tolist(),
        'pos_wts_dts':  daily['pos_wts_dts'].tolist(),
        'pos_wts_sim':  daily['pos_wts_sim'].tolist(),
        # 回测结果
        'wts':  {**r_wts,  'trades': r_wts['trades']},
        'dts':  {**r_dts,  'trades': r_dts['trades']},
        'sim':  {**r_sim,  'trades': r_sim['trades']},
        'status': {
            'name':        name,
            'date':        str(last['date'].date()),
            'close':       round(last['close'], 4),
            'weekly_perm': int(last['weekly_perm']),
            'dts_signal':  int(last['dts_signal']),
            'simple_signal': int(last['simple_signal']),
            'pos_wts':     int(last['pos_wts']),
            'pos_wts_dts': int(last['pos_wts_dts']),
            'pos_wts_sim': int(last['pos_wts_sim']),
            'dts_state':   str({1:'UP',-1:'DOWN',0:'FLAT'}[int(last['state'])]),
            # 三策略指标
            'wts_alpha': mw['alpha'], 'dts_alpha': md['alpha'], 'sim_alpha': ms['alpha'],
            'wts_ret': mw['total_return'], 'dts_ret': md['total_return'], 'sim_ret': ms['total_return'],
            'bnh_ret': mw['bnh_return'],
            'wts_sharpe': mw['sharpe'], 'dts_sharpe': md['sharpe'], 'sim_sharpe': ms['sharpe'],
            'wts_mdd': mw['max_drawdown'], 'dts_mdd': md['max_drawdown'], 'sim_mdd': ms['max_drawdown'],
            'wts_long_pct': mw['long_pct'], 'dts_long_pct': md['long_pct'], 'sim_long_pct': ms['long_pct'],
        }
    }

out = OUTPUT / 'dual_layer_data.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(chart_data, f, ensure_ascii=False, default=str)
print(f"\n数据已保存至 {out}")
