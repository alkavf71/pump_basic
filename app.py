import streamlit as st
import pandas as pd
import numpy as np

# Konfigurasi Halaman
st.set_page_config(page_title="Professional Pump Diagnostic (ISO 10816-3)", layout="wide", page_icon="⚙️")

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
# STANDAR & THRESHOLD CONSTANTS - ISO 10816-3
# ==============================================================================

# ISO 10816-3 Vibration Severity (mm/s RMS) - Based on Group & Foundation
# Foundation Type affects limits (Rigid = tighter limits)
ISO_10816_THRESHOLDS = {
    'Group 1': {  # <15 kW - ISO 10816-1
        'Rigid': {'A': 1.8, 'B': 4.5, 'C': 7.1},
        'Flexible': {'A': 2.8, 'B': 7.1, 'C': 11.2}
    },
    'Group 2': {  # 15-300 kW - ISO 10816-3 Tables 2 (Rigid) & 3 (Flexible)
        'Rigid': {'A': 1.8, 'B': 2.8, 'C': 4.5},
        'Flexible': {'A': 2.8, 'B': 4.5, 'C': 7.1}
    },
    'Group 3': {  # >300 kW - ISO 10816-3 Table 1 (Rigid) + Industry Practice (Flexible)
        'Rigid': {'A': 2.8, 'B': 4.5, 'C': 7.1},
        'Flexible': {'A': 4.5, 'B': 7.1, 'C': 11.2}
    },
    'Group 4': {  # Turbo Machinery - ISO 10816-2
        'Rigid': {'A': 1.12, 'B': 2.8, 'C': 4.5},
        'Flexible': {'A': 1.8, 'B': 4.5, 'C': 7.1}
    }
}

# API 610 / ISO 13709 Centrifugal Pump Specific Limits
API_610_LIMITS = {
    'Normal': 3.0,
    'Alert': 4.5,
    'Trip': 7.1
}

# IEC 60034-1 Electrical Standards
IEC_VOLTAGE_UNBALANCE_MAX = 1.0
IEC_CURRENT_UNBALANCE_MAX = 10.0

# Temperature Standards (ISO 12922)
TEMP_LIMITS = {
    'Normal': 70,
    'Warning': 85,
    'Critical': 95,
    'Overheat': 100
}

# Acceleration Bearing Fault (g RMS)
ACC_LIMITS = {
    'Normal': 3.0,
    'Warning': 5.0,
    'Critical': 10.0
}

# ==============================================================================
# FUNGSI HELPER & LOGIKA STANDAR
# ==============================================================================

def get_iso_severity(group, foundation, velocity_rms):
    """
    Menghitung Severity berdasarkan ISO 10816-3 dengan Group & Foundation Type.
    Returns: Zone, Color, Limit, Standard Name, Severity Level
    """
    thresholds = ISO_10816_THRESHOLDS[group][foundation]
    
    if velocity_rms < thresholds['A']:
        return "Zone A (Good)", "🟢", thresholds['A'], f"ISO 10816-3 ({group}, {foundation})", "normal"
    elif velocity_rms < thresholds['B']:
        return "Zone B (Satisfactory)", "🟡", thresholds['B'], f"ISO 10816-3 ({group}, {foundation})", "warning"
    elif velocity_rms < thresholds['C']:
        return "Zone C (Unsatisfactory)", "🟠", thresholds['C'], f"ISO 10816-3 ({group}, {foundation})", "critical"
    else:
        return "Zone D (Unacceptable)", "🔴", thresholds['C'], f"ISO 10816-3 ({group}, {foundation})", "critical"

def get_api_610_status(velocity_rms):
    if velocity_rms < API_610_LIMITS['Normal']:
        return "✅ Acceptable", "🟢", API_610_LIMITS['Normal'], "normal"
    elif velocity_rms < API_610_LIMITS['Alert']:
        return "⚠️ Alert", "🟡", API_610_LIMITS['Alert'], "warning"
    elif velocity_rms < API_610_LIMITS['Trip']:
        return "🛑 Trip Warning", "🟠", API_610_LIMITS['Trip'], "critical"
    else:
        return "🚨 Trip Required", "🔴", API_610_LIMITS['Trip'], "critical"

def diagnose_fault(h, v, a, total_v):
    """
    Mendiagnosa jenis fault berdasarkan rasio arah getaran (H/V/A).
    Returns: fault_type, reason
    """
    if total_v == 0:
        return None, None
    
    ratio_a = a / total_v
    ratio_v = v / total_v
    ratio_h = h / total_v
    
    # 1. Misalignment (Dominan Axial) - ISO 13373-1
    if ratio_a > 0.5:
        return "Misalignment", f"ISO 13373-1: Getaran Axial ({a:.2f} mm/s) > 50% total. Rasio Axial: {ratio_a:.1%}"
    
    # 2. Angular Misalignment (Axial tinggi di satu sisi)
    if a > h and a > v and a > 2.0:
        return "Misalignment", f"ISO 13373-1: Getaran Axial ({a:.2f} mm/s) dominan dibanding Radial (H:{h:.2f}, V:{v:.2f})"
    
    # 3. Unbalance (Dominan Radial) - ISO 13373-1
    if ratio_a < 0.3 and (ratio_v > 0.35 or ratio_h > 0.35):
        return "Unbalance", f"ISO 13373-1: Getaran Radial (H:{h:.2f}, V:{v:.2f}) dominan. Axial rendah ({ratio_a:.1%})."
        
    # 4. Looseness (Vertikal >> Horizontal) - ISO 13373-1
    if v > 1.5 * h and v > 2.0:
        return "Mechanical Looseness", f"ISO 13373-1: Getaran Vertikal ({v:.2f}) > 1.5x Horizontal ({h:.2f}). Indikasi fondasi/bearing loose."
    
    return None, None

def check_temperature(temp):
    if temp == 0:
        return "⚪ No Data", "Tidak ada input temperatur.", "normal"
    elif temp < TEMP_LIMITS['Normal']:
        return "🟢 Normal", f"Suhu bearing < {TEMP_LIMITS['Normal']}°C (ISO 12922).", "normal"
    elif temp < TEMP_LIMITS['Warning']:
        return "🟡 Warning", f"Suhu {temp}°C. Cek pelumasan ({TEMP_LIMITS['Normal']}-{TEMP_LIMITS['Warning']}°C).", "warning"
    elif temp < TEMP_LIMITS['Critical']:
        return "🟠 Critical", f"Suhu tinggi {temp}°C. Risiko kerusakan bearing ({TEMP_LIMITS['Warning']}-{TEMP_LIMITS['Critical']}°C).", "critical"
    else:
        return "🔴 Overheat", f"Suhu kritis {temp}°C! Stop mesin segera (>{TEMP_LIMITS['Critical']}°C).", "critical"

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
    
    if avg_v > 0 and avg_v < rated_voltage * 0.9:
        issues.append("Under Voltage")
        recommendations.append("Tegangan turun >10% dari rated. Cek supply transformer.")
        standards.append("IEC 60034-1")
    elif v_unbalance > IEC_VOLTAGE_UNBALANCE_MAX:
        issues.append(f"Voltage Unbalance ({v_unbalance:.1f}%)")
        recommendations.append(f"Unbalance >{IEC_VOLTAGE_UNBALANCE_MAX}%. Derating motor diperlukan.")
        standards.append("IEC 60034-1 / NEMA MG-1")

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
        return "✅ Electrical Healthy", "Parameter sesuai IEC 60034-1.", [], "normal"
    
    return "⚠️ " + ", ".join(issues), "; ".join(recommendations), standards, "warning"

def check_hydraulic(suction_p, discharge_p, flow_q, head_h, actual_rpm, rated_rpm):
    """
    Cek Hidrolik berdasarkan API 610 dengan parameter Q, H, dan RPM.
    """
    delta_p = discharge_p - suction_p
    issues = []
    recommendations = []
    
    # Convert head (m) to pressure (bar) for comparison: 1 bar ≈ 10.2 m head
    head_pressure_bar = head_h / 10.2 if head_h > 0 else 0
    
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
    
    # Flow Rate Check (BEP - Best Efficiency Point)
    if flow_q > 0 and head_h > 0:
        if delta_p > 0:
            efficiency_indicator = (delta_p / head_pressure_bar) * 100 if head_pressure_bar > 0 else 0
            if efficiency_indicator < 70:
                issues.append("Off-BEP Operation")
                recommendations.append("Operasi jauh dari BEP. Cek flow rate dan system curve.")
    
    # RPM Deviation Check
    if rated_rpm > 0 and actual_rpm > 0:
        rpm_deviation = abs(actual_rpm - rated_rpm) / rated_rpm * 100
        if rpm_deviation > 5:
            issues.append(f"RPM Deviation ({rpm_deviation:.1f}%)")
            recommendations.append("RPM aktual menyimpang >5% dari rated. Cek VFD atau belt drive.")
        
    if not issues:
        return "✅ Normal Operation", "Parameter hidrolik normal.", "normal"
    
    return "⚠️ " + ", ".join(issues), "; ".join(recommendations), "warning"

# ==============================================================================
# UI INPUT SECTION
# ==============================================================================

st.title("⚙️ Professional Motor Pump Diagnostic System")
st.markdown("**Standar Referensi:** ISO 10816-3, ISO 13709 (API 610), IEC 60034-1, ISO 12922, ISO 13373-1")

# --- SIDEBAR / TOP: MACHINE SPECS ---
with st.expander("📋 1. Machine Specifications (Klik untuk Isi)", expanded=True):
    col_spec1, col_spec2, col_spec3, col_spec4 = st.columns(4)
    
    with col_spec1:
        st.markdown("**Motor & Pump**")
        motor_kw = st.number_input("Motor Power (kW)", min_value=0.0, value=55.0)
        motor_rpm = st.number_input("Rated RPM", min_value=0, value=2900)
        actual_rpm = st.number_input("Actual RPM", min_value=0, value=2900)
        coupling_type = st.selectbox("Coupling Type", ["Flexible", "Rigid"])
    
    with col_spec2:
        st.markdown("**ISO 10816-3 Classification**")
        machine_group = st.selectbox("Machine Group", ["Group 1", "Group 2", "Group 3", "Group 4"], 
                                     help="Group 1: <15kW, Group 2: 15-75kW, Group 3: >75kW, Group 4: Turbo")
        foundation_type = st.selectbox("Foundation Type", ["Rigid", "Flexible"],
                                       help="Rigid: Concrete base, Flexible: Steel structure")
        pump_standard = st.selectbox("Pump Standard", ["API 610 / ISO 13709", "ISO 10816-3 General"])
    
    with col_spec3:
        st.markdown("**Electrical**")
        fla = st.number_input("Motor FLA (Amp)", min_value=0.0, value=100.0)
        rated_voltage = st.number_input("Rated Voltage (V)", min_value=0, value=380)
    
    with col_spec4:
        st.markdown("**Hydraulic**")
        flow_q = st.number_input("Flow Rate Q (m³/h)", min_value=0.0, value=0.0)
        head_h = st.number_input("Head H (m)", min_value=0.0, value=0.0)
    
    # Display calculated thresholds
    st.divider()
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        threshold_a = ISO_10816_THRESHOLDS[machine_group][foundation_type]['A']
        threshold_b = ISO_10816_THRESHOLDS[machine_group][foundation_type]['B']
        threshold_c = ISO_10816_THRESHOLDS[machine_group][foundation_type]['C']
        st.info(f"""
        **📊 ISO 10816-3 Thresholds ({machine_group}, {foundation_type}):**
        - Zone A: < {threshold_a} mm/s
        - Zone B: {threshold_a} - {threshold_b} mm/s
        - Zone C: {threshold_b} - {threshold_c} mm/s
        - Zone D: > {threshold_c} mm/s
        """)
    with col_info2:
        st.info(f"""
        **🔧 Machine Info:**
        - Rated RPM: {motor_rpm}
        - Actual RPM: {actual_rpm}
        - RPM Deviation: {abs(actual_rpm - motor_rpm) / motor_rpm * 100 if motor_rpm > 0 else 0:.1f}%
        - Flow: {flow_q} m³/h | Head: {head_h} m
        """)

# --- MAIN INPUTS ---
st.divider()

# Row 1: Vibration & Temp (SEMUA BEARING MEMILIKI H/V/A)
st.subheader("📊 2. Vibration Velocity & Temperature")
st.caption("ISO 10816-3: Measurement on bearing housing in mm/s RMS (H/V/A untuk semua bearing)")
vib_cols = st.columns(4)
bearings = ["Motor DE (B1)", "Motor NDE (B2)", "Pump DE (B3)", "Pump NDE (B4)"]
vib_data = {}
temp_data = {}

for i, b_name in enumerate(bearings):
    with vib_cols[i]:
        st.markdown(f"**{b_name}**")
        h = st.number_input(f"H (mm/s)", key=f"h_{i}", min_value=0.0, step=0.01, value=0.0)
        v = st.number_input(f"V (mm/s)", key=f"v_{i}", min_value=0.0, step=0.01, value=0.0)
        a = st.number_input(f"A (mm/s)", key=f"a_{i}", min_value=0.0, step=0.01, value=0.0)
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
        total_acc = b1 + b2 + b3
        
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
hyd_col1, hyd_col2, hyd_col3 = st.columns(3)
with hyd_col1:
    suction_p = st.number_input("Suction Pressure (bar)", min_value=0.0, value=0.0)
with hyd_col2:
    discharge_p = st.number_input("Discharge Pressure (bar)", min_value=0.0, value=0.0)
with hyd_col3:
    st.metric("Differential Pressure", f"{discharge_p - suction_p:.2f} bar")

# ==============================================================================
# ANALYSIS & DASHBOARD
# ==============================================================================
st.divider()
if st.button("🚀 RUN DIAGNOSTIC ENGINE", type="primary"):
    
    final_report = []
    detected_faults = []
    st.header("📋 Diagnostic Report & Conclusion")
    
    # 1. MECHANICAL VIBRATION ANALYSIS
    st.subheader("1. Mechanical Vibration Diagnosis")
    
    if pump_standard == "API 610 / ISO 13709":
        st.info("📜 **Standard Applied:** API 610 / ISO 13709 (Oil & Gas Industry - More Strict)")
    else:
        st.info(f"📜 **Standard Applied:** ISO 10816-3 {machine_group} ({foundation_type} Foundation)")
    
    mech_grid = st.columns(2)
    
    for i, b_name in enumerate(bearings):
        data = vib_data[b_name]
        total_v = data['total']
        is_pump = "Pump" in b_name
        
        # Pilih standar berdasarkan lokasi (Motor vs Pump)
        if is_pump and pump_standard == "API 610 / ISO 13709":
            zone, color, limit, severity_level = get_api_610_status(total_v)
            standard_name = "API 610 / ISO 13709"
        else:
            zone, color, limit, standard_name, severity_level = get_iso_severity(machine_group, foundation_type, total_v)
        
        # Fault Diagnosis - HANYA jika severity level warning atau critical
        fault = None
        reason = None
        if severity_level in ["warning", "critical"] and total_v > 0:
            fault, reason = diagnose_fault(data['h'], data['v'], data['a'], total_v)
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
                
                st.caption(f"📜 *Standard: {standard_name}*")
                st.caption(f"*H: {data['h']}, V: {data['v']}, A: {data['a']} mm/s*")
                
     # Tampilkan fault diagnosis HANYA jika severity di atas normal
     if severity_level == "critical" or temp_level == "critical":
    # KRUSIAL: Selalu laporkan vibration kritis meskipun tidak ada pola spesifik
    if severity_level == "critical":
        if fault:
            st.error(f"**⚠️ Fault Detected:** {fault}")
            st.caption(f"🔍 *Diagnosis Basis:* {reason}")
            final_report.append(f"{b_name}: {fault} ({zone})")
        else:
            # GENERIC CRITICAL VIBRATION MESSAGE
            st.error(f"**🚨 CRITICAL VIBRATION:** {zone} (Exceeds Limit)")
            st.caption(f"🔍 *Vibration {total_v:.2f} mm/s > Limit {limit} mm/s per {standard_name}*")
            final_report.append(f"{b_name}: CRITICAL VIBRATION ({zone}) - Requires Immediate Investigation")
            # Tambahkan ke detected_faults untuk trigger rekomendasi
            if "High Vibration" not in detected_faults:
                detected_faults.append("High Vibration")
    
    if temp_level == "critical":
        st.error(f"**🌡️ Temp Status:** {temp_stat}")
        st.caption(f"🔍 *Temp Basis:* {temp_reason}")
        # Hindari duplikat jika sudah ditambahkan karena vibration kritis
        if severity_level != "critical" or not fault:
            final_report.append(f"{b_name}: Temp {temp_stat}")

    # 2. BEARING ACCELERATION
    st.subheader("2. Bearing Condition (Acceleration)")
    st.caption("📜 *Standard: ISO 13381-1 Condition Monitoring*")
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
                rec = "Ganti Bearing segera. Cek pelumasan (ISO 12922)."
                bearing_fault_detected = True
                final_report.append(f"{b_name}: {status}")
            elif hf_ratio > 0.4 or data['b3'] >= 3.0 or data['total'] >= ACC_LIMITS['Warning']:
                status = "🟠 Early Bearing Fault"
                rec = "Monitoring ketat. Greasing schedule dipercepat."
                bearing_fault_detected = True
                final_report.append(f"{b_name}: {status}")
            elif data['total'] >= ACC_LIMITS['Normal']:
                status = "🟡 Warning"
                rec = "Periksa kondisi pelumasan."
                bearing_fault_detected = True
        
        if bearing_fault_detected:
            detected_faults.append("Bearing")
        
        with acc_grid[i]:
            st.metric(b_name, status)
            if status != "✅ Bearing OK":
                st.caption(rec)

    # 3. ELECTRICAL
    st.subheader("3. Electrical Health")
    st.caption("📜 *Standard: IEC 60034-1 & NEMA MG-1*")
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
    st.caption("📜 *Standard: API 610 - NPSH & Differential Pressure*")
    hyd_stat, hyd_rec, hyd_level = check_hydraulic(suction_p, discharge_p, flow_q, head_h, actual_rpm, motor_rpm)
    
    if hyd_level == "warning":
        detected_faults.append("Hydraulic")
        st.warning(f"**{hyd_stat}**")
        st.caption(f"💡 *Recommendation:* {hyd_rec}")
        final_report.append(f"Hydraulic: {hyd_stat}")
    else:
        st.success(hyd_stat)

    # ==============================================================================
    # FINAL SUMMARY - DYNAMIC RECOMMENDATIONS
    # ==============================================================================
    st.divider()
    st.header("📝 Final Conclusion & Recommendations")
    
    if not final_report:
        st.success("🎉 Semua parameter dalam kondisi baik sesuai standar ISO/API. Tidak ada tindakan segera diperlukan.")
    else:
        st.error("⚠️ Ditemukan beberapa anomali yang memerlukan perhatian:")
        
        summary_data = []
        for item in final_report:
            summary_data.append({"Issue": item})
        
        st.table(pd.DataFrame(summary_data))
        
        # Dynamic Recommendations - HANYA untuk fault yang terdeteksi
        st.markdown("### 🛠️ Recommended Actions:")
        
        recommendations_shown = []
        
        if "Misalignment" in detected_faults:
            recommendations_shown.append("**Misalignment:** Lakukan laser alignment check pada coupling motor-pump (ISO 17703).")
        
        if "Unbalance" in detected_faults:
            recommendations_shown.append("**Unbalance:** Lakukan balancing pada rotor/impeller (ISO 1940-1).")
        
        if "Mechanical Looseness" in detected_faults:
            recommendations_shown.append("**Looseness:** Periksa fondasi, baseplate, dan mounting bolt. Kencangkan semua fastener.")
        
        if "Bearing" in detected_faults:
            recommendations_shown.append("**Bearing Fault:** Ganti bearing dan cek lubrication schedule (ISO 12922).")
        
        if "Temperature" in detected_faults:
            recommendations_shown.append("**Temperature:** Cek sistem pendingin, pelumasan, dan beban mesin.")
        
        if "Electrical" in detected_faults:
            recommendations_shown.append("**Electrical:** Cek koneksi terminal box, tegangan supply, dan rotor bar (IEC 60034).")
        
        if "Hydraulic" in detected_faults:
            recommendations_shown.append("**Hydraulic:** Pastikan NPSH Available > NPSH Required untuk menghindari kavitasi (API 610).")
        
        if recommendations_shown:
            for i, rec in enumerate(recommendations_shown, 1):
                st.markdown(f"{i}. {rec}")
            
            st.markdown("""
            ---
            **Priority Action:**
            - 🔴 **Critical (Zone D/Trip/Overheat):** Rencanakan shutdown segera
            - 🟠 **Warning (Zone C/Alert):** Monitoring intensif, rencanakan maintenance
            - 🟡 **Attention (Zone B):** Monitor tren, jadwal maintenance berikutnya
            """)
        else:
            st.info("Tidak ada rekomendasi spesifik. Lakukan monitoring rutin.")
        
        st.markdown("---")
        st.caption("⚠️ **Disclaimer:** Diagnosa ini berdasarkan analisis data input dan standar internasional. Untuk konfirmasi akhir, lakukan inspeksi fisik dan analisis spektrum FFT mendalam.")

# ==============================================================================
# SIDEBAR - QUICK REFERENCE
# ==============================================================================
with st.sidebar:
    st.header("📚 Standard Reference")
    st.markdown("""
    **Vibration:**
    - **ISO 10816-3** (General Industrial Machines)
    - API 610 / ISO 13709 (Pumps)
    - ISO 13373-1 (Fault Diagnosis)
    
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
    st.markdown("**ISO 10816-3 Zones:**")
    st.markdown("""
    - 🟢 Zone A: Good
    - 🟡 Zone B: Satisfactory
    - 🟠 Zone C: Unsatisfactory
    - 🔴 Zone D: Unacceptable
    """)
    
    st.divider()
    st.markdown("**Foundation Impact:**")
    st.markdown("""
    - **Rigid:** Concrete base, tighter limits
    - **Flexible:** Steel structure, higher limits
    """)
    
    st.divider()
    st.markdown("**Fault Diagnosis Logic (ISO 13373-1):**")
    st.markdown("""
    - **Misalignment:** Axial > 50% total
    - **Unbalance:** Radial dominant, Axial < 30%
    - **Looseness:** Vertical > 1.5x Horizontal
    """)
    
    st.divider()
    st.markdown("**Catatan Penting:**")
    st.markdown("""
    ISO 10816-3 adalah standar yang masih banyak digunakan di industri Indonesia untuk evaluasi getaran mesin industri umum. Standar ini menggantikan ISO 2372 dan memberikan panduan evaluasi berdasarkan:
    - Ukuran mesin (Group)
    - Jenis fondasi (Rigid/Flexible)
    - Lokasi pengukuran (bearing housing)
    """)
