import sys, os
out_log = r"D:\pratik\New folder\pylog.txt"
with open(out_log, "w") as f:
    f.write("Starting...\n")
    try:
        import cv2
        f.write("cv2 imported successfully\n")
        vid = r"D:\pratik\New folder\Screen Recording 2026-03-23 110727.mp4"
        cap = cv2.VideoCapture(vid)
        if not cap.isOpened():
            f.write("Failed to open video\n")
        else:
            fps = cap.get(cv2.CAP_PROP_FPS)
            f.write(f"FPS: {fps}\n")
            out_dir = r"D:\pratik\New folder\video_frames"
            os.makedirs(out_dir, exist_ok=True)
            saved = 0
            idx = 0
            while True:
                ret, frame = cap.read()
                if not ret: break
                if idx % max(1, int(fps)) == 0:
                    cv2.imwrite(os.path.join(out_dir, f"frame_{saved:03d}.jpg"), frame)
                    saved += 1
                idx += 1
                if saved >= 30: break
            f.write(f"Saved {saved} frames\n")
    except Exception as e:
        f.write(f"Error: {e}\n")
    f.write("Done.\n")
