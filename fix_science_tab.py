import re

file_path = 'dashboard.py'
with open(file_path, 'r') as f:
    content = f.read()

# 1. Force the menu options to include the new tab
content = re.sub(r'options=\[.*?\]', 'options=["Home", "Science of Air", "Creator", "Data Transparency"]', content)
content = re.sub(r'icons=\[.*?\]', 'icons=["house", "book", "person", "shield-check"]', content)

# 2. The Science of Air Content
science_block = """
    if selected == "Science of Air":
        st.title("🔬 The Science of Air")
        st.markdown("---")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("🏔️ The Valley Trap (Thermal Inversion)")
            st.write("Guwahati sits in a topographic bowl. During winter nights, cold air is trapped by the hills.")
            st.latex(r"\\frac{dT}{dz} > 0")
            st.info("Normally, air cools with height. In an inversion, it warms up, trapping PM2.5 at breathing level.")
            
        with col2:
            st.subheader("💧 Hygroscopic Growth")
            st.write("High humidity causes aerosols to swell via deliquescence.")
            st.latex(r"D(RH) = D_{dry}(1-RH)^{-\\\\gamma}")

        st.markdown("---")
        st.subheader("⏳ Particle Residence Time")
        st.write("Why look back 48 hours? PM2.5 settling velocity is incredibly slow due to air viscosity.")
        st.latex(r"V_s = \\\\frac{2r^2(\\\\rho_p - \\\\rho_f)g}{9\\\\eta}")
        st.write("Stokes Law explains why the air you breathe today is linked to emissions from two days ago.")
"""

# 3. Inject it before the Creator section
if 'if selected == "Creator":' in content:
    content = content.replace('if selected == "Creator":', science_block + '\n    if selected == "Creator":')

with open(file_path, 'w') as f:
    f.write(content)
