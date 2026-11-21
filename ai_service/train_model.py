"""
train_model.py

AI Model Training Service
Data Source: SQL Server DataCenterKPI.ServerHistory

Purpose:
Predict future CPU usage based on server metrics.
"""

import pandas as pd
import joblib
from pathlib import Path

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

from database import load_training_data


# =====================================
# LOAD DATA
# =====================================

print("Loading training data...")

df = load_training_data()


if df.empty:
    raise Exception("No data found in ServerHistory table")


print("\nDataset Preview:")
print(df.head())


# =====================================
# DATA CLEANING
# =====================================

print("\nCleaning data...")


# Remove rows with missing values

df = df.dropna()


# Sort by server and time

df = df.sort_values(
    [
        "ServerNumber",
        "RecordedAt"
    ]
)


# =====================================
# CREATE AI TARGET
# =====================================

"""
The AI learns:

Current server condition
        |
        ↓
Future CPU usage


Example:

CPU now = 60%
Temperature = 65

AI predicts:
CPU after next reading = 75%
"""


df["Future_CPU"] = (
    df.groupby("ServerNumber")
    ["CPU_Percent"]
    .shift(-1)
)


# Remove last row of each server
# because it has no future value

df = df.dropna()


# =====================================
# FEATURES
# =====================================

features = [

    "CPU_Percent",
    "RAM_Percent",
    "Disk_Percent",
    "Temperature_C",
    "Network_Mbps",
    "Latency_ms",
    "Status"

]


X = df[features]

y = df["Future_CPU"]



# =====================================
# TRAIN TEST SPLIT
# =====================================

X_train, X_test, y_train, y_test = train_test_split(

    X,
    y,
    test_size=0.2,
    random_state=42

)


# =====================================
# SCALING
# =====================================

print("\nScaling data...")


scaler = StandardScaler()


X_train_scaled = scaler.fit_transform(X_train)

X_test_scaled = scaler.transform(X_test)



# =====================================
# TRAIN MODEL
# =====================================

print("\nTraining AI model...")


model = RandomForestRegressor(

    n_estimators=200,
    random_state=42

)


model.fit(

    X_train_scaled,
    y_train

)



# =====================================
# TEST MODEL
# =====================================

prediction = model.predict(
    X_test_scaled
)


mae = mean_absolute_error(

    y_test,
    prediction

)


r2 = r2_score(

    y_test,
    prediction

)


print("\n========== MODEL RESULT ==========")

print(
    "Mean Absolute Error:",
    mae
)

print(
    "Accuracy Score:",
    r2
)



# =====================================
# SAVE MODEL
# =====================================

joblib.dump(

    model,
    Path(__file__).resolve().parents[1] / "models" / "model.pkl"

)


joblib.dump(

    scaler,
    Path(__file__).resolve().parents[1] / "models" / "scaler.pkl"

)


print("\nAI Model saved successfully!")

print("Created:")
print("models/model.pkl")
print("models/scaler.pkl")