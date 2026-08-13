import pandas as pd
import random

# =====================================================
# STEP 1 - Load Dataset
# =====================================================

file_name = "instance_usage_grouped_300_seconds_month.csv"

df = pd.read_csv(file_name)

print("=" * 60)
print("Loading Dataset...")
print("=" * 60)

print(df.head())
print("\nOriginal Shape:", df.shape)

# =====================================================
# STEP 2 - Clean Column Names
# =====================================================

df.columns = df.columns.str.strip()

# =====================================================
# STEP 3 - Handle Missing Values
# =====================================================

print("\nMissing Values")
print(df.isnull().sum())

df.fillna(df.median(numeric_only=True), inplace=True)

# =====================================================
# STEP 4 - Remove Duplicates
# =====================================================

duplicates = df.duplicated().sum()
print("\nDuplicate Rows:", duplicates)

df.drop_duplicates(inplace=True)

# =====================================================
# STEP 5 - Convert Columns to Numeric
# =====================================================

for col in df.columns:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df.dropna(inplace=True)

# =====================================================
# STEP 6 - Remove Impossible Values
# =====================================================

df = df[(df["avg_cpu"] >= 0) & (df["avg_cpu"] <= 1)]
df = df[(df["avg_mem"] >= 0) & (df["avg_mem"] <= 1)]
df = df[(df["avg_assigned_mem"] >= 0) & (df["avg_assigned_mem"] <= 1)]
df = df[df["avg_cycles_per_instruction"] > 0]

# =====================================================
# STEP 7 - Remove Outliers (IQR)
# =====================================================

for col in df.columns:

    Q1 = df[col].quantile(0.25)
    Q3 = df[col].quantile(0.75)

    IQR = Q3 - Q1

    lower = Q1 - 1.5 * IQR
    upper = Q3 + 1.5 * IQR

    df = df[(df[col] >= lower) & (df[col] <= upper)]

df.reset_index(drop=True, inplace=True)

print("\nShape After Cleaning:", df.shape)

# =====================================================
# STEP 8 - Dynamic Thresholds
# =====================================================

cpu95 = df["avg_cpu"].quantile(0.95)
cpu85 = df["avg_cpu"].quantile(0.85)

mem95 = df["avg_mem"].quantile(0.95)
mem85 = df["avg_mem"].quantile(0.85)

assign95 = df["avg_assigned_mem"].quantile(0.95)

cpi95 = df["avg_cycles_per_instruction"].quantile(0.95)

print("\nThresholds")
print("----------------------")
print("CPU95 :", cpu95)
print("CPU85 :", cpu85)
print("MEM95 :", mem95)
print("MEM85 :", mem85)
print("ASSIGN95 :", assign95)
print("CPI95 :", cpi95)

# =====================================================
# STEP 9 - Create Alarm Labels
# =====================================================

def create_alarm(row):

    if row["avg_cpu"] >= cpu95 and row["avg_mem"] >= mem95:
        return "Server Failure"

    elif row["avg_cpu"] >= cpu95:
        return "High CPU"

    elif row["avg_mem"] >= mem95:
        return "High Memory"

    elif row["avg_assigned_mem"] >= assign95:
        return "Memory Allocation"

    elif row["avg_cycles_per_instruction"] >= cpi95:
        return "CPU Bottleneck"

    elif row["avg_cpu"] >= cpu85 or row["avg_mem"] >= mem85:
        return "Warning"

    else:
        return "Normal"

df["Alarm"] = df.apply(create_alarm, axis=1)

# =====================================================
# STEP 10 - Severity
# =====================================================

severity = {
    "Normal": "Low",
    "Warning": "Medium",
    "High CPU": "High",
    "High Memory": "High",
    "Memory Allocation": "High",
    "CPU Bottleneck": "High",
    "Server Failure": "Critical"
}

df["Severity"] = df["Alarm"].map(severity)

# =====================================================
# STEP 11 - Status
# =====================================================

def server_status(alarm):

    if alarm == "Server Failure":
        return "Offline"

    elif alarm == "Normal":
        return "Online"

    elif alarm == "Warning":
        return "Warning"

    else:
        return "Degraded"

df["Status"] = df["Alarm"].apply(server_status)

# =====================================================
# STEP 12 - Server IDs
# =====================================================

servers = [f"SRV-{i:03}" for i in range(1, 21)]

df["Server_ID"] = [
    random.choice(servers)
    for _ in range(len(df))
]

# =====================================================
# STEP 13 - Rack IDs
# =====================================================

racks = [
    "Rack-A",
    "Rack-B",
    "Rack-C",
    "Rack-D"
]

df["Rack"] = [
    random.choice(racks)
    for _ in range(len(df))
]

# =====================================================
# STEP 14 - Temperature
# =====================================================

df["Temperature"] = (
    25 + df["avg_cpu"] * 55
).round(1)

# =====================================================
# STEP 15 - Timestamp
# =====================================================

df["Timestamp"] = pd.date_range(
    start="2026-01-01",
    periods=len(df),
    freq="5min"
)

# =====================================================
# STEP 16 - Reorder Columns
# =====================================================

df = df[
    [
        "Timestamp",
        "Server_ID",
        "Rack",
        "avg_cpu",
        "avg_mem",
        "avg_assigned_mem",
        "avg_cycles_per_instruction",
        "Temperature",
        "Alarm",
        "Severity",
        "Status"
    ]
]

# =====================================================
# STEP 17 - Display Alarm Distribution
# =====================================================

print("\nAlarm Distribution")
print("=" * 60)
print(df["Alarm"].value_counts())

# =====================================================
# STEP 18 - Save Dataset
# =====================================================

output = "DataCenter_AI_Dataset.csv"

df.to_csv(output, index=False)

print("\nDataset Saved Successfully!")
print(output)

print("\nFinal Shape:", df.shape)

print("\nPreview:")
print(df.head())