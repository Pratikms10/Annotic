import cv2
import os
import sys

video_path = r"D:\pratik\New folder\Screen Recording 2026-03-23 110727.mp4"
out_dir = r"D:\pratik\New folder\video_frames"
os.makedirs(out_dir, exist_ok=True)

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print("Failed to open video")
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
print(f"Video FPS: {fps}")

frame_idx = 0
saved_idx = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    if int(fps) == 0: fps = 30 # fallback
    
    # Save ~1 frame per second
    if frame_idx % int(fps) == 0:
        cv2.imwrite(os.path.join(out_dir, f"frame_{saved_idx:03d}.jpg"), frame)
        saved_idx += 1
    
    frame_idx += 1
    if saved_idx >= 60:
        break

cap.release()
print(f"Saved {saved_idx} frames to {out_dir}")
