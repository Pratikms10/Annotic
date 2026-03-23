import os
path = r"D:\pratik\New folder\Screen Recording 2026-03-23 110727.mp4"
print(f"Exists: {os.path.exists(path)}")
if os.path.exists(path):
    print(f"Size: {os.path.getsize(path)} bytes")
