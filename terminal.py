"""
app.py — ProTrader Terminal v3
Professional Trading Terminal: Equity · Options · Futures · Auto Trading
All data persists across sessions via local JSON storage.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import time
import math

import storage as db
import engine as eng
from ui import (
    TERMINAL_CSS, sig_badge, strength_bar, pnl_fmt,
    ticker_item, metric_card, level_box, profit_book_row, greek_box
)

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ProTrader Terminal v3",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(TERMINAL_CSS, unsafe_allow_html=True)

# ─── Persistent State Bootstrap ───────────────────────────────────────────────
def load_persistent():
    """Load all persistent data into session_state on first load."""
    if "loaded" not in st.session_state:
        for key, default in [
            ("eq_portfolio",  []),
            ("eq_history",    []),
            ("opt_portfolio", []),
            ("opt_history",   []),
            ("fut_portfolio", []),
            ("fut_history",   []),
            ("journal",       []),
            ("kelly_wr",      0.55),
            ("scan_eq",       []),
            ("scan_opt",      []),
            ("scan_fut",      []),
            ("auto_eq",       False),
            ("auto_opt",      False),
            ("auto_fut",      False),
            ("auto_eq_end",   None),
            ("auto_opt_end",  None),
            ("auto_fut_end",  None),
        ]:
            st.session_state[key] = db.load(key, default)
        st.session_state["loaded"] = True

load_persistent()

def save_all():
    for key in ["eq_portfolio","eq_history","opt_portfolio","opt_history",
                "fut_portfolio","fut_history","journal","kelly_wr"]:
        db.save(key, st.session_state[key])

# ─── Live Index Data ──────────────────────────────────────────────────────────
@st.cache_data(ttl=20)
def get_indices():
    import yfinance as yf
    syms = {"BN":"^NSEBANK","NF":"^NSEI","VIX":"^INDIAVIX","SX":"^BSESN","IT":"^CNXIT","MID":"^NSMIDCP"}
    out  = {}
    for k,sym in syms.items():
        try:
            t  = yf.Ticker(sym)
            df = t.history(period="2d",interval="1d")
            lp = t.fast_info.last_price or (float(df["Close"].iloc[-1]) if not df.empty else 0)
            pr = float(df["Close"].iloc[-2]) if len(df)>=2 else float(lp)
            ch = float(lp)-pr; pct = ch/pr*100 if pr else 0
            out[k] = {"p":float(lp),"c":ch,"pct":pct,
                      "h":float(df["High"].iloc[-1]) if not df.empty else float(lp),
                      "l":float(df["Low"].iloc[-1])  if not df.empty else float(lp)}
        except:
            out[k] = {"p":0,"c":0,"pct":0,"h":0,"l":0}
    return out

@st.cache_data(ttl=3600)
def get_expiries(n=5):
    dates = []
    d = datetime.now().date()
    for _ in range(n*3):
        d += timedelta(days=1)
        if d.weekday()==3: dates.append(d)
        if len(dates)==n: break
    return dates

def update_kelly():
    j = st.session_state.journal
    if j:
        wins = sum(1 for x in j if x.get("win",False))
        st.session_state.kelly_wr = wins/len(j)
        db.save("kelly_wr", st.session_state.kelly_wr)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""<div style="font-family:Orbitron;font-size:0.9rem;color:var(--accent);
    letter-spacing:3px;padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:12px;">
    ⚙ SETTINGS</div>""", unsafe_allow_html=True)

    capital = st.number_input("Total Capital (₹)", 50000, 10000000, 500000, 50000)
    trade_cap = st.number_input("Capital/Trade (₹)", 2000, 500000, 15000, 1000)
    use_kelly  = st.checkbox("Kelly Criterion Sizing", value=True)
    use_trail  = st.checkbox("Trailing Stop Loss", value=True)
    use_time_x = st.checkbox("Time-Based Exit", value=True)
    use_mktf   = st.checkbox("Market Mood Filter", value=True)
    use_fundm  = st.checkbox("Fundamental Filter", value=False)
    min_str    = st.slider("Min Signal Strength", 45, 90, 58, 2)
    n_strikes  = st.slider("Option Chain Strikes (each side ATM)", 5, 15, 10, 1)

    st.markdown("---")
    st.markdown("""<div style="font-family:Orbitron;font-size:0.75rem;color:var(--accent);letter-spacing:2px;">📅 EXPIRY</div>""", unsafe_allow_html=True)
    expiries    = get_expiries(5)
    exp_labels  = [e.strftime("%d %b %Y") for e in expiries]
    exp_bn_lbl  = st.selectbox("BankNifty Expiry", exp_labels)
    exp_nf_lbl  = st.selectbox("Nifty50 Expiry",   exp_labels)
    exp_bn = expiries[exp_labels.index(exp_bn_lbl)]
    exp_nf = expiries[exp_labels.index(exp_nf_lbl)]

    st.markdown("---")
    st.markdown("""<div style="font-family:Orbitron;font-size:0.75rem;color:var(--accent);letter-spacing:2px;">📊 SESSION P&L</div>""", unsafe_allow_html=True)
    ep = sum(x.get("pnl",0) for x in st.session_state.eq_portfolio)
    op = sum(x.get("pnl",0) for x in st.session_state.opt_portfolio)
    fp = sum(x.get("pnl",0) for x in st.session_state.fut_portfolio)
    eh = sum(x.get("pnl",0) for x in st.session_state.eq_history)
    oh = sum(x.get("pnl",0) for x in st.session_state.opt_history)
    fh = sum(x.get("pnl",0) for x in st.session_state.fut_history)
    total = ep+op+fp+eh+oh+fh
    pnl_color = "var(--green)" if total>=0 else "var(--red)"
    st.markdown(f"""
    <div style="font-family:'JetBrains Mono';font-size:0.72rem;color:var(--text2);">
        Equity Open: <span style="color:{'var(--green)' if ep>=0 else 'var(--red)'}">₹{ep:+,.0f}</span><br>
        Options Open: <span style="color:{'var(--green)' if op>=0 else 'var(--red)'}">₹{op:+,.0f}</span><br>
        Futures Open: <span style="color:{'var(--green)' if fp>=0 else 'var(--red)'}">₹{fp:+,.0f}</span><br>
        Realized: <span style="color:{'var(--green)' if (eh+oh+fh)>=0 else 'var(--red)'}">₹{eh+oh+fh:+,.0f}</span><br>
        <span style="font-size:1rem;color:{pnl_color};font-weight:700;">TOTAL: ₹{total:+,.0f}</span>
    </div>""", unsafe_allow_html=True)

    st.markdown("---")
    kelly_wr = st.session_state.kelly_wr
    st.markdown(f"""<div class="info-b" style="font-size:0.72rem;">
    🧮 Kelly WR: <b>{kelly_wr*100:.1f}%</b><br>
    Trades: {len(st.session_state.journal)}</div>""", unsafe_allow_html=True)

    if st.button("🗑️ Clear ALL Data", use_container_width=True):
        for key in ["eq_portfolio","eq_history","opt_portfolio","opt_history",
                    "fut_portfolio","fut_history","journal"]:
            st.session_state[key] = []
            db.delete(key)
        st.success("All data cleared.")
        st.rerun()

# ─── Header ───────────────────────────────────────────────────────────────────
idx = get_indices()
bn  = idx.get("BN",{})
nf  = idx.get("NF",{})
vx  = idx.get("VIX",{})
sx  = idx.get("SX",{})
it  = idx.get("IT",{})
mid = idx.get("MID",{})
vix_val = vx.get("p", 15.0)

st.markdown(f"""
<div class="terminal-header">
    <div class="terminal-title">📡 PROTRADER TERMINAL v3</div>
    <div class="terminal-sub">NSE · BSE · Options · Futures · Auto AI Trading · {datetime.now().strftime('%d %b %Y %H:%M')}</div>
</div>""", unsafe_allow_html=True)

# Ticker tape
items  = [
    ticker_item("BANKNIFTY", bn.get("p",0), bn.get("pct",0)),
    ticker_item("NIFTY50",   nf.get("p",0), nf.get("pct",0)),
    ticker_item("SENSEX",    sx.get("p",0), sx.get("pct",0)),
    ticker_item("VIX",       vx.get("p",0), vx.get("pct",0)),
    ticker_item("NIFTYIT",   it.get("p",0), it.get("pct",0)),
    ticker_item("NIFTYMID",  mid.get("p",0),mid.get("pct",0)),
]
tape = " ◆ ".join(items)
st.markdown(f'<div class="ticker-outer"><div class="ticker-inner">{tape+" ◆ "+tape}</div></div>', unsafe_allow_html=True)

# Index cards
ic = st.columns(6)
def icard(col, label, d, css):
    c = "up" if d.get("pct",0)>=0 else "dn"
    a = "▲" if d.get("pct",0)>=0 else "▼"
    col.markdown(f"""<div class="idx-card {css}">
        <div class="idx-label">{label}</div>
        <div class="idx-price {c}">{d.get('p',0):,.2f}</div>
        <div class="idx-chg {c}">{a} {d.get('c',0):+,.2f} ({d.get('pct',0):+.2f}%)</div>
    </div>""", unsafe_allow_html=True)

icard(ic[0],"BANKNIFTY",bn,"bn")
icard(ic[1],"NIFTY 50", nf,"nf")
icard(ic[2],"SENSEX",   sx,"sx")
icard(ic[3],"VIX",      vx,"vx")
icard(ic[4],"NIFTY IT", it,"it")
icard(ic[5],"NIFTY MID",mid,"nf")

# VIX Alerts
if vix_val > 22:
    st.markdown(f'<div class="warn-b">⚠️ HIGH VIX {vix_val:.1f} — Options expensive. Prefer spreads. Widen stops. Avoid aggressive auto-trading.</div>', unsafe_allow_html=True)
elif vix_val < 13:
    st.markdown(f'<div class="info-b">🟢 LOW VIX {vix_val:.1f} — Options cheap. Good time to buy directional CE/PE on breakouts.</div>', unsafe_allow_html=True)

# Market mood
@st.cache_data(ttl=300)
def market_mood_data():
    try:
        import yfinance as yf
        df = yf.Ticker("^NSEI").history(period="5d", interval="1d")
        if df.empty or len(df)<2: return "NEUTRAL"
        c    = df["Close"].astype(float)
        e5   = c.ewm(span=5).mean()
        chg  = float((c.iloc[-1]-c.iloc[-2])/c.iloc[-2]*100)
        if c.iloc[-1]>e5.iloc[-1] and chg>0.3: return "BULLISH"
        elif c.iloc[-1]<e5.iloc[-1] and chg<-0.3: return "BEARISH"
        return "NEUTRAL"
    except: return "NEUTRAL"

mood = market_mood_data() if use_mktf else "NEUTRAL"
mood_filter = mood if use_mktf else "NEUTRAL"

st.markdown("<br>", unsafe_allow_html=True)

# ─── MAIN TABS ────────────────────────────────────────────────────────────────
page_tabs = st.tabs([
    "📈 EQUITY", "⚡ OPTIONS", "🔮 FUTURES",
    "💼 PORTFOLIO", "📜 HISTORY", "📓 JOURNAL", "📊 ANALYTICS"
])

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — EQUITY (Intraday + Delivery)
# ══════════════════════════════════════════════════════════════════════════════
with page_tabs[0]:
    st.markdown('<div class="sec-ttl">📈 EQUITY TRADING — NSE + BSE FULL UNIVERSE</div>', unsafe_allow_html=True)

    eq_tabs = st.tabs(["🔍 Scanner", "⚡ Auto Trading", "💼 Open Positions", "📜 Trade History"])

    # ── EQ Scanner ────────────────────────────────────────────────────────────
    with eq_tabs[0]:
        c1, c2, c3, c4 = st.columns([1,1,1,1])
        with c1:
            eq_mode = st.radio("Mode", ["INTRADAY","DELIVERY"], horizontal=True)
        with c2:
            eq_exch = st.multiselect("Exchange", ["NSE","BSE"], default=["NSE"])
        with c3:
            eq_filter = st.selectbox("Show", ["All Signals","BUY Only","SELL Only","STRONG Only"])
        with c4:
            eq_max_scan = st.number_input("Max stocks to scan", 50, len(eng.NSE_SYMBOLS)+len(eng.BSE_SYMBOLS), 200, 50)

        scan_universe = []
        if "NSE" in eq_exch: scan_universe += eng.NSE_SYMBOLS
        if "BSE" in eq_exch: scan_universe += eng.BSE_SYMBOLS
        scan_universe = scan_universe[:int(eq_max_scan)]

        col_btn, col_sym = st.columns([1,3])
        with col_btn:
            do_scan = st.button("🔭 SCAN ALL STOCKS", use_container_width=True)
        with col_sym:
            quick_sym = st.selectbox("Quick Analyse", [""]+eng.NSE_SYMBOLS[:100])

        if do_scan or (quick_sym and quick_sym!=""):
            syms = [quick_sym] if quick_sym else scan_universe
            prog = st.progress(0)
            with st.spinner(f"Scanning {len(syms)} stocks…"):
                results = eng.scan_parallel(syms, mode=eq_mode,
                    market_mood=mood_filter, vix=vix_val,
                    max_workers=40, min_strength=min_str)
            prog.progress(1.0)
            prog.empty()
            st.session_state["scan_eq"] = results

        results = st.session_state.get("scan_eq", [])
        if eq_filter == "BUY Only":    results = [r for r in results if "BUY" in r["rec"]]
        elif eq_filter == "SELL Only": results = [r for r in results if "SELL" in r["rec"]]
        elif eq_filter == "STRONG Only": results = [r for r in results if "STRONG" in r["rec"]]

        if results:
            buys  = [r for r in results if "BUY" in r["rec"]]
            sells = [r for r in results if "SELL" in r["rec"]]
            mc = st.columns(5)
            mc[0].markdown(metric_card(len(results), "Total Signals", "var(--accent)"), unsafe_allow_html=True)
            mc[1].markdown(metric_card(len(buys),  "BUY Signals",  "var(--green)"),  unsafe_allow_html=True)
            mc[2].markdown(metric_card(len(sells), "SELL Signals", "var(--red)"),    unsafe_allow_html=True)
            avg_s = int(np.mean([r["strength"] for r in results])) if results else 0
            mc[3].markdown(metric_card(f"{avg_s}%", "Avg Strength", "var(--gold)"),  unsafe_allow_html=True)
            sq_ct = len([r for r in results if "STRONG" in r["rec"]])
            mc[4].markdown(metric_card(sq_ct, "Strong Signals", "var(--teal)"),       unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            # Table view
            tbl = []
            for r in results:
                pats = ", ".join([p[0] for p in r.get("patterns",[])]) or "—"
                div  = "✓ " + r["divergence"][0] if r.get("divergence") else "—"
                tbl.append({
                    "Symbol": r["symbol"].replace(".NS","").replace(".BO",""),
                    "CMP(₹)": f"₹{r['price']:,.2f}",
                    "Signal": r["rec"],
                    "Strength": r["strength"],
                    "Target": f"₹{r['target']:,.2f}",
                    "SL": f"₹{r['sl']:,.2f}",
                    "R/R": f"{r['rr']:.2f}",
                    "Day%": f"{r.get('day_chg',0):+.2f}%",
                    "5D%": f"{r.get('m5',0):+.1f}%",
                    "RSI": f"{r.get('rsi',0):.0f}",
                    "ADX": f"{r.get('adx',0):.0f}",
                    "Vol Ratio": f"{r.get('vr',1):.1f}x",
                    "Pattern": pats,
                    "Divergence": div,
                })
            st.dataframe(pd.DataFrame(tbl), use_container_width=True, hide_index=True)
            st.markdown("<br>", unsafe_allow_html=True)

            st.markdown("#### 🔎 Detailed Cards")
            for r in results[:40]:
                icon = "🟢" if "BUY" in r["rec"] else ("🔴" if "SELL" in r["rec"] else "🟡")
                with st.expander(
                    f"{icon} {r['symbol'].replace('.NS','').replace('.BO','')} | "
                    f"₹{r['price']:,.2f} | {r['rec']} | Str:{r['strength']}% | "
                    f"ADX:{r.get('adx',0):.0f} | RSI:{r.get('rsi',0):.0f}"
                ):
                    d1,d2,d3,d4,d5,d6 = st.columns(6)
                    d1.metric("CMP",    f"₹{r['price']:,.2f}")
                    d2.metric("Target", f"₹{r['target']:,.2f}")
                    d3.metric("SL",     f"₹{r['sl']:,.2f}")
                    d4.metric("R/R",    f"{r['rr']:.2f}")
                    d5.metric("5D Mov", f"{r.get('m5',0):+.1f}%")
                    d6.metric("Vol Ratio", f"{r.get('vr',1):.1f}x")

                    ind = r.get("indicators",{})
                    if ind:
                        st.markdown("**Indicators**")
                        i1,i2,i3,i4,i5,i6,i7 = st.columns(7)
                        i1.metric("RSI",   f"{ind.get('rsi',0):.1f}")
                        i2.metric("MACD",  f"{ind.get('macd',0):.3f}")
                        i3.metric("ADX",   f"{ind.get('adx',0):.0f}")
                        i4.metric("BB%",   f"{ind.get('bb_pct',0):.2f}")
                        i5.metric("Stoch", f"{ind.get('sk',0):.0f}")
                        i6.metric("CCI",   f"{ind.get('cci',0):.0f}")
                        i7.metric("WR%",   f"{ind.get('wr',0):.0f}")

                    # S/R Levels
                    if ind.get("s1") and ind.get("r1"):
                        st.markdown("**Support & Resistance**")
                        sr1,sr2,sr3,sr4 = st.columns(4)
                        sr1.markdown(level_box("S2",ind.get("s2",0),"lvl-s"), unsafe_allow_html=True)
                        sr2.markdown(level_box("S1",ind.get("s1",0),"lvl-s"), unsafe_allow_html=True)
                        sr3.markdown(level_box("R1",ind.get("r1",0),"lvl-r"), unsafe_allow_html=True)
                        sr4.markdown(level_box("R2",ind.get("r2",0),"lvl-r"), unsafe_allow_html=True)

                    # Patterns
                    if r.get("patterns"):
                        phtml = " ".join([f'<span style="background:rgba(245,166,35,0.12);border:1px solid rgba(245,166,35,0.4);color:var(--gold);border-radius:4px;padding:2px 8px;font-size:0.72rem;font-family:JetBrains Mono;">{p[0]}</span>' for p in r["patterns"]])
                        st.markdown(f"**Candlestick:** {phtml}", unsafe_allow_html=True)

                    if r.get("divergence"):
                        st.markdown(f'<div class="success-b">📐 {r["divergence"][2]}</div>', unsafe_allow_html=True)

                    if ind.get("squeeze"):
                        st.markdown('<div class="warn-b">⚡ TTM SQUEEZE FIRING — Big move imminent!</div>', unsafe_allow_html=True)

                    st.markdown("**Signal Reasoning**")
                    for rn in r["reasons"][:8]:
                        st.markdown(f"<div style='font-size:0.78rem;color:var(--text2);padding:1px 0;'>• {rn}</div>", unsafe_allow_html=True)

                    # Strength bar
                    bar_c = "#00e676" if "BUY" in r["rec"] else "#ff1744"
                    st.markdown(strength_bar(r["strength"], bar_c), unsafe_allow_html=True)

                    # Kelly sizing
                    kc = eng.kelly_size(float(trade_cap), st.session_state.kelly_wr, r["rr"], r["strength"]) if use_kelly else float(trade_cap)
                    qty = max(1, int(kc / r["price"])) if r["price"]>0 else 1
                    cost = eng.equity_cost(r["price"], qty, "BUY", eq_mode=="DELIVERY")
                    st.markdown(f'<div class="info-b">🧮 Kelly Allocation: ₹{kc:,.0f} | Qty: {qty} shares | Est. Charges: ₹{cost:.2f}</div>', unsafe_allow_html=True)

                    # Trade button
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        if r["rec"] not in ("NEUTRAL",) and st.button(f"🚀 EXECUTE {r['rec']}", key=f"eq_exec_{r['symbol']}"):
                            qty2 = max(1, int(kc/r["price"])) if r["price"]>0 else 1
                            trade = {
                                "id": f"{r['symbol']}_{int(time.time()*1000)}",
                                "symbol": r["symbol"],
                                "type": "BUY" if "BUY" in r["rec"] else "SELL",
                                "mode": eq_mode,
                                "entry": r["price"], "cmp": r["price"],
                                "qty": qty2, "invested": round(r["price"]*qty2,2),
                                "brokerage": eng.equity_cost(r["price"],qty2,"BUY",eq_mode=="DELIVERY"),
                                "target": r["target"], "sl": r["sl"],
                                "trailing_sl": None, "pnl": 0.0,
                                "rec": r["rec"], "strength": r["strength"],
                                "rr": r["rr"], "reasons": r["reasons"][:5],
                                "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "entry_dt": datetime.now().isoformat(),
                                "patterns": [p[0] for p in r.get("patterns",[])],
                            }
                            st.session_state.eq_portfolio.append(trade)
                            db.save("eq_portfolio", st.session_state.eq_portfolio)
                            st.success(f"✅ {r['rec']} executed: {r['symbol']} @ ₹{r['price']:.2f}")

    # ── EQ Auto Trading ───────────────────────────────────────────────────────
    with eq_tabs[1]:
        st.markdown('<div class="sec-ttl">⚡ EQUITY AUTO TRADING ENGINE</div>', unsafe_allow_html=True)

        if not st.session_state.auto_eq:
            st.markdown(f"""<div style="background:var(--surface);border:1px solid var(--accent);border-radius:10px;padding:20px;text-align:center;margin-bottom:16px;">
            <div style="font-family:Orbitron;font-size:1.4rem;color:var(--accent);letter-spacing:3px;">AI EQUITY AUTO TRADER</div>
            <div style="color:var(--text2);font-size:0.82rem;margin-top:8px;">
                Scans ALL NSE+BSE stocks · Momentum + Technical + Pattern · Kelly Sizing · Auto SL · Trailing Stops
            </div></div>""", unsafe_allow_html=True)

            _, ac2, _ = st.columns([1,2,1])
            with ac2:
                a_dur  = st.number_input("Duration (minutes)", 1, 390, 30, 5, key="eq_dur")
                a_mode = st.radio("Trading Mode", ["INTRADAY","DELIVERY"], horizontal=True, key="eq_at_mode")
                a_max  = st.number_input("Max simultaneous positions", 1, 20, 5, 1, key="eq_max")
                a_scan = st.number_input("Stocks to scan per cycle", 50, len(eng.NSE_SYMBOLS), 200, 50, key="eq_scan_n")
                st.markdown(f'<div class="info-b">Market: <b>{mood}</b> | VIX: {vix_val:.1f} | Kelly WR: {st.session_state.kelly_wr*100:.1f}%</div>', unsafe_allow_html=True)
                if st.button("🚀 START EQUITY AUTO TRADING", use_container_width=True, key="eq_auto_start"):
                    st.session_state.auto_eq     = True
                    st.session_state.auto_eq_end = (datetime.now()+timedelta(minutes=int(a_dur))).isoformat()
                    st.session_state["eq_at_mode2"] = a_mode
                    st.session_state["eq_at_max"]   = int(a_max)
                    st.session_state["eq_at_scan"]  = int(a_scan)
                    db.save("auto_eq", True)
                    db.save("auto_eq_end", st.session_state.auto_eq_end)
                    st.rerun()
        else:
            end_dt   = datetime.fromisoformat(st.session_state.auto_eq_end)
            rem      = max(0.0,(end_dt-datetime.now()).total_seconds())
            tot_s    = (end_dt-datetime.now()+timedelta(seconds=rem)).total_seconds() if rem>0 else 1
            prog_pct = 1.0 - rem/max(tot_s,1)

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Time Left", f"{int(rem//60)}m {int(rem%60)}s")
            c2.metric("Open Pos",  len(st.session_state.eq_portfolio))
            opnl = sum(p.get("pnl",0) for p in st.session_state.eq_portfolio)
            c3.metric("Live P&L",  f"₹{opnl:+,.0f}")
            c4.metric("Realized",  f"₹{sum(p.get('pnl',0) for p in st.session_state.eq_history):+,.0f}")
            st.progress(min(prog_pct,1.0))

            if rem <= 0:
                st.warning("⏰ Session ended — squaring off all equity positions!")
                for pos in st.session_state.eq_portfolio:
                    ep = pos["entry"]; cmp = pos.get("cmp",ep); qty = pos["qty"]
                    gross = (cmp-ep)*qty if pos["type"]=="BUY" else (ep-cmp)*qty
                    net   = gross - pos.get("brokerage",0)
                    closed = {**pos,"exit":cmp,"exit_time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"pnl":round(net,2),"status":"CLOSED"}
                    st.session_state.eq_history.append(closed)
                    st.session_state.journal.append({"cat":"EQUITY","symbol":pos["symbol"],"pnl":round(net,2),"win":net>=0,"strength":pos.get("strength",0),"date":datetime.now().strftime("%Y-%m-%d"),"rec":pos.get("rec","")})
                st.session_state.eq_portfolio = []
                st.session_state.auto_eq = False
                db.save("auto_eq", False); db.save("eq_portfolio",[])
                db.save("eq_history",st.session_state.eq_history)
                db.save("journal", st.session_state.journal)
                update_kelly()
                st.rerun()
            else:
                _max  = st.session_state.get("eq_at_max",5)
                _mode = st.session_state.get("eq_at_mode2","INTRADAY")
                _sc   = st.session_state.get("eq_at_scan",200)

                if len(st.session_state.eq_portfolio) < _max:
                    with st.spinner("Scanning for signals…"):
                        scan_syms = eng.NSE_SYMBOLS[:_sc]
                        new_sigs  = eng.scan_parallel(scan_syms, _mode, mood_filter, vix_val, 40, min_str)
                    existing = {p["symbol"]+p["type"] for p in st.session_state.eq_portfolio}
                    for sig in new_sigs:
                        if len(st.session_state.eq_portfolio) >= _max: break
                        if sig["rec"]=="NEUTRAL": continue
                        k = sig["symbol"]+("BUY" if "BUY" in sig["rec"] else "SELL")
                        if k in existing: continue
                        if mood_filter=="BEARISH" and "BUY" in sig["rec"]: continue
                        if mood_filter=="BULLISH" and "SELL" in sig["rec"]: continue
                        p = sig["price"]
                        if p<=0: continue
                        kc   = eng.kelly_size(float(trade_cap), st.session_state.kelly_wr, sig["rr"], sig["strength"]) if use_kelly else float(trade_cap)
                        qty  = max(1, int(kc/p))
                        cost = eng.equity_cost(p, qty, "BUY", _mode=="DELIVERY")
                        trade = {
                            "id": f"{sig['symbol']}_{int(time.time()*1000)}",
                            "symbol": sig["symbol"], "type": "BUY" if "BUY" in sig["rec"] else "SELL",
                            "mode": _mode, "entry": p, "cmp": p,
                            "qty": qty, "invested": round(p*qty,2), "brokerage": cost,
                            "target": sig["target"], "sl": sig["sl"],
                            "trailing_sl": None, "pnl": 0.0,
                            "rec": sig["rec"], "strength": sig["strength"], "rr": sig["rr"],
                            "reasons": sig["reasons"][:5],
                            "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "entry_dt": datetime.now().isoformat(),
                            "patterns": [p2[0] for p2 in sig.get("patterns",[])],
                        }
                        st.session_state.eq_portfolio.append(trade)
                        existing.add(k)

                # Update P&L + check exits
                still = []
                for pos in st.session_state.eq_portfolio:
                    lp = eng.get_live_price(pos["symbol"]) or pos["entry"]
                    pos["cmp"] = lp
                    ep = pos["entry"]; qty = pos["qty"]; cost = pos.get("brokerage",0)
                    gross = (lp-ep)*qty if pos["type"]=="BUY" else (ep-lp)*qty
                    pos["pnl"] = round(gross-cost,2)
                    # Trailing SL
                    if use_trail:
                        pnl_pct = (lp-ep)/ep*100 if ep>0 else 0
                        if pnl_pct >= 1.5:
                            if pos.get("trailing_sl") is None: pos["trailing_sl"] = ep
                            else:
                                atr = pos.get("atr", ep*0.02)
                                new_t = lp-1.5*atr if pos["type"]=="BUY" else lp+1.5*atr
                                if pos["type"]=="BUY" and new_t>pos["trailing_sl"]: pos["trailing_sl"]=round(new_t,2)
                                elif pos["type"]=="SELL" and new_t<pos["trailing_sl"]: pos["trailing_sl"]=round(new_t,2)
                    eff_sl = pos.get("trailing_sl") or pos.get("sl",0)
                    hit = ((pos["type"]=="BUY" and (lp>=pos.get("target",lp+1) or lp<=eff_sl)) or
                           (pos["type"]=="SELL" and (lp<=pos.get("target",0) or lp>=eff_sl)))
                    # Time exit
                    if use_time_x:
                        try:
                            ed = datetime.fromisoformat(pos.get("entry_dt",datetime.now().isoformat()))
                            if (datetime.now()-ed).total_seconds()>1800 and abs(lp-ep)/ep<0.005: hit=True
                        except: pass
                    if hit:
                        cost2 = eng.equity_cost(lp, qty, pos["type"], _mode=="DELIVERY")
                        gross2 = (lp-ep)*qty if pos["type"]=="BUY" else (ep-lp)*qty
                        net = gross2-cost-cost2
                        closed = {**pos,"exit":lp,"exit_time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"pnl":round(net,2),"status":"CLOSED"}
                        st.session_state.eq_history.append(closed)
                        st.session_state.journal.append({"cat":"EQUITY","symbol":pos["symbol"],"pnl":round(net,2),"win":net>=0,"strength":pos.get("strength",0),"date":datetime.now().strftime("%Y-%m-%d"),"rec":pos.get("rec","")})
                    else:
                        still.append(pos)
                st.session_state.eq_portfolio = still
                db.save("eq_portfolio", still)
                db.save("eq_history", st.session_state.eq_history)
                db.save("journal", st.session_state.journal)
                update_kelly()

                # Display
                st.markdown("### Live Equity Positions")
                if st.session_state.eq_portfolio:
                    for pos in st.session_state.eq_portfolio:
                        pnl = pos.get("pnl",0)
                        trail = f" | Trail SL: ₹{pos['trailing_sl']:,.2f}" if pos.get("trailing_sl") else ""
                        cls = "win" if pnl>=0 else "loss"
                        st.markdown(f"""<div class="tc {cls}">
                            <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;">
                                <div><span class="tc-head">{pos['type']} {pos['symbol'].replace('.NS','')}</span>
                                <span class="tc-meta"> | Entry ₹{pos['entry']:.2f} | CMP ₹{pos.get('cmp',pos['entry']):.2f} | Qty {pos['qty']}{trail}</span></div>
                                <div>{pnl_fmt(pnl)}</div>
                            </div>
                        </div>""", unsafe_allow_html=True)

                stp, _ = st.columns([1,3])
                with stp:
                    if st.button("🛑 STOP & SQUARE OFF", key="eq_stop", use_container_width=True):
                        for pos in st.session_state.eq_portfolio:
                            lp = eng.get_live_price(pos["symbol"]) or pos["entry"]
                            ep=pos["entry"]; qty=pos["qty"]; cost=pos.get("brokerage",0)
                            gross=(lp-ep)*qty if pos["type"]=="BUY" else (ep-lp)*qty
                            cost2=eng.equity_cost(lp,qty,pos["type"],False)
                            net=gross-cost-cost2
                            st.session_state.eq_history.append({**pos,"exit":lp,"pnl":round(net,2),"status":"CLOSED","exit_time":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                            st.session_state.journal.append({"cat":"EQUITY","symbol":pos["symbol"],"pnl":round(net,2),"win":net>=0,"strength":pos.get("strength",0),"date":datetime.now().strftime("%Y-%m-%d"),"rec":pos.get("rec","")})
                        st.session_state.eq_portfolio=[]
                        st.session_state.auto_eq=False
                        db.save("auto_eq",False); db.save("eq_portfolio",[])
                        db.save("eq_history",st.session_state.eq_history)
                        db.save("journal",st.session_state.journal)
                        update_kelly(); st.rerun()

                time.sleep(12)
                st.rerun()

    # ── EQ Open Positions ─────────────────────────────────────────────────────
    with eq_tabs[2]:
        st.markdown('<div class="sec-ttl">💼 EQUITY OPEN POSITIONS</div>', unsafe_allow_html=True)
        if not st.session_state.eq_portfolio:
            st.info("No open equity positions.")
        else:
            tot_inv = sum(p.get("invested",0) for p in st.session_state.eq_portfolio)
            tot_pnl = sum(p.get("pnl",0) for p in st.session_state.eq_portfolio)
            tot_brk = sum(p.get("brokerage",0) for p in st.session_state.eq_portfolio)
            pc = st.columns(4)
            pc[0].markdown(metric_card(f"₹{tot_inv:,.0f}", "Invested", "var(--accent)"), unsafe_allow_html=True)
            pc[1].markdown(metric_card(f"₹{tot_pnl:+,.0f}", "Unrealised P&L", "var(--green)" if tot_pnl>=0 else "var(--red)"), unsafe_allow_html=True)
            pc[2].markdown(metric_card(f"{tot_pnl/tot_inv*100:+.1f}%" if tot_inv>0 else "0%", "Return %", "var(--teal)"), unsafe_allow_html=True)
            pc[3].markdown(metric_card(f"₹{tot_brk:,.0f}", "Charges", "var(--gold)"), unsafe_allow_html=True)
            st.markdown("<br>",unsafe_allow_html=True)

            for pos in st.session_state.eq_portfolio:
                lp = eng.get_live_price(pos["symbol"]) or pos["entry"]
                pos["cmp"]=lp
                ep=pos["entry"]; qty=pos["qty"]; cost=pos.get("brokerage",0)
                gross=(lp-ep)*qty if pos["type"]=="BUY" else (ep-lp)*qty
                pos["pnl"]=round(gross-cost,2)
                pnl=pos["pnl"]
                trail = f" | Trail: ₹{pos['trailing_sl']:.2f}" if pos.get("trailing_sl") else ""
                with st.expander(f"{'🟢' if pos['type']=='BUY' else '🔴'} {pos['symbol'].replace('.NS','')} | Entry ₹{ep:.2f} | CMP ₹{lp:.2f} | {pnl_fmt(pnl)}{trail}"):
                    d1,d2,d3,d4,d5 = st.columns(5)
                    d1.metric("Entry",  f"₹{ep:.2f}")
                    d2.metric("CMP",    f"₹{lp:.2f}")
                    d3.metric("Target", f"₹{pos.get('target',0):.2f}")
                    d4.metric("SL",     f"₹{pos.get('sl',0):.2f}")
                    d5.metric("Net P&L",f"₹{pnl:+,.2f}")

                    if pos.get("patterns"):
                        st.markdown(" ".join([f'<span style="background:rgba(245,166,35,0.12);border:1px solid rgba(245,166,35,0.3);color:var(--gold);border-radius:3px;padding:1px 6px;font-size:0.7rem;">{p}</span>' for p in pos["patterns"]]), unsafe_allow_html=True)

                    if st.button("✅ Square Off", key=f"eq_sq_{pos['id']}"):
                        cost2=eng.equity_cost(lp,qty,pos["type"],pos.get("mode","INTRADAY")=="DELIVERY")
                        net=gross-cost-cost2
                        st.session_state.eq_history.append({**pos,"exit":lp,"pnl":round(net,2),"status":"CLOSED","exit_time":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                        st.session_state.journal.append({"cat":"EQUITY","symbol":pos["symbol"],"pnl":round(net,2),"win":net>=0,"strength":pos.get("strength",0),"date":datetime.now().strftime("%Y-%m-%d"),"rec":pos.get("rec","")})
                        st.session_state.eq_portfolio=[p2 for p2 in st.session_state.eq_portfolio if p2["id"]!=pos["id"]]
                        db.save("eq_portfolio",st.session_state.eq_portfolio)
                        db.save("eq_history",st.session_state.eq_history)
                        db.save("journal",st.session_state.journal)
                        update_kelly()
                        st.success(f"Squared off ₹{net:+,.2f}"); st.rerun()
            db.save("eq_portfolio",st.session_state.eq_portfolio)

    # ── EQ History ────────────────────────────────────────────────────────────
    with eq_tabs[3]:
        st.markdown('<div class="sec-ttl">📜 EQUITY TRADE HISTORY</div>', unsafe_allow_html=True)
        h = st.session_state.eq_history
        if not h:
            st.info("No closed equity trades yet.")
        else:
            wins=len([x for x in h if x.get("pnl",0)>=0])
            net=sum(x.get("pnl",0) for x in h)
            wr=wins/len(h)*100 if h else 0
            hc=st.columns(5)
            hc[0].metric("Total",len(h)); hc[1].metric("Wins",wins); hc[2].metric("Losses",len(h)-wins)
            hc[3].metric("Win Rate",f"{wr:.1f}%"); hc[4].metric("Net P&L",f"₹{net:+,.0f}")
            df_h=pd.DataFrame(h)
            disp=[c for c in ["symbol","type","mode","entry","exit","qty","invested","brokerage","pnl","entry_time","exit_time"] if c in df_h.columns]
            st.dataframe(df_h[disp].rename(columns={"entry":"Entry(₹)","exit":"Exit(₹)","pnl":"Net P&L(₹)"}), use_container_width=True, hide_index=True)
            if len(h)>=2:
                df_h2=pd.DataFrame(h); df_h2["cum"]=df_h2["pnl"].cumsum()
                fig=go.Figure()
                fig.add_trace(go.Scatter(y=df_h2["cum"],mode="lines+markers",line=dict(color="#00e676",width=2),fill="tozeroy",fillcolor="rgba(0,230,118,0.08)",marker=dict(color=["#00e676" if p>=0 else "#ff1744" for p in df_h2["pnl"]],size=7)))
                fig.update_layout(title="Equity Cumulative P&L",paper_bgcolor="#080c14",plot_bgcolor="#080c14",font=dict(color="#b0c4d8"),height=250,margin=dict(l=40,r=20,t=30,b=20))
                st.plotly_chart(fig,use_container_width=True)
            st.download_button("📥 Download CSV",data=df_h.to_csv(index=False),file_name=f"equity_history_{datetime.now().strftime('%Y%m%d')}.csv",mime="text/csv")
            if st.button("🗑️ Clear Equity History"):
                st.session_state.eq_history=[]; db.save("eq_history",[]); st.rerun()
