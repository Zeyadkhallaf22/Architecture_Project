import pandas as pd

# Replace with your file name
df = pd.read_csv("machine_usage_days_1_to_8_grouped_300_seconds.csv")

print(df.head())
print("\nColumns:")
print(df.columns)

print("\nDataset Shape:")
print(df.shape)

print("\nInformation:")
print(df.info())