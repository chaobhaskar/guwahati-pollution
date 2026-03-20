import re

with open('dashboard.py', 'r') as f:
    content = f.read()

blog_code = """
st.sidebar.markdown('---')
st.sidebar.subheader('📚 The Physics of Air')
article = st.sidebar.selectbox('Select Article', ['Thermal Stratification', 'Aerosol Residence Time', 'Hygroscopic Growth'])

if article == 'Thermal Stratification':
    st.markdown('### 🏔️ Thermal Stratification & The Valley Effect')
    st.write('In the Brahmaputra Valley, the standard environmental lapse rate is often disrupted. During winter, radiative cooling of the surface creates a **Temperature Inversion**.')
    st.latex(r'\\frac{dT}{dz} > 0')
    st.write('This positive gradient acts as a physical cap, preventing vertical mixing. When the PBL height drops in Guwahati, PM2.5 concentrations spike regardless of traffic.')

elif article == 'Aerosol Residence Time':
    st.markdown('### ⏳ Aerosol Residence Time & Stokes Law')
    st.write('PM2.5 particles are so fine that their settling velocity ($V_s$) is dominated by the dynamic viscosity of air rather than gravity.')
    st.latex(r'V_s = \\frac{2r^2(\\rho_p - \\rho_f)g}{9\\eta}')
    st.write('For a 2.5μm particle, $V_s$ is so small that Brownian motion keeps it suspended for days. This justifies our **48-hour lookback window**.')

elif article == 'Hygroscopic Growth':
    st.markdown('### 💧 Hygroscopic Growth in High Humidity')
    st.write('Assam’s high relative humidity ($RH > 80\%$) causes aerosols to undergo **deliquescence**. Particles absorb water vapor, increasing their diameter.')
    st.latex(r'D(RH) = D_{dry} \cdot (1 - RH)^{-\gamma}')
    st.write('This growth changes the Light Scattering Coefficient, making the haze look denser even if the mass of dust hasn’t changed.')
"""

# Logic to insert or replace the blog
if 'st.sidebar.subheader' in content and 'Physics of Air' in content:
    # Replace existing block if it exists
    content = re.sub(r'st\.sidebar\.subheader\(\'📚 The Physics of Air\'\).*?(\n\n|(?=st\.sidebar\.markdown\(\"Updated\"))', blog_code, content, flags=re.DOTALL)
else:
    # Insert before the footer
    content = content.replace('st.sidebar.markdown("Updated")', blog_code + '\nst.sidebar.markdown("Updated")')

with open('dashboard.py', 'w') as f:
    f.write(content)
