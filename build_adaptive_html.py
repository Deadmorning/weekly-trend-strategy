"""自适应周五清仓策略对比仪表盘"""
import json
from pathlib import Path

OUTPUT = Path("/home/node/a0/workspace/9f6b0b84-8364-43ba-9e79-f77b9e0902c7/workspace/outputs")
with open(OUTPUT/'adaptive_results.json', encoding='utf-8') as f:
    raw = f.read()

HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>WTS 自适应周五清仓策略</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--border:#30363d;
  --text:#e6edf3;--muted:#8b949e;
  --green:#3fb950;--red:#f85149;--yellow:#d29922;
  --adt:#ffa657;--wts:#8b949e;--asy:#3fb950;--bnh:#555;
}
body{background:var(--bg);color:var(--text);font-family:-apple-system,sans-serif;font-size:13px}
.hdr{background:var(--bg2);border-bottom:1px solid var(--border);padding:9px 16px;
  display:flex;align-items:center;justify-content:space-between}
.hdr h1{font-size:14px;font-weight:700}
.leg{display:flex;gap:10px;font-size:10px;color:var(--muted)}
.li{display:flex;align-items:center;gap:4px}
.ld{width:20px;height:3px;border-radius:2px}

.layout{display:grid;grid-template-columns:232px 1fr;height:calc(100vh - 44px)}
.side{background:var(--bg2);border-right:1px solid var(--border);overflow-y:auto}
.main{overflow-y:auto;padding:10px;display:flex;flex-direction:column;gap:8px}

.sc{padding:9px 12px;cursor:pointer;border-left:3px solid transparent;
  border-bottom:1px solid rgba(48,54,61,.35);transition:.1s}
.sc:hover{background:var(--bg3)}.sc.on{background:var(--bg3);border-left-color:#ffa657}
.sn{font-size:12px;font-weight:700;margin-bottom:5px}
.sg{display:grid;grid-template-columns:repeat(3,1fr);gap:3px}
.si{background:var(--bg3);border-radius:3px;padding:3px 4px;text-align:center}
.sl{font-size:8px;color:var(--muted)}.sv{font-size:10px;font-weight:700}
.best-tag{font-size:9px;padding:1px 5px;border-radius:3px;font-weight:600;margin-left:4px}

.card{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:11px}
.ct{font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:7px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.g3{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}

#c-eq-all{width:100%;height:240px}
#c-alpha-bar{width:100%;height:200px}
#c-trades-bar{width:100%;height:160px}
.mini-eq{width:100%;height:130px}

.krow{display:flex;gap:5px;flex-wrap:wrap}
.kc{flex:1;min-width:100px;background:var(--bg);border:1px solid var(--border);
  border-radius:5px;padding:7px 10px}
.kl{font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
.kv{font-size:15px;font-weight:700;margin-top:1px}.ks{font-size:9px;color:var(--muted);margin-top:1px}

.ptbl{width:100%;border-collapse:collapse;font-size:11px}
.ptbl th{background:var(--bg3);padding:5px 8px;text-align:center;color:var(--muted);
  font-size:8px;text-transform:uppercase;border-bottom:1px solid var(--border);
  border-right:1px solid rgba(48,54,61,.4)}
.ptbl th.nm{text-align:left}.ptbl td{padding:4px 8px;text-align:center;
  border-bottom:1px solid rgba(48,54,61,.3);border-right:1px solid rgba(48,54,61,.2)}
.ptbl td.nm{text-align:left;font-weight:700;font-size:10px}
.ptbl tr:hover td{background:var(--bg3)}
.ptbl .sub{color:var(--muted);font-size:9px}
.winner{font-weight:700;text-decoration:underline}

.logic{background:var(--bg3);border-radius:6px;padding:10px 13px;font-size:11px;
  line-height:1.8;border:1px solid var(--border)}
.logic code{background:var(--bg);padding:1px 5px;border-radius:3px;
  font-family:monospace;font-size:10px;color:#ffa657}
.warn{background:rgba(210,153,34,.1);border:1px solid rgba(210,153,34,.3);
  padding:7px 11px;border-radius:5px;font-size:10px;color:#d29922}
.good{background:rgba(63,185,80,.1);border:1px solid rgba(63,185,80,.3);
  padding:7px 11px;border-radius:5px;font-size:10px;color:#3fb950}

.g{color:var(--green)}.r{color:var(--red)}.m{color:var(--muted)}
.b{color:#58a6ff}.o{color:var(--adt)}
</style>
</head>
<body>
<div class="hdr">
  <div>
    <h1>WTS + 自适应周五清仓 &mdash; 三策略对比</h1>
    <div style="font-size:10px;color:var(--muted);margin-top:2px">
      含手续费 · 最优参数 · 2023-04-17 ~ 2026-04-15 &nbsp;|&nbsp;
      规则：WTS=1 周一入场；<b style="color:#ffa657">当周涨天≥3 → 持仓过周末</b>；当周涨天&lt;3 → 周五收盘清仓
    </div>
  </div>
  <div class="leg">
    <div class="li"><div class="ld" style="background:var(--adt)"></div>自适应清仓WTS</div>
    <div class="li"><div class="ld" style="background:var(--wts)"></div>纯WTS</div>
    <div class="li"><div class="ld" style="background:var(--asy)"></div>非对称DTS</div>
    <div class="li"><div class="ld" style="background:var(--bnh);border:1px dashed #888"></div>BNH</div>
  </div>
</div>

<div class="layout">
  <div class="side" id="side"></div>
  <div class="main" id="main"></div>
</div>

<script>
const D = __DATA__;
const NS = Object.keys(D);
const STRATS = [
  {k:'pos_adaptive', l:'自适应清仓WTS', c:'#ffa657'},
  {k:'pos_wts',      l:'纯WTS',         c:'#8b949e'},
  {k:'pos_asym',     l:'非对称DTS',     c:'#3fb950'},
];
const PIDS    = ['全程','P1','P2','P3'];
const PLABELS = {全程:'全程(3年)',P1:'P1: 2025年1月~8月',P2:'P2: 2025年8月~2026年1月',P3:'P3: 2025年8月~2026年3月'};
const PCOLS   = {全程:'#8b949e',P1:'#58a6ff',P2:'#3fb950',P3:'#ffa657'};
let cur = NS[0];
const C={}, $=id=>document.getElementById(id);
const gc=id=>{if(!C[id])C[id]=echarts.init($(id),'dark');return C[id];};
const p2=v=>(v>=0?'+':'')+Number(v).toFixed(2)+'%';
const p1=v=>(v>=0?'+':'')+Number(v).toFixed(1)+'%';
const cc=v=>v>0?'g':v<0?'r':'m';

function bestStrat(name, pid){
  const pr=D[name].periods[pid]; if(!pr)return null;
  return STRATS.map(s=>({k:s.k,a:pr[s.k]?pr[s.k].metrics.alpha:null}))
    .filter(s=>s.a!==null).sort((a,b)=>b.a-a.a)[0]?.k;
}

function renderSide(){
  $('side').innerHTML = NS.map(n=>{
    const b=bestStrat(n,'全程');
    const bc={pos_adaptive:'#ffa657',pos_wts:'#8b949e',pos_asym:'#3fb950'};
    const bl={pos_adaptive:'自适应最优',pos_wts:'WTS最优',pos_asym:'非对称最优'};
    const full=D[n].periods['全程'];
    const adtAlpha=full?.pos_adaptive?.metrics?.alpha??0;
    return `<div class="sc ${n===cur?'on':''}" onclick="sel('${n}')">
      <div class="sn">${n}
        ${b?`<span class="best-tag" style="background:${bc[b]}20;color:${bc[b]}">${bl[b]}</span>`:''}
      </div>
      <div class="sg">${STRATS.map(s=>{
        const r=full?.[s.k];
        const a=r?r.metrics.alpha:null;
        return `<div class="si" style="${s.k===b?'border:1px solid '+s.c+';background:'+s.c+'12':''}">
          <div class="sl" style="color:${s.c}">${s.l.length>5?s.l.slice(0,5)+'…':s.l}</div>
          <div class="sv ${a!=null?cc(a):'m'}">${a!=null?p1(a):'--'}</div>
        </div>`;
      }).join('')}</div>
      <div style="font-size:9px;color:var(--muted);margin-top:3px">
        BNH ${p2(full?.pos_wts?.metrics?.bnh_return??0)}
        · T=${full?.pos_adaptive?.metrics?.n_trades??0}笔
      </div>
    </div>`;
  }).join('');
}

function renderMain(n){
  const ed=D[n];
  const full=ed.periods['全程'];
  const adtA=full?.pos_adaptive?.metrics?.alpha??0;
  const isPositive=adtA>0;

  $('main').innerHTML = `
    <div class="${isPositive?'good':'warn'}">
      ${isPositive
        ? `✓ ${n} 自适应策略 3年超额α <b>${p2(adtA)}</b>，成功跑赢BNH！当周强势时持仓过周末，弱势时收盘清仓有效降低了回撤风险`
        : `⚠ ${n} 自适应策略 3年超额α ${p2(adtA)}，未能跑赢BNH。策略在持续强势牛市中仍会错失部分涨幅`
      }
    </div>
    <div class="logic">
      <b style="color:#ffa657">自适应周五清仓规则</b>（状态机）：
      <code>WTS=1 周一</code> → 入场 &nbsp;|&nbsp;
      <code>WTS=0</code> → 立即清仓 &nbsp;|&nbsp;
      周五收盘时：<code>当周涨天≥3</code> → 不清仓持仓过周末 &nbsp;|&nbsp; <code>当周涨天&lt;3</code> → 收盘强制平仓
      <br><span class="m">与「每周五必清仓」相比：强势周可保留持仓，减少无谓手续费；弱势周及时止盈止损</span>
    </div>
    <div class="krow">${STRATS.map(s=>{
      const r=full?.[s.k]; if(!r)return '';
      const m=r.metrics;
      return `<div class="kc" style="border-color:${s.c}30">
        <div class="kl" style="color:${s.c}">${s.l}</div>
        <div class="kv ${cc(m.alpha)}">${p2(m.alpha)}</div>
        <div class="ks">收益${p2(m.total_return)} · 夏普${m.sharpe} · 回撤${m.max_drawdown}% · 持多${m.long_pct}% · ${m.n_trades}笔</div>
      </div>`;
    }).join('')}<div class="kc">
      <div class="kl m">BNH</div>
      <div class="kv ${cc(full?.pos_wts?.metrics?.bnh_return??0)}">${p2(full?.pos_wts?.metrics?.bnh_return??0)}</div>
      <div class="ks">买入持有基准</div>
    </div></div>
    <div class="card"><div class="ct">全程累计收益曲线</div><div id="c-eq-all"></div></div>
    <div class="g2">
      <div class="card"><div class="ct">各阶段超额α对比</div><div id="c-alpha-bar"></div></div>
      <div class="card"><div class="ct">交易笔数（全程）& 持多比</div><div id="c-trades-bar"></div></div>
    </div>
    <div class="g3">${['P1','P2','P3'].map(p=>{
      const pr=ed.periods[p]; if(!pr) return '';
      return `<div class="card" style="border-color:${PCOLS[p]}25">
        <div class="ct" style="color:${PCOLS[p]}">${PLABELS[p]}</div>
        <div id="c-mini-${p.toLowerCase()}" class="mini-eq"></div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:3px;margin-top:6px">
          ${STRATS.map(s=>{const r=pr[s.k]; if(!r)return '';
            const m=r.metrics;
            return `<div style="text-align:center">
              <div style="font-size:8px;color:${s.c}">${s.l.length>5?s.l.slice(0,5)+'…':s.l}</div>
              <div style="font-size:11px;font-weight:700" class="${cc(m.alpha)}">${p1(m.alpha)}</div>
              <div style="font-size:9px;color:var(--muted)">${p1(m.total_return)}</div>
            </div>`;
          }).join('')}
        </div>
      </div>`;
    }).join('')}</div>
    <div class="card">
      <div class="ct">全ETF × 全阶段 超额α汇总（自适应 / 纯WTS / 非对称DTS）</div>
      <table class="ptbl" id="tbl"></table>
    </div>
  `;

  // equity chart
  if(full?.pos_adaptive){
    gc('c-eq-all').setOption({
      backgroundColor:'transparent',
      tooltip:{trigger:'axis'},
      legend:{top:2,textStyle:{color:'#8b949e',fontSize:9}},
      grid:{top:26,bottom:22,left:50,right:46},
      xAxis:{type:'category',data:full.pos_adaptive.dates,
        axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e',fontSize:8,interval:'auto'}},
      yAxis:{scale:true,splitLine:{lineStyle:{color:'#21262d'}},
        axisLabel:{color:'#8b949e',fontSize:8,formatter:v=>v+'%'}},
      series:[
        {name:'自适应清仓WTS',type:'line',data:full.pos_adaptive.cum_ret,smooth:true,symbol:'none',
          lineStyle:{color:'#ffa657',width:2.5},
          areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,
            colorStops:[{offset:0,color:'rgba(255,166,87,.25)'},{offset:1,color:'rgba(255,166,87,.02)'}]}}},
        {name:'纯WTS',   type:'line',data:full.pos_wts.cum_ret,smooth:true,symbol:'none',lineStyle:{color:'#8b949e',width:1.5}},
        {name:'非对称DTS',type:'line',data:full.pos_asym.cum_ret,smooth:true,symbol:'none',lineStyle:{color:'#3fb950',width:1.5}},
        {name:'BNH',     type:'line',data:full.pos_wts.bnh_ret,smooth:true,symbol:'none',
          lineStyle:{color:'#444',width:1.5,type:'dashed'}},
      ]
    },true);
  }

  // mini charts
  ['P1','P2','P3'].forEach(p=>{
    const pr=ed.periods[p]; if(!pr||!pr.pos_adaptive)return;
    const el=$(`c-mini-${p.toLowerCase()}`); if(!el)return;
    const key=`mini-${p}-${n}`;
    if(!C[key])C[key]=echarts.init(el,'dark');
    C[key].setOption({
      backgroundColor:'transparent',
      grid:{top:4,bottom:16,left:32,right:6},
      xAxis:{type:'category',data:pr.pos_adaptive.dates,axisLine:{lineStyle:{color:'#30363d'}},
        axisLabel:{color:'#8b949e',fontSize:7,interval:'auto'}},
      yAxis:{scale:true,splitLine:{lineStyle:{color:'#21262d'}},
        axisLabel:{color:'#8b949e',fontSize:7,formatter:v=>v+'%'}},
      series:[
        {type:'line',data:pr.pos_adaptive.cum_ret,smooth:true,symbol:'none',lineStyle:{color:'#ffa657',width:2}},
        {type:'line',data:pr.pos_wts.cum_ret,smooth:true,symbol:'none',lineStyle:{color:'#8b949e',width:1}},
        {type:'line',data:pr.pos_asym.cum_ret,smooth:true,symbol:'none',lineStyle:{color:'#3fb950',width:1.2}},
        {type:'line',data:pr.pos_adaptive.bnh_ret,smooth:true,symbol:'none',lineStyle:{color:'#333',width:1,type:'dashed'}},
      ]
    },true);
  });

  // alpha bar
  gc('c-alpha-bar').setOption({
    backgroundColor:'transparent',tooltip:{},
    legend:{bottom:0,textStyle:{color:'#8b949e',fontSize:8}},
    grid:{top:8,bottom:28,left:42,right:8},
    xAxis:{type:'category',data:PIDS.map(p=>PLABELS[p]),axisLabel:{color:'#8b949e',fontSize:8,interval:0}},
    yAxis:{splitLine:{lineStyle:{color:'#21262d'}},axisLabel:{color:'#8b949e',fontSize:8,formatter:v=>v+'%'}},
    series:STRATS.map(s=>({
      name:s.l,type:'bar',barMaxWidth:14,
      data:PIDS.map(p=>{const r=ed.periods[p]?.[s.k]; return r?r.metrics.alpha:null;}),
      itemStyle:{color:s.c},
    }))
  },true);

  // trades + long_pct
  gc('c-trades-bar').setOption({
    backgroundColor:'transparent',tooltip:{},
    legend:{bottom:0,textStyle:{color:'#8b949e',fontSize:8}},
    grid:{top:8,bottom:28,left:36,right:60},
    xAxis:{type:'category',data:STRATS.map(s=>s.l),axisLabel:{color:'#8b949e',fontSize:9}},
    yAxis:[
      {name:'笔数',splitLine:{lineStyle:{color:'#21262d'}},axisLabel:{color:'#8b949e',fontSize:8}},
      {name:'持多%',max:100,axisLabel:{color:'#8b949e',fontSize:8,formatter:v=>v+'%'},splitLine:{show:false}}
    ],
    series:[
      {name:'交易笔数',type:'bar',barMaxWidth:22,yAxisIndex:0,
        data:STRATS.map(s=>{const r=ed.periods['全程']?.[s.k];return r?r.metrics.n_trades:null;}),
        itemStyle:{color(p){return STRATS[p.dataIndex].c;}},
        label:{show:true,position:'top',color:'#8b949e',fontSize:9}},
      {name:'持多天%',type:'line',yAxisIndex:1,symbol:'circle',symbolSize:7,
        data:STRATS.map(s=>{const r=ed.periods['全程']?.[s.k];return r?r.metrics.long_pct:null;}),
        lineStyle:{color:'#58a6ff',width:2},itemStyle:{color:'#58a6ff'}},
    ]
  },true);

  // summary table
  let th=`<thead><tr><th class="nm">标的</th>`;
  PIDS.forEach(p=>{ th+=`<th colspan="3" style="color:${PCOLS[p]}">${p}: α</th>`; });
  th+=`</tr><tr><th class="nm">参数</th>`;
  PIDS.forEach(()=>{ th+=`<th style="color:#ffa657">自适应</th><th style="color:#8b949e">WTS</th><th style="color:#3fb950">非对称</th>`; });
  th+=`</tr></thead>`;
  let tb=`<tbody>`;
  NS.forEach(nm=>{
    const ed2=D[nm];
    tb+=`<tr><td class="nm">${nm}<br><span class="sub" style="color:var(--muted);font-size:9px">SAME=${ed2.opt.same}/REV=${ed2.opt.rev}</span></td>`;
    PIDS.forEach(p=>{
      const pr=ed2.periods[p];
      if(!pr){tb+=`<td colspan="3" class="m">N/A</td>`;return;}
      const cols=['pos_adaptive','pos_wts','pos_asym'];
      const alphas=cols.map(k=>pr[k]?pr[k].metrics.alpha:null);
      const maxA=Math.max(...alphas.filter(a=>a!==null));
      alphas.forEach((a,si)=>{
        const sc=['#ffa657','#8b949e','#3fb950'];
        const isBest=a!==null&&Math.abs(a-maxA)<0.01;
        tb+=`<td class="${a!==null?cc(a):'m'} ${isBest?'winner':''}" style="${isBest?'background:'+sc[si]+'15':''}">
          ${a!==null?p1(a):'--'}</td>`;
      });
    });
    tb+=`</tr>`;
    tb+=`<tr class="sub"><td class="nm sub">总收益</td>`;
    PIDS.forEach(p=>{
      const pr=ed2.periods[p];
      if(!pr){tb+=`<td colspan="3"></td>`;return;}
      ['pos_adaptive','pos_wts','pos_asym'].forEach(k=>{
        const r=pr[k]; tb+=`<td class="sub ${r?cc(r.metrics.total_return):'m'}">${r?p1(r.metrics.total_return):'--'}</td>`;
      });
    });
    tb+=`</tr>`;
  });
  tb+=`</tbody>`;
  $('tbl').innerHTML=th+tb;
}

function sel(n){cur=n;renderSide();renderMain(n);}
sel(cur);
window.addEventListener('resize',()=>Object.values(C).forEach(c=>c.resize()));
</script>
</body>
</html>'''.replace('__DATA__', raw)

out = OUTPUT / 'adaptive_strategy.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(HTML)
print(f"HTML生成: {out}  ({out.stat().st_size//1024} KB)")
