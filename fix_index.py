import re

with open('dashboard.py', 'r') as f:
    content = f.read()

# This finds the default_index and forces it to 0 (Home)
# regardless of what number was there before
content = re.sub(r'default_index=\d+', 'default_index=0', content)

with open('dashboard.py', 'w') as f:
    f.write(content)
