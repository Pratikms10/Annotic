import json

dom_file = "d:/pratik/New folder/dom.html"

with open(dom_file, "r", encoding="utf-8") as f:
    html = f.read()

out = []

# Audio class
idx = html.find('<audio')
if idx != -1:
    end_idx = html.find('>', idx)
    out.append("Audio Tag: " + html[idx:end_idx+1])

# Container
c_idx = html.find('id="subTitleContainer"')
if c_idx != -1:
    c_html = html[c_idx:c_idx+10000] # First 10k chars of segments 
    out.append("\n--- CONTAINER SNIPPET ---")
    out.append(c_html)

with open("out3.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
