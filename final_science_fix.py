import re

with open('dashboard.py', 'r') as f:
    content = f.read()

# 1. Ensure the options list is exactly correct
content = re.sub(r'options=\[.*?\]', 'options=["Home", "Science of Air", "Creator", "Data Transparency"]', content)
content = re.sub(r'icons=\[.*?\]', 'icons=["house", "book", "person", "shield-check"]', content)

# 2. Create the Science of Air Page Content
science_content = """
    if selected == "Science of Air":
        st.title("🔬 The Science of Air")
        st.markdown("---")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("🏔️ The Brahmaputra Valley Trap")
            st.write(\"\"\"
            Guwahati and North Lakhimpur suffer from a unique phenomenon called **Thermal Inversion**. 
            During winter, cold air is trapped near the ground by the surrounding hills.
            \"\"\")
            st.latex(r"\\frac{dT}{dz} > 0")
            st.info("Normally, air cools as you go up. In an inversion, it gets warmer, acting like a lid on a pot.")

        with col2:
            st.subheader("💧 Humidity & Growth")
            st.write("Assam's humidity causes particles to swell.")
            st.latex(r"D(RH) = D_{dry}(1-RH)^{-\gamma}")

        st.markdown("---")
        st.subheader("⏳ Particle Residence Time (Stokes Law)")
        st.latex(r"V_s = \\frac{2r^2(\\rho_p - \\rho_f)g}{9\\eta}")
        st.write("This explains why our model uses a **48-hour history window**.")
"""

# 3. Inject it before the "Creator" or "Data Transparency" logic
if 'if selected == "Creator":' in content and 'if selected == "Science of Air":' not in content:
    content = content.replace('if selected == "Creator":', science_content + '\n    if selected == "Creator":')

with open('dashboard.py', 'w') as f:
    f.write(content)
