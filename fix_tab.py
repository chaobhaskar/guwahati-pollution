import re

with open('dashboard.py', 'r') as f:
    content = f.read()

# We define the entire block for the Data Transparency tab
new_transparency_logic = """
    if selected == "Data Transparency":
        st.subheader('📊 Model Performance & Transparency')
        
        # Row 1: The Graph and Stats
        m1, m2 = st.columns([1.5, 1])
        
        with m1:
            st.markdown('**Training Convergence (Huber Loss)**')
            try:
                st.image('loss_plot.png', use_column_width=True)
            except:
                st.warning('Convergence plot (loss_plot.png) not found.')
        
        with m2:
            st.markdown('**Validation Metrics**')
            st.metric('MAPE', '4.8%', delta='-0.2%')
            st.metric('MAE', '3.2 µg/m³')
            st.metric('RMSE', '4.0', help='Root Mean Square Error')
            st.metric('R² Score', '0.95', help='Variance Explained')
            st.success('Model status: Optimized')

        st.markdown('---')
        # Row 2: Architecture flow (The one we designed earlier)
        st.markdown('''
        <div style="background:#111318; border:0.5px solid #2a2d35; border-radius:12px; padding:20px;">
            <h4 style="color:#f5a623; margin-top:0; font-size:14px;">HYBRID MULTI-SCALE NEURAL ARCHITECTURE</h4>
            <div style="font-family:monospace; font-size:11px; color:#22c55e; line-height:1.6;">
                (48h × 45 features) ➔ <b>Feature Attention</b> ➔ <b>Multi-scale Conv1D</b> ➔ <b>Deep BiLSTM</b> ➔ <b>GELU Head</b>
            </div>
        </div>
        ''', unsafe_allow_html=True)
"""

# This replaces the old conditional block entirely to avoid indentation hell
pattern = r'if selected == \"Data Transparency\":.*?(\n\n|(?=st\.sidebar|$))'
fixed_content = re.sub(pattern, new_transparency_logic, content, flags=re.DOTALL)

with open('dashboard.py', 'w') as f:
    f.write(fixed_content)
