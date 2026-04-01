# This program is used to claculate the flow rate of the submersible pump

import time
import RPi.GPIO as GPIO

RELAY_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)

try:
    print("Pump starting...")
    print("Fill container to 1 litre, then press CTRL+C")

    GPIO.output(RELAY_PIN, GPIO.LOW)   # relay ON

    start_time = time.time()

    while True:
        time.sleep(1)

except KeyboardInterrupt:

    GPIO.output(RELAY_PIN, GPIO.HIGH)  # relay OFF
    end_time = time.time()

    duration = end_time - start_time

    print("\nPump stopped")
    print(f"Total runtime: {duration:.2f} seconds")

    GPIO.cleanup()

