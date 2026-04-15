"""
双层趋势策略回测 — 3年版
数据：2023-04-17 ~ 2026-04-15（725 日 / ~145 周 K 线）
策略：纯 WTS / WTS+DTS / WTS+简单UP-DOWN，三路对比
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

UPLOADS = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/uploads")
OUTPUT  = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/outputs")
OUTPUT.mkdir(exist_ok=True)

# ── 参数 ──────────────────────────────────────────────────────────────────────
W_FLAT = 0.015; W_SAME = 0.90; W_REV = 0.45   # 周线
D_FLAT = 0.005; D_SAME = 0.30; D_REV = 0.15   # 日线
UP=1; DOWN=-1; FLAT=0

ETF_FILES_3Y = {
    "上证50ETF":  "510050_上证_50ETF.csv",
    "沪深300ETF": "510300_沪深_300ETF.csv",
    "中证500ETF": "510500_中证_500ETF.csv",
    "科创50ETF":  "588080_科创_50ETF.csv",
    "深证100ETF": "159901_深证_100ETF.csv",
    "创业板ETF":  "159915_创业板_ETF.csv",
}

# ── 数据加载 ──────────────────────────────────────────────────────────────────
def load_3y(name):
    f = UPLOADS / ETF_FILES_3Y[name]
    df = pd.read_csv(f, encoding='utf-8-sig')
    df = df.rename(columns={'日期':'date','开盘':'open','收盘':'close',
                             '最高':'high','最低':'low','成交量':'volume','成交额':'amount'})
    df['date'] = pd.to_datetime(df['date'])
    return df[['date','open','high','low','close','volume']].sort_values('date').reset_index(drop=True)

# ── 信号工具 ──────────────────────────────────────────────────────────────────
def classify(row, thr):
    amp = (row['high'] - row['low']) / row['open']
    if amp < thr: return FLAT
    return UP if row['close'] >= row['open'] else DOWN

def amp_pct(row):
    return (row['high'] - row['low']) / row['open'] * 100.0

def seven_rules(dp, dc, ap, ac, prev_pos, same_thr, rev_thr):
    raw = None; rule = None
    if   dp==UP   and dc==UP:   rule,raw = 1, 1
    elif dp==DOWN and dc==DOWN: rule,raw = 2,-1
    elif dp==UP   and dc==DOWN: rule,raw = 3,-1
    elif dp==DOWN and dc==UP:   rule,raw = 4, 1
    elif (dp==FLAT or dp==UP)  and (dc==UP   or dc==FLAT): return 1,5,False
    elif (dp==FLAT or dp==DOWN)and (dc==DOWN or dc==FLAT): return 0,6,False
    elif dp==FLAT and dc==FLAT: return prev_pos,7,False
    else: return prev_pos,None,False
    diff = abs(ac - ap)
    thr  = same_thr if ((dp>0)==(dc>0)) else rev_thr
    if diff < thr: return prev_pos, rule, True
    return max(raw, 0), rule, False

# ── Layer 1：周线 WTS ─────────────────────────────────────────────────────────
def build_weekly_signals(daily):
    daily = daily.copy()
    daily['week_key'] = daily['date'].dt.to_period('W')

    def agg_w(g):
        g = g.sort_values('date')
        return pd.Series({
            'week_start': g['date'].iloc[0],
            'week_end':   g['date'].iloc[-1],
            'open':  g['open'].iloc[0], 'high': g['high'].max(),
            'low':   g['low'].min(),    'close': g['close'].iloc[-1],
        })
    weekly = daily.groupby('week_key').apply(agg_w).reset_index().dropna()
    weekly['state'] = weekly.apply(lambda r: classify(r, W_FLAT), axis=1)
    weekly['amp']   = weekly.apply(amp_pct, axis=1)

    pos=0; w_sigs=[]
    for i in range(len(weekly)):
        if i==0: w_sigs.append(0); continue
        prev, curr = weekly.iloc[i-1], weekly.iloc[i]
        new_pos,_,_ = seven_rules(prev['state'],curr['state'],prev['amp'],curr['amp'],pos,W_SAME,W_REV)
        w_sigs.append(new_pos); pos=new_pos
    weekly['wts_signal'] = w_sigs

    wk_keys  = weekly['week_key'].tolist()
    wts_sigs = weekly['wts_signal'].tolist()
    week_to_perm = {str(wk_keys[i+1]): wts_sigs[i] for i in range(len(wk_keys)-1)}
    daily['weekly_perm'] = daily['week_key'].apply(lambda wk: week_to_perm.get(str(wk), 0))
    return daily, weekly

# ── Layer 2A：DTS 完整规则 ────────────────────────────────────────────────────
def build_dts_signals(daily):
    daily = daily.copy()
    daily['d_state'] = daily.apply(lambda r: classify(r, D_FLAT), axis=1)
    daily['d_amp']   = daily.apply(amp_pct, axis=1)
    pos=0; sigs=[0]
    for i in range(1, len(daily)):
        prev, curr = daily.iloc[i-1], daily.iloc[i]
        new_pos,_,_ = seven_rules(prev['d_state'],curr['d_state'],prev['d_amp'],curr['d_amp'],pos,D_SAME,D_REV)
        sigs.append(new_pos); pos=new_pos
    daily['dts_signal'] = sigs
    return daily

# ── Layer 2B：简单 UP/DOWN ────────────────────────────────────────────────────
def build_simple_signals(daily):
    daily = daily.copy()
    today_up = (daily['close'] >= daily['open']).astype(int)
    daily['simple_signal'] = today_up.shift(1).fillna(0).astype(int)
    return daily

# ── 回测引擎 ──────────────────────────────────────────────────────────────────
def backtest(daily, pos_col, cost_bps=15, init_cash=1_000_000.0):
    """
    cost_bps: 单边成本，买入0.10%，卖出0.10%+印花税0.05% = 0.15% = 15bps
    """
    d = daily.copy().reset_index(drop=True)
    cash=init_cash; shares=0.0; pos=0; trades=[]
    entry_price=0.0; entry_date=None
    equity=[]; prev_pos=0

    for i, row in d.iterrows():
        new_pos = int(row[pos_col])
        o = row['open']; c = row['close']

        # 以开盘价换仓，扣手续费
        if new_pos != pos:
            if pos==1 and shares>0:
                sell_cost = shares * o * (cost_bps/10000)
                cash = shares * o - sell_cost
                pnl  = (o*(1-cost_bps/10000) - entry_price) / entry_price * 100
                trades.append({'entry_date':str(entry_date.date()),
                    'exit_date':str(row['date'].date()),
                    'entry_price':round(entry_price,4),
                    'exit_price':round(o,4),
                    'pnl_pct':round(pnl,2),
                    'hold_days':(row['date']-entry_date).days})
                shares=0.0
            if new_pos==1:
                buy_cost = cash * (cost_bps/10000)
                shares   = (cash - buy_cost) / o
                cash=0.0; entry_price=o*(1+cost_bps/10000); entry_date=row['date']
        pos=new_pos
        equity.append(cash + shares*c)

    if pos==1 and shares>0:
        last=d.iloc[-1]
        sell_cost=shares*last['close']*(cost_bps/10000)
        cash=shares*last['close']-sell_cost
        pnl=(last['close']*(1-cost_bps/10000)-entry_price)/entry_price*100
        trades.append({'entry_date':str(entry_date.date()),
            'exit_date':str(last['date'].date()),
            'entry_price':round(entry_price,4),
            'exit_price':round(last['close'],4),
            'pnl_pct':round(pnl,2),
            'hold_days':(last['date']-entry_date).days})

    eq  = pd.Series(equity, index=d.index)
    bnh = init_cash * d['close'] / d['close'].iloc[0]
    n   = len(eq)
    total_r = eq.iloc[-1]/init_cash - 1
    bnh_r   = bnh.iloc[-1]/init_cash - 1
    ann_r   = (1+total_r)**(252/n) - 1
    bnh_ann = (1+bnh_r)  **(252/n) - 1
    dr      = eq.pct_change().dropna()
    sharpe  = dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0
    mdd     = ((eq - eq.cummax())/eq.cummax()).min()
    wins    = [t for t in trades if t['pnl_pct']>0]
    wr      = len(wins)/len(trades) if trades else 0
    long_d  = (d[pos_col]==1).sum()

    # 年度收益
    d2=d.copy(); d2['equity']=equity
    d2['year']=d2['date'].dt.year
    yr_ret={}
    for yr, g in d2.groupby('year'):
        r=(g['equity'].iloc[-1]/g['equity'].iloc[0]-1)*100
        yr_ret[str(yr)]=round(r,2)

    return {
        'equity':   eq.round(2).tolist(),
        'bnh':      bnh.round(2).tolist(),
        'cum_ret':  ((eq/init_cash-1)*100).round(2).tolist(),
        'bnh_ret':  ((bnh/init_cash-1)*100).round(2).tolist(),
        'trades':   trades,
        'yr_ret':   yr_ret,
        'metrics':{
            'total_return':  round(total_r*100,2),
            'bnh_return':    round(bnh_r*100,2),
            'alpha':         round((total_r-bnh_r)*100,2),
            'annual_return': round(ann_r*100,2),
            'bnh_annual':    round(bnh_ann*100,2),
            'sharpe':        round(sharpe,2),
            'max_drawdown':  round(mdd*100,2),
            'win_rate':      round(wr*100,1),
            'n_trades':      len(trades),
            'long_days':     int(long_d),
            'long_pct':      round(long_d/n*100,1),
        }
    }

# ── 主流程 ────────────────────────────────────────────────────────────────────
chart_data = {}
print(f"{'标的':12s} {'BNH':>8s}  {'纯WTS':>8s} {'α':>7s}  {'WTS+DTS':>8s} {'α':>7s}  {'WTS+简单':>8s} {'α':>7s}")
print("─"*80)

for name in ETF_FILES_3Y:
    daily = load_3y(name)
    daily, weekly = build_weekly_signals(daily)
    daily = build_dts_signals(daily)
    daily = build_simple_signals(daily)

    # dts_signal[i] 用的是 bar[i] 的收盘生成，须在 bar[i+1] 开盘执行，shift(1)
    dts_shifted = daily['dts_signal'].shift(1).fillna(0).astype(int)
    daily['pos_wts']     = daily['weekly_perm']
    daily['pos_wts_dts'] = (daily['weekly_perm'] * dts_shifted).clip(0, 1)
    daily['pos_wts_sim'] = (daily['weekly_perm'] * daily['simple_signal']).clip(0, 1)

    r_wts = backtest(daily, 'pos_wts')
    r_dts = backtest(daily, 'pos_wts_dts')
    r_sim = backtest(daily, 'pos_wts_sim')
    mw=r_wts['metrics']; md=r_dts['metrics']; ms=r_sim['metrics']

    def s(v): return f"{v:+.2f}%"
    print(f"{name:12s}  BNH {s(mw['bnh_return'])}  "
          f"WTS {s(mw['total_return'])} α{s(mw['alpha'])}  "
          f"DTS {s(md['total_return'])} α{s(md['alpha'])}  "
          f"SIM {s(ms['total_return'])} α{s(ms['alpha'])}")

    last = daily.iloc[-1]
    chart_data[name] = {
        'dates':        [str(d.date()) for d in daily['date']],
        'open':         daily['open'].round(4).tolist(),
        'high':         daily['high'].round(4).tolist(),
        'low':          daily['low'].round(4).tolist(),
        'close':        daily['close'].round(4).tolist(),
        'volume':       daily['volume'].tolist(),
        'weekly_dates': [str(w['week_end'].date()) for _,w in weekly.iterrows()],
        'weekly_open':  weekly['open'].round(4).tolist(),
        'weekly_high':  weekly['high'].round(4).tolist(),
        'weekly_low':   weekly['low'].round(4).tolist(),
        'weekly_close': weekly['close'].round(4).tolist(),
        'weekly_state': [{1:'UP',-1:'DOWN',0:'FLAT'}[s] for s in weekly['state']],
        'weekly_sig':   weekly['wts_signal'].tolist(),
        'weekly_perm':  daily['weekly_perm'].tolist(),
        'dts_signal':   daily['dts_signal'].tolist(),
        'simple_signal':daily['simple_signal'].tolist(),
        'dts_state':    daily['d_state'].tolist(),
        'pos_wts':      daily['pos_wts'].tolist(),
        'pos_wts_dts':  daily['pos_wts_dts'].tolist(),
        'pos_wts_sim':  daily['pos_wts_sim'].tolist(),
        'wts':  r_wts,
        'dts':  r_dts,
        'sim':  r_sim,
        'status':{
            'name': name, 'date': str(last['date'].date()), 'close': round(last['close'],4),
            'weekly_perm':    int(last['weekly_perm']),
            'dts_signal':     int(last['dts_signal']),
            'simple_signal':  int(last['simple_signal']),
            'pos_wts':        int(last['pos_wts']),
            'pos_wts_dts':    int(last['pos_wts_dts']),
            'pos_wts_sim':    int(last['pos_wts_sim']),
            'dts_state':      {1:'UP',-1:'DOWN',0:'FLAT'}[int(last['d_state'])],
            'wts_alpha': mw['alpha'],   'dts_alpha': md['alpha'],   'sim_alpha': ms['alpha'],
            'wts_ret': mw['total_return'], 'dts_ret': md['total_return'], 'sim_ret': ms['total_return'],
            'bnh_ret': mw['bnh_return'],
            'wts_sharpe': mw['sharpe'],  'dts_sharpe': md['sharpe'],  'sim_sharpe': ms['sharpe'],
            'wts_mdd': mw['max_drawdown'],'dts_mdd': md['max_drawdown'],'sim_mdd': ms['max_drawdown'],
            'wts_long_pct': mw['long_pct'],'dts_long_pct': md['long_pct'],'sim_long_pct': ms['long_pct'],
            'wts_annual': mw['annual_return'], 'dts_annual': md['annual_return'],
            'bnh_annual': mw['bnh_annual'], 'n_weeks': len(weekly),
            'wts_wr': mw['win_rate'], 'dts_wr': md['win_rate'],
            'wts_trades': mw['n_trades'], 'dts_trades': md['n_trades'],
            'wts_yr': r_wts['yr_ret'], 'dts_yr': r_dts['yr_ret'],
        }
    }

out = OUTPUT / 'dual_3y_data.json'
with open(out,'w',encoding='utf-8') as f:
    json.dump(chart_data, f, ensure_ascii=False, default=str)
print(f"\n数据已保存: {out}  ({out.stat().st_size//1024} KB)")
