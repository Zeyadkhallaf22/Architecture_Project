import pandas as pd

# ==========================
# 1. Load Dataset
# ==========================
df = pd.read_csv("instance_usage_grouped_300_seconds_month.csv")

print("Original Dataset Shape:", df.shape)

# ==========================
# 2. Remove extra spaces from column names
# ==========================
df.columns = df.columns.str.strip()

# ==========================
# 3. Check missing values
# ==========================
print("\nMissing Values:")
print(df.isnull().sum())

# Fill missing values with the median
df.fillna(df.median(numeric_only=True), inplace=True)

# ==========================
# 4. Remove duplicate rows
# ==========================
duplicates = df.duplicated().sum()
print("\nDuplicate Rows:", duplicates)

df.drop_duplicates(inplace=True)

# ==========================
# 5. Convert all columns to numeric
# ==========================
for col in df.columns:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Remove rows that became invalid
df.dropna(inplace=True)

# ==========================
# 6. Remove impossible values
# ==========================

# CPU should be between 0 and 1
df = df[(df["avg_cpu"] >= 0) & (df["avg_cpu"] <= 1)]

# Memory should be between 0 and 1
df = df[(df["avg_mem"] >= 0) & (df["avg_mem"] <= 1)]

# Assigned memory should be between 0 and 1
df = df[(df["avg_assigned_mem"] >= 0) & (df["avg_assigned_mem"] <= 1)]

# CPI should be positive
df = df[df["avg_cycles_per_instruction"] > 0]

# ==========================
# 7. Remove Outliers (IQR)
# ==========================
for col in df.columns:
    Q1 = df[col].quantile(0.25)
    Q3 = df[col].quantile(0.75)

    IQR = Q3 - Q1

    lower = Q1 - 1.5 * IQR
    upper = Q3 + 1.5 * IQR

    df = df[(df[col] >= lower) & (df[col] <= upper)]

# ==========================
# 8. Reset Index
# ==========================
df.reset_index(drop=True, inplace=True)

# ==========================
# 9. Save Clean Dataset
# ==========================
df.to_csv("cleaned_instance_usage.csv", index=False)

print("\nCleaning Finished Successfully!")
print("Clean Dataset Shape:", df.shape)

print("\nFirst 5 Rows:")
print(df.head())