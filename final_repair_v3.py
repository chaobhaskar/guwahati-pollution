import re

file_path = 'dashboard.py'
with open(file_path, 'r') as f:
    content = f.read()

# 1. Fix the broken slider on line 417 (Restore numeric range [7, 14, 30, 60, 90])
# We use a broad regex to find where the menu accidentally replaced the numbers
broken_pattern = r'st\.select_slider\("Range",\s*options=\["Home",.*?\]'
fixed_slider = 'st.select_slider("Range", options=[7, 14, 30, 60, 90]'
content = re.sub(broken_pattern, fixed_slider, content)

# 2. Ensure the Sidebar Navigation remains intact at the top of the file
content = re.sub(r'options=\["Home",\s*"Creator"', 'options=["Home", "Science of Air", "Creator"', content)

# 3. Create the Science of Air Page Logic
science_blog_code = """
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

# 4. Insert the blog logic before the Creator section
if 'if selected == "Creator":' in content and 'if selected == "Science of Air":' not in content:
    content = content.replace('if selected == "Creator":', science_blog_code + '\n    if selected == "Creator":')

with open(file_path, 'w') as f:
    f.write(content)
