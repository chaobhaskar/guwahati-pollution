import re

with open('dashboard.py', 'r') as f:
    content = f.read()

# 1. Force the menu options to include Science of Air
content = re.sub(r'options=\[.*?\]', 'options=["Home", "Science of Air", "Creator", "Data Transparency"]', content)
content = re.sub(r'icons=\[.*?\]', 'icons=["house", "book", "person", "shield-check"]', content)

# 2. Add the actual page content
science_page = """
    if selected == "Science of Air":
        st.header("🔬 The Science of Air")
        st.write("Physico-chemical dynamics of the Guwahati atmosphere.")
        
        t1, t2, t3 = st.tabs(["Thermal Inversion", "Stokes Law", "Hygroscopic Growth"])
        
        with t1:
            st.subheader("🏔️ The Valley Trap")
            st.write("During winter nights in Assam, the ground cools faster than the air above. This creates a **Positive Temperature Gradient**.")
            st.latex(r"\\\\frac{dT}{dz} > 0")
            st.write("This 'lid' traps PM2.5 at the surface. Our model uses this physics to predict morning spikes.")
            
        with t2:
            st.subheader("⏳ Particle Residence Time")
            st.write("Why use a 48-hour history? Because PM2.5 settling velocity is dominated by air viscosity.")
            st.latex(r"V_s = \\\\frac{2r^2(\\\\rho_p - \\\\rho_f)g}{9\\\\eta}")
            st.write("Stokes Law explains why these particles stay suspended for days in the valley.")

        with t3:
            st.subheader("💧 Humidity & Growth")
            st.write("Assam’s high humidity causes aerosols to swell (deliquescence).")
            st.latex(r"D(RH) = D_{dry} \\\\cdot (1 - RH)^{-\\\\gamma}")
"""

# Insert before Creator
if 'if selected == "Creator":' in content:
    content = content.replace('if selected == "Creator":', science_page + '\n    if selected == "Creator":')

with open('dashboard.py', 'w') as f:
    f.write(content)
