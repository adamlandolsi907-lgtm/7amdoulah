import numpy as np
import time
import json
from collections import deque

# -----------------------------
# 1. SIMULATED DATA GENERATOR
# -----------------------------
def generate_sensor_data(t):
    noise = lambda scale: np.random.normal(0, scale)

    temp = 25 + 0.01*t + noise(0.3)
    humidity = 60 + noise(1.0)
    gas = 300 + 0.05*t + noise(5.0)
    flow = max(0, 1.2 + noise(0.2))

    # Inject occasional anomalies
    if np.random.rand() < 0.02:
        gas += 100  # spike
    if np.random.rand() < 0.01: 
        flow = 0  # dropout

    return {
        "temperature_raw": temp,
        "humidity_raw": humidity,
        "gas_raw": gas,
        "flow_raw": flow
    }

# -----------------------------
# 2. VALIDATION
# -----------------------------
def validate(data):
    if not (-20 <= data["temperature_raw"] <= 80):
        return None
    if not (0 <= data["humidity_raw"] <= 100):
        return None
    if data["flow_raw"] < 0:
        return None
    return data

# -----------------------------
# 3. SIMPLE 1D KALMAN FILTER
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

        # Prediction
        self.P = self.P + self.Q

        # Update
        K = self.P / (self.P + self.R)
        self.x = self.x + K * (measurement - self.x)
        self.P = (1 - K) * self.P

        return self.x

# -----------------------------
# 4. MOVING AVERAGE
# -----------------------------
class MovingAverage:
    def __init__(self, window=5):
        self.buffer = deque(maxlen=window)

    def update(self, value):
        self.buffer.append(value)
        return sum(self.buffer) / len(self.buffer)

# -----------------------------
# 5. INTERPOLATION BUFFER
# -----------------------------
class Interpolator:
    def __init__(self):
        self.prev = None

    def update(self, current):
        if self.prev is None:
            self.prev = current
            return current

        # Linear interpolation (midpoint)
        interp = {}
        for key in current:
            interp[key] = (self.prev[key] + current[key]) / 2

        self.prev = current
        return interp

# -----------------------------
# INITIALIZE FILTERS
# -----------------------------
kalman_temp = Kalman1D(Q=0.01, R=0.8)
kalman_gas = Kalman1D(Q=0.2, R=6.0)

ma_flow = MovingAverage(window=5)
interpolator = Interpolator()

prev_flow = None

# -----------------------------
# MAIN LOOP
# -----------------------------
for t in range(100):
    timestamp = time.time()

    # 1. Acquisition
    raw = generate_sensor_data(t)

    # 2. Validation
    valid = validate(raw)
    if valid is None:
        continue

    # 3. Temporal alignment (interpolation)
    aligned = interpolator.update(valid)

    # 4. Filtering
    temp_f = kalman_temp.update(aligned["temperature_raw"])
    gas_f = kalman_gas.update(aligned["gas_raw"])
    humidity_f = aligned["humidity_raw"]  # simple pass-through or EMA
    flow_s = ma_flow.update(aligned["flow_raw"])

    # 5. Sensor correction (fusion)
    a, b = 0.01, 0.005
    gas_corrected = gas_f / (1 + a*(temp_f - 25) + b*(humidity_f - 50))

    # 6. Virtual sensor (AQI)
    aqi = max(0, min(100, (gas_corrected - 200) / (800 - 200) * 100))

    # 7. Anomaly detection
    gas_spike = abs(aligned["gas_raw"] - gas_f) > 50

    flow_anomaly = False
    if prev_flow is not None:
        flow_anomaly = abs(flow_s - prev_flow) > 0.8
    prev_flow = flow_s

    # 8. Output JSON
    output = {
        "timestamp": timestamp,

        "temperature_raw": aligned["temperature_raw"],
        "temperature_filtered": temp_f,

        "humidity": humidity_f,

        "gas_raw": aligned["gas_raw"],
        "gas_filtered": gas_f,
        "gas_corrected": gas_corrected,

        "flow_raw": aligned["flow_raw"],
        "flow_smoothed": flow_s,

        "air_quality_index": aqi,

        "gas_spike": gas_spike,
        "flow_anomaly": flow_anomaly
    }

    print(json.dumps(output, indent=2))

    time.sleep(0.5)