import RPi.GPIO as GPIO
import time

# กำหนดขา
PIR_PIN = 4
BUZZER_PIN = 27  # ใช้ขา 27 ตามที่เปลี่ยนล่าสุด

# ตั้งค่า GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(PIR_PIN, GPIO.IN)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# Active High Buzzer: 0V=เงียบ, 3.3V=ร้อง
# เริ่มต้นสั่งให้เงียบก่อน (0V)
GPIO.output(BUZZER_PIN, GPIO.LOW)

print("=== PIR Motion Sensor Test (Active High) ===")
print("Move in front of the sensor to test buzzer...")
print("Press Ctrl+C to exit")

def beep():
    # Active High Beep
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    time.sleep(0.1)
    GPIO.output(BUZZER_PIN, GPIO.LOW)

try:
    while True:
        if GPIO.input(PIR_PIN) == 1:
            print("\r🏃 Motion Detected!  ", end="", flush=True)
            beep() # ร้องติ๊ดๆ
            time.sleep(0.1) # เว้นจังหวะนิดนึงจะได้ไม่รัวเกิน
        else:
            print("\r💤 No Motion...       ", end="", flush=True)
            # เงียบ (GPIO.HIGH ถูกสั่งไว้ใน beep แล้ว)
        
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nExiting...")
finally:
    GPIO.output(BUZZER_PIN, GPIO.HIGH) # บังคับเงียบก่อนออก
    GPIO.cleanup()
