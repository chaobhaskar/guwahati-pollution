import re

with open('dashboard.py', 'r') as f:
    content = f.read()

# This finds the specific broken slider on line 417 and restores numeric options
broken_pattern = r'st\.select_slider\("Range",\s*options=\["Home", "Science of Air", "Creator", "Data Transparency"\],\s*value=14'
restored_slider = 'st.select_slider("Range", options=[7, 14, 30, 60, 90], value=14'

content = re.sub(broken_pattern, restored_slider, content)

with open('dashboard.py', 'w') as f:
    f.write(content)
