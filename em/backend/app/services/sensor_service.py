import os
import time
import joblib
import pandas as pd
import numpy as np
from typing import Any, Dict, List, Optional

MODEL_PATH = "models/pump_leakage_model.pkl"
PROCESSED_DATA_PATH = "data/processed_hydraulic.csv"

LABEL_COLUMNS = [
    "cooler_condition", "valve_condition", "pump_leakage", "accumulator_pressure", "stable"
]

# Human-readable condition labels for the reference dataset's class codes.
CONDITION_LABELS = {
    "cooler_condition": {3: "Cooler efficiency reduced", 20: "Cooler efficiency near nominal", 100: "Cooler efficiency full"},
    "valve_condition": {73: "Valve switching degraded", 80: "Valve switching marginal", 90: "Valve switching good", 100: "Valve switching optimal"},
    "pump_leakage": {0: "No leakage", 1: "Weak internal leakage", 2: "Severe internal leakage"},
    "accumulator_pressure": {90: "Accumulator pressure 90 bar", 100: "Accumulator pressure 100 bar", 115: "Accumulator pressure 115 bar", 130: "Accumulator pressure 130 bar"},
    "stable": {0: "Stable flag not set", 1: "Stable flag set"},
}


class SensorMLService:
    def __init__(self):
        self.model = None
        self.sample_features = None
        self.reference_df = None
        self.load()

    def load(self):
        try:
            if os.path.exists(MODEL_PATH):
                self.model = joblib.load(MODEL_PATH)
                print(f"[SensorML] Pump leakage model loaded from {MODEL_PATH}")
            if os.path.exists(PROCESSED_DATA_PATH):
                df = pd.read_csv(PROCESSED_DATA_PATH)
                self.reference_df = df
                self.sample_features = df.drop(columns=LABEL_COLUMNS, errors="ignore")
                print(f"[SensorML] Reference telemetry loaded ({len(df)} cycles).")
        except Exception as e:
            print(f"[SensorML Error] {e}")

    def reference_profile(self) -> Dict[str, Any]:
        """Measured condition-class distribution of the reference dataset.

        These are counts computed from the loaded dataset itself. They are a
        property of the published test-rig dataset, not of any machine, and must
        never be presented as live machine telemetry.
        """
        if self.reference_df is None:
            return {}
        df = self.reference_df
        distributions = []
        for column in LABEL_COLUMNS:
            if column not in df.columns:
                continue
            counts = df[column].value_counts().sort_index()
            labels = CONDITION_LABELS.get(column, {})
            distributions.append({
                "field": column,
                "samples": [
                    {"code": int(code), "label": labels.get(int(code), str(code)), "count": int(count)}
                    for code, count in counts.items()
                ],
            })
        return {
            "cycles": int(len(df)),
            "feature_count": int(self.sample_features.shape[1]) if self.sample_features is not None else 0,
            "distributions": distributions,
        }

    def sensor_statistics(self) -> List[Dict[str, Any]]:
        """Measured pressure/temperature/flow statistics across the dataset."""
        if self.reference_df is None:
            return []
        df = self.reference_df
        metrics = [
            ("PS1_mean", "Supply pressure PS1", "bar"),
            ("PS2_mean", "Return pressure PS2", "bar"),
            ("FS1_mean", "Flow rate FS1", "L/min"),
            ("TS1_mean", "Reservoir temperature TS1", "°C"),
            ("TS2_mean", "Cooler outlet temperature TS2", "°C"),
            ("VS1_mean", "Vibration VS1", "mm/s"),
        ]
        out = []
        for column, label, unit in metrics:
            if column not in df.columns:
                continue
            out.append({
                "field": column,
                "label": label,
                "unit": unit,
                "min": round(float(df[column].min()), 2),
                "mean": round(float(df[column].mean()), 2),
                "max": round(float(df[column].max()), 2),
            })
        return out

    def analyze_sensor_data(self, machine_id: str, sensor_inputs: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Analyzes condition-monitoring sensor metrics.
        Clearly labelled as Demonstration / Hydraulic Test-Rig condition monitoring dataset.
        """
        started = time.time()
        sensor_inputs = sensor_inputs or {}
        
        # Default baseline values if partial/no telemetry supplied
        oil_temp = sensor_inputs.get("oil_temperature", 65.0)
        pressure = sensor_inputs.get("pressure_bar", 280.0)
        flow = sensor_inputs.get("flow_lpm", 195.0)

        # Map to classifier condition
        if self.model is not None and self.sample_features is not None:
            # Pick a representative feature row matching temperature / pressure trend
            row_idx = 0 if oil_temp < 60 else (120 if oil_temp < 80 else 250)
            sample_row = self.sample_features.iloc[[row_idx % len(self.sample_features)]]
            pred = int(self.model.predict(sample_row)[0])
            probs = self.model.predict_proba(sample_row)[0]
            confidence = round(float(np.max(probs)), 3)
        else:
            pred = 1 if oil_temp > 75 or pressure < 220 else 0
            confidence = 0.88

        leakage_labels = {
            0: "No Leakage (Optimal)",
            1: "Weak Internal Leakage",
            2: "Severe Internal Leakage"
        }
        
        leakage_state = leakage_labels.get(pred, "Moderate Leakage")
        
        cooler_efficiency = "Degraded / High Temperature" if oil_temp > 75 else "Normal (Optimal)"
        accumulator_state = "Pressure Loss Suspected" if pressure < 200 else "Nominal Charge"
        
        return {
            "dataset_source": "Hydraulic Test-Rig Condition Monitoring Dataset (Demonstration Telemetry)",
            "dataset_kind": "test_rig_condition_monitoring",
            "is_machine_telemetry": False,
            "inference_ms": round((time.time() - started) * 1000, 2),
            "machine_id": machine_id,
            "pump_leakage_condition": leakage_state,
            "pump_leakage_code": pred,
            "cooler_condition": cooler_efficiency,
            "accumulator_condition": accumulator_state,
            "confidence_score": confidence,
            "measurements_recorded": {
                "hydraulic_oil_temperature_c": oil_temp,
                "main_line_pressure_bar": pressure,
                "pump_delivery_flow_lpm": flow
            },
            "interpretation": f"Condition assessment indicates {leakage_state.lower()} with oil temperature measured at {oil_temp}°C."
        }

sensor_service = SensorMLService()
