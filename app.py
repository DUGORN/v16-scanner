import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime
import os
import scanner

# ตั้งค่าหน้าเว็บ
st.set_page_config(
    page_title="V16.1 Scanner",
    page_icon="🚀",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ============================================================================
#  ไฟล์เก็บข้อมูล
# ============================================================================

COINS_FILE = 'coins.txt'
TRADES_FILE = 'trades_log.csv'

# ============================================================================
#  ฟังก์ชันจัดการ coins.txt
# ============================================================================

def load_coins():
    if not os.path.exists(COINS_FILE):
        return []
    with open(COINS_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def save_coins(coins):
    with open(COINS_FILE, 'w', encoding='utf-8') as f:
        for coin in coins:
            f.write(coin + '\n')

def add_coin(symbol):
    symbol = symbol.strip().upper()
    if not symbol:
        return False, " กรุณาพิมพ์ชื่อเหรียญ"
    if not symbol.endswith('.P'):
        symbol += '.P'
    coins = load_coins()
    if symbol in coins:
        return False, f"⚠️ {symbol} มีอยู่แล้ว"
    coins.append(symbol)
    save_coins(coins)
    return True, f"✅ เพิ่ม {symbol} สำเร็จ!"

def remove_coin(symbol):
    coins = load_coins()
    if symbol not in coins:
        return False, f"⚠️ ไม่พบ {symbol}"
    coins.remove(symbol)
    save_coins(coins)
    return True, f"✅ ลบ {symbol} สำเร็จ!"

def remove_multiple_coins(symbols_to_remove):
    coins = load_coins()
    for symbol in symbols_to_remove:
        if symbol in coins:
            coins.remove(symbol)
    save_coins(coins)
    return True, f"✅ ลบ {len(symbols_to_remove)} เหรียญสำเร็จ!"

# ============================================================================
#  🆕 ฟังก์ชันจัดการ Trade Journal
# ============================================================================

def load_trades():
    """โหลดรายการเทรดจาก CSV"""
    if not os.path.exists(TRADES_FILE):
        return pd.DataFrame(columns=[
            'id', 'symbol', 'direction', 'entry_price', 'sl', 'tp1', 'tp2',
            'exit_price', 'exit_date', 'position_size', 'leverage',
            'pnl_usd', 'pnl_pct', 'status', 'score', 'regime',
            'confidence', 'notes', 'entry_date', 'ai_prompt'
        ])
    try:
        df = pd.read_csv(TRADES_FILE)
        return df
    except:
        return pd.DataFrame()

def save_trades(df):
    """บันทึกรายการเทรดลง CSV"""
    df.to_csv(TRADES_FILE, index=False, encoding='utf-8')

def calculate_pnl(entry, exit_price, direction, position_size, leverage):
    """คำนวณ P&L"""
    if entry == 0 or exit_price == 0:
        return 0, 0
    
    if direction == "LONG":
        pnl_pct = (exit_price - entry) / entry * 100
    else:
        pnl_pct = (entry - exit_price) / entry * 100
    
    pnl_usd = position_size * (pnl_pct / 100) * leverage
    
    return round(pnl_usd, 2), round(pnl_pct, 2)

def determine_status(pnl_pct):
    """กำหนดสถานะ Win/Loss/BE"""
    if pnl_pct > 0.1:
        return "WIN"
    elif pnl_pct < -0.1:
        return "LOSS"
    else:
        return "BREAKEVEN"

def add_trade(trade_data):
    """เพิ่มเทรดใหม่"""
    df = load_trades()
    
    trade_id = len(df) + 1 if len(df) > 0 else 1
    
    pnl_usd = 0
    pnl_pct = 0
    status = "OPEN"
    
    if trade_data.get('exit_price') and trade_data['exit_price'] > 0:
        pnl_usd, pnl_pct = calculate_pnl(
            trade_data['entry_price'],
            trade_data['exit_price'],
            trade_data['direction'],
            trade_data['position_size'],
            trade_data['leverage']
        )
        status = determine_status(pnl_pct)
    
    new_trade = {
        'id': trade_id,
        'symbol': trade_data['symbol'],
        'direction': trade_data['direction'],
        'entry_price': trade_data['entry_price'],
        'sl': trade_data.get('sl', 0),
        'tp1': trade_data.get('tp1', 0),
        'tp2': trade_data.get('tp2', 0),
        'exit_price': trade_data.get('exit_price', 0),
        'exit_date': trade_data.get('exit_date', ''),
        'position_size': trade_data['position_size'],
        'leverage': trade_data['leverage'],
        'pnl_usd': pnl_usd,
        'pnl_pct': pnl_pct,
        'status': status,
        'score': trade_data.get('score', 0),
        'regime': trade_data.get('regime', ''),
        'confidence': trade_data.get('confidence', 'MEDIUM'),
        'notes': trade_data.get('notes', ''),
        'entry_date': trade_data.get('entry_date', datetime.now().strftime('%Y-%m-%d %H:%M')),
        'ai_prompt': trade_data.get('ai_prompt', '')
    }
    
    df = pd.concat([df, pd.DataFrame([new_trade])], ignore_index=True)
    save_trades(df)
    
    return True, f"✅ บันทึกเทรด #{trade_id} สำเร็จ!"

def delete_trade(trade_id):
    """ลบเทรด"""
    df = load_trades()
    df = df[df['id'] != trade_id]
    save_trades(df)
    return True, "✅ ลบเทรดสำเร็จ!"

def get_trade_stats():
    """คำนวณสถิติรวม"""
    df = load_trades()
    
    if len(df) == 0:
        return {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'breakeven': 0,
            'open': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0
        }
    
    closed = df[df['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])]
    
    wins = len(df[df['status'] == 'WIN'])
    losses = len(df[df['status'] == 'LOSS'])
    breakeven = len(df[df['status'] == 'BREAKEVEN'])
    open_trades = len(df[df['status'] == 'OPEN'])
    
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0
    
    total_pnl = df['pnl_usd'].sum()
    avg_pnl = df['pnl_usd'].mean() if len(df) > 0 else 0
    
    best_trade = df['pnl_usd'].max() if len(df) > 0 else 0
    worst_trade = df['pnl_usd'].min() if len(df) > 0 else 0
    
    avg_win = df[df['pnl_usd'] > 0]['pnl_usd'].mean() if wins > 0 else 0
    avg_loss = df[df['pnl_usd'] < 0]['pnl_usd'].mean() if losses > 0 else 0
    
    gross_profit = df[df['pnl_usd'] > 0]['pnl_usd'].sum() if wins > 0 else 0
    gross_loss = abs(df[df['pnl_usd'] < 0]['pnl_usd'].sum()) if losses > 0 else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
    
    return {
        'total_trades': len(df),
        'wins': wins,
        'losses': losses,
        'breakeven': breakeven,
        'open': open_trades,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_pnl': avg_pnl,
        'best_trade': best_trade,
        'worst_trade': worst_trade,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor
    }

# ============================================================================
#  ฟังก์ชันดึงข้อมูล 24h Ticker
# ============================================================================

def get_24h_ticker(symbol):
    try:
        api_symbol = symbol.replace('.P', '')
        response = scanner.requests.get(
            'https://fapi.binance.com/fapi/v1/ticker/24hr',
            params={'symbol': api_symbol},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"API Error: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error in get_24h_ticker: {e}")
        return None

# ============================================================================
#  ฟังก์ชันวิเคราะห์เหรียญเดียว
# ============================================================================

def analyze_single_coin(symbol):
    try:
        print(f"\n🔍 ===== Analyzing: {symbol} =====")
        symbol = symbol.strip().upper()
        if not symbol.endswith('.P'):
            symbol += '.P'
        
        print(f"📡 Fetching ticker data...")
        ticker_24h = get_24h_ticker(symbol)
        
        print(f"📊 Fetching klines data...")
        tf_4h = scanner.get_klines(symbol, '4h', 100)
        tf_1h = scanner.get_klines(symbol, '1h', 100)
        tf_15m = scanner.get_klines(symbol, '15m', 350)
        tf_1d = scanner.get_klines(symbol, '1d', 30)
        
        print(f"✅ Data received:")
        print(f"   - tf_4h: {len(tf_4h) if tf_4h else 0} candles")
        print(f"   - tf_1h: {len(tf_1h) if tf_1h else 0} candles")
        print(f"   - tf_15m: {len(tf_15m) if tf_15m else 0} candles")
        print(f"   - tf_1d: {len(tf_1d) if tf_1d else 0} candles")
        
        if not all([tf_4h, tf_1h, tf_15m]):
            error_msg = "❌ ไม่สามารถดึงข้อมูลได้ - API อาจมีปัญหาชั่วคราว"
            print(f"⚠️ {error_msg}")
            return None, error_msg
        
        current_price = float(tf_15m[-1][4])
        print(f"💰 Current price: {current_price}")
        
        if tf_1d and len(tf_1d) >= 2:
            pdh = float(tf_1d[-2][2])
            pdl = float(tf_1d[-2][3])
        else:
            pdh = float(tf_15m[-2][2])
            pdl = float(tf_15m[-2][3])
        
        high_24h = float(ticker_24h['highPrice']) if ticker_24h else float(tf_15m[-1][2])
        low_24h = float(ticker_24h['lowPrice']) if ticker_24h else float(tf_15m[-1][3])
        price_change = float(ticker_24h['priceChange']) if ticker_24h else 0
        price_change_pct = float(ticker_24h['priceChangePercent']) if ticker_24h else 0
        volume_24h = float(ticker_24h['volume']) if ticker_24h else 0
        quote_volume = float(ticker_24h['quoteVolume']) if ticker_24h else 0
        
        dist_pdh = (current_price - pdh) / pdh * 100
        dist_pdl = (current_price - pdl) / pdl * 100
        
        is_xau = 'XAU' in symbol or 'GOLD' in symbol
        
        print(f"🔧 Calculating indicators...")
        htf_bias, htf_score = scanner.get_htf_bias(tf_4h, tf_1h)
        sweep_data = scanner.detect_liquidity_sweep(tf_15m, is_xau)
        volume_ratio = scanner.calculate_volume_ratio(tf_15m)
        sd_supply, sd_demand = scanner.detect_sd_zones(tf_15m)
        signal_priority = scanner.calculate_signal_priority(
            sweep_data if sweep_data else {}, volume_ratio, htf_bias, sd_supply, sd_demand
        )
        
        direction = "NONE"
        if sweep_data and sweep_data['is_sweep_low']:
            direction = "LONG"
        elif sweep_data and sweep_data['is_sweep_high']:
            direction = "SHORT"
        
        highs_arr = np.array([float(c[2]) for c in tf_15m])
        lows_arr = np.array([float(c[3]) for c in tf_15m])
        dom_cycle = scanner.calculate_dominant_cycle(highs_arr, lows_arr)
        
        rsi_value, regime, rsi_p, rsi_s, rsi_os, rsi_ob, rsi_score = scanner.calculate_adaptive_rsi(tf_15m)
        
        macd_value, signal_value, hist_value, macd_cross_up, macd_cross_down = scanner.calculate_adaptive_macd(
            tf_15m, dom_cycle
        )
        
        macd_div, div_score = scanner.detect_macd_divergence(tf_15m)
        
        rsi_os_entry = False
        rsi_ob_exit = False
        if rsi_value is not None:
            rsi_os_entry = rsi_value < rsi_os
            rsi_ob_exit = rsi_value > rsi_ob
        
        conf_score = scanner.calculate_confluence_score(
            rsi_value, rsi_os, rsi_ob, regime,
            macd_cross_up, macd_cross_down,
            macd_div, macd_value,
            rsi_os_entry, rsi_ob_exit
        ) if rsi_value is not None else 0
        
        total_score = 0
        breakdown = {}
        
        htf_final = htf_score * 0.83
        total_score += htf_final
        breakdown['HTF_Bias'] = f"{htf_bias} ({htf_final:.0f}/25)"
        
        if sweep_data and sweep_data['sweep_detected']:
            sweep_score = 25 + max(0, 5 - (sweep_data['min_distance'] * 5))
            total_score += sweep_score
            breakdown['Sweep'] = f"Detected ({sweep_score:.0f}/25+)"
        else:
            breakdown['Sweep'] = "None (0/25)"
        
        if (direction == "LONG" and conf_score > 0) or (direction == "SHORT" and conf_score < 0):
            amc_score = min(30, abs(conf_score))
            total_score += amc_score
            breakdown['AMC_Confluence'] = f"{conf_score:+.1f} ({amc_score:.0f}/30)"
        else:
            breakdown['AMC_Confluence'] = f"{conf_score:+.1f} (0/30)"
        
        vol_score = 0
        if volume_ratio > 0.65:
            vol_score = 10
        elif volume_ratio > 0.55:
            vol_score = 7
        elif volume_ratio > 0.45:
            vol_score = 5
        total_score += vol_score
        breakdown['Volume'] = f"{volume_ratio:.2f} ({vol_score}/10)"
        
        sd_score = 0
        if direction == "LONG" and sd_demand and sd_demand['score'] >= 5:
            sd_score = 10
        elif direction == "SHORT" and sd_supply and sd_supply['score'] >= 5:
            sd_score = 10
        total_score += sd_score
        breakdown['SD_Magnet'] = f"{'Active' if sd_score > 0 else 'Inactive'} ({sd_score}/10)"
        
        g_ma = scanner.calculate_ema(tf_1h, 50)
        
        penalty, validation_reasons = scanner.validate_confluence(
            direction, htf_bias, current_price, g_ma, regime, conf_score
        )
        
        total_score += penalty
        breakdown['Validation'] = f"{penalty:+.0f} ({len(validation_reasons)} issues)"
        
        # 🆕 MACRO CONTEXT FILTER
        print(f"🌍 Analyzing macro context...")
        macro_data = scanner.analyze_macro_context(symbol, current_price)
        
        if macro_data:
            total_score, direction, validation_reasons = scanner.apply_macro_filter(
                direction, macro_data, total_score, validation_reasons, current_price
            )
            breakdown['Macro_Filter'] = f"Applied ({macro_data['major_level_type'] or 'None'})"
            print(f"✅ Macro filter applied")
        else:
            macro_data = {
                'weekly_high_52w': 0, 'weekly_low_52w': 0, 'monthly_high_24m': 0, 'monthly_low_24m': 0,
                'weekly_ema_50': None, 'monthly_ema_20': None, 'weekly_trend': 'UNKNOWN',
                'dist_to_weekly_high': 0, 'dist_to_weekly_low': 0, 'dist_to_monthly_high': 0, 'dist_to_monthly_low': 0,
                'dist_to_weekly_ema': 0, 'dist_to_monthly_ema': 0, 'near_major_support': False,
                'near_major_resistance': False, 'major_level_type': None, 'major_level_distance': 0
            }
            breakdown['Macro_Filter'] = "No Data"
            print(f"⚠️ Macro data not available")
        
        basic_info = {
            'symbol': symbol,
            'symbol_short': symbol.replace('.P', ''),
            'price': current_price,
            'pdh': pdh,
            'pdl': pdl,
            'high_24h': high_24h,
            'low_24h': low_24h,
            'price_change': price_change,
            'price_change_pct': price_change_pct,
            'volume_24h': volume_24h,
            'quote_volume': quote_volume,
            'dist_pdh': dist_pdh,
            'dist_pdl': dist_pdl,
        }
        
        setup = {
            'symbol': symbol,
            'price': current_price,
            'score': round(total_score, 1),
            'direction': direction,
            'distance': sweep_data['min_distance'] if sweep_data else 0,
            'volume_ratio': volume_ratio,
            'htf_bias': htf_bias,
            'signal_priority': signal_priority,
            'pdh': pdh,
            'pdl': pdl,
            'sweep_low': sweep_data['is_sweep_low'] if sweep_data else False,
            'sweep_high': sweep_data['is_sweep_high'] if sweep_data else False,
            'sd_supply': sd_supply,
            'sd_demand': sd_demand,
            'regime': regime,
            'rsi_value': rsi_value if rsi_value else 0,
            'rsi_p': rsi_p,
            'rsi_s': rsi_s,
            'rsi_os': rsi_os,
            'rsi_ob': rsi_ob,
            'dom_cycle': dom_cycle,
            'macd_value': macd_value,
            'signal_value': signal_value,
            'hist_value': hist_value,
            'macd_cross_up': macd_cross_up,
            'macd_cross_down': macd_cross_down,
            'macd_div': macd_div,
            'conf_score': conf_score,
            'g_ma': g_ma,
            'penalty': penalty,
            'validation_reasons': validation_reasons,
            'breakdown': breakdown,
            'basic_info': basic_info,
            # 🆕 MACRO FIELDS
            'macro_data': macro_data,
            'weekly_high_52w': macro_data['weekly_high_52w'],
            'weekly_low_52w': macro_data['weekly_low_52w'],
            'monthly_high_24m': macro_data['monthly_high_24m'],
            'monthly_low_24m': macro_data['monthly_low_24m'],
            'weekly_trend': macro_data['weekly_trend'],
            'near_major_support': macro_data['near_major_support'],
            'near_major_resistance': macro_data['near_major_resistance'],
            'major_level_type': macro_data['major_level_type'],
            'major_level_distance': macro_data['major_level_distance'],
        }
        
        print(f"✅ Analysis complete! Score: {total_score:.1f}/100")
        print(f"🎯 Direction: {direction}")
        print(f"===== End Analysis =====\n")
        
        return setup, None
        
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        print(f"🚨 {error_msg}")
        import traceback
        traceback.print_exc()
        return None, error_msg

# ============================================================================
#  Sidebar
# ============================================================================

st.sidebar.title("⚙️ Settings")
auto_refresh = st.sidebar.checkbox("Auto-refresh ทุก 15 นาที", value=True)
min_score = st.sidebar.slider("Min Score", 0, 100, 50)
filter_dir = st.sidebar.radio("Filter Direction", ["All", "LONG", "SHORT"])
filter_regime = st.sidebar.multiselect(
    "Filter Regime", 
    ["CHOP", "TRENDING", "QUIET", "NOISY", "ADAPTING"],
    default=["CHOP", "TRENDING"]
)

# ============================================================================
#  📋 Manage Coins
# ============================================================================

st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Manage Coins")

current_coins = load_coins()
st.sidebar.markdown(f"**Total:** {len(current_coins)} coins")

st.sidebar.markdown("**➕ Add Coin:**")
new_coin = st.sidebar.text_input("Symbol:", placeholder="BTCUSDT.P", key="add_coin_input")

if st.sidebar.button("➕ Add", use_container_width=True):
    if new_coin:
        success, msg = add_coin(new_coin)
        if success:
            st.sidebar.success(msg)
            st.rerun()
        else:
            st.sidebar.warning(msg)
    else:
        st.sidebar.warning("⚠️ กรุณาพิมพ์ชื่อเหรียญ")

st.sidebar.markdown("**➖ Remove Coins:**")
coins_to_remove = st.sidebar.multiselect("เลือกเหรียญที่จะลบ:", options=current_coins, key="remove_coins_select")

if st.sidebar.button("➖ Remove Selected", use_container_width=True):
    if coins_to_remove:
        success, msg = remove_multiple_coins(coins_to_remove)
        if success:
            st.sidebar.success(msg)
            st.rerun()
        else:
            st.sidebar.warning(msg)
    else:
        st.sidebar.warning("⚠️ กรุณาเลือกเหรียญที่จะลบ")

st.sidebar.markdown("**📜 Current Coins:**")
if current_coins:
    coins_text = "\n".join([f"• {c}" for c in current_coins])
    st.sidebar.text_area("Coins List:", value=coins_text, height=200, disabled=True)
else:
    st.sidebar.warning("️ ไม่มีเหรียญในรายการ")

# ============================================================================
#  Header
# ============================================================================

st.title("🚀 V16.1 Scanner - Mobile Edition")
st.markdown(f"**Last Update:** {datetime.now().strftime('%H:%M:%S')}")

# ============================================================================
#  Navigation Tabs
# ============================================================================

tab1, tab2, tab3, tab4 = st.tabs([
    " Scanner",
    " Analyze Coin",
    "📓 Trade Journal",
    "📊 Statistics"
])

# ============================================================================
#  TAB 1: Scanner
# ============================================================================

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Scan All Coins", use_container_width=True):
            if not current_coins:
                st.error("⚠️ ไม่มีเหรียญในรายการ! กรุณาเพิ่มเหรียญใน Sidebar ก่อน")
            else:
                with st.spinner('Scanning...'):
                    st.session_state['setups'] = scanner.scan_coins_v16()
                    st.session_state['last_scan'] = datetime.now()
                st.success(f"✅ Scanned {len(st.session_state['setups'])} setups!")
    
    setups = st.session_state.get('setups', [])
    
    if setups:
        filtered = [s for s in setups if s['score'] >= min_score]
        if filter_dir != "All":
            filtered = [s for s in filtered if s['direction'] == filter_dir]
        if filter_regime:
            filtered = [s for s in filtered if s['regime'] in filter_regime]
        
        st.markdown(f"### 📊 พบ {len(filtered)} setups")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total", len(filtered))
        col2.metric("LONG", sum(1 for s in filtered if s['direction'] == "LONG"))
        col3.metric("SHORT", sum(1 for s in filtered if s['direction'] == "SHORT"))
        col4.metric("Valid", sum(1 for s in filtered if s['penalty'] == 0))
        
        df = pd.DataFrame([{
            'Symbol': s['symbol'],
            'Score': s['score'],
            'Dir': s['direction'],
            'HTF': s['htf_bias'],
            'Regime': s['regime'],
            'Conf': f"{s['conf_score']:+.1f}",
            'Penalty': s['penalty'],
            'Valid': '✅' if s['penalty'] == 0 else '⚠️',
            'Macro': '🟢' if s.get('near_major_support') else ('' if s.get('near_major_resistance') else '⚪'),
            'W_Trend': s.get('weekly_trend', 'N/A'),
            'Price': s['price'],
            'Dist%': s['distance']
        } for s in filtered])
        
        st.dataframe(df, use_container_width=True)
        
        st.subheader("🎯 เลือกเหรียญเพื่อดูรายละเอียด")
        coin_options = [f"{s['symbol']} ({s['score']})" for s in filtered]
        if coin_options:
            selected = st.selectbox("Coin:", coin_options)
            if selected:
                symbol = selected.split(' ')[0]
                setup = next(s for s in filtered if s['symbol'] == symbol)
                
                st.markdown(f"### 📊 {setup['symbol']} Breakdown")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Scoring:**")
                    for k, v in setup['breakdown'].items():
                        st.text(f"  {k}: {v}")
                    st.markdown(f"**Total: {setup['score']}/100**")
                
                with col2:
                    st.markdown("**AMC Data:**")
                    st.text(f"Regime: {setup['regime']}")
                    st.text(f"RSI: {setup['rsi_value']:.1f}")
                    st.text(f"Confluence: {setup['conf_score']:+.1f}")
                
                if setup['validation_reasons']:
                    st.error("⚠️ Validation Issues:")
                    for r in setup['validation_reasons']:
                        st.text(f"  {r}")
                else:
                    st.success("✅ No conflicts - Signal is valid!")

# ============================================================================
#  TAB 2: Analyze Single Coin
# ============================================================================

with tab2:
    st.markdown("### 🔍 CHECK SINGLE COIN")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        manual_symbol = st.text_input("Enter coin (e.g., BTCUSDT.P):", placeholder="XPLUSDT.P", key="manual_symbol_input")
    with col2:
        analyze_clicked = st.button("🔍 Analyze", use_container_width=True, type="primary")
    
    if analyze_clicked and manual_symbol:
        with st.spinner(f'📊 Fetching data for {manual_symbol.upper()}...'):
            setup, error = analyze_single_coin(manual_symbol)
            if setup:
                st.session_state['analyzed_coin'] = setup
            else:
                st.error(error)
    
    if 'analyzed_coin' in st.session_state:
        setup = st.session_state['analyzed_coin']
        info = setup['basic_info']
        
        st.markdown("---")
        st.markdown(f"""
<div style="background-color: #1e1e1e; padding: 20px; border-radius: 10px; border: 2px solid #333;">
    <h2 style="color: #00ff00; margin: 0;"> {info['symbol_short']}</h2>
    <h1 style="color: #ffffff; margin: 10px 0;">{info['price']:.4f}</h1>
</div>
""", unsafe_allow_html=True)
        
        st.markdown("### 📊 Price Information")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**PDH:** {info['pdh']:.4f}  \n**PDL:** {info['pdl']:.4f}")
        with col2:
            st.markdown(f"**High (24h):** {info['high_24h']:.4f}  \n**Low (24h):** {info['low_24h']:.4f}")
        
        st.markdown("---")
        st.markdown("### 📏 Distance from Key Levels")
        if info['dist_pdh'] < 0:
            st.markdown(f"📉 **Below PDH:** ({info['dist_pdh']:.2f}%)")
        else:
            st.markdown(f"📈 **Above PDH:** (+{info['dist_pdh']:.2f}%)")
        
        if info['dist_pdl'] < 0:
            st.markdown(f"📉 **Below PDL:** ({info['dist_pdl']:.2f}%)")
        else:
            st.markdown(f"📈 **Above PDL:** (+{info['dist_pdl']:.2f}%)")
        
        # 🆕 MACRO CONTEXT SECTION
        if 'macro_data' in setup and setup['macro_data']:
            macro = setup['macro_data']
            
            st.markdown("---")
            st.markdown("### 🌍 MACRO CONTEXT (ภาพใหญ่)")
            
            if macro['near_major_support']:
                st.success(f"🟢 ราคาอยู่ใกล้แนวรับใหญ่: **{macro['major_level_type']}** ({macro['major_level_distance']:+.2f}%)")
            elif macro['near_major_resistance']:
                st.error(f"🔴 ราคาอยู่ใกล้แนวต้านใหญ่: **{macro['major_level_type']}** ({macro['major_level_distance']:+.2f}%)")
            else:
                st.info("⚪ ราคาอยู่ห่างจาก Major Levels")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Weekly Trend", macro['weekly_trend'])
                st.metric("52W High", f"{macro['weekly_high_52w']:.4f}")
                st.metric("52W Low", f"{macro['weekly_low_52w']:.4f}")
            with col2:
                st.metric("Dist to 52W High", f"{macro['dist_to_weekly_high']:+.2f}%")
                st.metric("Dist to 52W Low", f"{macro['dist_to_weekly_low']:+.2f}%")
                w_ema = macro['weekly_ema_50']
                st.metric("Weekly EMA 50", f"{w_ema:.4f}" if w_ema else "N/A")
            with col3:
                st.metric("Dist to 24M High", f"{macro['dist_to_monthly_high']:+.2f}%")
                st.metric("Dist to 24M Low", f"{macro['dist_to_monthly_low']:+.2f}%")
                m_ema = macro['monthly_ema_20']
                st.metric("Monthly EMA 20", f"{m_ema:.4f}" if m_ema else "N/A")
        
        st.markdown("---")
        st.markdown("### 📈 24h Statistics")
        change_sign = "+" if info['price_change'] >= 0 else ""
        st.markdown(f"""
**24h Change:** {change_sign}{info['price_change']:.4f} ({change_sign}{info['price_change_pct']:.2f}%)  
**Volume:** {info['volume_24h']:,.0f}  
**Quote Volume:** ${info['quote_volume']:,.2f} USDT
""")
        
        st.markdown("---")
        st.markdown("### 🎯 V16.1 Analysis")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Score", f"{setup['score']}/100")
        col2.metric("Direction", setup['direction'])
        col3.metric("Regime", setup['regime'])
        col4.metric("Priority", f"{'⭐' * setup['signal_priority']}")
        
        st.markdown("###  Scoring Breakdown")
        for k, v in setup['breakdown'].items():
            st.text(f"  {k}: {v}")
        
        st.markdown("### 📊 AMC Data")
        col1, col2 = st.columns(2)
        with col1:
            st.text(f"RSI: {setup['rsi_value']:.1f}")
            st.text(f"OS/OB: {setup['rsi_os']}/{setup['rsi_ob']}")
            st.text(f"Confluence: {setup['conf_score']:+.1f}")
        with col2:
            st.text(f"MACD: {setup['macd_value']:.4f}")
            st.text(f"Cross: {'UP 🟢' if setup['macd_cross_up'] else 'DOWN ' if setup['macd_cross_down'] else 'NONE'}")
            st.text(f"Divergence: {setup['macd_div']}")
        
        st.markdown("### 🎯 Validation")
        if setup['validation_reasons']:
            st.error("️ Validation Issues Detected:")
            for r in setup['validation_reasons']:
                st.text(f"  {r}")
        else:
            st.success("✅ No conflicts detected - Signal is valid!")
        
        # 🆕 ปุ่ม Log This Trade
        st.markdown("---")
        st.markdown("### 📓 บันทึกเทรดนี้")
        if st.button("📝 Log This Trade", use_container_width=True, type="primary"):
            st.session_state['trade_from_analyze'] = setup
            st.session_state['active_tab'] = 2
            st.success("✅ ไปที่หน้า Trade Journal เพื่อบันทึกรายละเอียด!")
        
        # Prompt สำหรับ Copy
        st.markdown("### 💡 Copy ข้อมูลนี้ไปถาม AI")
        
        macro_info = ""
        if 'macro_data' in setup and setup['macro_data']:
            m = setup['macro_data']
            macro_info = f"""
🌍 MACRO CONTEXT:
- Weekly Trend: {m['weekly_trend']}
- 52W High: {m['weekly_high_52w']:.4f} | 52W Low: {m['weekly_low_52w']:.4f}
- 24M High: {m['monthly_high_24m']:.4f} | 24M Low: {m['monthly_low_24m']:.4f}
- Near Major Support: {'YES' if m['near_major_support'] else 'NO'}
- Near Major Resistance: {'YES' if m['near_major_resistance'] else 'NO'}
- Major Level Type: {m['major_level_type'] or 'None'}
- Dist to 52W High: {m['dist_to_weekly_high']:+.2f}%
- Dist to 52W Low: {m['dist_to_weekly_low']:+.2f}%
"""
        
        prompt = f"""{info['symbol_short']}
ราคา: {info['price']:.4f}
PDH: {info['pdh']:.4f} | PDL: {info['pdl']:.4f}
High: {info['high_24h']:.4f} | Low: {info['low_24h']:.4f}
24h Change: {change_sign}{info['price_change']:.4f} ({change_sign}{info['price_change_pct']:.2f}%)
{macro_info}
📊 V16.1 Analysis:
- Score: {setup['score']}/100
- Direction: {setup['direction']}
- Regime: {setup['regime']}
- HTF Bias: {setup['htf_bias']}
- RSI: {setup['rsi_value']:.1f}
- Confluence: {setup['conf_score']:+.1f}
- MACD Cross: {'Bullish' if setup['macd_cross_up'] else 'Bearish' if setup['macd_cross_down'] else 'None'}
- Divergence: {setup['macd_div']}

💡 ควรเข้า LONG/SHORT หรือไม่? Entry/SL/TP เท่าไหร่?
(วิเคราะห์ภาพใหญ่ Monthly/Weekly ก่อนเสมอ)"""
        
        st.code(prompt, language='text')

# ============================================================================
#   TAB 3: Trade Journal
# ============================================================================

with tab3:
    st.markdown("### 📓 Trade Journal")
    
    st.markdown("---")
    st.markdown("#### ➕ เพิ่มเทรดใหม่")
    
    prefill = st.session_state.get('trade_from_analyze', None)
    
    with st.form("add_trade_form"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            symbol = st.text_input("Symbol *", value=prefill['symbol'] if prefill else "", placeholder="BTCUSDT.P")
            direction = st.selectbox("Direction *", ["LONG", "SHORT"], index=0 if (prefill and prefill['direction'] == "LONG") else 1)
            entry_price = st.number_input("Entry Price *", value=float(prefill['price']) if prefill else 0.0, step=0.0001, format="%.4f")
        
        with col2:
            sl = st.number_input("Stop Loss", value=0.0, step=0.0001, format="%.4f")
            tp1 = st.number_input("TP1", value=0.0, step=0.0001, format="%.4f")
            tp2 = st.number_input("TP2", value=0.0, step=0.0001, format="%.4f")
        
        with col3:
            position_size = st.number_input("Position Size ($)", value=10.0, step=1.0)
            leverage = st.number_input("Leverage (x)", value=75, step=1)
            confidence = st.selectbox("AI Confidence", ["HIGH", "MEDIUM", "LOW"])
        
        col1, col2 = st.columns(2)
        with col1:
            exit_price = st.number_input("Exit Price (ถ้าปิดแล้ว)", value=0.0, step=0.0001, format="%.4f")
            exit_date = st.text_input("Exit Date/Time", placeholder="YYYY-MM-DD HH:MM")
        with col2:
            score = st.number_input("Setup Score", value=float(prefill['score']) if prefill else 0.0, step=0.1)
            regime = st.text_input("Regime", value=prefill['regime'] if prefill else "")
        
        notes = st.text_area("Notes / AI Analysis", placeholder="วางคำตอบจาก AI ที่นี่...")
        
        submitted = st.form_submit_button(" บันทึกเทรด", use_container_width=True, type="primary")
        
        if submitted:
            if not symbol or entry_price == 0:
                st.error("⚠️ กรุณากรอก Symbol และ Entry Price")
            else:
                trade_data = {
                    'symbol': symbol.upper() if not symbol.upper().endswith('.P') else symbol.upper(),
                    'direction': direction,
                    'entry_price': entry_price,
                    'sl': sl,
                    'tp1': tp1,
                    'tp2': tp2,
                    'exit_price': exit_price,
                    'exit_date': exit_date,
                    'position_size': position_size,
                    'leverage': leverage,
                    'confidence': confidence,
                    'score': score,
                    'regime': regime,
                    'notes': notes,
                    'entry_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'ai_prompt': ''
                }
                
                success, msg = add_trade(trade_data)
                if success:
                    st.success(msg)
                    if 'trade_from_analyze' in st.session_state:
                        del st.session_state['trade_from_analyze']
                    st.rerun()
                else:
                    st.error(msg)
    
    st.markdown("---")
    st.markdown("#### 📋 รายการเทรดทั้งหมด")
    
    trades_df = load_trades()
    
    if len(trades_df) > 0:
        col1, col2, col3 = st.columns(3)
        with col1:
            filter_status = st.multiselect("Filter Status", ["OPEN", "WIN", "LOSS", "BREAKEVEN"], default=["OPEN", "WIN", "LOSS", "BREAKEVEN"])
        with col2:
            filter_symbol = st.multiselect("Filter Symbol", options=trades_df['symbol'].unique().tolist())
        with col3:
            filter_direction = st.radio("Direction", ["All", "LONG", "SHORT"])
        
        filtered_trades = trades_df[trades_df['status'].isin(filter_status)]
        if filter_symbol:
            filtered_trades = filtered_trades[filtered_trades['symbol'].isin(filter_symbol)]
        if filter_direction != "All":
            filtered_trades = filtered_trades[filtered_trades['direction'] == filter_direction]
        
        display_df = filtered_trades[['id', 'symbol', 'direction', 'entry_price', 'exit_price', 'pnl_usd', 'pnl_pct', 'status', 'entry_date']].copy()
        display_df['pnl_usd'] = display_df['pnl_usd'].apply(lambda x: f"${x:,.2f}")
        display_df['pnl_pct'] = display_df['pnl_pct'].apply(lambda x: f"{x:+.2f}%")
        
        st.dataframe(display_df, use_container_width=True)
        
        st.markdown("#### 🗑️ ลบเทรด")
        trade_to_delete = st.selectbox("เลือกเทรดที่จะลบ:", options=filtered_trades['id'].tolist(), format_func=lambda x: f"#{x} - {filtered_trades[filtered_trades['id']==x]['symbol'].values[0]}")
        
        if st.button("🗑️ ลบเทรดที่เลือก", use_container_width=True):
            if st.checkbox("ยืนยันการลบ?", key="confirm_delete_trade"):
                success, msg = delete_trade(trade_to_delete)
                if success:
                    st.success(msg)
                    st.rerun()
        
        st.markdown("#### 📥 Export")
        if st.button("📥 Export to CSV", use_container_width=True):
            csv = trades_df.to_csv(index=False).encode('utf-8')
            st.download_button("💾 Download CSV", csv, file_name=f"trades_{datetime.now().strftime('%Y%m%d')}.csv", mime='text/csv')
    else:
        st.info(" ยังไม่มีเทรดในรายการ เริ่มบันทึกเทรดแรกของคุณด้านบน!")

# ============================================================================
#  🆕 TAB 4: Statistics
# ============================================================================

with tab4:
    st.markdown("### 📊 Trading Statistics")
    
    stats = get_trade_stats()
    
    if stats['total_trades'] == 0:
        st.info(" ยังไม่มีข้อมูลสถิติ เริ่มบันทึกเทรดเพื่อเห็นสถิติ!")
    else:
        st.markdown("#### 📈 Overview")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", stats['total_trades'])
        col2.metric("Win Rate", f"{stats['win_rate']:.1f}%")
        col3.metric("Total P&L", f"${stats['total_pnl']:,.2f}", delta=f"${stats['total_pnl']:,.2f}")
        col4.metric("Profit Factor", f"{stats['profit_factor']:.2f}")
        
        st.markdown("#### 🎯 Win/Loss Breakdown")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Wins", stats['wins'], delta=f"{stats['avg_win']:+.2f}")
        col2.metric("Losses", stats['losses'], delta=f"{stats['avg_loss']:+.2f}")
        col3.metric("Breakeven", stats['breakeven'])
        col4.metric("Open Trades", stats['open'])
        
        st.markdown("#### 💰 Performance")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Best Trade", f"${stats['best_trade']:,.2f}")
        col2.metric("Worst Trade", f"${stats['worst_trade']:,.2f}")
        col3.metric("Avg P&L", f"${stats['avg_pnl']:,.2f}")
        col4.metric("Avg Win", f"${stats['avg_win']:,.2f}")
        
        if stats['wins'] + stats['losses'] > 0:
            st.markdown("#### 📊 Win/Loss Distribution")
            chart_data = pd.DataFrame({
                'Status': ['Wins', 'Losses', 'Breakeven'],
                'Count': [stats['wins'], stats['losses'], stats['breakeven']]
            })
            st.bar_chart(chart_data.set_index('Status'))
        
        st.markdown("#### 📋 Recent Trades")
        trades_df = load_trades()
        if len(trades_df) > 0:
            recent = trades_df.tail(10)[['id', 'symbol', 'direction', 'entry_price', 'exit_price', 'pnl_usd', 'pnl_pct', 'status', 'entry_date']]
            st.dataframe(recent, use_container_width=True)

# ============================================================================
#  Footer
# ============================================================================

st.markdown("---")
if auto_refresh:
    st.markdown(f"⏰ Auto-refresh: จะสแกนใหม่ใน 15 นาที")
st.markdown("**V16.1 Scanner** | Pan Sniper + AMC + Macro Filter | Built with Streamlit")
