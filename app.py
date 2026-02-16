import streamlit as st
import pandas as pd
import numpy as np

# Konfigurasi Halaman
st.set_page_config(page_title="Professional Pump Diagnostic (ISO/API)", layout="wide", page_icon="⚙️")

# CSS Custom
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ccc;
        margin-bottom: 10px;
    }
    .stAlert { margin-top: 10px; }
    .standard-ref { font-size: 0.8em; color: #666; font-style: italic; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# STANDAR & THRESHOLD CONSTANTS
# ==============================================================================

# ISO 20816-1 / ISO 10816-3 Vibration Severity (mm/s RMS)
# Group 1: Small (<15kW), Group 2: Medium (15-75kW), Group 3: Large (>75kW)
ISO_20816_THRESHOLDS = {
    'Group 1': {'A': 1.4, 'B': 2.8, 'C': 4.5},
    'Group 2': {'A': 1.8, 'B': 4.5, 'C': 7.1},
    'Group 3': {'A': 2.3, 'B': 4.5, 'C': 11.2}
}

# API 610 / ISO 13709 Centrifugal Pump Specific Limits
API_610_LIMITS = {
    'Normal': 3.0,    # mm/s RMS
    'Alert': 4.5,     # mm/s RMS
    'Trip': 7.1       # mm/s RMS
}

# IEC 60034-1 Electrical Standards
IEC_VOLTAGE_UNBALANCE_MAX = 1.0  # %
IEC_CURRENT_UNBALANCE_MAX = 10.0 # %
NEMA_VOLTAGE_UNBALANCE_WARN = 5.0 # %

# Temperature Standards (ISO 12922 / General Bearing Practice)
# Based on Bearing Housing Temperature
TEMP_LIMITS = {
    'Normal': 70,    # °C
    'Warning': 85,   # °C
    'Critical': 95,  # °C
    'Overheat': 100  # °C
}

# Acceleration Bearing Fault (g RMS)
# Based on SKF/ISO 13381-1 Condition Monitoring
ACC_LIMITS = {
    'Normal': 3.0,   # g
    'Warning': 5.0,  # g
    'Critical': 10.0 # g
}

# ==============================================================================
# FUNGSI HELPER & LOGIKA STANDAR
# ==============================================================================

def get_machine_group(power_kw):
    """Menentukan Group Mesin berdasarkan ISO 20816-1"""
    if power_kw < 15:
        return 'Group 1'
    elif power_kw <= 75:
        return 'Group 2'
    else:
        return 'Group 3'

def get_iso_severity(power_kw, velocity_rms):
    """
    Menghitung Severity berdasarkan ISO 20816-1.
    Returns: Zone, Color, Limit Value, Standard Name
    """
    group = get_machine_group(power_kw)
    thresholds = ISO_20816_THRESHOLDS[group]
    
    if velocity_rms < thresholds['A']:
        return "Zone A (Good)", "🟢", thresholds['A'], f"ISO 20816-1 ({group})"
    elif velocity_rms < thresholds['B']:
        return "Zone B (Satisfactory)", "🟡", thresholds['B'], f"ISO 20816-1 ({group})"
    elif velocity_rms < thresholds['C']:
        return "Zone C (Unsatisfactory)", "🟠", thresholds['C'], f"ISO 20816-1 ({group})"
    else:
        return "Zone D (Unacceptable)", "🔴", thresholds['C'], f"ISO 20816-1 ({group})"

def get_api_610_status(velocity_rms):
    """
    Menghitung Status berdasarkan API 610 / ISO 13709 untuk Pompa.
    """
    if velocity_rms < API_610_LIMITS['Normal']:
        return "✅ Acceptable", "🟢", API_610_LIMITS['Normal']
    elif velocity_rms < API_610_LIMITS['Alert']:
        return "⚠️ Alert", "🟡", API_610_LIMITS['Alert']
    elif velocity_rms < API_610_LIMITS['Trip']:
        return "🛑 Trip Warning", "🟠", API_610_LIMITS['Trip']
    else:
        return "🚨 Trip Required", "🔴", API_610_LIMITS['Trip']

def diagnose_fault(h, v, a, total_v):
    """
    Mendiagnosa jenis fault berdasarkan rasio arah getaran (Pattern Recognition).
    """
    if total_v == 0:
        return "No Data", "Tidak ada data getaran."
    
    ratio_a = a / total_v
    ratio_v = v / total_v
    ratio_h = h / total_v
    
    faults = []
    reasons = []
    
    # 1. Misalignment (Dominan Axial)
    # ISO 13373-1: Axial vibration > 50% of radial indicates misalignment
    if ratio_a > 0.5 or (a > h and a > v and a > 2.0):
        faults.append("Misalignment")
        reasons.append(f"ISO 13373-1: Getaran Axial ({a:.2f} mm/s) > 50% total. Rasio Axial: {ratio_a:.1%}")
    
    # 2. Unbalance (Dominan Radial)
    # ISO 13373-1: Radial dominant with low axial indicates unbalance
    if ratio_a < 0.3 and (ratio_v > 0.35 or ratio_h > 0.35):
        faults.append("Unbalance")
        reasons.append(f"ISO 13373-1: Getaran Radial (H:{h:.2f}, V:{v:.2f}) dominan. Axial rendah ({ratio_a:.1%}).")
        
    # 3. Looseness (Vertikal >> Horizontal)
    # ISO 13373-1: V > 1.5x H indicates mechanical looseness
    if v > 1.5 * h and v > 2.0:
        if "Unbalance" in faults:
            faults.remove("Unbalance")
        faults.append("Mechanical Looseness")
        reasons.append(f"ISO 13373-1: Getaran Vertikal ({v:.2f}) > 1.5x Horizontal ({h:.2f}). Indikasi fondasi/bearing loose.")
        
    if not faults:
        return "Normal / General Vibration", "Kondisi getaran dalam batas wajar sesuai ISO 20816-1."
    
    return ", ".join(faults), "; ".join(reasons)

def check_temperature(temp):
    """
    Cek Temperatur berdasarkan ISO 12922 & General Bearing Practice.
    """
    if temp < TEMP_LIMITS['Normal']:
        return "🟢 Normal", f"Suhu bearing < {TEMP_LIMITS['Normal']}°C (ISO 12922)."
    elif temp < TEMP_LIMITS['Warning']:
        return "🟡 Warning", f"Suhu {temp}°C. Cek pelumasan ({TEMP_LIMITS['Normal']}-{TEMP_LIMITS['Warning']}°C)."
    elif temp < TEMP_LIMITS['Critical']:
        return "🟠 Critical", f"Suhu tinggi {temp}°C. Risiko kerusakan bearing ({TEMP_LIMITS['Warning']}-{TEMP_LIMITS['Critical']}°C)."
    else:
        return "🔴 Overheat", f"Suhu kritis {temp}°C! Stop mesin segera (>{TEMP_LIMITS['Critical']}°C)."

def check_electrical(v_r, v_s, v_t, i_r, i_s, i_t, fla, rated_voltage):
    """
    Cek Elektrikal berdasarkan IEC 60034-1 & NEMA MG-1.
    """
    issues = []
    recommendations = []
    standards = []
    
    # Voltage Analysis
    avg_v = np.mean([v_r, v_s, v_t])
    if avg_v > 0:
        max_dev_v = max([abs(v - avg_v) for v in [v_r, v_s, v_t]])
        v_unbalance = (max_dev_v / avg_v) * 100
    else:
        v_unbalance = 0
    
    if avg_v > 0 and avg_v < rated_voltage * 0.9:
        issues.append("Under Voltage")
        recommendations.append("Tegangan turun >10% dari rated. Cek supply transformer.")
        standards.append("IEC 60034-1")
    elif v_unbalance > IEC_VOLTAGE_UNBALANCE_MAX:
        issues.append(f"Voltage Unbalance ({v_unbalance:.1f}%)")
        recommendations.append(f"Unbalance >{IEC_VOLTAGE_UNBALANCE_MAX}%. Derating motor diperlukan.")
        standards.append("IEC 60034-1 / NEMA MG-1")

    # Current Analysis
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
            recommendations.append("Motor <40% FLA. Efisiensi rendah.")
        elif load_pct > 100:
            issues.append("Over Loading")
            recommendations.append("Motor >100% FLA. Risiko thermal overload.")
            standards.append("IEC 60034-1")
            
    if i_unbalance > IEC_CURRENT_UNBALANCE_MAX:
        issues.append(f"Current Unbalance ({i_unbalance:.1f}%)")
        recommendations.append("Unbalance arus >10%. Cek rotor bar atau winding.")
        standards.append("NEMA MG-1")
    elif i_unbalance > 5:
        issues.append(f"Minor Current Unbalance ({i_unbalance:.1f}%)")
        recommendations.append("Monitor tren unbalance arus.")
        
    if not issues:
        return "✅ Electrical Healthy", "Parameter sesuai IEC 60034-1.", []
    
    return "⚠️ " + ", ".join(issues), "; ".join(recommendations), standards

def check_hydraulic(suction_p, discharge_p):
    """
    Cek Hidrolik berdasarkan API 610 & General Pump Practice.
    """
    delta_p = discharge_p - suction_p
    issues = []
    recommendations = []
    
    # Cavitation Check (NPSH related)
    if suction_p < 1.0 and discharge_p > 2.0:
        issues.append("Risk of Cavitation")
        recommendations.append("Suction pressure <1 bar. Cek NPSH Available vs Required (API 610).")
    elif suction_p < 0.5:
        issues.append("Critical Suction Pressure")
        recommendations.append("Suction sangat rendah. Risiko kavitasi parah.")
    
    # Low Head Check
    if delta_p < 1.0 and discharge_p > 0:
        issues.append("Low Differential Pressure")
        recommendations.append("Delta P rendah. Cek impeller wear atau valve position.")
        
    if not issues:
        return "✅ Normal Operation", "Parameter hidrolik normal."
    
    return "⚠️ " + ", ".join(issues), "; ".join(recommendations)

# ==============================================================================
# UI INPUT SECTION
# ==============================================================================

st.title("⚙️ Professional Motor Pump Diagnostic System")
st.markdown("**Standar Referensi:** ISO 20816-1, ISO 13709 (API 610), IEC 60034-1, ISO 12922")

# --- SIDEBAR / TOP: MACHINE SPECS ---
with st.expander("📋 1. Machine Specifications (Klik untuk Isi)", expanded=True):
    col_spec1, col_spec2, col_spec3 = st.columns(3)
    with col_spec1:
        motor_kw = st.number_input("Motor Power (kW)", min_value=0.0, value=55.0, help="Digunakan untuk menentukan ISO 20816 Group")
        motor_rpm = st.number_input("Rated RPM", min_value=0, value=2900)
        coupling_type = st.selectbox("Coupling Type", ["Flexible", "Rigid"], help="Mempengaruhi threshold alignment")
    with col_spec2:
        pump_standard = st.selectbox("Pump Standard", ["API 610 / ISO 13709", "ISO 20816 General"], help="API 610 lebih ketat untuk industri oil & gas")
        fla = st.number_input("Motor FLA (Amp)", min_value=0.0, value=100.0)
        rated_voltage = st.number_input("Rated Voltage (V)", min_value=0, value=380)
    with col_spec3:
        machine_group = get_machine_group(motor_kw)
        st.info(f"**ISO 20816 Group:** {machine_group}\n\n**Threshold Zone A:** <{ISO_20816_THRESHOLDS[machine_group]['A']} mm/s")

# --- MAIN INPUTS ---
st.divider()

# Row 1: Vibration & Temp
st.subheader("📊 2. Vibration Velocity & Temperature")
st.caption("ISO 20816-1: Measurement on bearing housing in mm/s RMS")
vib_cols = st.columns(4)
bearings = ["Motor DE (B1)", "Motor NDE (B2)", "Pump DE (B3)", "Pump NDE (B4)"]
vib_data = {}
temp_data = {}

for i, b_name in enumerate(bearings):
    with vib_cols[i]:
        st.markdown(f"**{b_name}**")
        has_axial = (i == 0 or i == 2) # B1 & B3 have Axial
        
        h = st.number_input(f"H (mm/s)", key=f"h_{i}", min_value=0.0, step=0.01, value=0.0)
        v = st.number_input(f"V (mm/s)", key=f"v_{i}", min_value=0.0, step=0.01, value=0.0)
        a = st.number_input(f"A (mm/s)", key=f"a_{i}", min_value=0.0, step=0.01, value=0.0) if has_axial else 0.0
        temp = st.number_input(f"Temp (°C)", key=f"t_{i}", min_value=0.0, step=0.1, value=0.0)
        
        vib_data[b_name] = {'h': h, 'v': v, 'a': a, 'total': h+v+a}
        temp_data[b_name] = temp

# Row 2: Acceleration
st.subheader("📈 3. Acceleration Bands (g RMS)")
st.caption("ISO 13381-1: High frequency for early bearing fault detection")
acc_cols = st.columns(4)
acc_data = {}

for i, b_name in enumerate(bearings):
    with acc_cols[i]:
        st.markdown(f"**{b_name}**")
        b1 = st.number_input(f"0.5-1.5 kHz", key=f"ab1_{i}", min_value=0.0, step=0.01, value=0.0)
        b2 = st.number_input(f"1.5-5 kHz", key=f"ab2_{i}", min_value=0.0, step=0.01, value=0.0)
        b3 = st.number_input(f"5-16 kHz", key=f"ab3_{i}", min_value=0.0, step=0.01, value=0.0)
        total_acc = b1 + b2 + b3 # Auto Calculate
        
        st.write(f"**Total Acc: {total_acc:.2f} g**")
        acc_data[b_name] = {'b1': b1, 'b2': b2, 'b3': b3, 'total': total_acc}

# Row 3: Electrical
st.subheader("⚡ 4. Electrical Measurements")
st.caption("IEC 60034-1: Rotating Electrical Machines Rating and Performance")
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
st.caption("API 610: Centrifugal Pumps for Petroleum Industries")
hyd_col1, hyd_col2 = st.columns(2)
with hyd_col1:
    suction_p = st.number_input("Suction Pressure (bar)", min_value=0.0, value=0.0)
with hyd_col2:
    discharge_p = st.number_input("Discharge Pressure (bar)", min_value=0.0, value=0.0)

# ==============================================================================
# ANALYSIS & DASHBOARD
# ==============================================================================
st.divider()
if st.button("🚀 RUN DIAGNOSTIC ENGINE", type="primary"):
    
    final_report = []
    st.header("📋 Diagnostic Report & Conclusion")
    
    # 1. MECHANICAL VIBRATION ANALYSIS
    st.subheader("1. Mechanical Vibration Diagnosis")
    
    # Tampilkan standar yang digunakan
    if pump_standard == "API 610 / ISO 13709":
        st.info("📜 **Standard Applied:** API 610 / ISO 13709 (Oil & Gas Industry - More Strict)")
    else:
        st.info(f"📜 **Standard Applied:** ISO 20816-1 {get_machine_group(motor_kw)}")
    
    mech_grid = st.columns(2)
    
    for i, b_name in enumerate(bearings):
        data = vib_data[b_name]
        total_v = data['total']
        is_pump = "Pump" in b_name
        
        # Pilih standar berdasarkan lokasi (Motor vs Pump)
        if is_pump and pump_standard == "API 610 / ISO 13709":
            zone, color, limit = get_api_610_status(total_v)
            standard_name = "API 610 / ISO 13709"
        else:
            zone, color, limit, standard_name = get_iso_severity(motor_kw, total_v)
        
        # Fault Diagnosis
        fault, reason = diagnose_fault(data['h'], data['v'], data['a'], total_v)
        
        # Temp Check
        temp_stat, temp_reason = check_temperature(temp_data[b_name])
        
        with mech_grid[i % 2]:
            with st.container(border=True):
                st.markdown(f"#### {b_name}")
                c1, c2 = st.columns(2)
                c1.metric("Vibration Severity", zone, delta=f"Limit: {limit} mm/s")
                c2.metric("Temperature", f"{temp_data[b_name]}°C", delta=temp_stat.split()[0])
                
                st.caption(f"📜 *Standard: {standard_name}*")
                
                # Tampilkan warning/error berdasarkan severity
                if "Zone C" in zone or "Zone D" in zone or "Trip" in zone or "Critical" in temp_stat or "Overheat" in temp_stat:
                    st.error(f"**⚠️ Fault Detected:** {fault}")
                    st.caption(f"🔍 *Diagnosis Basis:* {reason}")
                    st.caption(f"🌡️ *Temp Status:* {temp_reason}")
                    final_report.append(f"{b_name}: {fault} ({zone}), Temp: {temp_stat}")
                elif "Zone B" in zone or "Alert" in zone or "Warning" in temp_stat:
                    st.warning(f"**⚠️ Attention:** {fault}")
                    st.caption(f"🔍 *Diagnosis Basis:* {reason}")
                    st.caption(f"🌡️ *Temp Status:* {temp_reason}")
                    final_report.append(f"{b_name}: {fault} ({zone}), Temp: {temp_stat}")
                else:
                    st.success(f"**✅ Status:** {fault}")
                    st.caption(f"🔍 *Diagnosis Basis:* {reason}")

    # 2. BEARING ACCELERATION
    st.subheader("2. Bearing Condition (Acceleration)")
    st.caption("📜 *Standard: ISO 13381-1 Condition Monitoring*")
    acc_grid = st.columns(4)
    for i, b_name in enumerate(bearings):
        data = acc_data[b_name]
        status = "✅ Bearing OK"
        rec = "No action needed."
        color = "🟢"
        
        if data['total'] > 0:
            hf_ratio = data['b3'] / data['total'] # 5-16kHz ratio
            
            if data['total'] >= ACC_LIMITS['Critical']:
                status = "🔴 Bearing Damage"
                rec = "Ganti Bearing segera. Cek pelumasan (ISO 12922)."
                color = "🔴"
                final_report.append(f"{b_name}: {status}")
            elif hf_ratio > 0.4 or data['b3'] >= 3.0 or data['total'] >= ACC_LIMITS['Warning']:
                status = "🟠 Early Bearing Fault"
                rec = "Monitoring ketat. Greasing schedule dipercepat."
                color = "🟠"
                final_report.append(f"{b_name}: {status}")
            elif data['total'] >= ACC_LIMITS['Normal']:
                status = "🟡 Warning"
                rec = "Periksa kondisi pelumasan."
                color = "🟡"
        
        with acc_grid[i]:
            st.metric(b_name, status)
            if status != "✅ Bearing OK":
                st.caption(rec)

    # 3. ELECTRICAL
    st.subheader("3. Electrical Health")
    st.caption("📜 *Standard: IEC 60034-1 & NEMA MG-1*")
    elec_stat, elec_rec, elec_std = check_electrical(v_r, v_s, v_t, i_r, i_s, i_t, fla, rated_voltage)
    
    if "⚠️" in elec_stat:
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
    st.caption("📜 *Standard: API 610 - NPSH & Differential Pressure*")
    delta_p = discharge_p - suction_p
    hyd_stat, hyd_rec = check_hydraulic(suction_p, discharge_p)
    
    st.metric("Differential Pressure", f"{delta_p:.2f} bar")
    if "⚠️" in hyd_stat:
        st.warning(f"**{hyd_stat}**")
        st.caption(f"💡 *Recommendation:* {hyd_rec}")
        final_report.append(f"Hydraulic: {hyd_stat}")
    else:
        st.success(hyd_stat)

    # ==============================================================================
    # FINAL SUMMARY
    # ==============================================================================
    st.divider()
    st.header("📝 Final Conclusion & Recommendations")
    
    if not final_report:
        st.success("🎉 Semua parameter dalam kondisi baik sesuai standar ISO/API. Tidak ada tindakan segera diperlukan.")
    else:
        st.error("⚠️ Ditemukan beberapa anomali yang memerlukan perhatian:")
        
        # Create a summary dataframe
        summary_data = []
        for item in final_report:
            summary_data.append({"Issue": item})
        
        st.table(pd.DataFrame(summary_data))
        
        st.markdown("### 🛠️ Recommended Actions:")
        st.markdown("""
        1. **Prioritas Tinggi (Zone D / Trip / Overheat):** Rencanakan shutdown segera untuk mencegah catastrophic failure.
        2. **Misalignment:** Lakukan laser alignment check pada coupling motor-pump (ISO 17703).
        3. **Unbalance:** Lakukan balancing pada rotor/impeller (ISO 1940-1).
        4. **Bearing Fault:** Ganti bearing dan cek lubrication schedule (ISO 12922).
        5. **Electrical:** Cek koneksi terminal box, tegangan supply, dan rotor bar (IEC 60034).
        6. **Hydraulic:** Pastikan NPSH Available > NPSH Required untuk menghindari kavitasi (API 610).
        """)
        
        st.markdown("---")
        st.caption("⚠️ **Disclaimer:** Diagnosa ini berdasarkan analisis data input dan standar internasional. Untuk konfirmasi akhir, lakukan inspeksi fisik dan analisis spektrum FFT mendalam.")

# ==============================================================================
# SIDEBAR - QUICK REFERENCE
# ==============================================================================
with st.sidebar:
    st.header("📚 Standard Reference")
    st.markdown("""
    **Vibration:**
    - ISO 20816-1 (General)
    - API 610 / ISO 13709 (Pumps)
    
    **Electrical:**
    - IEC 60034-1
    - NEMA MG-1
    
    **Temperature:**
    - ISO 12922 (Lubricants)
    
    **Bearing:**
    - ISO 13381-1 (Condition Monitoring)
    
    **Hydraulic:**
    - API 610 (NPSH)
    """)
    
    st.divider()
    st.markdown("**ISO 20816 Zones:**")
    st.markdown("""
    - 🟢 Zone A: Good
    - 🟡 Zone B: Satisfactory
    - 🟠 Zone C: Unsatisfactory
    - 🔴 Zone D: Unacceptable
    """)
