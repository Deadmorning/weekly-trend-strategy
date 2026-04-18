---
name: strategy-framework
description: >
  A structured framework for evaluating and developing quantitative trading strategies,
  especially trend-following and behavioral-finance-based strategies for equity markets
  (A-shares, ETFs, broad-based indices). Use this skill proactively whenever a user
  mentions building a new strategy, testing a strategy idea, asking "should I try X strategy",
  evaluating whether a signal works, or wants to understand why a strategy does or doesn't work.
  Also use when the user asks about Alpha sources, behavioral biases in markets, mechanism vs strategy
  distinction, or wants to validate a strategy hypothesis before writing code.
  Do NOT wait for the user to ask explicitly — if the conversation is about strategy development,
  invoke this skill immediately.
---

# 策略开发框架（Strategy Development Framework）

This skill guides rigorous evaluation of trading strategy ideas using a 6-layer analytical framework derived from behavioral finance + execution system (Turtle Trading integration). The goal is to answer ONE question efficiently: **Is this idea worth building?**

---

## Core Principle: Answer These Questions in Order. Stop Early if Blocked.

The framework is a sequential filter. Each layer either passes the idea forward or stops it. This saves time — don't optimize a strategy that fails the structural test in Layer 0.

---

## The Framework

### Layer 0: Beta vs Alpha — What Are We Actually Trying to Do?

Start here every time.

- **Beta return** = compensation for bearing systematic market risk (just hold the index)
- **Alpha** = excess return above what buy-and-hold delivers

> The correct benchmark for any long-only strategy is buy-and-hold, not zero.
> A strategy that returns +20% in a +30% year has negative Alpha (-10%), even though it made money.

Ask: **Is this strategy trying to generate Alpha, or is it disguised Beta?**

---

### Layer 1+2: What Generates the Mechanism? (Four Parallel Sources)

Market mechanisms that can be exploited come from four independent sources:

```
[认知限制 × 信息结构] → 行为规律 ──┐
[基本面渐进修正]       ─────────────┤
                                     ├──→ 机制 → 策略
[制度性约束]           ─────────────┤
[市场微观结构]         ─────────────┘
```

**For behavioral strategies (primary focus of this framework):**

The behavioral path: Cognitive limits × Information structure → Collective behavior patterns → Market mechanism

Key cognitive limits: loss aversion, herding, recency bias, overconfidence, confirmation bias, anchoring, disposition effect, bounded attention.

Information structure matters: dispersed (most markets) vs. concentrated (policy-driven, single decision-maker). Market maturity reduces cognitive biases but does NOT eliminate information asymmetry biases.

**Reflexivity**: Prices themselves become information, creating self-reinforcing feedback loops. This amplifies trends in the middle phase and causes overshoots at the end.

---

### Layer 3: Which Behavioral Bias Type?

| Type | Bias | Market Expression | Strategy Direction |
|------|------|-------------------|-------------------|
| **A** | Herding + panic | Trend continuation, accelerated reversal | Trend following |
| **B** | FOMO + momentum | Chasing winners, bull market acceleration | Momentum |
| **C** | Overreaction | Post-event overshoot → mean reversion | Mean reversion |
| **D** | Multi-timeframe blind spot | Short-term noise hides long-term signal | Multi-timeframe framework |

> **One strategy = one bias type.** Mixing types makes failure attribution impossible and increases overfitting risk.

> **Note**: Attention cascade (volume leads price) is a mechanism description, not an independent bias type. It lacks directionality and cannot become a standalone strategy — it must attach to a directional layer.

---

### Layer 4: Can This Mechanism Become a Strategy?

A mechanism needs ALL of the following to become deployable:

**Checklist (must pass all):**

- [ ] **Directionality** — Does the signal have a clear direction? (Pure volume signals fail this — high volume can be buying OR panic selling)
- [ ] **Observable proxy** — Can you actually measure this from available data? Is the proxy clean or noisy? (e.g., ETF volume is contaminated by creation/redemption)
- [ ] **Positive EV after costs** — Does the edge survive transaction costs and slippage?
- [ ] **Not already priced in** — Has reflexivity already absorbed this signal into prices?

**If any item fails → structural impossibility → STOP. Do not test. Do not code.**

This is the most important filter. Testing a structurally impossible idea wastes time and produces misleading results.

---

### Layer 5: Strategy Design

**Alpha type classification (determines durability):**

| Alpha Type | Source | Durability | Decay Pattern |
|-----------|--------|-----------|--------------|
| **Behavioral Alpha** | Cognitive biases (loss aversion, herding) | High | Does NOT decay with more users — cognitive limits are neurological, not learnable away |
| **Information Alpha** | Information asymmetry or faster processing | Low | Decays quickly as more people use the strategy |
| **Structural Alpha** | Market rules, institutional mechanics | Medium | Changes with regulatory/product rule changes |

**Define failure conditions BEFORE writing code:**

Three failure types with different responses:

| Failure Type | Cause | Will It Recover? | Response |
|-------------|-------|-----------------|---------|
| **Cyclical** | Wrong market phase (e.g., trend strategy in ranging market) | Yes, next phase | Pause, wait |
| **Mechanism decay** | Edge being arbitraged away, more people using similar strategies | Slow decline, no sudden recovery | Reduce size, monitor trend |
| **Structural** | Market rules changed, product structure changed | Possibly permanent | Reassess mechanism hypothesis |

> **If you cannot write specific failure conditions, you do not understand the mechanism well enough to build the strategy yet.**

**Design principles:**
- **Simplest implementation first** — from 11-strategy comparison: simpler strategies are consistently more robust. Three lines of logic beats ten parameters.
- Every additional signal layer must solve a specifically defined problem from the failure conditions above.
- Trend strategies are cycle-dependent — you are choosing which market phase to "parasitize."

**Build sequence:**
1. Write failure conditions (Step 4)
2. Minimum viable implementation
3. Walk-Forward validation (NOT optimization — you're finding "parameters that work in the future," not "parameters that worked in the past")
4. Compare against simpler strategies doing the same thing

---

### Layer 6: Execution System (from Turtle Trading)

Strategy logic without execution rules is incomplete.

**ATR-based position sizing:**
```
1 Unit = Account Size × Risk% per trade / ATR(N)
```
This ensures equal risk per trade regardless of asset volatility. High volatility → smaller position automatically.

**Pyramiding (adding to winning positions):**
- Add 1 unit per 0.5×ATR of favorable movement
- Maximum 4 units total per position

**ATR-based stop loss:**
```
Stop = Entry Price − 2×ATR (long)
```

**Position limits:**
- Single asset: max 4 units
- Correlated assets combined: max 8 units
- Same direction total: max 12 units
- Full portfolio: max 20 units

**Portfolio construction:**
Diversify across BIAS TYPES, not just assets. Two Type-A strategies are correlated by construction — they'll both fail simultaneously in non-trending markets.

**The discipline insight:** Understanding WHY a strategy works (the behavioral mechanism) is what lets you continue executing it during drawdowns. If you only know the rules (not the reason), you'll abandon the strategy exactly when you should be following it — at the cyclical low.

---

## Output Format

When evaluating a strategy idea, produce a structured verdict:

```
STRATEGY EVALUATION: [Strategy Name/Idea]
═══════════════════════════════════════

LAYER 0 - Alpha vs Beta:
[Is this Alpha? What's the benchmark?]

LAYER 1+2 - Mechanism Source:
[Which of the 4 paths: behavioral / fundamental / institutional / microstructure]

LAYER 3 - Bias Type:
[Type A/B/C/D — or mixed (flag this as a risk)]

LAYER 4 - Structural Check:
□ Directionality: [PASS / FAIL — explain]
□ Observable proxy: [PASS / FAIL — explain]
□ Positive EV after costs: [PASS / uncertain / FAIL]
□ Not already priced in: [PASS / uncertain / FAIL]

VERDICT:
  ❌ STRUCTURAL IMPOSSIBILITY — [reason] — Do not test
  ⚠️  THEORETICALLY VALID — needs empirical testing — [define failure conditions first]
  ✅  READY TO BUILD — [list: failure conditions + minimum implementation + validation plan]

FAILURE CONDITIONS (if not blocked):
  Cyclical: [specific market conditions where this stops working temporarily]
  Mechanism decay: [signs that the edge is being arbitraged away]
  Structural: [rule/structure changes that would invalidate the mechanism]

ALPHA DURABILITY:
  Type: [Behavioral / Information / Structural]
  Expected persistence: [High / Medium / Low] — [reason]
```

---

## Quick Reference: Common Structural Impossibilities

These ideas fail Layer 4 and should be stopped immediately:

| Idea | Why It Fails |
|------|-------------|
| "Buy when volume is high" | Volume is directionless — high volume can be buying or panic selling |
| "Buy when volatility spikes" | Same issue — volatility spikes occur in both directions |
| "Follow analyst upgrades" | Priced in by the time the upgrade is published (unless you have pre-release access) |
| "Buy on high social media sentiment" | Sentiment often lags price; and what is the direction definition? |

---

## When the Framework Gives "Theoretically Valid" — Next Steps

1. Write the failure conditions in a document before opening a code editor
2. Code the minimum implementation (fewest parameters)
3. Run Walk-Forward validation (not in-sample optimization)
4. Compare against the simplest possible alternative doing the same thing
5. If it beats the simpler alternative: ship with execution rules
6. If it doesn't: either the mechanism is real but the implementation is wrong, or the mechanism itself is weaker than expected — go back to Layer 3

---

*Framework derived from: weekly-trend-strategy project, integrating behavioral finance theory + Turtle Trading execution system*
