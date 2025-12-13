import cv2
import numpy as np
from ultralytics import YOLO
import threading
import requests
import time
import math
import io

# ================================
# Google Drive API (Upload จาก RAM)
# ================================
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def upload_image_to_drive(image, filename):
    # โหลด credentials
    creds = None
    try:
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    except:
        pass

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "client_secret_676814135170-ndnl58eep16ecf72rmlhj1hv6epskuul.apps.googleusercontent.com.json",
            SCOPES
        )
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build("drive", "v3", credentials=creds)

    # แปลงภาพจาก OpenCV → JPEG → Bytes
    success, buffer = cv2.imencode(".jpg", image)
    if not success:
        print("❌ ไม่สามารถแปลงภาพเป็น JPEG ได้")
        return None

    img_bytes = io.BytesIO(buffer.tobytes())

    file_metadata = {"name": filename}
    media = MediaIoBaseUpload(img_bytes, mimetype="image/jpeg")

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    print(f"✔ Uploaded to Drive: ID = {file.get('id')}")
    return file.get("id")


# ================================
# Telegram
# ================================
TELEGRAM_TOKEN = '8209553840:AAEpwjYQbVWyALzcIjOpZcpeHJ3k5Qlx-ZM'
CHAT_ID = '7906440545'
ALERT_COOLDOWN = 10

def send_telegram(msg):
    try:
        url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
        requests.post(url, data={'chat_id': CHAT_ID, 'text': msg})
        print("✔ ส่ง Telegram:", msg)
    except Exception as e:
        print("❌ Telegram error:", e)

def send_telegram_snapshot_link(drive_id, cow_id):
    url = f"https://drive.google.com/file/d/{drive_id}/view?usp=sharing"
    msg = f"📸 Snapshot วัวหลุดคอก (ID {cow_id})\n{url}"
    send_telegram(msg)


# ================================
# YOLO
# ================================
print("กำลังโหลดโมเดล YOLOv8...")
model = YOLO("yolov8n.pt")

# ================================
# Polygon
# ================================
polygon_points = [
    (650, 400), (47, 300), (646, 180),
    (850, 200), (900, 200), (1000, 350)
]
polygon_np = np.array(polygon_points, np.int32)

# ================================
# Video
# ================================
cap = cv2.VideoCapture(0)

# ================================
# Re-ID Storage
# ================================
MAX_DISTANCE_REID = 150
MAX_FRAME_MEMORY = 120

cow_history = {}
last_alert = {}
escaped_cows_ids = set()
id_map = {}
last_known_pos = {}
frame_count = 0

print("🎉 System Started")


# ================================
# Main Loop
# ================================
while True:
    ret, frame = cap.read()
    if not ret:
        print("⚠ วิดีโอจบแล้ว")
        break

    frame_count += 1
    cv2.polylines(frame, [polygon_np.reshape((-1,1,2))], True, (0,255,0), 2)

    results = model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False)
    current_frame_ids = set()

    if results and results[0].boxes is not None:
        for box in results[0].boxes:

            cls = int(box.cls[0])
            if cls != 19:  # cow
                continue

            if box.id is None:
                continue

            raw_id = int(box.id[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx, cy = (x1 + x2)//2, (y1 + y2)//2

            # ------------------------
            # Internal Re-ID
            # ------------------------
            final_id = raw_id

            if raw_id in id_map:
                final_id = id_map[raw_id]
            else:
                possible = []
                for old_id, (ox, oy, last_seen) in last_known_pos.items():
                    if frame_count - last_seen < MAX_FRAME_MEMORY:
                        dist = math.dist((cx, cy), (ox, oy))
                        if dist < MAX_DISTANCE_REID:
                            possible.append((dist, old_id))

                if possible:
                    possible.sort()
                    best = possible[0][1]
                    id_map[raw_id] = best
                    final_id = best

            last_known_pos[final_id] = (cx, cy, frame_count)
            current_frame_ids.add(final_id)

            # ------------------------
            # Check escape
            # ------------------------
            inside = cv2.pointPolygonTest(polygon_np, (cx, cy), False)
            status = "INSIDE" if inside >= 0 else "OUTSIDE"

            if final_id not in cow_history:
                cow_history[final_id] = []
            cow_history[final_id].append(status)
            if len(cow_history[final_id]) > 10:
                cow_history[final_id].pop(0)

            recent = cow_history[final_id][-5:]
            escaped_confirmed = (len(recent) == 5 and all(v == "OUTSIDE" for v in recent))

            color = (0,255,0)

            if escaped_confirmed:
                color = (0,0,255)

                if final_id not in escaped_cows_ids:
                    escaped_cows_ids.add(final_id)
                    send_telegram(f"🚨 วัวหลุดคอก! (ID {final_id})")

                    # ⚡ SNAPSHOT → UPLOAD TO DRIVE
                    snapshot = frame.copy()
                    filename = f"cow_{final_id}_{int(time.time())}.jpg"
                    drive_id = upload_image_to_drive(snapshot, filename)

                    if drive_id:
                        send_telegram_snapshot_link(drive_id, final_id)

                now = time.time()
                if final_id not in last_alert or now - last_alert[final_id] > ALERT_COOLDOWN:
                    last_alert[final_id] = now

            # Draw box
            cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
            cv2.putText(frame, f"ID:{final_id}", (x1, y1-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    # Clean dead IDs
    for cid, (_,_,last_seen) in list(last_known_pos.items()):
        if frame_count - last_seen > 200:
            del last_known_pos[cid]

    cv2.putText(frame, f"Escaped: {len(escaped_cows_ids)}",
                (20,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 3)

    cv2.imshow("Cow Tracking + Drive Upload", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
