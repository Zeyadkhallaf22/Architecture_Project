"""
database.py
-----------------------------------
Handles SQL Server connection and
retrieves historical/live server data.
"""

import pyodbc
import pandas as pd

# =====================================
# SQL SERVER CONNECTION
# =====================================

SERVER = r"MARIAM\MSSQLSERVER03"
DATABASE = "DataCenterKPI"

CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    "Trusted_Connection=yes;"
)

# =====================================
# CONNECT
# =====================================

def get_connection():
    """
    Returns an active SQL Server connection.
    """
    return pyodbc.connect(CONNECTION_STRING)


# =====================================
# LOAD TRAINING DATA
# =====================================

def load_training_data():
    """
    Loads all historical server values.
    """

    query = """
    SELECT
        ServerNumber,
        CPU_Percent,
        RAM_Percent,
        Disk_Percent,
        Temperature_C,
        Network_Mbps,
        Latency_ms,
        Status,
        RecordedAt
    FROM ServerHistory
    ORDER BY RecordedAt;
    """

    conn = get_connection()

    df = pd.read_sql(query, conn)

    conn.close()

    return df


# =====================================
# LOAD CURRENT SERVER STATE
# =====================================

def load_current_state():

    query = """
    SELECT
        ServerNumber,
        CPU_Percent,
        RAM_Percent,
        Disk_Percent,
        Temperature_C,
        Network_Mbps,
        Latency_ms,
        Status
    FROM CurrentServerState
    ORDER BY ServerNumber;
    """

    conn = get_connection()

    df = pd.read_sql(query, conn)

    conn.close()

    return df


# =====================================
# LOAD SERVER HISTORY
# =====================================

def load_server_history(server_number):

    query = f"""
    SELECT *
    FROM ServerHistory
    WHERE ServerNumber = {server_number}
    ORDER BY RecordedAt;
    """

    conn = get_connection()

    df = pd.read_sql(query, conn)

    conn.close()

    return df


# =====================================
# SAVE AI PREDICTION (optional)
# =====================================

def save_prediction(server,
                    predicted_cpu,
                    predicted_temp,
                    risk,
                    health):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
    IF OBJECT_ID('AIPredictions','U') IS NULL
    BEGIN

        CREATE TABLE AIPredictions
        (
            ID INT IDENTITY PRIMARY KEY,

            ServerNumber INT,

            PredictedCPU FLOAT,

            PredictedTemperature FLOAT,

            RiskLevel VARCHAR(20),

            HealthScore FLOAT,

            PredictionTime DATETIME DEFAULT GETDATE()
        )

    END
    """)

    cursor.execute("""
    INSERT INTO AIPredictions
    (
        ServerNumber,
        PredictedCPU,
        PredictedTemperature,
        RiskLevel,
        HealthScore
    )
    VALUES (?,?,?,?,?)
    """,
    (
        server,
        predicted_cpu,
        predicted_temp,
        risk,
        health
    ))

    conn.commit()

    conn.close()


# =====================================
# TEST CONNECTION
# =====================================

if __name__ == "__main__":

    print("Connecting...")

    df = load_training_data()

    print(df.head())

    print()

    print("Rows:", len(df))