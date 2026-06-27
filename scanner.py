import requests
import numpy as np
from datetime import datetime

def get_klines(symbol, interval, limit=100):
    """ดึงข้อมูล candles จาก Binance"""
    try:
        api_symbol = symbol.replace('.P', '')
        response = requests.get(
            'https://fapi.binance.com/fapi/v1/klines',
            params={'symbol': api_symbol, 'interval': interval, 'limit': limit},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def calculate_ema(data, period):
    """คำนวณ EMA"""
    if not data or len(data) < period:
        return None
    
    if isinstance(data[0], list):
        closes = [float(candle[4]) for candle in data]
    else:
        closes = data
    
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    
    for close in closes[period:]:
        ema = (close - ema) * multiplier + ema
    
    return ema

def supersmoother(src, period):
    """Supersmoother filter"""
    if len(src) < 3:
        return src.copy()
    
    a = np.exp(-np.sqrt(2) * np.pi / period)
    b = 2 * a * np.cos(np.sqrt(2) * np.pi / period)
    c2 = b
    c3 = -a * a
    c1 = 1 - c2 - c3
    
    result = np.zeros(len(src))
    result[0] = src[0]
    if len(src) > 1:
        result[1] = src[1]
    
    for i in range(2, len(src)):
        result[i] = c1 * (src[i] + src[i-1]) / 2 + c2 * result[i-1] + c3 * result[i-2]
    
    return result

def ss_rsi(closes, rsi_period, smooth_period):
    """Smoothed RSI with supersmoother"""
    if len(closes) < rsi_period + smooth_period:
        return None
    
    chg = np.diff(closes)
    g = np.maximum(chg, 0)
    l = np.maximum(-chg, 0)
    
    ag = supersmoother(g, smooth_period)
    al = supersmoother(l, smooth_period)
    
    with np.errstate(divide='ignore', invalid='ignore'):
        rs = np.divide(ag, al, out=np.full_like(ag, np.nan), where=al!=0)
    
    rsi = 100 - 100 / (1 + rs)
    return rsi

def calculate_volume_ratio(tf_15m):
    """คำนวณ Bull/Bear Volume Ratio"""
    if not tf_15m or len(tf_15m) < 20:
        return 0.5
    
    bull_vol = 0.0
    total_vol = 0.0
    
    for candle in tf_15m[-20:]:
        open_price = float(candle[1])
        close_price = float(candle[4])
        volume = float(candle[5])
        
        total_vol += volume
        if close_price > open_price:
            bull_vol += volume
    
    return bull_vol / total_vol if total_vol > 0 else 0.5

def get_htf_bias(tf_4h, tf_1h):
    """วิเคราะห์ HTF Bias"""
    if not tf_4h or not tf_1h:
        return "NEUTRAL", 0
    
    current_price = float(tf_1h[-1][4])
    
    ema_4h_20 = calculate_ema(tf_4h, 20)
    ema_4h_50 = calculate_ema(tf_4h, 50)
    ema_1h_20 = calculate_ema(tf_1h, 20)
    ema_1h_50 = calculate_ema(tf_1h, 50)
    
    if not all([ema_4h_20, ema_4h_50, ema_1h_20, ema_1h_50]):
        return "NEUTRAL", 0
    
    g_ma = calculate_ema(tf_1h, 50)
    
    score = 0
    bias = "NEUTRAL"
    
    if (current_price > ema_4h_20 > ema_4h_50 and 
        current_price > ema_1h_20 > ema_1h_50 and
        current_price > g_ma):
        bias = "BULLISH"
        score = 30
    elif (current_price < ema_4h_20 < ema_4h_50 and 
          current_price < ema_1h_20 < ema_1h_50 and
          current_price < g_ma):
        bias = "BEARISH"
        score = 30
    else:
        bias = "NEUTRAL"
        score = 10
    
    return bias, score

def detect_liquidity_sweep(tf_15m, is_xau=False):
    """ตรวจจับ Liquidity Sweep"""
    if not tf_15m or len(tf_15m) < 2:
        return None
    
    current = float(tf_15m[-1][4])
    prev_high = float(tf_15m[-2][2])
    prev_low = float(tf_15m[-2][3])
    current_high = float(tf_15m[-1][2])
    current_low = float(tf_15m[-1][3])
    
    max_dist = 1.0 if is_xau else 0.8
    
    dist_to_pdh = abs(current - prev_high) / prev_high * 100
    dist_to_pdl = abs(current - prev_low) / prev_low * 100
    min_distance = min(dist_to_pdh, dist_to_pdl)
    
    if min_distance > max_dist:
        return None
    
    is_sweep_low = current_low < prev_low and current > prev_low
    is_sweep_high = current_high > prev_high and current < prev_high
    
    return {
        'pdh': prev_high,
        'pdl': prev_low,
        'current': current,
        'min_distance': min_distance,
        'is_sweep_low': is_sweep_low,
        'is_sweep_high': is_sweep_high,
        'sweep_detected': is_sweep_low or is_sweep_high,
        'v6_valid': min_distance <= max_dist
    }

def detect_sd_zones(tf_15m, swing_len=12):
    """ตรวจจับ SD Zones"""
    if not tf_15m or len(tf_15m) < swing_len * 2:
        return None, None
    
    highs = [float(candle[2]) for candle in tf_15m]
    lows = [float(candle[3]) for candle in tf_15m]
    
    recent_high = max(highs[-swing_len*2:-swing_len])
    recent_low = min(lows[-swing_len*2:-swing_len])
    
    current_high = highs[-1]
    current_low = lows[-1]
    
    in_supply = current_high >= recent_high * 0.995
    supply_score = 0
    if in_supply:
        dist = abs(current_high - recent_high) / recent_high * 100
        supply_score = max(0, 10 - dist * 10)
    
    in_demand = current_low <= recent_low * 1.005
    demand_score = 0
    if in_demand:
        dist = abs(current_low - recent_low) / recent_low * 100
        demand_score = max(0, 10 - dist * 10)
    
    return {
        'in_supply': in_supply,
        'score': supply_score,
        'level': recent_high
    }, {
        'in_demand': in_demand,
        'score': demand_score,
        'level': recent_low
    }

def calculate_signal_priority(sweep_data, volume_ratio, htf_bias, sd_supply, sd_demand):
    """คำนวณ Signal Priority"""
    priority = 0
    
    if sweep_data and sweep_data['sweep_detected']:
        if sd_demand and sd_demand['in_demand'] and sd_demand['score'] >= 5:
            priority = max(priority, 4)
        elif sd_supply and sd_supply['in_supply'] and sd_supply['score'] >= 5:
            priority = max(priority, 4)
        else:
            priority = max(priority, 3)
    
    if volume_ratio > 0.6:
        priority = max(priority, 3)
    
    if htf_bias in ["BULLISH", "BEARISH"]:
        priority = max(priority, 2)
    
    priority = max(priority, 1)
    return priority

def calculate_dominant_cycle(highs, lows, cyc_min=8, cyc_max=50):
    """Ehlers Homodyne Discriminator"""
    if len(highs) < 10:
        return 20.0
    
    price = (highs + lows) / 2.0
    period = float(cyc_min)
    smooth_period = float(cyc_min)
    
    for i in range(7, len(price)):
        p_prev = period
        smooth = (4.0*price[i] + 3.0*price[i-1] + 2.0*price[i-2] + price[i-3]) / 10.0
        adj = 0.075 * p_prev + 0.54
        
        detrender = (0.0962*smooth + 0.5769*price[i-2] - 0.5769*price[i-4] - 0.0962*price[i-6]) * adj if i >= 6 else 0
        
        q1 = detrender
        i1 = detrender
        
        re = i1 * i1 + q1 * q1
        im = i1 * q1
        
        if im != 0 and re != 0:
            per = 2.0 * np.pi / max(0.01, np.arctan(im / re))
            per = min(max(per, 0.67 * p_prev), 1.5 * p_prev)
            per = max(min(per, float(cyc_max)), float(cyc_min))
            period = 0.2 * per + 0.8 * p_prev
            smooth_period = 0.33 * period + 0.67 * smooth_period
    
    return smooth_period

def calculate_adaptive_rsi(tf_data, lookback=200, eval_bars=5, min_triggers=3):
    """คำนวณ Adaptive RSI + Regime"""
    if not tf_data or len(tf_data) < lookback:
        return None, "ADAPTING", 14, 10, 25, 75, 0
    
    closes = np.array([float(candle[4]) for candle in tf_data])
    
    periods = [7, 14, 21]
    smooths = [6, 10, 16]
    os_levels = [15, 20, 25, 30]
    ob_levels = [85, 80, 75, 70]
    
    rsi_variants = []
    for p in periods:
        for s in smooths:
            rsi = ss_rsi(closes, p, s)
            rsi_variants.append(rsi)
    
    scores = []
    trigger_counts = []
    
    for pi in range(len(periods)):
        for si in range(len(smooths)):
            variant_scores = []
            variant_triggers = 0
            
            rsi = rsi_variants[pi * len(smooths) + si]
            if rsi is None or len(rsi) < lookback:
                scores.append(0)
                trigger_counts.append(0)
                continue
            
            for ti in range(len(os_levels)):
                total_return = 0
                triggers = 0
                
                for b in range(eval_bars, min(lookback, len(rsi) - 1)):
                    if np.isnan(rsi[-b]) or np.isnan(rsi[-b-1]):
                        continue
                    
                    os_level = os_levels[ti]
                    ob_level = ob_levels[ti]
                    
                    if rsi[-b-1] >= os_level and rsi[-b] < os_level:
                        p_then = closes[-b]
                        p_fwd = closes[-b - eval_bars] if b + eval_bars < len(closes) else closes[0]
                        if p_then > 0:
                            fret = p_fwd / p_then - 1
                            total_return += fret
                            triggers += 1
                    elif rsi[-b-1] >= ob_level and rsi[-b] < ob_level:
                        p_then = closes[-b]
                        p_fwd = closes[-b - eval_bars] if b + eval_bars < len(closes) else closes[0]
                        if p_then > 0:
                            fret = -(p_fwd / p_then - 1)
                            total_return += fret
                            triggers += 1
                
                if triggers >= min_triggers:
                    variant_scores.append(total_return / triggers)
                    variant_triggers += 1
            
            if variant_triggers > 0:
                scores.append(np.mean(variant_scores))
                trigger_counts.append(variant_triggers)
            else:
                scores.append(0)
                trigger_counts.append(0)
    
    if not scores:
        return None, "ADAPTING", 14, 10, 25, 75, 0
    
    best_idx = np.argmax(scores)
    best_pi = best_idx // len(smooths)
    best_si = best_idx % len(smooths)
    
    active_rsi = rsi_variants[best_pi * len(smooths) + best_si]
    if active_rsi is None or len(active_rsi) == 0 or np.isnan(active_rsi[-1]):
        return None, "ADAPTING", 14, 10, 25, 75, 0
    
    current_rsi = float(active_rsi[-1])
    active_os = os_levels[min(best_idx // (len(smooths) * len(os_levels)), len(os_levels)-1)]
    active_ob = ob_levels[min(best_idx // (len(smooths) * len(os_levels)), len(ob_levels)-1)]
    active_p = periods[best_pi]
    active_s = smooths[best_si]
    best_score = float(scores[best_idx])
    
    regime = "ADAPTING"
    if best_score == 0:
        regime = "ADAPTING"
    elif abs(best_score) < 0.0005 and best_si == 2:
        regime = "NOISY"
    elif best_pi >= 2 and best_si >= 2:
        regime = "TRENDING"
    elif best_pi <= 0 and best_si <= 1:
        regime = "CHOP"
    else:
        regime = "QUIET"
    
    return current_rsi, regime, active_p, active_s, active_os, active_ob, best_score

def calculate_adaptive_macd(tf_data, dom_cycle, r_fast=0.5, r_sig=0.346, sig_mult=1.0):
    """คำนวณ Adaptive MACD"""
    if not tf_data or len(tf_data) < 50:
        return 0, 0, 0, False, False
    
    closes = np.array([float(candle[4]) for candle in tf_data])
    
    slow_len = dom_cycle
    fast_len = max(dom_cycle * r_fast, 2.0)
    sig_len = max(max(dom_cycle * r_sig, 2.0) * sig_mult, 2.0)
    
    def ema(src, length):
        result = np.zeros(len(src))
        alpha = 2.0 / (length + 1.0)
        result[0] = src[0]
        for i in range(1, len(src)):
            result[i] = alpha * src[i] + (1 - alpha) * result[i-1]
        return result
    
    fast_ma = ema(closes, fast_len)
    slow_ma = ema(closes, slow_len)
    macd_raw = fast_ma - slow_ma
    signal_line = ema(macd_raw, sig_len)
    hist_line = macd_raw - signal_line
    
    cross_up = False
    cross_down = False
    if len(macd_raw) >= 2:
        cross_up = macd_raw[-2] <= signal_line[-2] and macd_raw[-1] > signal_line[-1]
        cross_down = macd_raw[-2] >= signal_line[-2] and macd_raw[-1] < signal_line[-1]
    
    return float(macd_raw[-1]), float(signal_line[-1]), float(hist_line[-1]), cross_up, cross_down

def detect_macd_divergence(tf_data, lookback=60, pivot_left=5, pivot_right=5):
    """ตรวจจับ MACD Divergences"""
    if not tf_data or len(tf_data) < lookback:
        return "NONE", 0
    
    highs = np.array([float(candle[2]) for candle in tf_data])
    lows = np.array([float(candle[3]) for candle in tf_data])
    
    pivot_highs = []
    pivot_lows = []
    
    for i in range(pivot_left, len(highs) - pivot_right):
        is_high = True
        for j in range(1, pivot_left + 1):
            if i-j >= 0 and highs[i-j] >= highs[i]:
                is_high = False
                break
        if is_high:
            for j in range(1, pivot_right + 1):
                if i+j < len(highs) and highs[i+j] >= highs[i]:
                    is_high = False
                    break
        if is_high:
            pivot_highs.append((i, highs[i]))
        
        is_low = True
        for j in range(1, pivot_left + 1):
            if i-j >= 0 and lows[i-j] <= lows[i]:
                is_low = False
                break
        if is_low:
            for j in range(1, pivot_right + 1):
                if i+j < len(lows) and lows[i+j] <= lows[i]:
                    is_low = False
                    break
        if is_low:
            pivot_lows.append((i, lows[i]))
    
    if len(pivot_highs) >= 2:
        ph1_idx, price1 = pivot_highs[-2]
        ph2_idx, price2 = pivot_highs[-1]
        
        if price2 > price1 and (ph2_idx - ph1_idx) <= lookback:
            return "BEARISH", 20
    
    if len(pivot_lows) >= 2:
        pl1_idx, price1 = pivot_lows[-2]
        pl2_idx, price2 = pivot_lows[-1]
        
        if price2 < price1 and (pl2_idx - pl1_idx) <= lookback:
            return "BULLISH", 20
    
    return "NONE", 0

def calculate_confluence_score(rsi_value, rsi_os, rsi_ob, regime, macd_cross_up, macd_cross_down, 
                                macd_div, macd_value, rsi_os_entry, rsi_ob_exit):
    """คำนวณ Confluence Score"""
    conf_score = 0.0
    
    if rsi_os_entry:
        conf_score += 15.0 if regime == "CHOP" else 8.0
    if rsi_ob_exit:
        conf_score -= 15.0 if regime == "CHOP" else 8.0
    
    if macd_cross_up:
        conf_score += 12.0 if regime == "TRENDING" else 6.0
    if macd_cross_down:
        conf_score -= 12.0 if regime == "TRENDING" else 6.0
    
    if macd_div == "BULLISH":
        conf_score += 20.0
    elif macd_div == "BEARISH":
        conf_score -= 20.0
    
    if macd_value > 0 and macd_cross_up:
        conf_score += 3.0
    if macd_value < 0 and macd_cross_down:
        conf_score -= 3.0
    
    if regime == "NOISY":
        conf_score *= 0.3
    
    return conf_score

def validate_confluence(direction, htf_bias, current_price, g_ma, regime, conf_score):
    """ตรวจสอบความสอดคล้องของสัญญาณ"""
    penalty = 0
    reasons = []
    
    if direction == "LONG" and htf_bias == "BEARISH":
        penalty -= 20
        reasons.append("❌ HTF BEARISH แต่ LONG")
    elif direction == "SHORT" and htf_bias == "BULLISH":
        penalty -= 20
        reasons.append("❌ HTF BULLISH แต่ SHORT")
    
    if g_ma is not None:
        if direction == "LONG" and current_price < g_ma:
            penalty -= 15
            reasons.append(" LONG แต่ราคาอยู่ใต้ Gaussian")
        elif direction == "SHORT" and current_price > g_ma:
            penalty -= 15
            reasons.append(" SHORT แต่ราคาอยู่เหนือ Gaussian")
    
    if regime == "NOISY":
        penalty -= 20
        reasons.append("⚠️ Regime NOISY")
    elif regime == "QUIET":
        penalty -= 10
        reasons.append("⚠️ Regime QUIET")
    
    if abs(conf_score) < 10:
        penalty -= 10
        reasons.append(f"⚠️ Confluence Score อ่อน ({conf_score:+.1f})")
    
    return penalty, reasons

# ============================================================================
# 🆕 MACRO CONTEXT ANALYSIS - V16.1 ENHANCED
# ============================================================================

def analyze_macro_context(symbol, current_price):
    """วิเคราะห์ภาพใหญ่ Weekly/Monthly เพื่อป้องกันเทรดผิดทาง"""
    try:
        tf_1w = get_klines(symbol, '1w', 52)
        tf_1M = get_klines(symbol, '1M', 24)
        
        if not tf_1w or not tf_1M:
            return None
        
        weekly_highs = [float(c[2]) for c in tf_1w]
        weekly_lows = [float(c[3]) for c in tf_1w]
        weekly_high_52w = max(weekly_highs)
        weekly_low_52w = min(weekly_lows)
        
        monthly_highs = [float(c[2]) for c in tf_1M]
        monthly_lows = [float(c[3]) for c in tf_1M]
        monthly_high_24m = max(monthly_highs)
        monthly_low_24m = min(monthly_lows)
        
        dist_to_weekly_high = (current_price - weekly_high_52w) / weekly_high_52w * 100
        dist_to_weekly_low = (current_price - weekly_low_52w) / weekly_low_52w * 100
        dist_to_monthly_high = (current_price - monthly_high_24m) / monthly_high_24m * 100
        dist_to_monthly_low = (current_price - monthly_low_24m) / monthly_low_24m * 100
        
        weekly_ema_50 = calculate_ema(tf_1w, 50)
        monthly_ema_20 = calculate_ema(tf_1M, 20)
        
        if len(tf_1w) >= 20:
            recent_closes = [float(c[4]) for c in tf_1w[-20:]]
            weekly_trend = "UPTREND" if recent_closes[-1] > recent_closes[0] else "DOWNTREND"
        else:
            weekly_trend = "UNKNOWN"
        
        near_major_support = False
        near_major_resistance = False
        major_level_type = None
        major_level_distance = 0
        
        if abs(dist_to_weekly_low) <= 5:
            near_major_support = True
            major_level_type = "52W_LOW"
            major_level_distance = dist_to_weekly_low
        elif abs(dist_to_monthly_low) <= 5:
            near_major_support = True
            major_level_type = "24M_LOW"
            major_level_distance = dist_to_monthly_low
        elif abs(dist_to_weekly_high) <= 5:
            near_major_resistance = True
            major_level_type = "52W_HIGH"
            major_level_distance = dist_to_weekly_high
        elif abs(dist_to_monthly_high) <= 5:
            near_major_resistance = True
            major_level_type = "24M_HIGH"
            major_level_distance = dist_to_monthly_high
        
        dist_to_weekly_ema = 0
        if weekly_ema_50:
            dist_to_weekly_ema = (current_price - weekly_ema_50) / weekly_ema_50 * 100
            if abs(dist_to_weekly_ema) <= 3 and not near_major_support and not near_major_resistance:
                if current_price > weekly_ema_50:
                    near_major_support = True
                    major_level_type = "W_EMA50"
                    major_level_distance = dist_to_weekly_ema
                else:
                    near_major_resistance = True
                    major_level_type = "W_EMA50"
                    major_level_distance = dist_to_weekly_ema
        
        dist_to_monthly_ema = 0
        if monthly_ema_20:
            dist_to_monthly_ema = (current_price - monthly_ema_20) / monthly_ema_20 * 100
            if abs(dist_to_monthly_ema) <= 3 and not near_major_support and not near_major_resistance:
                if current_price > monthly_ema_20:
                    near_major_support = True
                    major_level_type = "M_EMA20"
                    major_level_distance = dist_to_monthly_ema
                else:
                    near_major_resistance = True
                    major_level_type = "M_EMA20"
                    major_level_distance = dist_to_monthly_ema
        
        return {
            'weekly_high_52w': weekly_high_52w,
            'weekly_low_52w': weekly_low_52w,
            'monthly_high_24m': monthly_high_24m,
            'monthly_low_24m': monthly_low_24m,
            'weekly_ema_50': weekly_ema_50,
            'monthly_ema_20': monthly_ema_20,
            'weekly_trend': weekly_trend,
            'dist_to_weekly_high': round(dist_to_weekly_high, 2),
            'dist_to_weekly_low': round(dist_to_weekly_low, 2),
            'dist_to_monthly_high': round(dist_to_monthly_high, 2),
            'dist_to_monthly_low': round(dist_to_monthly_low, 2),
            'dist_to_weekly_ema': round(dist_to_weekly_ema, 2),
            'dist_to_monthly_ema': round(dist_to_monthly_ema, 2),
            'near_major_support': near_major_support,
            'near_major_resistance': near_major_resistance,
            'major_level_type': major_level_type,
            'major_level_distance': round(major_level_distance, 2)
        }
    except Exception as e:
        print(f"❌ Macro analysis error: {e}")
        return None


def apply_macro_filter(direction, macro_data, current_score, validation_reasons, current_price):
    """ใช้ Macro Context กรองสัญญาณ"""
    if not macro_data:
        return current_score, direction, validation_reasons
    
    new_score = current_score
    new_direction = direction
    new_reasons = validation_reasons.copy() if validation_reasons else []
    
    if macro_data['near_major_support'] and direction == "SHORT":
        new_score -= 40
        new_direction = "NONE"
        new_reasons.append(
            f"🚫 BLOCKED: SHORT at {macro_data['major_level_type']} "
            f"(Distance: {macro_data['major_level_distance']:+.2f}%) - "
            f"ราคาอยู่ใกล้แนวรับใหญ่ ห้าม SHORT!"
        )
    elif macro_data['near_major_resistance'] and direction == "LONG":
        new_score -= 40
        new_direction = "NONE"
        new_reasons.append(
            f"🚫 BLOCKED: LONG at {macro_data['major_level_type']} "
            f"(Distance: {macro_data['major_level_distance']:+.2f}%) - "
            f"ราคาอยู่ใกล้แนวต้านใหญ่ ห้าม LONG!"
        )
    elif macro_data['near_major_support'] and direction == "LONG":
        new_score += 15
        new_reasons.append(
            f"✅ BONUS: LONG at {macro_data['major_level_type']} - "
            f"เทรดตามแนวรับใหญ่ +15"
        )
    elif macro_data['near_major_resistance'] and direction == "SHORT":
        new_score += 15
        new_reasons.append(
            f"✅ BONUS: SHORT at {macro_data['major_level_type']} - "
            f"เทรดตามแนวต้านใหญ่ +15"
        )
    
    if macro_data['weekly_trend'] == "UPTREND" and direction == "LONG":
        new_score += 5
    elif macro_data['weekly_trend'] == "DOWNTREND" and direction == "SHORT":
        new_score += 5
    elif macro_data['weekly_trend'] == "UPTREND" and direction == "SHORT":
        new_score -= 10
        new_reasons.append(f"⚠️ CONTRA: SHORT ใน Weekly UPTREND -10")
    elif macro_data['weekly_trend'] == "DOWNTREND" and direction == "LONG":
        new_score -= 10
        new_reasons.append(f"⚠️ CONTRA: LONG ใน Weekly DOWNTREND -10")
    
    if macro_data.get('weekly_ema_50') and current_price:
        if current_price < macro_data['weekly_ema_50'] and direction == "LONG":
            new_score -= 8
            new_reasons.append(f"⚠️ CONTRA: LONG ต่ำกว่า Weekly EMA 50 -8")
        elif current_price > macro_data['weekly_ema_50'] and direction == "SHORT":
            new_score -= 8
            new_reasons.append(f"⚠️ CONTRA: SHORT สูงกว่า Weekly EMA 50 -8")
    
    return new_score, new_direction, new_reasons


def scan_coins_v16():
    """สแกนเหรียญ V16.1 + Macro Filter"""
    try:
        with open('coins.txt', 'r') as f:
            symbols = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []
    
    setups = []
    total_coins = len(symbols)
    
    for i, symbol in enumerate(symbols, 1):
        try:
            is_xau = 'XAU' in symbol or 'GOLD' in symbol
            
            tf_4h = get_klines(symbol, '4h', 100)
            tf_1h = get_klines(symbol, '1h', 100)
            tf_15m = get_klines(symbol, '15m', 350)
            
            if not all([tf_4h, tf_1h, tf_15m]):
                continue
            
            current_price = float(tf_15m[-1][4])
            
            htf_bias, htf_score = get_htf_bias(tf_4h, tf_1h)
            sweep_data = detect_liquidity_sweep(tf_15m, is_xau)
            
            if not sweep_data or not sweep_data['v6_valid']:
                continue
            
            volume_ratio = calculate_volume_ratio(tf_15m)
            sd_supply, sd_demand = detect_sd_zones(tf_15m)
            signal_priority = calculate_signal_priority(
                sweep_data, volume_ratio, htf_bias, sd_supply, sd_demand
            )
            
            direction = "NONE"
            if sweep_data['is_sweep_low']:
                direction = "LONG"
            elif sweep_data['is_sweep_high']:
                direction = "SHORT"
            
            highs_arr = np.array([float(c[2]) for c in tf_15m])
            lows_arr = np.array([float(c[3]) for c in tf_15m])
            dom_cycle = calculate_dominant_cycle(highs_arr, lows_arr)
            
            rsi_value, regime, rsi_p, rsi_s, rsi_os, rsi_ob, rsi_score = calculate_adaptive_rsi(tf_15m)
            
            macd_value, signal_value, hist_value, macd_cross_up, macd_cross_down = calculate_adaptive_macd(
                tf_15m, dom_cycle
            )
            
            macd_div, div_score = detect_macd_divergence(tf_15m)
            
            rsi_os_entry = False
            rsi_ob_exit = False
            if rsi_value is not None:
                rsi_os_entry = rsi_value < rsi_os
                rsi_ob_exit = rsi_value > rsi_ob
            
            conf_score = calculate_confluence_score(
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
            
            if sweep_data['sweep_detected']:
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
            
            g_ma = calculate_ema(tf_1h, 50)
            
            penalty, validation_reasons = validate_confluence(
                direction, htf_bias, current_price, g_ma, regime, conf_score
            )
            
            total_score += penalty
            breakdown['Validation'] = f"{penalty:+.0f} ({len(validation_reasons)} issues)"
            
            # 🆕 MACRO CONTEXT FILTER
            macro_data = analyze_macro_context(symbol, current_price)
            
            if macro_data:
                total_score, direction, validation_reasons = apply_macro_filter(
                    direction, macro_data, total_score, validation_reasons, current_price
                )
                breakdown['Macro_Filter'] = f"Applied ({macro_data['major_level_type'] or 'None'})"
            else:
                macro_data = {
                    'weekly_high_52w': 0, 'weekly_low_52w': 0, 'monthly_high_24m': 0, 'monthly_low_24m': 0,
                    'weekly_ema_50': None, 'monthly_ema_20': None, 'weekly_trend': 'UNKNOWN',
                    'dist_to_weekly_high': 0, 'dist_to_weekly_low': 0, 'dist_to_monthly_high': 0, 'dist_to_monthly_low': 0,
                    'dist_to_weekly_ema': 0, 'dist_to_monthly_ema': 0, 'near_major_support': False,
                    'near_major_resistance': False, 'major_level_type': None, 'major_level_distance': 0
                }
                breakdown['Macro_Filter'] = "No Data"
            
            if total_score >= 50 and signal_priority >= 3:
                setups.append({
                    'symbol': symbol,
                    'price': current_price,
                    'score': round(total_score, 1),
                    'direction': direction,
                    'distance': sweep_data['min_distance'],
                    'volume_ratio': volume_ratio,
                    'htf_bias': htf_bias,
                    'signal_priority': signal_priority,
                    'pdh': sweep_data['pdh'],
                    'pdl': sweep_data['pdl'],
                    'sweep_low': sweep_data['is_sweep_low'],
                    'sweep_high': sweep_data['is_sweep_high'],
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
                })
        
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
            continue
    
    setups.sort(key=lambda x: (x['score'], x['signal_priority']), reverse=True)
    return setups

def generate_prompt(setup):
    """สร้าง Prompt สำหรับ AI"""
    direction_text = "LONG 🟢" if setup['direction'] == "LONG" else "SHORT 🔴"
    supply_level = f"{setup['sd_supply']['level']:.2f}" if setup['sd_supply'] else 'N/A'
    demand_level = f"{setup['sd_demand']['level']:.2f}" if setup['sd_demand'] else 'N/A'
    
    validation_section = ""
    if setup['validation_reasons']:
        validation_section = "\n⚠️ WARNING - CONFLICTS DETECTED:\n"
        for r in setup['validation_reasons']:
            validation_section += f"- {r}\n"
        validation_section += "\n"
    
    prompt = f"""{setup['symbol']} - V16.1 EXTREME PATIENCE REVERSAL SETUP

Current Price: {setup['price']}
Direction: {direction_text}
Score: {setup['score']}/100
Signal Priority: {setup['signal_priority']}/5
Leverage: 75x
Portfolio: $1000
Risk per trade: 1% ($10)

🔍 PAN SNIPER V14.0 DATA:
- HTF Bias: {setup['htf_bias']}
- PDH: {setup['pdh']}
- PDL: {setup['pdl']}
- Distance: {setup['distance']:.2f}%
- Sweep: {'Low (Bullish)' if setup['sweep_low'] else 'High (Bearish)' if setup['sweep_high'] else 'None'}
- SD Supply: {supply_level}
- SD Demand: {demand_level}

📊 AMC DATA:
- Regime: {setup['regime']}
- RSI: {setup['rsi_value']:.1f} (Period: {setup['rsi_p']}, Smooth: {setup['rsi_s']})
- OS/OB: {setup['rsi_os']}/{setup['rsi_ob']}
- Dominant Cycle: {setup['dom_cycle']:.1f} bars
- MACD: {setup['macd_value']:.4f}
- Signal: {setup['signal_value']:.4f}
- Histogram: {setup['hist_value']:.4f}
- Cross: {'Bullish' if setup['macd_cross_up'] else 'Bearish' if setup['macd_cross_down'] else 'None'}
- Divergence: {setup['macd_div']}
- Confluence Score: {setup['conf_score']:+.1f}

🎯 VALIDATION:
- Gaussian MA (1H EMA 50): {setup['g_ma']:.4f}
- Price vs Gaussian: {'Above' if setup['g_ma'] and setup['price'] > setup['g_ma'] else 'Below'}
- Penalty Score: {setup['penalty']:+.0f}
{validation_section}
📊 TRADINGVIEW CONFIRMATION NEEDED:
- Pan Sniper V14.0: [BUY/SELL]
- AMC Indicator: [Regime/Confluence]
- Gaussian Filter: [BULL/BEAR]
- Waterfall: [COLD/HOT]
- CDV: [RISING/FALLING]

💡 REQUIRED OUTPUT:
Entry (within 0.3% of current price)
SL (max 1% from Entry)
TP1 (1-2% from Entry)
TP2 (2-3% from Entry)
Risk:Reward ratio
Position Size
Confidence: [HIGH/MEDIUM/LOW]"""
    
    return prompt
# ============================================================================
# 🆕 MACRO CONTEXT ANALYSIS - V16.1 ENHANCED
# ============================================================================

def analyze_macro_context(symbol, current_price):
    """วิเคราะห์ภาพใหญ่ Weekly/Monthly เพื่อป้องกันเทรดผิดทาง"""
    try:
        tf_1w = get_klines(symbol, '1w', 52)
        tf_1M = get_klines(symbol, '1M', 24)
        
        if not tf_1w or not tf_1M:
            return None
        
        weekly_highs = [float(c[2]) for c in tf_1w]
        weekly_lows = [float(c[3]) for c in tf_1w]
        weekly_high_52w = max(weekly_highs)
        weekly_low_52w = min(weekly_lows)
        
        monthly_highs = [float(c[2]) for c in tf_1M]
        monthly_lows = [float(c[3]) for c in tf_1M]
        monthly_high_24m = max(monthly_highs)
        monthly_low_24m = min(monthly_lows)
        
        dist_to_weekly_high = (current_price - weekly_high_52w) / weekly_high_52w * 100
        dist_to_weekly_low = (current_price - weekly_low_52w) / weekly_low_52w * 100
        dist_to_monthly_high = (current_price - monthly_high_24m) / monthly_high_24m * 100
        dist_to_monthly_low = (current_price - monthly_low_24m) / monthly_low_24m * 100
        
        weekly_ema_50 = calculate_ema(tf_1w, 50)
        monthly_ema_20 = calculate_ema(tf_1M, 20)
        
        if len(tf_1w) >= 20:
            recent_closes = [float(c[4]) for c in tf_1w[-20:]]
            weekly_trend = "UPTREND" if recent_closes[-1] > recent_closes[0] else "DOWNTREND"
        else:
            weekly_trend = "UNKNOWN"
        
        near_major_support = False
        near_major_resistance = False
        major_level_type = None
        major_level_distance = 0
        
        if abs(dist_to_weekly_low) <= 5:
            near_major_support = True
            major_level_type = "52W_LOW"
            major_level_distance = dist_to_weekly_low
        elif abs(dist_to_monthly_low) <= 5:
            near_major_support = True
            major_level_type = "24M_LOW"
            major_level_distance = dist_to_monthly_low
        elif abs(dist_to_weekly_high) <= 5:
            near_major_resistance = True
            major_level_type = "52W_HIGH"
            major_level_distance = dist_to_weekly_high
        elif abs(dist_to_monthly_high) <= 5:
            near_major_resistance = True
            major_level_type = "24M_HIGH"
            major_level_distance = dist_to_monthly_high
        
        dist_to_weekly_ema = 0
        if weekly_ema_50:
            dist_to_weekly_ema = (current_price - weekly_ema_50) / weekly_ema_50 * 100
            if abs(dist_to_weekly_ema) <= 3 and not near_major_support and not near_major_resistance:
                if current_price > weekly_ema_50:
                    near_major_support = True
                    major_level_type = "W_EMA50"
                    major_level_distance = dist_to_weekly_ema
                else:
                    near_major_resistance = True
                    major_level_type = "W_EMA50"
                    major_level_distance = dist_to_weekly_ema
        
        dist_to_monthly_ema = 0
        if monthly_ema_20:
            dist_to_monthly_ema = (current_price - monthly_ema_20) / monthly_ema_20 * 100
            if abs(dist_to_monthly_ema) <= 3 and not near_major_support and not near_major_resistance:
                if current_price > monthly_ema_20:
                    near_major_support = True
                    major_level_type = "M_EMA20"
                    major_level_distance = dist_to_monthly_ema
                else:
                    near_major_resistance = True
                    major_level_type = "M_EMA20"
                    major_level_distance = dist_to_monthly_ema
        
        return {
            'weekly_high_52w': weekly_high_52w,
            'weekly_low_52w': weekly_low_52w,
            'monthly_high_24m': monthly_high_24m,
            'monthly_low_24m': monthly_low_24m,
            'weekly_ema_50': weekly_ema_50,
            'monthly_ema_20': monthly_ema_20,
            'weekly_trend': weekly_trend,
            'dist_to_weekly_high': round(dist_to_weekly_high, 2),
            'dist_to_weekly_low': round(dist_to_weekly_low, 2),
            'dist_to_monthly_high': round(dist_to_monthly_high, 2),
            'dist_to_monthly_low': round(dist_to_monthly_low, 2),
            'dist_to_weekly_ema': round(dist_to_weekly_ema, 2),
            'dist_to_monthly_ema': round(dist_to_monthly_ema, 2),
            'near_major_support': near_major_support,
            'near_major_resistance': near_major_resistance,
            'major_level_type': major_level_type,
            'major_level_distance': round(major_level_distance, 2)
        }
    except Exception as e:
        print(f"❌ Macro analysis error: {e}")
        return None


def apply_macro_filter(direction, macro_data, current_score, validation_reasons, current_price):
    """ใช้ Macro Context กรองสัญญาณ"""
    if not macro_data:
        return current_score, direction, validation_reasons
    
    new_score = current_score
    new_direction = direction
    new_reasons = validation_reasons.copy() if validation_reasons else []
    
    if macro_data['near_major_support'] and direction == "SHORT":
        new_score -= 40
        new_direction = "NONE"
        new_reasons.append(
            f"🚫 BLOCKED: SHORT at {macro_data['major_level_type']} "
            f"(Distance: {macro_data['major_level_distance']:+.2f}%) - "
            f"ราคาอยู่ใกล้แนวรับใหญ่ ห้าม SHORT!"
        )
    elif macro_data['near_major_resistance'] and direction == "LONG":
        new_score -= 40
        new_direction = "NONE"
        new_reasons.append(
            f"🚫 BLOCKED: LONG at {macro_data['major_level_type']} "
            f"(Distance: {macro_data['major_level_distance']:+.2f}%) - "
            f"ราคาอยู่ใกล้แนวต้านใหญ่ ห้าม LONG!"
        )
    elif macro_data['near_major_support'] and direction == "LONG":
        new_score += 15
        new_reasons.append(
            f"✅ BONUS: LONG at {macro_data['major_level_type']} - "
            f"เทรดตามแนวรับใหญ่ +15"
        )
    elif macro_data['near_major_resistance'] and direction == "SHORT":
        new_score += 15
        new_reasons.append(
            f"✅ BONUS: SHORT at {macro_data['major_level_type']} - "
            f"เทรดตามแนวต้านใหญ่ +15"
        )
    
    if macro_data['weekly_trend'] == "UPTREND" and direction == "LONG":
        new_score += 5
    elif macro_data['weekly_trend'] == "DOWNTREND" and direction == "SHORT":
        new_score += 5
    elif macro_data['weekly_trend'] == "UPTREND" and direction == "SHORT":
        new_score -= 10
        new_reasons.append(f"⚠️ CONTRA: SHORT ใน Weekly UPTREND -10")
    elif macro_data['weekly_trend'] == "DOWNTREND" and direction == "LONG":
        new_score -= 10
        new_reasons.append(f"⚠️ CONTRA: LONG ใน Weekly DOWNTREND -10")
    
    if macro_data.get('weekly_ema_50') and current_price:
        if current_price < macro_data['weekly_ema_50'] and direction == "LONG":
            new_score -= 8
            new_reasons.append(f"⚠️ CONTRA: LONG ต่ำกว่า Weekly EMA 50 -8")
        elif current_price > macro_data['weekly_ema_50'] and direction == "SHORT":
            new_score -= 8
            new_reasons.append(f"⚠️ CONTRA: SHORT สูงกว่า Weekly EMA 50 -8")
    
    return new_score, new_direction, new_reasons


def scan_coins_v16():
    """สแกนเหรียญ V16.1 + Macro Filter"""
    try:
        with open('coins.txt', 'r') as f:
            symbols = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []
    
    setups = []
    total_coins = len(symbols)
    
    for i, symbol in enumerate(symbols, 1):
        try:
            is_xau = 'XAU' in symbol or 'GOLD' in symbol
            
            tf_4h = get_klines(symbol, '4h', 100)
            tf_1h = get_klines(symbol, '1h', 100)
            tf_15m = get_klines(symbol, '15m', 350)
            
            if not all([tf_4h, tf_1h, tf_15m]):
                continue
            
            current_price = float(tf_15m[-1][4])
            
            htf_bias, htf_score = get_htf_bias(tf_4h, tf_1h)
            sweep_data = detect_liquidity_sweep(tf_15m, is_xau)
            
            if not sweep_data or not sweep_data['v6_valid']:
                continue
            
            volume_ratio = calculate_volume_ratio(tf_15m)
            sd_supply, sd_demand = detect_sd_zones(tf_15m)
            signal_priority = calculate_signal_priority(
                sweep_data, volume_ratio, htf_bias, sd_supply, sd_demand
            )
            
            direction = "NONE"
            if sweep_data['is_sweep_low']:
                direction = "LONG"
            elif sweep_data['is_sweep_high']:
                direction = "SHORT"
            
            highs_arr = np.array([float(c[2]) for c in tf_15m])
            lows_arr = np.array([float(c[3]) for c in tf_15m])
            dom_cycle = calculate_dominant_cycle(highs_arr, lows_arr)
            
            rsi_value, regime, rsi_p, rsi_s, rsi_os, rsi_ob, rsi_score = calculate_adaptive_rsi(tf_15m)
            
            macd_value, signal_value, hist_value, macd_cross_up, macd_cross_down = calculate_adaptive_macd(
                tf_15m, dom_cycle
            )
            
            macd_div, div_score = detect_macd_divergence(tf_15m)
            
            rsi_os_entry = False
            rsi_ob_exit = False
            if rsi_value is not None:
                rsi_os_entry = rsi_value < rsi_os
                rsi_ob_exit = rsi_value > rsi_ob
            
            conf_score = calculate_confluence_score(
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
            
            if sweep_data['sweep_detected']:
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
            
            g_ma = calculate_ema(tf_1h, 50)
            
            penalty, validation_reasons = validate_confluence(
                direction, htf_bias, current_price, g_ma, regime, conf_score
            )
            
            total_score += penalty
            breakdown['Validation'] = f"{penalty:+.0f} ({len(validation_reasons)} issues)"
            
            # 🆕 MACRO CONTEXT FILTER
            macro_data = analyze_macro_context(symbol, current_price)
            
            if macro_data:
                total_score, direction, validation_reasons = apply_macro_filter(
                    direction, macro_data, total_score, validation_reasons, current_price
                )
                breakdown['Macro_Filter'] = f"Applied ({macro_data['major_level_type'] or 'None'})"
            else:
                macro_data = {
                    'weekly_high_52w': 0, 'weekly_low_52w': 0, 'monthly_high_24m': 0, 'monthly_low_24m': 0,
                    'weekly_ema_50': None, 'monthly_ema_20': None, 'weekly_trend': 'UNKNOWN',
                    'dist_to_weekly_high': 0, 'dist_to_weekly_low': 0, 'dist_to_monthly_high': 0, 'dist_to_monthly_low': 0,
                    'dist_to_weekly_ema': 0, 'dist_to_monthly_ema': 0, 'near_major_support': False,
                    'near_major_resistance': False, 'major_level_type': None, 'major_level_distance': 0
                }
                breakdown['Macro_Filter'] = "No Data"
            
            if total_score >= 50 and signal_priority >= 3:
                setups.append({
                    'symbol': symbol,
                    'price': current_price,
                    'score': round(total_score, 1),
                    'direction': direction,
                    'distance': sweep_data['min_distance'],
                    'volume_ratio': volume_ratio,
                    'htf_bias': htf_bias,
                    'signal_priority': signal_priority,
                    'pdh': sweep_data['pdh'],
                    'pdl': sweep_data['pdl'],
                    'sweep_low': sweep_data['is_sweep_low'],
                    'sweep_high': sweep_data['is_sweep_high'],
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
                })
        
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
            continue
    
    setups.sort(key=lambda x: (x['score'], x['signal_priority']), reverse=True)
    return setups
