"""
日线DTS参数优化：针对每只ETF独立搜索最优 D_SAME / D_REV
目标：最大化 alpha（策略收益 - BNH）
约束：交易笔数 >= 3（避免退化为空仓）
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import itertools
import warnings
warnings.filterwarnings('ignore')

UPLOADS = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/uploads")
OUTPUT  = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/outputs")

# ── 固定参数 ──────────────────────────────────────────────────────────────────
W_FLAT=0.015; W_SAME=0.90; W_REV=0.45
D_FLAT=0.005
UP=1; DOWN=-1; FLAT=0
COST_BPS = 15   # 单边 0.15%

ETF_FILES = {
    "上证50ETF":  "510050_上证_50ETF.csv",
    "沪深300ETF": "510300_沪深_300ETF.csv",
    "中证500ETF": "510500_中证_500ETF.csv",
    "科创50ETF":  "588080_科创_50ETF.csv",
    "深证100ETF": "159901_深证_100ETF.csv",
    "创业板ETF":  "159915_创业板_ETF.csv",
}

# ── 搜索空间 ──────────────────────────────────────────────────────────────────
# 粗粒度全局搜索，再在最优附近细化
SAME_RANGE = [0.30, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.50, 3.00, 3.50, 4.00]
REV_RANGE  = [0.15, 0.30, 0.45, 0.60, 0.75, 1.00, 1.25, 1.50, 2.00]

# ── 工具函数 ──────────────────────────────────────────────────────────────────
def load_etf(name):
    df = pd.read_csv(UPLOADS / ETF_FILES[name], encoding='utf-8-sig')
    df = df.rename(columns={'日期':'date','开盘':'open','收盘':'close',
                             '最高':'high','最低':'low','成交量':'volume'})
    df['date'] = pd.to_datetime(df['date'])
    return df[['date','open','high','low','close']].sort_values('date').reset_index(drop=True)

def classify(row, thr):
    amp = (row['high']-row['low'])/row['open']
    if amp < thr: return FLAT
    return UP if row['close']>=row['open'] else DOWN

def amp_pct(row):
    return (row['high']-row['low'])/row['open']*100.0

def seven_rules(dp, dc, ap, ac, prev_pos, same_thr, rev_thr):
    raw=None; rule=None
    if   dp==UP   and dc==UP:   rule,raw=1, 1
    elif dp==DOWN and dc==DOWN: rule,raw=2,-1
    elif dp==UP   and dc==DOWN: rule,raw=3,-1
    elif dp==DOWN and dc==UP:   rule,raw=4, 1
    elif (dp==FLAT or dp==UP)  and (dc==UP   or dc==FLAT): return 1,5,False
    elif (dp==FLAT or dp==DOWN)and (dc==DOWN or dc==FLAT): return 0,6,False
    elif dp==FLAT and dc==FLAT: return prev_pos,7,False
    else: return prev_pos,None,False
    diff=abs(ac-ap); thr=same_thr if (dp>0)==(dc>0) else rev_thr
    if diff<thr: return prev_pos,rule,True
    return max(raw,0),rule,False

def build_weekly_signals(daily):
    d=daily.copy()
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
    wk_keys=weekly['week_key'].tolist(); wts_s=weekly['wts_signal'].tolist()
    w2p={str(wk_keys[i+1]):wts_s[i] for i in range(len(wk_keys)-1)}
    d['weekly_perm']=d['week_key'].apply(lambda wk:w2p.get(str(wk),0))
    return d

def build_dts(daily, d_same, d_rev):
    d=daily.copy()
    d['ds']=d.apply(lambda r:classify(r,D_FLAT),axis=1)
    d['da']=d.apply(amp_pct,axis=1)
    pos=0; sigs=[0]
    for i in range(1,len(d)):
        p,c=d.iloc[i-1],d.iloc[i]
        np_,_,_=seven_rules(p['ds'],c['ds'],p['da'],c['da'],pos,d_same,d_rev)
        sigs.append(np_); pos=np_
    d['dts']=sigs
    dts_shifted=d['dts'].shift(1).fillna(0).astype(int)
    d['pos']=(d['weekly_perm']*dts_shifted).clip(0,1)
    return d

def backtest_fast(daily, pos_col='pos', init=1_000_000.0):
    d=daily.reset_index(drop=True)
    cash=init; shares=0.0; pos=0; trades=0; entry_p=0.0
    equity=[]
    for i,row in d.iterrows():
        np_=int(row[pos_col]); o=row['open']; c=row['close']
        if np_!=pos:
            if pos==1 and shares>0:
                cash=shares*o*(1-COST_BPS/10000); shares=0.0; trades+=1
            if np_==1:
                shares=(cash*(1-COST_BPS/10000))/o; cash=0.0; entry_p=o; trades+=1
        pos=np_
        equity.append(cash+shares*c)
    if pos==1 and shares>0:
        cash=shares*d.iloc[-1]['close']*(1-COST_BPS/10000); trades+=1
    eq=pd.Series(equity)
    bnh=init*d['close']/d['close'].iloc[0]
    total_r=(eq.iloc[-1]/init-1)*100
    bnh_r=(bnh.iloc[-1]/init-1)*100
    alpha=total_r-bnh_r
    dr=eq.pct_change().dropna()
    sharpe=dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0
    mdd=((eq-eq.cummax())/eq.cummax()).min()*100
    long_pct=(d[pos_col]==1).sum()/len(d)*100
    n_trades=trades//2  # 买+卖算一笔
    return {'alpha':round(alpha,3),'total_r':round(total_r,3),'bnh_r':round(bnh_r,3),
            'sharpe':round(sharpe,3),'mdd':round(mdd,3),'long_pct':round(long_pct,1),
            'n_trades':n_trades}

# ── 统计日线振幅分布 ──────────────────────────────────────────────────────────
print("═"*70)
print("日线振幅分布（用于理解参数量纲）")
print("─"*70)
for name in ETF_FILES:
    d=load_etf(name)
    amps=d.apply(amp_pct,axis=1)
    print(f"{name:12s}  均值{amps.mean():.2f}%  中位数{amps.median():.2f}%  "
          f"25%分位{amps.quantile(.25):.2f}%  75%分位{amps.quantile(.75):.2f}%")

# ── 主优化循环 ────────────────────────────────────────────────────────────────
print("\n" + "═"*70)
print("参数优化（当前基准：SAME=0.30%, REV=0.15%）")
print("─"*70)

all_results = {}
baseline_params = (0.30, 0.15)

for name in ETF_FILES:
    daily_raw = load_etf(name)
    daily_w   = build_weekly_signals(daily_raw)

    # 基准结果
    d_base = build_dts(daily_w, *baseline_params)
    r_base = backtest_fast(d_base)

    # 网格搜索
    records = []
    for same, rev in itertools.product(SAME_RANGE, REV_RANGE):
        if rev > same: continue   # rev 应 <= same
        d = build_dts(daily_w, same, rev)
        r = backtest_fast(d)
        records.append({'same':same,'rev':rev, **r})

    df_res = pd.DataFrame(records)

    # 最优：alpha 最大，且交易笔数 >= 3
    valid = df_res[df_res['n_trades'] >= 3]
    if valid.empty: valid = df_res
    best_idx = valid['alpha'].idxmax()
    best = valid.loc[best_idx]

    # 按 alpha 排列，取 top-10
    top10 = valid.nlargest(10, 'alpha')[['same','rev','alpha','total_r','n_trades','sharpe','mdd','long_pct']]

    print(f"\n{name}")
    print(f"  基准(0.30/0.15): α={r_base['alpha']:+.2f}%  收益{r_base['total_r']:+.2f}%  "
          f"交易{r_base['n_trades']}笔  夏普{r_base['sharpe']:.2f}  回撤{r_base['mdd']:.2f}%")
    print(f"  最优({best['same']:.2f}/{best['rev']:.2f}): α={best['alpha']:+.2f}%  "
          f"收益{best['total_r']:+.2f}%  交易{int(best['n_trades'])}笔  "
          f"夏普{best['sharpe']:.2f}  回撤{best['mdd']:.2f}%  持多{best['long_pct']:.1f}%")
    print(f"  改善: α {r_base['alpha']:+.2f}% → {best['alpha']:+.2f}%  "
          f"({best['alpha']-r_base['alpha']:+.2f}ppt)  "
          f"交易{r_base['n_trades']}笔 → {int(best['n_trades'])}笔")

    all_results[name] = {
        'baseline': {**r_base, 'same':0.30, 'rev':0.15},
        'best':     best.to_dict(),
        'top10':    top10.to_dict('records'),
        'grid':     df_res[['same','rev','alpha','n_trades','sharpe']].to_dict('records'),
        'amp_stats': {
            'mean':   round(daily_raw.apply(amp_pct,axis=1).mean(),3),
            'median': round(daily_raw.apply(amp_pct,axis=1).median(),3),
            'q25':    round(daily_raw.apply(amp_pct,axis=1).quantile(.25),3),
            'q75':    round(daily_raw.apply(amp_pct,axis=1).quantile(.75),3),
        },
        'bnh_r': r_base['bnh_r'],
    }

out = OUTPUT / 'opt_results.json'
with open(out,'w',encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, default=str)
print(f"\n数据已保存: {out}")
