import os
import pandas as pd
import numpy as np

DATA_DIR = "data/condition+monitoring+of+hydraulic+systems"
OUTPUT = "data/processed_hydraulic.csv"

sensors = [
    "PS1", "PS2", "PS3", "PS4", "PS5", "PS6",
    "FS1", "FS2",
    "TS1", "TS2", "TS3", "TS4",
    "VS1", "CE", "CP", "SE"
]

features = {}

for sensor in sensors:
    path = os.path.join(DATA_DIR, sensor + ".txt")
    data = pd.read_csv(path, sep="\t", header=None)

    features[sensor + "_mean"] = data.mean(axis=1)
    features[sensor + "_std"] = data.std(axis=1)
    features[sensor + "_min"] = data.min(axis=1)
    features[sensor + "_max"] = data.max(axis=1)

X = pd.DataFrame(features)

profile = pd.read_csv(
    os.path.join(DATA_DIR, "profile.txt"),
    sep=r"\s+",
    header=None
)

profile.columns = [
    "cooler_condition",
    "valve_condition",
    "pump_leakage",
    "accumulator_pressure",
    "stable"
]

df = pd.concat([X, profile], axis=1)

os.makedirs("data", exist_ok=True)
df.to_csv(OUTPUT, index=False)

print("Preprocessing completed.")
print("Dataset shape:", df.shape)
print("\nFirst 5 rows:")
print(df.head())
print("\nSaved to:", OUTPUT)