import re

with open('dashboard.py', 'r') as f:
    content = f.read()

# 1. Update the Menu Options
content = content.replace(
    'options=["Home", "Creator", "Data Transparency"]', 
    'options=["Home", "Science of Air", "Creator", "Data Transparency"]'
)
content = content.replace(
    'icons=["house", "person", "shield-check"]', 
    'icons=["house", "book", "person", "shield-check"]'
)

# 2. Add the Science of Air Page Logic
science_code = """
    if selected == "Science of Air":
        st.header("🔬 The Physics of Air")
        st.write("Atmospheric dynamics of the Brahmaputra Valley.")
        
        t1, t2, t3 = st.tabs(["Thermal Stratification", "Particle Dynamics", "Hygroscopic Growth"])
        
        with t1:
            st.subheader("🏔️ The Valley Trap")
            st.write("Guwahati acts as a topographic bowl. Radiative cooling creates an **Inversion**.")
            st.latex(r"\\\\frac{dT}{dz} > 0")
            st.write("This traps PM2.5 at breathing level, explaining our high morning spikes.")
            
        with t2:
            st.subheader("⏳ Stokes Law & Residence Time")
            st.write("PM2.5 particles are so light that gravity is countered by air viscosity.")
            st.latex(r"V_s = \\\\frac{2r^2(\\\\rho_p - \\\\rho_f)g}{9\\\\eta}")
            st.write("This justifies the **48-hour history window** used in our AI model.")

        with t3:
            st.subheader("💧 Hygroscopic Growth")
            st.write("High humidity in Assam causes aerosols to absorb water and swell.")
            st.latex(r"D(RH) = D_{dry} \\\\cdot (1 - RH)^{-\\\\gamma}")
"""

# Insert the new page logic before the Creator section
if 'if selected == "Creator":' in content:
    content = content.replace('if selected == "Creator":', science_code + '\n    if selected == "Creator":')

with open('dashboard.py', 'w') as f:
    f.write(content)
