"""
WTS+DTS 分阶段回测（使用各ETF最优参数）
注意：信号在全量数据上计算（需要历史热身），
      仅截取各阶段区间内的仓位和收益进行统计。
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

UPLOADS = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/uploads")
OUTPUT  = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/outputs")

# ── 固定参数 ──────────────────────────────────────────────────────────────────
W_FLAT=0.015; W_SAME=0.90; W_REV=0.45
D_FLAT=0.005
COST_BPS=15
UP=1; DOWN=-1; FLAT=0

# 各ETF最优日线参数（来自网格搜索结果）
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

# 三个测试区间
PERIODS = [
    ("P1", "2025-01-01", "2025-08-31", "2025年1月～8月"),
    ("P2", "2025-08-01", "2026-01-31", "2025年8月～2026年1月"),
    ("P3", "2025-08-01", "2026-03-31", "2025年8月～2026年3月"),
]

# ── 工具函数 ──────────────────────────────────────────────────────────────────
def load_etf(name):
    df = pd.read_csv(UPLOADS/ETF_FILES[name], encoding='utf-8-sig')
    df = df.rename(columns={'日期':'date','开盘':'open','收盘':'close',
                             '最高':'high','最低':'low','成交量':'volume'})
    df['date'] = pd.to_datetime(df['date'])
    return df[['date','open','high','low','close']].sort_values('date').reset_index(drop=True)

def classify(row, thr):
    amp=(row['high']-row['low'])/row['open']
    if amp<thr: return FLAT
    return UP if row['close']>=row['open'] else DOWN

def amp_pct(row):
    return (row['high']-row['low'])/row['open']*100.0

def seven_rules(dp,dc,ap,ac,prev_pos,st,rt):
    raw=None; rule=None
    if   dp==UP   and dc==UP:   rule,raw=1, 1
    elif dp==DOWN and dc==DOWN: rule,raw=2,-1
    elif dp==UP   and dc==DOWN: rule,raw=3,-1
    elif dp==DOWN and dc==UP:   rule,raw=4, 1
    elif (dp==FLAT or dp==UP)  and (dc==UP   or dc==FLAT): return 1,5,False
    elif (dp==FLAT or dp==DOWN)and (dc==DOWN or dc==FLAT): return 0,6,False
    elif dp==FLAT and dc==FLAT: return prev_pos,7,False
    else: return prev_pos,None,False
    diff=abs(ac-ap); thr=st if (dp>0)==(dc>0) else rt
    if diff<thr: return prev_pos,rule,True
    return max(raw,0),rule,False

def build_all_signals(daily, d_same, d_rev):
    """在全量数据上计算所有信号，返回带信号的完整日线表"""
    d=daily.copy()
    # 周线
    d['week_key']=d['date'].dt.to_period('W')
    def agg_w(g):
        g=g.sort_values('date')
        return pd.Series({'week_end':g['date'].iloc[-1],
            'open':g['open'].iloc[0],'high':g['high'].max(),
            'low':g['low'].min(),'close':g['close'].iloc[-1]})
    weekly=d.groupby('week_key').apply(agg_w).reset_index().dropna()
    weekly['state']=weekly.apply(lambda r:classify(r,W_FLAT),axis=1)
    weekly['amp']  =weekly.apply(amp_pct,axis=1)
    pos=0; sigs=[0]
    for i in range(1,len(weekly)):
        p,c=weekly.iloc[i-1],weekly.iloc[i]
        np_,_,_=seven_rules(p['state'],c['state'],p['amp'],c['amp'],pos,W_SAME,W_REV)
        sigs.append(np_); pos=np_
    weekly['wts_signal']=sigs
    wk_keys=weekly['week_key'].tolist(); ws=weekly['wts_signal'].tolist()
    w2p={str(wk_keys[i+1]):ws[i] for i in range(len(wk_keys)-1)}
    d['weekly_perm']=d['week_key'].apply(lambda wk:w2p.get(str(wk),0))

    # 日线DTS
    d['ds']=d.apply(lambda r:classify(r,D_FLAT),axis=1)
    d['da']=d.apply(amp_pct,axis=1)
    pos=0; dsigs=[0]
    for i in range(1,len(d)):
        p,c=d.iloc[i-1],d.iloc[i]
        np_,_,_=seven_rules(p['ds'],c['ds'],p['da'],c['da'],pos,d_same,d_rev)
        dsigs.append(np_); pos=np_
    d['dts_signal']=dsigs
    dts_shifted=d['dts_signal'].shift(1).fillna(0).astype(int)
    d['pos']=(d['weekly_perm']*dts_shifted).clip(0,1)
    d['pos_wts']=d['weekly_perm']   # 纯WTS对比
    return d, weekly

def backtest_period(daily_full, pos_col, start, end, init=1_000_000.0):
    """截取指定时间段，以该段第一日开盘价为基准执行回测"""
    d=daily_full[(daily_full['date']>=start)&(daily_full['date']<=end)].copy().reset_index(drop=True)
    if len(d)<5:
        return None

    cash=init; shares=0.0; pos=0; trades=[]; entry_p=0.0; entry_date=None
    equity=[]
    for i,row in d.iterrows():
        np_=int(row[pos_col]); o=row['open']; c=row['close']
        if np_!=pos:
            if pos==1 and shares>0:
                cash=shares*o*(1-COST_BPS/10000)
                pnl=(o*(1-COST_BPS/10000)-entry_p)/entry_p*100
                trades.append({'entry_date':str(entry_date.date()),
                    'exit_date':str(row['date'].date()),
                    'entry_price':round(entry_p,4),'exit_price':round(o,4),
                    'pnl_pct':round(pnl,2),'hold_days':(row['date']-entry_date).days})
                shares=0.0
            if np_==1:
                shares=(cash*(1-COST_BPS/10000))/o
                cash=0.0; entry_p=o*(1+COST_BPS/10000); entry_date=row['date']
        pos=np_
        equity.append(cash+shares*c)

    if pos==1 and shares>0:
        last=d.iloc[-1]
        sell=shares*last['close']*(1-COST_BPS/10000)
        pnl=(last['close']*(1-COST_BPS/10000)-entry_p)/entry_p*100
        trades.append({'entry_date':str(entry_date.date()),
            'exit_date':str(last['date'].date()),
            'entry_price':round(entry_p,4),'exit_price':round(last['close'],4),
            'pnl_pct':round(pnl,2),'hold_days':(last['date']-entry_date).days})

    eq=pd.Series(equity); bnh=init*d['close']/d['close'].iloc[0]
    n=len(eq)
    total_r=(eq.iloc[-1]/init-1)*100
    bnh_r=(bnh.iloc[-1]/init-1)*100
    alpha=total_r-bnh_r
    dr=eq.pct_change().dropna()
    sharpe=dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0
    mdd=((eq-eq.cummax())/eq.cummax()).min()*100
    wins=[t for t in trades if t['pnl_pct']>0]
    wr=len(wins)/len(trades)*100 if trades else 0
    long_p=(d[pos_col]==1).sum()/n*100

    return {
        'dates':  [str(x.date()) for x in d['date']],
        'close':  d['close'].round(4).tolist(),
        'equity': eq.round(2).tolist(),
        'bnh':    bnh.round(2).tolist(),
        'cum_ret':((eq/init-1)*100).round(2).tolist(),
        'bnh_ret':((bnh/init-1)*100).round(2).tolist(),
        'pos':    d[pos_col].tolist(),
        'trades': trades,
        'metrics':{
            'total_return': round(total_r,2),
            'bnh_return':   round(bnh_r,2),
            'alpha':        round(alpha,2),
            'sharpe':       round(sharpe,2),
            'max_drawdown': round(mdd,2),
            'win_rate':     round(wr,1),
            'n_trades':     len(trades),
            'long_pct':     round(long_p,1),
            'n_days':       n,
            'start':        str(d['date'].iloc[0].date()),
            'end':          str(d['date'].iloc[-1].date()),
        }
    }

# ── 主流程 ────────────────────────────────────────────────────────────────────
all_data = {}

print(f"{'标的':12s}  {'参数':12s}  ", end='')
for _,s,e,label in PERIODS:
    print(f"{'['+label+']':20s} ", end='')
print()
print("─"*110)

for name in ETF_FILES:
    d_same, d_rev = OPT_PARAMS[name]
    daily = load_etf(name)
    daily_sig, weekly = build_all_signals(daily, d_same, d_rev)

    print(f"{name:12s}  SAME={d_same:.2f}/REV={d_rev:.2f}  ", end='')

    etf_results = {'opt_params': {'same': d_same, 'rev': d_rev}, 'periods': {}}

    for pid, start, end, label in PERIODS:
        r_dts = backtest_period(daily_sig, 'pos',     start, end)
        r_wts = backtest_period(daily_sig, 'pos_wts', start, end)

        if r_dts is None:
            print(f"{'N/A':20s} ", end='')
            etf_results['periods'][pid] = None
            continue

        m=r_dts['metrics']; mw=r_wts['metrics']
        print(f"α{m['alpha']:+.1f}% DTS{m['total_return']:+.1f}% WTS{mw['total_return']:+.1f}% BNH{m['bnh_return']:+.1f}%  ", end='')

        etf_results['periods'][pid] = {
            'label': label, 'pid': pid,
            'dts': r_dts, 'wts': r_wts,
        }

    all_data[name] = etf_results
    print()

out = OUTPUT / 'period_results.json'
with open(out,'w',encoding='utf-8') as f:
    json.dump(all_data, f, ensure_ascii=False, default=str)
print(f"\n数据已保存: {out}  ({out.stat().st_size//1024} KB)")
