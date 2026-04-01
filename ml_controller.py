import time
import smbus
import board
import adafruit_dht
import requests
import RPi.GPIO as GPIO
import csv
import joblib
import numpy as np
from datetime import datetime

# =========================
# THINGSPEAK CONFIG
# =========================

WRITE_API_KEY = "" #here goes the channel write api key
THINGSPEAK_URL = "https://api.thingspeak.com/update"

# =========================
# LOAD ML MODELS
# =========================

runtime_model = joblib.load("pump_runtime_model.pkl")
time_model = joblib.load("next_irrigation_model.pkl")
scaler = joblib.load("irrigation_scaler.pkl")

# =========================
# HARDWARE CONFIG
# =========================

ADC_ADDR = 0x48

RELAY_PIN = 17
FAN_PIN = 27

INTERVAL = 15
FLOW_RATE = 3.75

GPIO.setmode(GPIO.BCM)

GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.setup(FAN_PIN, GPIO.OUT)

GPIO.output(RELAY_PIN, GPIO.HIGH)
GPIO.output(FAN_PIN, GPIO.LOW)

bus = smbus.SMBus(1)
time.sleep(2)

dht = adafruit_dht.DHT11(board.D4, use_pulseio=False)

previous_moisture = None

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
            "predicted_runtime",
            "predicted_next_irrigation",
            "actual_runtime",
            "fan_state"
        ])

# =========================
# MOISTURE SENSOR
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
# DHT11 SENSOR
# =========================

def read_dht():

    for i in range(3):

        try:

            temp = dht.temperature
            humidity = dht.humidity

            if temp is not None and humidity is not None:
                return temp, humidity

        except RuntimeError:
            time.sleep(1)

        except Exception:
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
# FAN CONTROL
# =========================

def control_fan(temp, hum):

    fan_state = 0

    if temp > 30 or hum > 80:

        GPIO.output(FAN_PIN, GPIO.HIGH)
        fan_state = 1

    else:

        GPIO.output(FAN_PIN, GPIO.LOW)
        fan_state = 0

    return fan_state


# =========================
# MAIN LOOP
# =========================

print("Smart Irrigation ML Controller Started")

while True:

    try:

        now = datetime.now()
        hour = now.hour + now.minute / 60

        soil = read_moisture()

        if soil is None:
            time.sleep(2)
            continue

        temp, hum = read_dht()

        if temp is None:
            continue

        # =========================
        # DRY RATE
        # =========================

        if previous_moisture is None:
            dry_rate = 0
        else:
            dry_rate = previous_moisture - soil

        previous_moisture = soil

        # =========================
        # ML FEATURE VECTOR
        # =========================

        sample = [[soil, temp, hum, dry_rate, hour]]

        sample_scaled = scaler.transform(sample)

        pred_runtime = runtime_model.predict(sample_scaled)[0]
        pred_next = time_model.predict(sample_scaled)[0]

        pred_runtime = max(pred_runtime, 0)

        # =========================
        # IRRIGATION ACTUATION
        # =========================

        actual_runtime = 0

        if soil < 30:

            actual_runtime = round(pred_runtime, 2)

            print("Running pump:", actual_runtime)

            run_pump(actual_runtime)

        # =========================
        # FAN CONTROL
        # =========================

        fan_state = control_fan(temp, hum)

        # =========================
        # PRINT STATUS
        # =========================

        print("-----------")
        print("Time:", now)
        print("Soil:", soil)
        print("Temp:", temp)
        print("Humidity:", hum)
        print("Dry rate:", dry_rate)
        print("Pred Runtime:", pred_runtime)
        print("Next Irrigation:", pred_next)
        print("Fan State:", "ON" if fan_state else "OFF")

        # =========================
        # SAVE DATASET
        # =========================

        with open(filename, "a", newline="") as f:

            writer = csv.writer(f)

            writer.writerow([
                now,
                soil,
                temp,
                hum,
                hour,
                dry_rate,
                pred_runtime,
                pred_next,
                actual_runtime,
                fan_state
            ])

        # =========================
        # THINGSPEAK UPLOAD
        # =========================

        payload = {

            "api_key": WRITE_API_KEY,

            "field1": soil,
            "field2": temp,
            "field3": hum,
            "field4": actual_runtime,
            "field5": fan_state,
            "field6": dry_rate,
            "field7": pred_runtime,
            "field8": pred_next
        }

        try:

            requests.get(THINGSPEAK_URL, params=payload, timeout=5)

        except:

            print("ThingSpeak upload failed")

    except Exception as e:

        print("Main loop error:", e)

    time.sleep(INTERVAL)



