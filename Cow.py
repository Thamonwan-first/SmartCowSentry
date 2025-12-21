import cv2
import numpy as np
from ultralytics import YOLO
import threading
import requests
import time
import math
import io

# ================================
# CONFIGURATION
# ================================
BUZZER_ACTIVE_HIGH = False  # <--- ถ้ามันร้องตลอด ให้ลองเปลี่ยนเป็น False
TARGET_CLASS = 19           # 0 = Person, 19 = Cow

# ================================
# Raspberry Pi GPIO (RPi.GPIO Version)
# ================================
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # Buzzer -> GPIO 27 (Active High: 0V=เงียบ, 3.3V=ร้อง)
    # เราต้องสั่ง 0V ทันทีที่รันโปรแกรมเพื่อให้เงียบ
    GPIO.setup(27, GPIO.OUT)
    GPIO.output(27, GPIO.LOW) # สั่ง LOW (0V) ทันที
    
    # PIR Sensor -> GPIO 4 (Input)
    GPIO.setup(4, GPIO.IN)
    
    time.sleep(0.5) # รอให้ระบบไฟนิ่ง
    GPIO.output(27, GPIO.LOW) # ย้ำอีกครั้งว่าให้เงียบ
    
    USE_GPIO = True
    print(f"✔ GPIO Ready: ขา 27 ถูกสั่งเป็น LOW (0V) เพื่อปิดเสียง (Active High Mode)")

except (ImportError, Exception) as e:
    USE_GPIO = False
    print(f"⚠️ ไม่พบ GPIO หรือเกิดข้อผิดพลาด: {e}")

# Wrapper Functions เพื่อให้โค้ดข้างล่างเรียกใช้ได้เหมือนเดิม
def is_motion_detected():
    if USE_GPIO:
        return GPIO.input(4) == 1
    return True

def buzzer_beep():
    if USE_GPIO:
        # Active High: จ่ายไฟ 3.3V เพื่อร้อง
        GPIO.output(27, GPIO.HIGH)
        time.sleep(0.1)
        # ดึงลง 0V เพื่อเงียบ
        GPIO.output(27, GPIO.LOW)


motion_active = False      # สถานะว่ามีการเคลื่อนไหวหรือไม่
last_motion_time = 0
MOTION_TIMEOUT = 5.0       # ให้ YOLO ทำงานต่ออีก 5 วินาทีหลังการเคลื่อนไหวหยุด

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
    (300, 26), (559, 26), (559, 441),(300 ,441)
]
polygon_np = np.array(polygon_points, np.int32)

# ================================
# Video
# ================================
#cap = cv2.VideoCapture("/home/th/cow_env/b2d58b44-9a5d-4eb6-972c-00a223d5ce7b.mp4")
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


def alert_worker(snapshot, cow_id, total_escaped):
    """ฟังก์ชันแจ้งเตือนแบบแยก Thread ไม่ให้วิดีโอค้าง"""
    print(f"🚀 เริ่มกระบวนการแจ้งเตือนสำหรับ ID {cow_id}...")
    
    send_telegram(f"🚨 ตรวจพบวัวหลุดคอก! (รวมทั้งหมด: {total_escaped} ตัว)")

    # 🔊 BUZZER ALARM!
    if USE_GPIO:
        # ร้อง 3 ครั้ง
        for _ in range(3):
            buzzer_beep()
            time.sleep(0.1)

    # ⚡ SNAPSHOT → UPLOAD TO DRIVE
    filename = f"cow_escape_{int(time.time())}.jpg"
    drive_id = upload_image_to_drive(snapshot, filename)

    if drive_id:
        url = f"https://drive.google.com/file/d/{drive_id}/view?usp=sharing"
        msg = f"📸 Snapshot วัวหลุดคอก\n{url}"
        send_telegram(msg)
    
    print(f"✅ แจ้งเตือนเสร็จสิ้น (ID {cow_id})")

# ================================
# Main Loop
# ================================
skip_frame_count = 0
last_results = None  # เก็บผลลัพธ์ล่าสุดไว้วาดในเฟรมที่ข้าม

while True:
    ret, frame = cap.read()
    if not ret:
        print("⚠ วิดีโอจบแล้ว")
        break

    # ------------------------
    # Check PIR Sensor (CM4 GPIO)
    # ------------------------
    if USE_GPIO:
        if is_motion_detected():
            if not motion_active:
                print("🏃 ตรวจพบการเคลื่อนไหว! (PIR Activated)")
            last_motion_time = time.time()
            motion_active = True
        
        # ตรวจสอบว่าหมดเวลา Motion หรือยัง (Cooldown)
        if time.time() - last_motion_time > MOTION_TIMEOUT:
            motion_active = False
    else:
        # ถ้าไม่มี Sensor ให้ทำงานตลอดเวลา
        motion_active = True 

    frame_count += 1
    
    # วาด Polygon และ Status เสมอ (ไม่ว่าจะข้ามเฟรมหรือไม่)
    cv2.polylines(frame, [polygon_np.reshape((-1,1,2))], True, (0,255,0), 2)
    status_text = "PIR: MOTION DETECTED" if motion_active else "PIR: IDLE (Power Saving)"
    status_color = (0, 255, 0) if motion_active else (100, 100, 100)
    cv2.putText(frame, status_text, (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

    # ถ้าไม่มีการเคลื่อนไหว (และใช้ GPIO) ให้แสดงแค่ภาพสด แต่ไม่ต้องรัน YOLO (ลดความร้อน CM4)
    if USE_GPIO and not motion_active:
        # แสดงสถานะ Standby
        cv2.putText(frame, "Standby: Waiting for Motion...", (50, 300), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (100, 100, 100), 2)
        cv2.imshow("Cow Tracking + Drive Upload", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break
        continue

    # cv2.putText(frame, "TEST MODE: ALWAYS ON", (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    # ------------------------
    # Frame Skipping Logic (Process every 2nd frame)
    # ------------------------
    skip_frame_count += 1
    
    if skip_frame_count % 2 == 0:
        # ========================
        # YOLO TRACKING (Update)
        # ========================
        results = model.track(frame, persist=True, tracker="cow_tracker.yaml", verbose=False, conf=0.3)
        last_results = results 
    else:
        # เฟรมที่ข้าม: ใช้ผลลัพธ์เก่า
        results = last_results

    # ========================
    # Draw & Logic (Run on every frame using latest results)
    # ========================
    current_frame_ids = set()

    if results and results[0].boxes is not None:
        for box in results[0].boxes:
            cls = int(box.cls[0])
            if cls != TARGET_CLASS:
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
                # Visual Feedback: แสดงข้อความ ALARM บนหน้าจอ
                cv2.putText(frame, "ALARM! OUTSIDE", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

                if final_id not in escaped_cows_ids:
                    escaped_cows_ids.add(final_id)
                    
                    # แจ้งเตือนครั้งแรก (Telegram + รูป + เสียง)
                    snapshot = frame.copy()
                    t = threading.Thread(target=alert_worker, args=(snapshot, final_id, len(escaped_cows_ids)))
                    t.start()

                # แจ้งเตือนซ้ำ (เฉพาะเสียง) ถ้ายังอยู่นอกเขตทุกๆ 0.5 วินาที
                now = time.time()
                if final_id not in last_alert or now - last_alert[final_id] > 0.5:
                    last_alert[final_id] = now
                    # เรียกเสียงร้องแบบไม่บล็อกโปรแกรม
                    threading.Thread(target=buzzer_beep).start()

            # Draw box (No ID display)
            cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)

    # Clean dead IDs
    for cid, (_,_,last_seen) in list(last_known_pos.items()):
        if frame_count - last_seen > 200:
            del last_known_pos[cid]

    cv2.imshow("Cow Tracking + Drive Upload", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
