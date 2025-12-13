import cv2

point = None

def mouse_callback(event, x, y, flags, param):
    global point

    if event == cv2.EVENT_LBUTTONDOWN:
        point = (x, y)   # เก็บพิกัดที่คลิก

# -------------------------------
# เปิดไฟล์วิดีโอ
# -------------------------------
video_path = "F:\\Cow\\b2d58b44-9a5d-4eb6-972c-00a223d5ce7b.mp4"   # <--- ใส่ชื่อไฟล์ตรงนี้
cap = cv2.VideoCapture(video_path)

cv2.namedWindow("Video XY")
cv2.setMouseCallback("Video XY", mouse_callback)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # ถ้ามีการคลิก → วาดจุด + โชว์พิกัด
    if point is not None:
        cv2.circle(frame, point, 6, (0, 0, 255), -1)
        text = f"{point}"
        cv2.putText(frame, text, (point[0] + 10, point[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    cv2.imshow("Video XY", frame)

    if cv2.waitKey(20) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
