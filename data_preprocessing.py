#!/usr/bin/env python3
import argparse
import json
import random
import sys
import time
import uuid
import hashlib
import logging
import signal
from collections import deque
from datetime import datetime, timezone

import numpy as np
import paho.mqtt.client as mqtt

try:
    import adafruit_dht
    import board
except ImportError:
    adafruit_dht = None
    board = None

try:
    from gpiozero import DigitalInputDevice
except ImportError:
    DigitalInputDevice = None


DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "factory/sensors/pi-01"
DEFAULT_DEVICE_IDS = ["pi-01"]
DEFAULT_INTERVAL_SEC = 2.0
DEFAULT_GPIO_PIN = 4
DEFAULT_GAS_GPIO_PIN = 17
DEFAULT_FLOW_GPIO_PIN = 27

TEMP_RANGE = (-20.0, 80.0)
HUM_RANGE = (0.0, 100.0)
GAS_RANGE = (200.0, 2000.0)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


# -----------------------------
# PIPELINE: SIGNAL PROCESSING
# -----------------------------

class Kalman1D:
    def __init__(self, Q=0.01, R=1.0):
        self.Q = Q
        self.R = R
        self.x = None
        self.P = 1.0

    def update(self, measurement):
        if self.x is None:
            self.x = measurement
        self.P = self.P + self.Q
        K = self.P / (self.P + self.R)
        self.x = self.x + K * (measurement - self.x)
        self.P = (1 - K) * self.P
        return self.x


class MovingAverage:
    def __init__(self, window=5):
        self.buffer = deque(maxlen=window)

    def update(self, value):
        self.buffer.append(value)
        return sum(self.buffer) / len(self.buffer)


class Interpolator:
    def __init__(self):
        self.prev = None

    def update(self, current):
        if self.prev is None:
            self.prev = current
            return current
        interp = {k: (self.prev[k] + current[k]) / 2 for k in current}
        self.prev = current
        return interp


# Module-level pipeline state (persistent across loop iterations)
_kalman_temp = Kalman1D(Q=0.01, R=0.8)
_kalman_gas = Kalman1D(Q=0.2, R=6.0)
_ma_flow = MovingAverage(window=5)
_interpolator = Interpolator()
_prev_flow_smoothed = None


def process_pipeline(sensor_data):
    """Apply temporal alignment, filtering, sensor fusion, AQI, and anomaly detection."""
    global _prev_flow_smoothed

    raw = {
        "temperature_raw": sensor_data["temperature_c"],
        "humidity_raw": sensor_data["humidity_percent"],
        "gas_raw": sensor_data["gas_ppm"],
        "flow_raw": sensor_data.get("flow_raw", 0.0),
    }

    # Temporal alignment (linear interpolation between frames)
    aligned = _interpolator.update(raw)

    # Filtering
    temp_f = _kalman_temp.update(aligned["temperature_raw"])
    gas_f = _kalman_gas.update(aligned["gas_raw"])
    humidity_f = aligned["humidity_raw"]
    flow_s = _ma_flow.update(aligned["flow_raw"])

    # Gas correction with temperature and humidity compensation
    a, b = 0.01, 0.005
    denom = 1 + a * (temp_f - 25) + b * (humidity_f - 50)
    gas_corrected = gas_f / denom if denom != 0 else gas_f

    # Virtual sensor: Air Quality Index mapped to 0–100
    aqi = max(0.0, min(100.0, (gas_corrected - 200) / (800 - 200) * 100))

    # Anomaly detection
    gas_spike = bool(abs(aligned["gas_raw"] - gas_f) > 50)
    flow_anomaly = False
    if _prev_flow_smoothed is not None:
        flow_anomaly = bool(abs(flow_s - _prev_flow_smoothed) > 0.)
    _prev_flow_smoothed = flow_s

    return {
        "temperature_filtered": round(temp_f, 4),
        "gas_filtered": round(gas_f, 4),
        "gas_corrected": round(gas_corrected, 4),
        "flow_raw": round(aligned["flow_raw"], 4),
        "flow_smoothed": round(flow_s, 4),
        "air_quality_index": round(aqi, 2),
        "gas_spike": gas_spike,
        "flow_anomaly": flow_anomaly,
    }


# -----------------------------
# MQTT INFRASTRUCTURE
# -----------------------------

class OfflineBuffer:
    def __init__(self, maxlen=500):
        self._buffer = deque(maxlen=maxlen)

    def push(self, topic, payload):
        self._buffer.append((topic, payload))

    def has_items(self):
        return len(self._buffer) > 0

    def pop_left(self):
        return self._buffer.popleft()

    def size(self):
        return len(self._buffer)


class IoTPublisher:
    def __init__(self, client, default_topic, qos, buffer_obj):
        self.client = client
        self.default_topic = default_topic
        self.qos = qos
        self.buffer = buffer_obj

    def publish(self, payload, override_topic=None):
        target_topic = override_topic if override_topic else self.default_topic

        if not self.client.is_connected():
            self.buffer.push(target_topic, payload)
            logging.warning(f"Publish failed: not connected. Buffered for {target_topic}")
            return False

        result = self.client.publish(target_topic, payload, qos=self.qos)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            self.buffer.push(target_topic, payload)
            logging.error(f"Publish failed (rc={result.rc}). Buffered for {target_topic}")
            return False

        logging.info(f"Published to {target_topic}: {payload}")
        return True

    def buffer_handler(self):
        if not self.client.is_connected():
            return

        while self.buffer.has_items():
            topic, payload = self.buffer.pop_left()
            result = self.client.publish(topic, payload, qos=self.qos)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                self.buffer.push(topic, payload)
                logging.error(f"Buffer resend failed (rc={result.rc}). Stopping flush.")
                break
            logging.info(f"Replayed from buffer to {topic}: {payload}")


# -----------------------------
# SENSOR READING
# -----------------------------

class FlowCounter:
    def __init__(self, device):
        self.device = device
        self.count = 0
        if self.device is not None:
            self.device.when_activated = self._on_pulse

    def _on_pulse(self):
        self.count += 1

    def consume(self):
        count = self.count
        self.count = 0
        return count


def read_dht11_circuitpython(device, retries=3, delay=0.5):
    if device is None:
        return None, None

    for _ in range(retries):
        try:
            temperature = device.temperature
            humidity = device.humidity
        except (RuntimeError, OSError):
            temperature = None
            humidity = None

        if temperature is not None and humidity is not None:
            return float(temperature), float(humidity)
        time.sleep(delay)
    return None, None


def read_gas_simulated():
    gas = round(random.uniform(GAS_RANGE[0], GAS_RANGE[1]), 2)
    if random.random() < 0.02:
        gas = min(gas + 100, GAS_RANGE[1])
    return gas


def read_gas_digital(device, active_low, ppm_low, ppm_high):
    value = bool(device.value)
    gas_detected = (not value) if active_low else value
    return float(ppm_high if gas_detected else ppm_low)


def read_sensors(args, gas_device, dht_device, flow_counter):
    temperature = None
    humidity = None
    if not args.gas_only:
        temperature, humidity = read_dht11_circuitpython(dht_device)
        if temperature is None or humidity is None and args.simulate:
            temperature = round(random.uniform(15.0, 35.0), 2)
            humidity = round(random.uniform(30.0, 70.0), 2)
        if temperature is None or humidity is None:
            logging.warning("Sensor read failed: DHT11 unavailable")
    else:
        temperature = 0.0
        humidity = 0.0

    if args.simulate:
        gas_ppm = read_gas_simulated()
        flow_raw = round(max(0.0, float(np.random.normal(1.2, 0.2))), 4)
        if random.random() < 0.01:
            flow_raw = 0.0
    else:
        if gas_device is None:
            gas_ppm = None
            logging.warning("Sensor read failed: gas device unavailable")
        else:
            gas_ppm = read_gas_digital(
                gas_device,
                args.gas_active_low,
                GAS_RANGE[0],
                GAS_RANGE[1],
            )
        if flow_counter is None:
            flow_raw = 0.0
        else:
            pulse_count = flow_counter.consume()
            flow_raw = float(pulse_count) / max(args.interval, 0.001)

    return {
        "temperature_c": float(temperature) if temperature is not None else None,
        "humidity_percent": float(humidity) if humidity is not None else None,
        "gas_ppm": float(gas_ppm) if gas_ppm is not None else None,
        "flow_raw": flow_raw,
    }


def validate(data):
    temp_ok = TEMP_RANGE[0] <= data["temperature_c"] <= TEMP_RANGE[1]
    hum_ok = HUM_RANGE[0] <= data["humidity_percent"] <= HUM_RANGE[1]
    gas_ok = GAS_RANGE[0] <= data["gas_ppm"] <= GAS_RANGE[1]
    flow_ok = data.get("flow_raw", 0.0) >= 0
    return temp_ok and hum_ok and gas_ok and flow_ok


def build_payload(device_id, data, pipeline_data, include_alert, is_invalid=False):
    msg_id = uuid.uuid4().hex
    raw_values = f"{data['temperature_c']}_{data['humidity_percent']}_{data['gas_ppm']}"
    checksum = hashlib.sha256(raw_values.encode('utf-8')).hexdigest()[:16]

    payload = {
        "message_id": msg_id,
        "device_id": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # Raw sensor readings
        "temperature_c": data["temperature_c"],
        "humidity_percent": data["humidity_percent"],
        "gas_ppm": data["gas_ppm"],
        # Processed pipeline outputs
        **pipeline_data,
        "checksum": checksum,
        "status": "fault" if is_invalid else "active",
    }

    if include_alert and not is_invalid and data["temperature_c"] > 50.0:
        payload["alert"] = "temp_high"

    return json.dumps(payload)


# -----------------------------
# MQTT CALLBACKS
# -----------------------------

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT broker")
    else:
        logging.error(f"Connect failed with code rc={rc}")


def on_disconnect(client, userdata, rc):
    if rc != 0:
        logging.warning(f"Unexpected disconnect rc={rc}, reconnecting...")
    else:
        logging.info("Disconnected gracefully")


def parse_args():
    parser = argparse.ArgumentParser(description="IoT sensor MQTT publisher")
    parser.add_argument("--broker", default=DEFAULT_BROKER)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--device-ids", default=",".join(DEFAULT_DEVICE_IDS))
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    parser.add_argument("--gpio-pin", type=int, default=DEFAULT_GPIO_PIN)
    parser.add_argument("--gas-gpio-pin", type=int, default=DEFAULT_GAS_GPIO_PIN)
    parser.add_argument("--flow-gpio-pin", type=int, default=DEFAULT_FLOW_GPIO_PIN)
    parser.add_argument("--gas-active-low", action="store_true")
    parser.add_argument("--gas-pull-up", action="store_true")
    parser.add_argument("--flow-pull-up", action="store_true")
    parser.add_argument("--gas-only", action="store_true")
    parser.add_argument("--qos", type=int, default=1)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--include-alert", action="store_true")
    return parser.parse_args()


def resolve_board_pin(gpio_pin):
    if board is None:
        return None
    attr = f"D{gpio_pin}"
    return getattr(board, attr, None)


def main():
    args = parse_args()
    device_ids = [d.strip() for d in args.device_ids.split(",") if d.strip()]
    if not device_ids:
        logging.error("No device ids provided")
        return 1

    dht_device = None
    if not args.simulate and not args.gas_only and adafruit_dht is not None and board is not None:
        try:
            pin = resolve_board_pin(args.gpio_pin)
            if pin is None:
                logging.error(f"Unsupported gpio pin for circuitpython dht: {args.gpio_pin}")
            else:
                dht_device = adafruit_dht.DHT11(pin, use_pulseio=False)
        except Exception as exc:
            logging.error(f"Failed to init circuitpython dht: {exc}")

    gas_device = None
    flow_device = None
    flow_counter = None
    if not args.simulate:
        if DigitalInputDevice is None:
            logging.error("gpiozero not available; install gpiozero or use --simulate")
            return 1
        gas_device = DigitalInputDevice(args.gas_gpio_pin, pull_up=args.gas_pull_up)
        flow_device = DigitalInputDevice(args.flow_gpio_pin, pull_up=args.flow_pull_up)
        flow_counter = FlowCounter(flow_device)

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    lwt_payload = json.dumps({"device_id": device_ids[0], "status": "offline"})
    client.will_set(args.topic, payload=lwt_payload, qos=1, retain=False)
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    def signal_handler(sig, frame):
        logging.info("Shutting down gracefully...")
        client.loop_stop()
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        client.connect(args.broker, args.port, keepalive=30)
    except Exception as exc:
        logging.error(f"Initial connect failed: {exc}")

    client.loop_start()

    buffer_obj = OfflineBuffer()
    publisher = IoTPublisher(client, args.topic, args.qos, buffer_obj)

    invalid_topic = f"{args.topic}/invalid"
    last_good = {}

    logging.info(f"Starting sensor loop. Publishing to {args.topic}")

    while True:
        sensor_data = read_sensors(args, gas_device, dht_device, flow_counter)
        missing = [k for k, v in sensor_data.items() if v is None]

        if missing:
            for key in missing:
                if key in last_good:
                    sensor_data[key] = last_good[key]

            still_missing = [k for k, v in sensor_data.items() if v is None]
            if still_missing:
                logging.warning(f"Skipping publish, missing data: {', '.join(still_missing)}")
                time.sleep(args.interval)
                continue

        is_invalid = not validate(sensor_data)

        if is_invalid:
            logging.warning("Invalid data detected, routing to invalid bucket.")
        else:
            last_good.update(sensor_data)

        pipeline_data = process_pipeline(sensor_data)

        if pipeline_data["gas_spike"]:
            logging.warning("Anomaly detected: gas spike")
        if pipeline_data["flow_anomaly"]:
            logging.warning("Anomaly detected: flow anomaly")

        for device_id in device_ids:
            payload = build_payload(
                device_id, sensor_data, pipeline_data,
                args.include_alert, is_invalid=is_invalid
            )

            if is_invalid:
                publisher.publish(payload, override_topic=invalid_topic)
            else:
                publisher.publish(payload)

        publisher.buffer_handler()
        time.sleep(args.interval)

if __name__ == "__main__":
    sys.exit(main())