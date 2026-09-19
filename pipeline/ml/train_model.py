"""Train the optional classifier without leaking repeated locations across splits."""

import argparse
from pathlib import Path
import sys

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ml.features import location_id_for

FEATURES = ["distance_m", "facility_type", "frp", "persistence_count", "hour", "month"]
MODEL_PATH = Path(__file__).with_name("fire_classifier.pkl")


def build_features(frame):
    """Return normalized model features and location groups from historical rows."""
    data = frame.copy()
    if "location_id" not in data:
        data["location_id"] = [location_id_for(a, b) for a, b in zip(data["lat"], data["lon"])]
    else:
        missing = data["location_id"].isna() | (data["location_id"].astype(str) == "")
        data.loc[missing, "location_id"] = [
            location_id_for(a, b) for a, b in zip(data.loc[missing, "lat"], data.loc[missing, "lon"])
        ]
    def column(name, default):
        return data[name] if name in data else pd.Series(default, index=data.index)

    data["distance_m"] = pd.to_numeric(column("distance_m", 999999), errors="coerce").fillna(999999)
    data["frp"] = pd.to_numeric(column("frp", column("brightness", 0)), errors="coerce").fillna(0)
    data["persistence_count"] = pd.to_numeric(column("persistence_count", 0), errors="coerce").fillna(0)
    data["facility_type"] = column("facility_type", column("nearest_facility", "unknown")).fillna("unknown")
    timestamp = pd.to_datetime(column("acq_date", None), errors="coerce")
    data["month"] = timestamp.dt.month.fillna(0).astype(int)
    acq_time = column("acq_time", 0).astype(str).str.zfill(4)
    data["hour"] = pd.to_numeric(acq_time.str[:2], errors="coerce").fillna(0).clip(0, 23)
    return data[FEATURES], data["classification"].astype(str), data["location_id"].astype(str)


def load_history(csv_path=None):
    if csv_path:
        return pd.read_csv(csv_path)
    from pipeline.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Set Supabase credentials or supply --csv")
    return pd.DataFrame(create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).table("hotspots").select("*").execute().data)


def train(frame):
    X, y, groups = build_features(frame)
    if len(X) < 2 or y.nunique() < 2 or groups.nunique() < 2:
        raise ValueError("Need at least two labels and two distinct location groups to train")
    # Groups prevent separate visits to one real-world location leaking into both sets.
    train_idx, test_idx = next(GroupShuffleSplit(test_size=0.25, random_state=42).split(X, y, groups))
    preprocess = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median"), ["distance_m", "frp", "persistence_count", "hour", "month"]),
        ("facility", Pipeline([("fill", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), ["facility_type"]),
    ])
    model = Pipeline([("features", preprocess), ("classifier", RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced"))])
    model.fit(X.iloc[train_idx], y.iloc[train_idx])
    predicted = model.predict(X.iloc[test_idx])
    print("Accuracy:", round(accuracy_score(y.iloc[test_idx], predicted), 4))
    print("Per-class F1:\n", classification_report(y.iloc[test_idx], predicted, zero_division=0))
    print("Confusion matrix (rows=true, columns=predicted):\n", confusion_matrix(y.iloc[test_idx], predicted))
    model.fit(X, y)
    joblib.dump(model, MODEL_PATH)
    print(f"Saved final model trained on all {len(X)} rows to {MODEL_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="Historical hotspot CSV; otherwise query Supabase")
    train(load_history(parser.parse_args().csv))
