import re

file_path = 'dashboard.py'
with open(file_path, 'r') as f:
    content = f.read()

# 1. Fix the broken slider on line 417 (Restore numeric range)
# This looks for the broken options list and puts back the numbers [7, 14, 30, 60]
broken_slider = r'options=\["Home", "Science of Air", "Creator", "Data Transparency"\]'
fixed_slider = 'options=[7, 14, 30, 60]'
content = re.sub(broken_slider, fixed_slider, content)

# 2. Ensure the Sidebar Menu has the correct options
content = re.sub(r'options=\[.*?\]', 'options=["Home", "Science of Air", "Creator", "Data Transparency"]', content, count=1)
content = re.sub(r'icons=\[.*?\]', 'icons=["house", "book", "person", "shield-check"]', content, count=1)

# 3. Create the Science of Air Blog Content
science_blog = """
    if selected == "Science of Air":
        st.title("🔬 The Science of Air")
        st.markdown("---")
        
        t1, t2, t3 = st.tabs(["Thermal Inversion", "Stokes Law", "Hygroscopic Growth"])
        
        with t1:
            st.subheader("🏔️ The Valley Trap")
            st.write("Guwahati's topography creates a 'lid' during winter nights.")
            st.latex(r"\\\\frac{dT}{dz} > 0")
            st.info("This positive temperature gradient (Inversion) traps pollutants at ground level.")
            
            
        with t2:
            st.subheader("⏳ Stokes Law & Residence Time")
            st.write("PM2.5 particles settle slowly due to air viscosity, justifying our 48-hour model window.")
            st.latex(r"V_s = \\\\frac{2r^2(\\\\rho_p - \\\\rho_f)g}{9\\\\eta}")
            
            
        with t3:
            st.subheader("💧 Deliquescence")
            st.write("Assam's humidity causes particles to swell and scatter more light (Hygroscopic Growth).")
            st.latex(r"D(RH) = D_{dry}(1-RH)^{-\\\\gamma}")
            
"""

# 4. Inject the blog logic before the Creator section
if 'if selected == "Creator":' in content and 'if selected == "Science of Air":' not in content:
    content = content.replace('if selected == "Creator":', science_blog + '\n    if selected == "Creator":')

with open(file_path, 'w') as f:
    f.write(content)
