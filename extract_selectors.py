import re
import json

dom_file = "d:/pratik/New folder/dom.html"

with open(dom_file, "r", encoding="utf-8") as f:
    html = f.read()

# Find audio tag
audio_match = re.search(r'<audio[^>]*id="([^"]+)"[^>]*src="([^"]+)"[^>]*>', html)
if audio_match:
    print(f"Audio ID: {audio_match.group(1)}")
    
# Find subTitleContainer
container_match = re.search(r'id="subTitleContainer">(.*)', html, re.DOTALL)
if container_match:
    container_html = container_match.group(1)
    # the container has elements with default="" id="0_resizable"
    segments = re.finditer(r'<div default="" id="(\d+)_resizable"(.*?)</div></div></div></div></div>', container_html)
    for i, match in enumerate(segments):
        if i >= 3: break
        seg_id = match.group(1)
        seg_html = match.group(2)
        
        print(f"\n--- Segment {seg_id} ---")
        
        # Try to find Speaker dropdown input
        speaker_match = re.search(r'value="(Speaker \d+\s*\([^)]+\))"', seg_html)
        if speaker_match:
             print(f"Speaker Value: {speaker_match.group(1)}")
             
        # Try to find class of speaker input
        speaker_class = re.search(r'type="text"[^>]*class="([^"]+)"[^>]*value="Speaker', seg_html)
        if speaker_class:
             print(f"Speaker Input Class: {speaker_class.group(1)}")

        # Try to find textarea
        textarea_match = re.search(r'<textarea[^>]*class="([^"]+)"', seg_html)
        if textarea_match:
             print(f"Textarea Class: {textarea_match.group(1)}")
             text_content = re.search(r'<textarea[^>]*>(.*?)</textarea>', seg_html)
             if text_content:
                  print(f"Textarea Content: {text_content.group(1)}")
                  
        # Try to find time divs (e.g. >00 : 00 : 00 . 000<)
        times = re.findall(r'>(\d{2}\s*:\s*\d{2}\s*:\s*\d{2}\s*\.\s*\d{3})<', seg_html)
        if times:
             print("Timestamps:", times)

with open("out.txt", "w") as f:
    f.write("Done parsing.")
