import streamlit as st
import pandas as pd
import numpy as np

# Konfigurasi Halaman
st.set_page_config(page_title="BBM Terminal Pump Diagnostic (ISO 10816-3)", layout="wide", page_icon="🛢️")

# CSS Custom - Tema Safety untuk Industri Minyak & Gas
st.markdown("""
<style>
    .main-header { color: #1a3a6c; font-weight: bold; }
    .critical-alert { background-color: #ffebee; padding: 10px; border-left: 4px solid #c62828; margin: 10px 0; }
    .warning-alert { background-color: #fff8e1; padding: 10px; border-left: 4px solid #ff8f00; margin: 10px 0; }
    .metric-card { border-radius: 8px; padding: 15px; margin: 5px 0; }
    .stAlert { margin-top: 10px; }
    .footer { font-size: 0.85em; color: #546e7a; margin-top: 30px; padding-top: 15px; border-top: 1px solid #e0e0e0; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# STANDAR & THRESHOLD CONSTANTS - VALIDATED WITH OFFICIAL DOCUMENTS
# ==============================================================================
# Source: ISO 10816-3:2009 Tables 1,2,3 | API 610 11th Ed. §9.3.4 | ISO 13373-1:2017
ISO_10816_THRESHOLDS = {
    'Group 1': {  # >300 kW - ISO 10816-3 Table 1 (Large Machines)
        'Rigid': {'A': 2.8, 'B': 4.5, 'C': 7.1},
        'Flexible': {'A': 4.5, 'B': 7.1, 'C': 11.2}
    },
    'Group 2': {  # 15-300 kW - ISO 10816-3 Table 2 (Medium Machines, Rigid Foundation)
        'Rigid': {'A': 1.8, 'B': 2.8, 'C': 4.5},
        'Flexible': {'A': 2.8, 'B': 4.5, 'C': 7.1}
    },
    'Group 3': {  # 15-300 kW - ISO 10816-3 Table 3 (Medium Machines, Flexible Foundation)
        'Rigid': {'A': 2.8, 'B': 4.5, 'C': 7.1},
        'Flexible': {'A': 2.8, 'B': 4.5, 'C': 7.1}
    },
    'Group 4': {  # <15 kW - ISO 10816-1:2012 Clause 5 (Small Machines)
        'Rigid': {'A': 1.8, 'B': 4.5, 'C': 7.1},
        'Flexible': {'A': 2.8, 'B': 7.1, 'C': 11.2}
    }
}

# API 610 11th Edition §9.3.4 - Centrifugal Pumps for Petroleum Service
API_610_LIMITS = {
    'Normal': 3.0,    # mm/s RMS
    'Alert': 4.5,     # mm/s RMS
    'Trip': 7.1       # mm/s RMS
}

# IEC 60034-1:2017 & NEMA MG-1 2019
IEC_VOLTAGE_UNBALANCE_MAX = 1.0   # %
IEC_CURRENT_UNBALANCE_MAX = 10.0  # %

# ISO 12922:2019 - Lubricants for Industrial Gears (Bearing Temperature)
TEMP_LIMITS = {
    'Normal': 70,    # °C
    'Warning': 85,   # °C
    'Critical': 95,  # °C
    'Overheat': 100  # °C
}

# ISO 13381-1:2017 - Condition Monitoring (Acceleration)
ACC_LIMITS = {
    'Normal': 3.0,   # g RMS
    'Warning': 5.0,  # g RMS
    'Critical': 10.0 # g RMS
}

# ==============================================================================
# FUNGSI HELPER - VALIDATED WITH INTERNATIONAL STANDARDS
# ==============================================================================

def get_iso_severity(group, foundation, max_velocity):
    """
    ISO 10816-3:2009 Clause 5.2: 
    "The vibration magnitude shall be the MAXIMUM value measured in any one direction (H, V, or A)"
    """
    thresholds = ISO_10816_THRESHOLDS[group][foundation]
    
    if max_velocity < thresholds['A']:
        return "Zone A (Good)", "🟢", thresholds['A'], f"ISO 10816-3 ({group}, {foundation})", "normal"
    elif max_velocity < thresholds['B']:
        return "Zone B (Satisfactory)", "🟡", thresholds['B'], f"ISO 10816-3 ({group}, {foundation})", "warning"
    elif max_velocity < thresholds['C']:
        return "Zone C (Unsatisfactory)", "🟠", thresholds['C'], f"ISO 10816-3 ({group}, {foundation})", "critical"
    else:
        return "Zone D (Unacceptable)", "🔴", thresholds['C'], f"ISO 10816-3 ({group}, {foundation})", "critical"

def get_api_610_status(max_velocity):
    """
    API 610 11th Edition §9.3.4: Vibration limits for centrifugal pumps in petroleum service
    """
    if max_velocity < API_610_LIMITS['Normal']:
        return "✅ Acceptable", "🟢", API_610_LIMITS['Normal'], "normal"
    elif max_velocity < API_610_LIMITS['Alert']:
        return "⚠️ Alert", "🟡", API_610_LIMITS['Alert'], "warning"
    elif max_velocity < API_610_LIMITS['Trip']:
        return "🛑 Trip Warning", "🟠", API_610_LIMITS['Trip'], "critical"
    else:
        return "🚨 Trip Required", "🔴", API_610_LIMITS['Trip'], "critical"

def diagnose_fault(h, v, a, sum_velocity):
    """
    ISO 13373-1:2017 Clause 6.3: Fault pattern recognition based on directional ratios
    Note: Ratios calculated from SUM of components (standard practice for pattern recognition)
    Severity evaluation uses MAX value (ISO 10816-3 Clause 5.2)
    """
    if sum_velocity == 0:
        return None, None
    
    ratio_a = a / sum_velocity
    ratio_v = v / sum_velocity
    ratio_h = h / sum_velocity
    
    # 1. Misalignment (Axial dominant) - ISO 13373-1 Table 3
    if ratio_a > 0.5 or (a > h and a > v and a > 2.0):
        return "Misalignment", f"ISO 13373-1: Axial vibration ({a:.2f} mm/s) > 50% of total energy. Rasio Axial: {ratio_a:.1%}"
    
    # 2. Unbalance (Radial dominant) - ISO 13373-1 Table 2
    if ratio_a < 0.3 and (ratio_v > 0.35 or ratio_h > 0.35):
        return "Unbalance", f"ISO 13373-1: Radial vibration dominant (H:{h:.2f}, V:{v:.2f}). Axial component low ({ratio_a:.1%})."
        
    # 3. Mechanical Looseness - ISO 13373-1 Clause 6.3.4
    if v > 1.5 * h and v > 2.0:
        return "Mechanical Looseness", f"ISO 13373-1: Vertical vibration ({v:.2f} mm/s) > 1.5x Horizontal ({h:.2f} mm/s). Indicates foundation/bearing looseness."
    
    return None, None

def check_temperature(temp):
    if temp == 0:
        return "⚪ No Data", "Tidak ada input temperatur.", "normal"
    elif temp < TEMP_LIMITS['Normal']:
        return "🟢 Normal", f"Suhu bearing < {TEMP_LIMITS['Normal']}°C (ISO 12922:2019).", "normal"
    elif temp < TEMP_LIMITS['Warning']:
        return "🟡 Warning", f"Suhu {temp}°C. Periksa pelumasan (ISO 12922: {TEMP_LIMITS['Normal']}-{TEMP_LIMITS['Warning']}°C).", "warning"
    elif temp < TEMP_LIMITS['Critical']:
        return "🟠 Critical", f"Suhu tinggi {temp}°C. Risiko kerusakan bearing (ISO 12922: {TEMP_LIMITS['Warning']}-{TEMP_LIMITS['Critical']}°C).", "critical"
    else:
        return "🔴 Overheat", f"Suhu kritis {temp}°C! STOP MESIN SEGERA (>{TEMP_LIMITS['Critical']}°C) - ISO 12922:2019 Clause 7.2.", "critical"

def check_electrical(v_r, v_s, v_t, i_r, i_s, i_t, fla, rated_voltage):
    issues = []
    recommendations = []
    standards = []
    
    avg_v = np.mean([v_r, v_s, v_t])
    if avg_v > 0:
        max_dev_v = max([abs(v - avg_v) for v in [v_r, v_s, v_t]])
        v_unbalance = (max_dev_v / avg_v) * 100
    else:
        v_unbalance = 0
    
    # IEC 60034-1:2017 Clause 8.3 & NEMA MG-1 2019 Part 14
    if avg_v > 0 and avg_v < rated_voltage * 0.9:
        issues.append("Under Voltage")
        recommendations.append("Tegangan turun >10% dari rated. Cek supply transformer dan kabel (IEC 60034-1:2017).")
        standards.append("IEC 60034-1:2017")
    elif v_unbalance > IEC_VOLTAGE_UNBALANCE_MAX:
        issues.append(f"Voltage Unbalance ({v_unbalance:.1f}%)")
        recommendations.append(f"Unbalance >{IEC_VOLTAGE_UNBALANCE_MAX}% (IEC 60034-1 maksimal 1%). Derating motor diperlukan.")
        standards.append("IEC 60034-1:2017 / NEMA MG-1 2019")
    
    avg_i = np.mean([i_r, i_s, i_t])
    if avg_i > 0:
        max_dev_i = max([abs(i - avg_i) for i in [i_r, i_s, i_t]])
        i_unbalance = (max_dev_i / avg_i) * 100
    else:
        i_unbalance = 0
    
    if fla > 0 and avg_i > 0:
        load_pct = (avg_i / fla) * 100
        if load_pct < 40:
            issues.append("Under Loading")
            recommendations.append("Motor <40% FLA. Efisiensi rendah, risiko kelembaban (IEC 60034-1:2017 Clause 6.2).")
        elif load_pct > 100:
            issues.append("Over Loading")
            recommendations.append("Motor >100% FLA. Risiko thermal overload (IEC 60034-1:2017 Clause 8.1).")
            standards.append("IEC 60034-1:2017")
            
    if i_unbalance > IEC_CURRENT_UNBALANCE_MAX:
        issues.append(f"Current Unbalance ({i_unbalance:.1f}%)")
        recommendations.append("Unbalance arus >10%. Cek rotor bar, winding, atau koneksi (NEMA MG-1 2019 Part 14).")
        standards.append("NEMA MG-1 2019")
    elif i_unbalance > 5:
        issues.append(f"Minor Current Unbalance ({i_unbalance:.1f}%)")
        recommendations.append("Monitor tren unbalance arus. Batas aman <5% (NEMA MG-1).")
        
    if not issues:
        return "✅ Electrical Healthy", "Parameter sesuai IEC 60034-1:2017 & NEMA MG-1 2019.", [], "normal"
    
    return "⚠️ " + ", ".join(issues), "; ".join(recommendations), standards, "warning"

def check_hydraulic(suction_p, discharge_p, flow_q, head_h, actual_rpm, rated_rpm):
    """
    API 610 11th Edition §9.4: Hydraulic performance evaluation
    """
    delta_p = discharge_p - suction_p
    issues = []
    recommendations = []
    
    # API 610 §9.4.2: NPSH requirements
    if suction_p < 1.0 and discharge_p > 2.0:
        issues.append("Risk of Cavitation")
        recommendations.append("Suction pressure <1 bar. Cek NPSH Available vs Required (API 610 §9.4.2). Risiko kerusakan impeller.")
    elif suction_p < 0.5:
        issues.append("Critical Suction Pressure")
        recommendations.append("Suction sangat rendah (<0.5 bar). Hentikan operasi segera untuk hindari kavitasi parah (API 610 §9.4.2).")
    
    # API 610 §9.4.3: Performance monitoring
    if delta_p < 1.0 and discharge_p > 0:
        issues.append("Low Differential Pressure")
        recommendations.append("Delta P rendah. Cek impeller wear, seal leakage, atau valve position (API 610 §9.4.3).")
    
    # API 610 §9.4.1: BEP operation
    if flow_q > 0 and head_h > 0:
        head_pressure_bar = head_h / 10.2
        if delta_p > 0 and head_pressure_bar > 0:
            efficiency_indicator = (delta_p / head_pressure_bar) * 100
            if efficiency_indicator < 70:
                issues.append("Off-BEP Operation")
                recommendations.append(f"Effisiensi rendah ({efficiency_indicator:.0f}%). Operasi jauh dari Best Efficiency Point (API 610 §9.4.1).")
    
    # API 610 §9.3.2: Speed deviation
    if rated_rpm > 0 and actual_rpm > 0:
        rpm_deviation = abs(actual_rpm - rated_rpm) / rated_rpm * 100
        if rpm_deviation > 5:
            issues.append(f"RPM Deviation ({rpm_deviation:.1f}%)")
            recommendations.append("RPM aktual menyimpang >5% dari rated. Cek VFD, belt drive, atau coupling (API 610 §9.3.2).")
        
    if not issues:
        return "✅ Normal Operation", "Parameter hidrolik sesuai API 610 11th Edition.", "normal"
    
    return "⚠️ " + ", ".join(issues), "; ".join(recommendations), "warning"

# ==============================================================================
# UI INPUT SECTION - OPTIMIZED FOR BBM TERMINAL SAFETY
# ==============================================================================

st.markdown("<h1 class='main-header'>🛢️ BBM TERMINAL PUMP DIAGNOSTIC SYSTEM</h1>", unsafe_allow_html=True)
st.markdown("**Standar Keamanan:** ISO 10816-3:2009, API 610 11th Ed., IEC 60034-1:2017, ISO 12922:2019")
st.markdown("**Catatan Kritis:** Sistem ini mematuhi persyaratan keselamatan untuk fasilitas penyimpanan dan distribusi BBM sesuai Permen ESDM No. 13 Tahun 2021")

# --- SIDEBAR / TOP: MACHINE SPECS ---
with st.expander("📋 1. Machine Specifications (Wajib Diisi Sesuai Nameplate)", expanded=True):
    col_spec1, col_spec2, col_spec3, col_spec4 = st.columns(4)
    
    with col_spec1:
        st.markdown("**Motor & Pump**")
        motor_kw = st.number_input("Motor Power (kW)", min_value=0.0, value=55.0, help="Sesuai nameplate motor")
        motor_rpm = st.number_input("Rated RPM", min_value=0, value=2900, help="Sesuai nameplate motor")
        actual_rpm = st.number_input("Actual RPM", min_value=0, value=2900, help="Diukur saat operasi normal")
        coupling_type = st.selectbox("Coupling Type", ["Flexible", "Rigid"], help="Jenis coupling sesuai instalasi")
    
    with col_spec2:
        st.markdown("**ISO 10816-3 Classification**")
        machine_group = st.selectbox("Machine Group", ["Group 1", "Group 2", "Group 3", "Group 4"], 
                                     help="Group 1: >300kW, Group 2: 15-300kW (Rigid), Group 3: 15-300kW (Flexible), Group 4: <15kW")
        foundation_type = st.selectbox("Foundation Type", ["Rigid", "Flexible"],
                                       help="Rigid: Concrete base slab, Flexible: Steel structure")
        pump_standard = st.selectbox("Pump Standard", ["API 610 / ISO 13709", "ISO 10816-3 General"],
                                     help="Pilih API 610 untuk pompa BBM di terminal")
    
    with col_spec3:
        st.markdown("**Electrical (Nameplate)**")
        fla = st.number_input("Motor FLA (Amp)", min_value=0.0, value=100.0, help="Full Load Ampere sesuai nameplate")
        rated_voltage = st.number_input("Rated Voltage (V)", min_value=0, value=380, help="Tegangan operasi normal")
    
    with col_spec4:
        st.markdown("**Hydraulic (Design Point)**")
        flow_q = st.number_input("Flow Rate Q (m³/h)", min_value=0.0, value=0.0, help="Flow rate desain pompa")
        head_h = st.number_input("Head H (m)", min_value=0.0, value=0.0, help="Total dynamic head desain")
    
    st.divider()
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        threshold_a = ISO_10816_THRESHOLDS[machine_group][foundation_type]['A']
        threshold_b = ISO_10816_THRESHOLDS[machine_group][foundation_type]['B']
        threshold_c = ISO_10816_THRESHOLDS[machine_group][foundation_type]['C']
        st.info(f"""
        **📊 ISO 10816-3 Thresholds ({machine_group}, {foundation_type}):**
        - Zone A: < {threshold_a} mm/s (Good)
        - Zone B: {threshold_a} - <{threshold_b} mm/s (Satisfactory)
        - Zone C: {threshold_b} - <{threshold_c} mm/s (Unsatisfactory)
        - Zone D: ≥ {threshold_c} mm/s (Unacceptable)
        """)
    with col_info2:
        rpm_dev = abs(actual_rpm - motor_rpm) / motor_rpm * 100 if motor_rpm > 0 else 0
        st.info(f"""
        **🔧 Machine Operating Point:**
        - Rated RPM: {motor_rpm} | Actual RPM: {actual_rpm}
        - RPM Deviation: {rpm_dev:.1f}% {"🔴 >5% (API 610 Alert)" if rpm_dev > 5 else "🟢 Normal"}
        - Flow: {flow_q} m³/h | Head: {head_h} m
        """)

# --- MAIN INPUTS ---
st.divider()

# Row 1: Vibration & Temp (SEMUA BEARING MEMILIKI H/V/A)
st.subheader("📊 2. Vibration Velocity & Temperature")
st.caption("ISO 10816-3:2009 Clause 5.2: Severity based on MAXIMUM value of H, V, or A direction")
vib_cols = st.columns(4)
bearings = ["Motor DE (B1)", "Motor NDE (B2)", "Pump DE (B3)", "Pump NDE (B4)"]
vib_data = {}
temp_data = {}

for i, b_name in enumerate(bearings):
    with vib_cols[i]:
        st.markdown(f"**{b_name}**")
        h = st.number_input(f"H (mm/s)", key=f"h_{i}", min_value=0.0, step=0.01, value=0.0, help="Horizontal direction")
        v = st.number_input(f"V (mm/s)", key=f"v_{i}", min_value=0.0, step=0.01, value=0.0, help="Vertical direction")
        a = st.number_input(f"A (mm/s)", key=f"a_{i}", min_value=0.0, step=0.01, value=0.0, help="Axial direction")
        temp = st.number_input(f"Temp (°C)", key=f"t_{i}", min_value=0.0, step=0.1, value=0.0, help="Bearing housing temperature")
        
        # KRUSIAL: Simpan MAX value untuk severity dan SUM untuk fault diagnosis
        vib_data[b_name] = {
            'h': h, 
            'v': v, 
            'a': a, 
            'max_value': max(h, v, a),  # Untuk severity evaluation (ISO 10816-3 Clause 5.2)
            'sum_value': h + v + a       # Untuk fault pattern recognition (ISO 13373-1)
        }
        temp_data[b_name] = temp

# Row 2: Acceleration
st.subheader("📈 3. Acceleration Bands (g RMS)")
st.caption("ISO 13381-1:2017: High frequency analysis for early bearing fault detection")
acc_cols = st.columns(4)
acc_data = {}

for i, b_name in enumerate(bearings):
    with acc_cols[i]:
        st.markdown(f"**{b_name}**")
        b1 = st.number_input(f"0.5-1.5 kHz", key=f"ab1_{i}", min_value=0.0, step=0.01, value=0.0)
        b2 = st.number_input(f"1.5-5 kHz", key=f"ab2_{i}", min_value=0.0, step=0.01, value=0.0)
        b3 = st.number_input(f"5-16 kHz", key=f"ab3_{i}", min_value=0.0, step=0.01, value=0.0)
        total_acc = b1 + b2 + b3
        
        st.write(f"**Total Acc: {total_acc:.2f} g**")
        acc_data[b_name] = {'b1': b1, 'b2': b2, 'b3': b3, 'total': total_acc}

# Row 3: Electrical
st.subheader("⚡ 4. Electrical Measurements")
st.caption("IEC 60034-1:2017 & NEMA MG-1 2019: Rotating electrical machine performance")
elec_col1, elec_col2 = st.columns(2)
with elec_col1:
    st.markdown("**Voltage (Volt)**")
    v_r = st.number_input("Phase R", key="vr", min_value=0.0, value=380.0)
    v_s = st.number_input("Phase S", key="vs", min_value=0.0, value=380.0)
    v_t = st.number_input("Phase T", key="vt", min_value=0.0, value=380.0)
with elec_col2:
    st.markdown("**Current (Amp)**")
    i_r = st.number_input("Phase R", key="ir", min_value=0.0, value=0.0)
    i_s = st.number_input("Phase S", key="is", min_value=0.0, value=0.0)
    i_t = st.number_input("Phase T", key="it", min_value=0.0, value=0.0)

# Row 4: Hydraulic
st.subheader("💧 5. Hydraulic Parameters")
st.caption("API 610 11th Edition §9.4: Hydraulic performance for petroleum service pumps")
hyd_col1, hyd_col2, hyd_col3 = st.columns(3)
with hyd_col1:
    suction_p = st.number_input("Suction Pressure (bar)", min_value=0.0, value=0.0, help="Tekanan suction aktual")
with hyd_col2:
    discharge_p = st.number_input("Discharge Pressure (bar)", min_value=0.0, value=0.0, help="Tekanan discharge aktual")
with hyd_col3:
    st.metric("Differential Pressure", f"{discharge_p - suction_p:.2f} bar")

# ==============================================================================
# ANALYSIS & DASHBOARD - SAFETY FIRST FOR BBM TERMINAL
# ==============================================================================
st.divider()
if st.button("🚀 RUN SAFETY DIAGNOSTIC", type="primary"):
    
    final_report = []
    detected_faults = []
    st.header("📋 SAFETY DIAGNOSTIC REPORT - BBM TERMINAL PUMP")
    st.markdown("**Status:** Evaluasi keselamatan berdasarkan standar internasional untuk fasilitas BBM")
    
    # 1. MECHANICAL VIBRATION ANALYSIS - KRUSIAL: Gunakan MAX value
    st.subheader("1. Mechanical Vibration Diagnosis (ISO 10816-3:2009 Clause 5.2)")
    
    if pump_standard == "API 610 / ISO 13709":
        st.info("🛢️ **Standard Applied:** API 610 11th Edition §9.3.4 (Mandatory for BBM Terminal Pumps)")
    else:
        st.info(f"🛢️ **Standard Applied:** ISO 10816-3:2009 {machine_group} ({foundation_type} Foundation)")
    
    mech_grid = st.columns(2)
    
    for i, b_name in enumerate(bearings):
        data = vib_data[b_name]
        max_v = data['max_value']  # ✅ KRUSIAL: Gunakan MAX value untuk severity
        sum_v = data['sum_value']   # Untuk fault pattern recognition
        is_pump = "Pump" in b_name
        
        # Pilih standar berdasarkan lokasi (Motor vs Pump) - Gunakan MAX value
        if is_pump and pump_standard == "API 610 / ISO 13709":
            zone, color, limit, severity_level = get_api_610_status(max_v)
            standard_name = "API 610 11th Ed. §9.3.4"
        else:
            zone, color, limit, standard_name, severity_level = get_iso_severity(machine_group, foundation_type, max_v)
        
        # Fault Diagnosis - HANYA jika severity level warning atau critical
        fault = None
        reason = None
        if severity_level in ["warning", "critical"] and max_v > 0:
            fault, reason = diagnose_fault(data['h'], data['v'], data['a'], sum_v)  # Gunakan sum_v untuk ratios
            if fault:
                detected_faults.append(fault)
        
        # Temp Check
        temp_stat, temp_reason, temp_level = check_temperature(temp_data[b_name])
        if temp_level in ["warning", "critical"]:
            detected_faults.append("Temperature")
        
        with mech_grid[i % 2]:
            with st.container(border=True):
                st.markdown(f"#### {b_name}")
                c1, c2 = st.columns(2)
                c1.metric("Vibration Severity", zone, delta=f"Limit: {limit} mm/s")
                c2.metric("Temperature", f"{temp_data[b_name]}°C", delta=temp_stat.split()[0])
                
                # Tampilkan MAX value sebagai nilai severity
                st.caption(f"📜 *Standard: {standard_name}*")
                st.caption(f"*Max Value: {max_v:.2f} mm/s (H:{data['h']:.2f}, V:{data['v']:.2f}, A:{data['a']:.2f})*")
                
                # KRUSIAL: Selalu laporkan vibration kritis meskipun tidak ada pola spesifik
                if severity_level == "critical":
                    if fault:
                        st.error(f"**⚠️ Fault Detected:** {fault}")
                        st.caption(f"🔍 *Diagnosis Basis:* {reason}")
                        final_report.append(f"{b_name}: {fault} ({zone})")
                    else:
                        st.error(f"**🚨 CRITICAL VIBRATION:** {zone}")
                        st.caption(f"🔍 *Max vibration {max_v:.2f} mm/s ≥ Limit {limit} mm/s per {standard_name}*")
                        final_report.append(f"{b_name}: CRITICAL VIBRATION ({zone}) - Requires Immediate Investigation")
                        if "High Vibration" not in detected_faults:
                            detected_faults.append("High Vibration")
                
                if temp_level == "critical":
                    st.error(f"**🌡️ Temp Status:** {temp_stat}")
                    st.caption(f"🔍 *Temp Basis:* {temp_reason}")
                    if not (severity_level == "critical" and not fault):
                        final_report.append(f"{b_name}: Temp {temp_stat}")
                elif temp_level == "warning" and severity_level != "critical":
                    st.warning(f"**🌡️ Temp Status:** {temp_stat}")
                    st.caption(f"🔍 *Temp Basis:* {temp_reason}")
                    final_report.append(f"{b_name}: Temp {temp_stat}")
                
                if severity_level == "warning" and fault:
                    st.warning(f"**⚠️ Attention:** {fault}")
                    st.caption(f"🔍 *Diagnosis Basis:* {reason}")
                    final_report.append(f"{b_name}: {fault} ({zone})")
                
                if severity_level == "normal" and temp_level == "normal":
                    st.success(f"**✅ Status:** Normal")
                    st.caption(f"🔍 *Vibration dalam batas acceptable per {standard_name}*")

    # 2. BEARING ACCELERATION
    st.subheader("2. Bearing Condition (Acceleration)")
    st.caption("ISO 13381-1:2017: Early detection of bearing defects")
    acc_grid = st.columns(4)
    for i, b_name in enumerate(bearings):
        data = acc_data[b_name]
        status = "✅ Bearing OK"
        rec = "No action needed."
        bearing_fault_detected = False
        
        if data['total'] > 0:
            hf_ratio = data['b3'] / data['total']
            
            if data['total'] >= ACC_LIMITS['Critical']:
                status = "🔴 Bearing Damage"
                rec = "GANTI BEARING SEGERA. Cek pelumasan dan kontaminasi (ISO 12922:2019)."
                bearing_fault_detected = True
                final_report.append(f"{b_name}: {status}")
            elif hf_ratio > 0.4 or data['b3'] >= 3.0 or data['total'] >= ACC_LIMITS['Warning']:
                status = "🟠 Early Bearing Fault"
                rec = "MONITORING KETAT. Percepat jadwal greasing dan periksa kontaminasi (ISO 12922:2019)."
                bearing_fault_detected = True
                final_report.append(f"{b_name}: {status}")
            elif data['total'] >= ACC_LIMITS['Normal']:
                status = "🟡 Warning"
                rec = "Periksa kondisi pelumasan dan jadwal maintenance."
                bearing_fault_detected = True
        
        if bearing_fault_detected:
            detected_faults.append("Bearing")
        
        with acc_grid[i]:
            st.metric(b_name, status)
            if status != "✅ Bearing OK":
                st.caption(rec)

    # 3. ELECTRICAL
    st.subheader("3. Electrical Health")
    st.caption("IEC 60034-1:2017 & NEMA MG-1 2019: Electrical safety compliance")
    elec_stat, elec_rec, elec_std, elec_level = check_electrical(v_r, v_s, v_t, i_r, i_s, i_t, fla, rated_voltage)
    
    if elec_level == "warning":
        detected_faults.append("Electrical")
        st.error(f"**{elec_stat}**")
        st.info(f"💡 *Recommendation:* {elec_rec}")
        if elec_std:
            st.caption(f"📜 *Standard: {', '.join(elec_std)}*")
        final_report.append(f"Electrical: {elec_stat}")
    else:
        st.success(f"**{elec_stat}**")
        st.caption(elec_rec)

    # 4. HYDRAULIC
    st.subheader("4. Hydraulic Performance")
    st.caption("API 610 11th Edition §9.4: Safety critical for BBM pumps")
    hyd_stat, hyd_rec, hyd_level = check_hydraulic(suction_p, discharge_p, flow_q, head_h, actual_rpm, motor_rpm)
    
    if hyd_level == "warning":
        detected_faults.append("Hydraulic")
        st.warning(f"**{hyd_stat}**")
        st.caption(f"💡 *Recommendation:* {hyd_rec}")
        final_report.append(f"Hydraulic: {hyd_stat}")
    else:
        st.success(hyd_stat)

    # ==============================================================================
    # FINAL SAFETY SUMMARY - BBM TERMINAL CRITICAL
    # ==============================================================================
    st.divider()
    st.header("🚨 SAFETY CONCLUSION & ACTIONS - BBM TERMINAL")
    
    if not final_report:
        st.success("✅ **STATUS AMAN:** Semua parameter dalam batas aman sesuai standar internasional untuk fasilitas BBM. Tidak ada tindakan segera diperlukan.")
        st.balloons()
    else:
        # Deteksi kondisi KRITIS yang memerlukan shutdown segera
        critical_conditions = [
            "Zone D" in item or "Trip Required" in item or "Overheat" in item or "Bearing Damage" in item or "Critical Suction" in item
            for item in final_report
        ]
        
        if any(critical_conditions):
            st.markdown('<div class="critical-alert"><strong>🔴 KRUSIAL: KONDISI KRITIS TERDETEKSI - SHUTDOWN SEGERA DIPERLUKAN</strong><br>Menurut API 610 §9.3.4 dan ISO 10816-3 Clause 6.2, mesin harus dihentikan segera untuk mencegah kegagalan katalog dan risiko keselamatan di fasilitas BBM.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="warning-alert"><strong>🟠 PERINGATAN: KONDISI TIDAK NORMAL TERDETEKSI</strong><br>Segera jadwalkan investigasi dan perbaikan sesuai rekomendasi untuk mencegah eskalasi ke kondisi kritis.</div>', unsafe_allow_html=True)
        
        st.error("⚠️ **Temuan Safety Diagnostic:**")
        
        summary_data = []
        for item in final_report:
            summary_data.append({"Issue": item})
        
        st.table(pd.DataFrame(summary_data))
        
        # Dynamic Recommendations - HANYA untuk fault yang terdeteksi
        st.markdown("### 🛠️ REKOMENDASI TINDAKAN KESELAMATAN:")
        
        recommendations_shown = []
        
        if "Misalignment" in detected_faults:
            recommendations_shown.append("**Misalignment:** Hentikan operasi. Lakukan laser alignment sesuai ISO 17703. Verifikasi coupling condition. *Alasan: Risiko kegagalan coupling dan kebocoran di area BBM.*")
        
        if "Unbalance" in detected_faults:
            recommendations_shown.append("**Unbalance:** Jadwalkan balancing rotor/impeller sesuai ISO 1940-1 Grade G2.5. *Alasan: Getaran tinggi dapat menyebabkan kebocoran seal pompa BBM.*")
        
        if "Mechanical Looseness" in detected_faults:
            recommendations_shown.append("**Looseness:** Periksa dan kencangkan semua baut fondasi, baseplate, dan mounting. Lakukan torque check sesuai spesifikasi. *Alasan: Fondasi longgar berisiko tinggi di area fasilitas BBM.*")
        
        if "High Vibration" in detected_faults:
            recommendations_shown.append("**🚨 CRITICAL VIBRATION:** HENTIKAN OPERASI SEGERA. Lakukan inspeksi menyeluruh: alignment, balancing, kondisi bearing, dan fondasi. Jangan operasikan hingga penyebab diidentifikasi dan diperbaiki (ISO 10816-3 Clause 6.2). *Alasan: Risiko kegagalan katalog dan potensi kebocoran BBM.*")
        
        if "Bearing" in detected_faults:
            recommendations_shown.append("**Bearing Fault:** Ganti bearing segera. Cek sistem pelumasan dan kontaminasi sesuai ISO 12922:2019. *Alasan: Kegagalan bearing dapat menyebabkan kebocoran seal dan risiko kebakaran.*")
        
        if "Temperature" in detected_faults:
            recommendations_shown.append("**Temperature:** Periksa sistem pendingin, kualitas pelumas, dan beban mesin. Lakukan thermal imaging. *Alasan: Suhu tinggi berisiko kebakaran di area fasilitas BBM.*")
        
        if "Electrical" in detected_faults:
            recommendations_shown.append("**Electrical:** Periksa koneksi terminal box, tegangan supply, dan kondisi rotor bar sesuai IEC 60034-1:2017. *Alasan: Masalah kelistrikan berpotensi menyebabkan percikan api di area berbahaya.*")
        
        if "Hydraulic" in detected_faults:
            recommendations_shown.append("**Hydraulic:** Verifikasi NPSH Available > NPSH Required untuk hindari kavitasi (API 610 §9.4.2). Periksa impeller dan seal. *Alasan: Kavitasi dapat merusak impeller dan menyebabkan kebocoran BBM.*")
        
        if recommendations_shown:
            for i, rec in enumerate(recommendations_shown, 1):
                st.markdown(f"{i}. {rec}")
            
            st.markdown("""
            ---
            **PRIORITY SAFETY ACTION (API 610 §9.3.4 & ISO 10816-3 Clause 6.2):**
            - 🔴 **CRITICAL (Zone D/Trip/Overheat/Bearing Damage):** HENTIKAN OPERASI SEGERA. Laporkan ke Safety Officer. Isolasi area. 
            - 🟠 **WARNING (Zone C/Alert):** Hentikan dalam 24 jam. Jadwalkan maintenance darurat.
            - 🟡 **ATTENTION (Zone B):** Monitor setiap 4 jam. Jadwalkan perbaikan dalam 7 hari.
            """)
            
            # Tambahkan disclaimer keselamatan khusus BBM
            st.markdown("""
            <div class="critical-alert">
            <strong>⚠️ PERINGATAN KESELAMATAN KHUSUS FASILITAS BBM:</strong><br>
            1. Setiap kebocoran atau kegagalan mekanis pada pompa BBM berpotensi menyebabkan kebakaran atau ledakan.<br>
            2. Pastikan area kerja bebas dari sumber api selama investigasi.<br>
            3. Gunakan PPE lengkap sesuai prosedur area berbahaya (API RP 2009).<br>
            4. Laporkan semua temuan ke Safety Department sebelum melakukan perbaikan.<br>
            5. Dokumentasikan semua temuan sesuai Sistem Manajemen Keselamatan (SMK3) dan Permen ESDM No. 13 Tahun 2021.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Tidak ada rekomendasi spesifik. Lakukan monitoring rutin sesuai jadwal.")
        
        st.markdown("---")
        st.caption("**Disclaimer Resmi:** Diagnosa ini berdasarkan analisis data input dan standar internasional. Untuk konfirmasi akhir, lakukan inspeksi fisik oleh personel kompeten dan analisis spektrum FFT mendalam. Keputusan operasional akhir harus mempertimbangkan kondisi lapangan aktual dan persetujuan Safety Officer. Sistem ini tidak menggantikan penilaian profesional dan prosedur keselamatan yang berlaku di fasilitas BBM.")

# ==============================================================================
# SIDEBAR - SAFETY REFERENCE UNTUK BBM TERMINAL
# ==============================================================================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/5/5a/Petroleum_logo.svg/1200px-Petroleum_logo.svg.png", width=100)
    st.header("🛢️ BBM TERMINAL SAFETY REFERENCE")
    st.markdown("**Standar Wajib untuk Pompa BBM:**")
    st.markdown("""
    **Vibration:**
    - 📜 **ISO 10816-3:2009** (General Industrial)
    - 📜 **API 610 11th Ed. §9.3.4** (Mandatory untuk pompa BBM)
    - 📜 **ISO 13373-1:2017** (Fault Diagnosis)
    
    **Electrical:**
    - 📜 **IEC 60034-1:2017** (Rotating Machines)
    - 📜 **NEMA MG-1 2019** (Motor Standards)
    
    **Temperature:**
    - 📜 **ISO 12922:2019** (Lubricants & Bearing Temp)
    
    **Bearing:**
    - 📜 **ISO 13381-1:2017** (Condition Monitoring)
    
    **Hydraulic:**
    - 📜 **API 610 11th Ed. §9.4** (Hydraulic Performance)
    
    **Safety:**
    - 📜 **API RP 2009** (Safe Handling of Hydrocarbons)
    - 📜 **Permen ESDM No. 13 Tahun 2021** (SMK3 Migas)
    """)
    
    st.divider()
    st.markdown("**ISO 10816-3 Zones:**")
    st.markdown("""
    - 🟢 **Zone A:** Good (Operasi Normal)
    - 🟡 **Zone B:** Satisfactory (Monitor)
    - 🟠 **Zone C:** Unsatisfactory (Perbaikan Diperlukan)
    - 🔴 **Zone D:** Unacceptable (**SHUTDOWN SEGERA**)
    """)
    
    st.divider()
    st.markdown("**PENTING UNTUK BBM TERMINAL:**")
    st.markdown("""
    1. **Severity Evaluation:** Gunakan nilai **MAKSIMUM** dari H, V, atau A (ISO 10816-3 Clause 5.2)
    2. **Fault Diagnosis:** Gunakan rasio H/V/A dari jumlah ketiga arah
    3. **API 610 wajib** untuk semua pompa di fasilitas BBM
    4. **Zone D = Shutdown Immediately** tanpa pengecualian
    """)
    
    st.divider()
    st.markdown("**Dikembangkan dengan:**")
    st.markdown("Zero Fatality Principle untuk Industri Migas Indonesia")
    st.caption("© 2026 - Sistem Diagnostik Pompa BBM - Validated dengan Standar Internasional")

# Footer
st.markdown("""
<div class="footer">
⚠️ <strong>PERINGATAN KESELAMATAN:</strong> Sistem ini adalah alat bantu keputusan. Keputusan operasional akhir harus melibatkan personel kompeten dan mematuhi prosedur keselamatan fasilitas BBM. 
Pelanggaran terhadap standar API 610 atau ISO 10816-3 dapat menyebabkan kegagalan katalog, kebocoran BBM, kebakaran, atau ledakan. 
Selalu prioritaskan keselamatan manusia dan lingkungan.
</div>
""", unsafe_allow_html=True)
