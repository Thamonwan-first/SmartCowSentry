import RPi.GPIO as GPIO
import time

# ตั้งค่าขา GPIO
BUZZER_PIN = 27

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

print("Starting Buzzer Test (Active Low Module)")
print(f"Buzzer connected to GPIO {BUZZER_PIN}")

try:
    while True:
        # ขั้นตอนที่ 1: สั่งให้เงียบ (ส่งไฟ 3.3V / HIGH)
        print(">>> SILENT (Output: HIGH / 3.3V)")
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        time.sleep(5)

        # ขั้นตอนที่ 2: สั่งให้ร้อง (ส่งไฟ 0V / LOW)
        print(">>> BEEPING (Output: LOW / 0V)")
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        time.sleep(5)

except KeyboardInterrupt:
    print("\nStopping test...")
finally:
    # ก่อนจบโปรแกรม ให้ส่ง HIGH เพื่อให้เงียบ
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    GPIO.cleanup()
    print("GPIO Cleaned up. (If it's beeping now, it's because GPIO is floating)")
