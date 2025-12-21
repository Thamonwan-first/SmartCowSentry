from gpiozero import Buzzer
from time import sleep

print("Testing Buzzer on GPIO 17...")

# Test 1: Active High
print("\n[Test 1] Assuming Active HIGH (True = Beep)")
try:
    bz = Buzzer(17, active_high=True)
    print("Command: ON")
    bz.on()
    sleep(2)
    print("Command: OFF")
    bz.off()
    sleep(2)
    bz.close()
except Exception as e:
    print(e)

# Test 2: Active Low
print("\n[Test 2] Assuming Active LOW (False = Beep)")
try:
    bz = Buzzer(17, active_high=False)
    print("Command: ON")
    bz.on()
    sleep(2)
    print("Command: OFF")
    bz.off()
    sleep(2)
    bz.close()
except Exception as e:
    print(e)

print("\nDone.")
