import time
import smbus
import board
import adafruit_dht
import requests
import RPi.GPIO as GPIO
import csv
from datetime import datetime

# =========================
# THINGSPEAK CONFIG
# =========================

WRITE_API_KEY = "" #here goes the write api key of the thigspeak channel
THINGSPEAK_URL = "https://api.thingspeak.com/update"

# =========================
# HARDWARE CONFIG
# =========================

ADC_ADDR = 0x48
RELAY_PIN = 17

MOISTURE_THRESHOLD = 26
IRRIGATION_COOLDOWN = 7200
last_irrigation_time = 0

PUMP_RUNTIME = 3
INTERVAL = 15

# =========================
# GPIO SETUP
# =========================

GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, GPIO.HIGH)

# =========================
# SENSOR SETUP
# =========================

bus = smbus.SMBus(1)
time.sleep(2)

dht = adafruit_dht.DHT11(board.D4, use_pulseio=False)

previous_moisture = None
previous_irrigation = 0

# =========================
# DATASET FILE
# =========================

filename = "irrigation_dataset.csv"

with open(filename, "a", newline="") as f:

    writer = csv.writer(f)

    if f.tell() == 0:
        writer.writerow([
            "timestamp",
            "soil_moisture",
            "temperature",
            "humidity",
            "hour",
            "dry_rate",
            "previous_irrigation",
            "pump_runtime",
            "fan_state"
        ])

# =========================
# MOISTURE READ FUNCTION
# =========================

def read_moisture():

    try:

        bus.write_byte(ADC_ADDR, 0x40)
        time.sleep(0.01)

        bus.read_byte(ADC_ADDR)
        time.sleep(0.01)

        raw = bus.read_byte(ADC_ADDR)

        moisture = 100 - (raw / 255) * 100

        return round(moisture, 2)

    except Exception as e:

        print("Moisture read error:", e)
        return None


# =========================
# READ DHT11 WITH RETRY
# =========================

def read_dht():

    temp = None
    humidity = None

    for i in range(3):

        try:

            temp = dht.temperature
            humidity = dht.humidity

            if temp is not None and humidity is not None:
                return temp, humidity

        except RuntimeError:
            time.sleep(1)

        except Exception:
            adafruit_dht.exit()
            time.sleep(1)

    return None, None


# =========================
# PUMP CONTROL
# =========================

def run_pump(runtime):

    GPIO.output(RELAY_PIN, GPIO.LOW)

    time.sleep(runtime)

    GPIO.output(RELAY_PIN, GPIO.HIGH)


# =========================
# MAIN LOOP
# =========================

print("Starting irrigation data collection...")

while True:

    try:

        now = datetime.now()
        hour = now.hour

        moisture = read_moisture()

        if moisture is None:
            time.sleep(2)
            continue

        temp, humidity = read_dht()

        # =========================
        # DRY RATE
        # =========================

        if previous_moisture is None:
            dry_rate = 0
        else:
            dry_rate = previous_moisture - moisture

        previous_moisture = moisture

        pump_runtime = 0
        fan_state = 0

        # =========================
        # IRRIGATION LOGIC
        # =========================

        current_time = time.time()

        if moisture < MOISTURE_THRESHOLD and (current_time - last_irrigation_time) > IRRIGATION_COOLDOWN:

            pump_runtime = PUMP_RUNTIME

            print("Pump ON for", pump_runtime, "seconds")

            run_pump(pump_runtime)

            previous_irrigation = pump_runtime

            # update cooldown timer
            last_irrigation_time = current_time

        else:

            previous_irrigation = 0

        print("-----------------------------")
        print("Time:", now)
        print("Moisture:", moisture)
        print("Temp:", temp)
        print("Humidity:", humidity)
        print("Dry rate:", dry_rate)
        print("Pump runtime:", pump_runtime)

        # =========================
        # SAVE DATASET
        # =========================

        with open(filename, "a", newline="") as f:

            writer = csv.writer(f)

            writer.writerow([
                now,
                moisture,
                temp,
                humidity,
                hour,
                dry_rate,
                previous_irrigation,
                pump_runtime,
                fan_state
            ])

        # =========================
        # THINGSPEAK UPLOAD
        # =========================

        payload = {

            "api_key": WRITE_API_KEY,
            "field1": moisture,
            "field2": temp,
            "field3": humidity,
            "field4": pump_runtime,
            "field5": fan_state,
            "field6": dry_rate

        }

        try:

            requests.get(THINGSPEAK_URL, params=payload, timeout=5)

        except:

            print("ThingSpeak upload failed")

    except Exception as e:

        print("Main loop error:", e)

    time.sleep(INTERVAL)

