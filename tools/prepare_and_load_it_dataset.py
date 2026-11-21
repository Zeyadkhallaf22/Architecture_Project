"""
Prepare Kaggle "IT System Performance & Resource Metrics" for DataCenterKPI.

1. Rename / map CSV columns to dashboard SQL tag names
2. Split rows across Server 1–4
3. Load into SQL Express (MARIAM\\MSSQLSERVER03 / DataCenterKPI)
4. Seed CurrentServerState + history so the dashboard can go live without InTouch

Source CSV: Big_data_dataset.csv (approved IT System Performance dataset)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pyodbc

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CSV = ROOT / "datasets" / "Big_data_dataset.csv"
OUTPUT_CSV = ROOT / "datasets" / "IT_System_Performance_renamed.csv"

CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=MARIAM\\MSSQLSERVER03;"
    "DATABASE=DataCenterKPI;"
    "Trusted_Connection=yes;"
)

THRESHOLDS = {
    "cpu_critical": 90.0,
    "temp_critical": 75.0,
    "latency_critical": 50.0,
}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Rename dataset columns to match dbo.CurrentServerState / tag naming."""
    out = pd.DataFrame()
    out["SourceRow"] = range(1, len(df) + 1)
    # Round-robin assign rows to the four dashboard servers
    out["ServerNumber"] = ((out["SourceRow"] - 1) % 4) + 1

    out["CPU_Percent"] = df["cpu_utilization"].astype(float).clip(0, 100).round(2)
    out["RAM_Percent"] = df["memory_usage"].astype(float).clip(0, 100).round(2)
    # disk_io is 1–50 in this dataset → scale to a Disk_% style KPI
    out["Disk_Percent"] = (df["disk_io"].astype(float) * 2.0).clip(0, 100).round(2)
    out["Temperature_C"] = df["temperature"].astype(float).round(2)
    # Network Mbps is not in the IT set → derive a stable Mbps-like series
    out["Network_Mbps"] = (
        (df["power_consumption"].astype(float) * 0.65).clip(15, 280).round(2)
    )
    out["Latency_ms"] = df["network_latency"].astype(float).round(2)

    # In this CSV, status=1 is rare → treat as fault/down; 0 = normal/up
    fault = df["status"].astype(int) == 1
    out["Status"] = (~fault).astype(int)
    out["Down_Alarm"] = fault.astype(int)
    out["CPU_Alarm"] = (out["CPU_Percent"] >= THRESHOLDS["cpu_critical"]).astype(int)
    out["Temp_Alarm"] = (out["Temperature_C"] >= THRESHOLDS["temp_critical"]).astype(int)

    out["Process_Count"] = df["process_count"].astype(int)
    out["Thread_Count"] = df["thread_count"].astype(int)
    out["Context_Switches"] = df["context_switches"].astype(int)
    out["Cache_Miss_Rate"] = df["cache_miss_rate"].astype(float).round(5)
    out["Power_Consumption"] = df["power_consumption"].astype(float).round(2)
    out["Uptime"] = df["uptime"].astype(float).round(2)

    # Tag-style aliases (for LatestTagValues / export clarity)
    out["Tag_CPU"] = out.apply(lambda r: f"Server{int(r.ServerNumber)}_CPU_Percent", axis=1)
    out["Tag_RAM"] = out.apply(lambda r: f"Server{int(r.ServerNumber)}_RAM_Percent", axis=1)
    out["Tag_Disk"] = out.apply(lambda r: f"Server{int(r.ServerNumber)}_Disk_Percent", axis=1)
    out["Tag_Temp"] = out.apply(lambda r: f"Server{int(r.ServerNumber)}_Temp_C", axis=1)
    out["Tag_Net"] = out.apply(lambda r: f"Server{int(r.ServerNumber)}_Network_Mbps", axis=1)
    out["Tag_Lat"] = out.apply(lambda r: f"Server{int(r.ServerNumber)}_Latency_ms", axis=1)

    return out


def ensure_tables(cursor: pyodbc.Cursor) -> None:
    cursor.execute(
        """
        IF OBJECT_ID('dbo.ITSystemDataset', 'U') IS NULL
        CREATE TABLE dbo.ITSystemDataset (
            Id                INT IDENTITY(1,1) PRIMARY KEY,
            SourceRow         INT NOT NULL,
            ServerNumber      INT NOT NULL,
            CPU_Percent       FLOAT NOT NULL,
            RAM_Percent       FLOAT NOT NULL,
            Disk_Percent      FLOAT NOT NULL,
            Temperature_C     FLOAT NOT NULL,
            Network_Mbps      FLOAT NOT NULL,
            Latency_ms        FLOAT NOT NULL,
            Status            BIT NOT NULL,
            CPU_Alarm         BIT NOT NULL,
            Temp_Alarm        BIT NOT NULL,
            Down_Alarm        BIT NOT NULL,
            Process_Count     INT NULL,
            Thread_Count      INT NULL,
            Context_Switches  INT NULL,
            Cache_Miss_Rate   FLOAT NULL,
            Power_Consumption FLOAT NULL,
            Uptime            FLOAT NULL,
            LoadedAt          DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
        );
        """
    )
    cursor.execute(
        """
        IF OBJECT_ID('dbo.ITSystemLiveCursor', 'U') IS NULL
        CREATE TABLE dbo.ITSystemLiveCursor (
            ServerNumber INT NOT NULL PRIMARY KEY,
            LastId       INT NOT NULL DEFAULT 0,
            UpdatedAt    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
        );
        """
    )
    # Ensure core live tables exist (InTouch-independent)
    cursor.execute(
        """
        IF OBJECT_ID('dbo.CurrentServerState', 'U') IS NULL
        CREATE TABLE dbo.CurrentServerState (
            ServerNumber  INT NOT NULL PRIMARY KEY,
            CPU_Percent   FLOAT NOT NULL,
            RAM_Percent   FLOAT NOT NULL,
            Disk_Percent  FLOAT NOT NULL,
            Temperature_C FLOAT NOT NULL,
            Network_Mbps  FLOAT NOT NULL,
            Latency_ms    FLOAT NOT NULL,
            Status        BIT NOT NULL
        );
        """
    )
    cursor.execute(
        """
        IF OBJECT_ID('dbo.ServerHistory', 'U') IS NULL
        CREATE TABLE dbo.ServerHistory (
            Id            INT IDENTITY(1,1) PRIMARY KEY,
            ServerNumber  INT NOT NULL,
            CPU_Percent   FLOAT NOT NULL,
            RAM_Percent   FLOAT NOT NULL,
            Disk_Percent  FLOAT NOT NULL,
            Temperature_C FLOAT NOT NULL,
            Network_Mbps  FLOAT NOT NULL,
            Latency_ms    FLOAT NOT NULL,
            Status        BIT NOT NULL,
            RecordedAt    DATETIME2 NOT NULL
        );
        """
    )
    cursor.execute(
        """
        IF OBJECT_ID('dbo.ServerMonitoringHistory', 'U') IS NULL
        CREATE TABLE dbo.ServerMonitoringHistory (
            Id            INT IDENTITY(1,1) PRIMARY KEY,
            ServerNumber  INT NOT NULL,
            CPU_Percent   FLOAT NOT NULL,
            RAM_Percent   FLOAT NOT NULL,
            Disk_Percent  FLOAT NOT NULL,
            Temp_C        FLOAT NOT NULL,
            Network_Mbps  FLOAT NOT NULL,
            Latency_ms    FLOAT NOT NULL,
            Status        BIT NOT NULL,
            RecordedAt    DATETIME2 NOT NULL
        );
        """
    )
    cursor.execute(
        """
        IF OBJECT_ID('dbo.ServerMonitoringValues', 'U') IS NULL
        CREATE TABLE dbo.ServerMonitoringValues (
            ServerNumber INT NOT NULL PRIMARY KEY,
            CPU_Percent  FLOAT NOT NULL,
            RAM_Percent  FLOAT NOT NULL,
            Disk_Percent FLOAT NOT NULL,
            Temp_C       FLOAT NOT NULL,
            Network_Mbps FLOAT NOT NULL,
            Latency_ms   FLOAT NOT NULL,
            Status       BIT NOT NULL,
            UpdatedAt    DATETIME2 NOT NULL
        );
        """
    )
    cursor.execute(
        """
        IF OBJECT_ID('dbo.LatestTagValues', 'U') IS NULL
        CREATE TABLE dbo.LatestTagValues (
            TagName   NVARCHAR(128) NOT NULL PRIMARY KEY,
            Value     NVARCHAR(64) NOT NULL,
            UpdatedAt DATETIME2 NOT NULL
        );
        """
    )


def load_to_sql(df: pd.DataFrame, history_points: int = 60) -> None:
    connection = pyodbc.connect(CONNECTION_STRING, timeout=15)
    with connection:
        cursor = connection.cursor()
        ensure_tables(cursor)

        print("Clearing previous ITSystemDataset / live cursor…")
        cursor.execute("DELETE FROM dbo.ITSystemLiveCursor")
        cursor.execute("DELETE FROM dbo.ITSystemDataset")

        print(f"Inserting {len(df)} renamed rows into dbo.ITSystemDataset…")
        cursor.fast_executemany = True
        insert_sql = """
            INSERT INTO dbo.ITSystemDataset (
                SourceRow, ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                Temperature_C, Network_Mbps, Latency_ms, Status,
                CPU_Alarm, Temp_Alarm, Down_Alarm,
                Process_Count, Thread_Count, Context_Switches,
                Cache_Miss_Rate, Power_Consumption, Uptime
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                int(r.SourceRow), int(r.ServerNumber),
                float(r.CPU_Percent), float(r.RAM_Percent), float(r.Disk_Percent),
                float(r.Temperature_C), float(r.Network_Mbps), float(r.Latency_ms),
                int(r.Status), int(r.CPU_Alarm), int(r.Temp_Alarm), int(r.Down_Alarm),
                int(r.Process_Count), int(r.Thread_Count), int(r.Context_Switches),
                float(r.Cache_Miss_Rate), float(r.Power_Consumption), float(r.Uptime),
            )
            for r in df.itertuples(index=False)
        ]
        cursor.executemany(insert_sql, rows)

        # Init live cursor at first row per server
        for server in range(1, 5):
            cursor.execute(
                """
                DECLARE @id INT = (
                    SELECT MIN(Id) FROM dbo.ITSystemDataset WHERE ServerNumber = ?
                );
                MERGE dbo.ITSystemLiveCursor AS t
                USING (SELECT ? AS ServerNumber) AS s
                ON t.ServerNumber = s.ServerNumber
                WHEN MATCHED THEN UPDATE SET LastId = ISNULL(@id, 0) - 1, UpdatedAt = SYSUTCDATETIME()
                WHEN NOT MATCHED THEN INSERT (ServerNumber, LastId, UpdatedAt)
                VALUES (?, ISNULL(@id, 0) - 1, SYSUTCDATETIME());
                """,
                (server, server, server),
            )

        print("Seeding CurrentServerState + LatestTagValues from first dataset rows…")
        for server in range(1, 5):
            cursor.execute(
                """
                SELECT TOP 1 Id, CPU_Percent, RAM_Percent, Disk_Percent, Temperature_C,
                       Network_Mbps, Latency_ms, Status, CPU_Alarm, Temp_Alarm, Down_Alarm
                FROM dbo.ITSystemDataset
                WHERE ServerNumber = ?
                ORDER BY Id
                """,
                (server,),
            )
            row = cursor.fetchone()
            if not row:
                continue
            _, cpu, ram, disk, temp, net, lat, status, cpu_a, temp_a, down_a = row
            cursor.execute(
                """
                MERGE dbo.CurrentServerState AS t
                USING (SELECT ? AS ServerNumber) AS s
                ON t.ServerNumber = s.ServerNumber
                WHEN MATCHED THEN UPDATE SET
                    CPU_Percent=?, RAM_Percent=?, Disk_Percent=?, Temperature_C=?,
                    Network_Mbps=?, Latency_ms=?, Status=?
                WHEN NOT MATCHED THEN INSERT
                    (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                     Temperature_C, Network_Mbps, Latency_ms, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (server, cpu, ram, disk, temp, net, lat, status,
                 server, cpu, ram, disk, temp, net, lat, status),
            )
            cursor.execute(
                """
                MERGE dbo.ServerMonitoringValues AS t
                USING (SELECT ? AS ServerNumber) AS s
                ON t.ServerNumber = s.ServerNumber
                WHEN MATCHED THEN UPDATE SET
                    CPU_Percent=?, RAM_Percent=?, Disk_Percent=?, Temp_C=?,
                    Network_Mbps=?, Latency_ms=?, Status=?, UpdatedAt=SYSUTCDATETIME()
                WHEN NOT MATCHED THEN INSERT
                    (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                     Temp_C, Network_Mbps, Latency_ms, Status, UpdatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME());
                """,
                (server, cpu, ram, disk, temp, net, lat, status,
                 server, cpu, ram, disk, temp, net, lat, status),
            )
            tag_pairs = [
                (f"Server{server}_CPU_Percent", str(cpu)),
                (f"Server{server}_RAM_Percent", str(ram)),
                (f"Server{server}_Disk_Percent", str(disk)),
                (f"Server{server}_Temp_C", str(temp)),
                (f"Server{server}_Network_Mbps", str(net)),
                (f"Server{server}_Latency_ms", str(lat)),
                (f"Server{server}_Status", "true" if status else "false"),
                (f"Server{server}_CPU_Alarm", "true" if cpu_a else "false"),
                (f"Server{server}_Temp_Alarm", "true" if temp_a else "false"),
                (f"Server{server}_Down_Alarm", "true" if down_a else "false"),
            ]
            for tag, value in tag_pairs:
                cursor.execute(
                    """
                    MERGE dbo.LatestTagValues AS t
                    USING (SELECT ? AS TagName) AS s
                    ON t.TagName = s.TagName
                    WHEN MATCHED THEN UPDATE SET Value=?, UpdatedAt=SYSUTCDATETIME()
                    WHEN NOT MATCHED THEN INSERT (TagName, Value, UpdatedAt)
                    VALUES (?, ?, SYSUTCDATETIME());
                    """,
                    (tag, value, tag, value),
                )

        print(f"Seeding ~{history_points} history points per server for charts…")
        # Detect existing ServerMonitoringHistory temp column name
        cursor.execute(
            """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='ServerMonitoringHistory'
              AND COLUMN_NAME IN ('Temp_C', 'Temperature_C')
            """
        )
        temp_cols = {r[0] for r in cursor.fetchall()}
        mon_temp_col = "Temperature_C" if "Temperature_C" in temp_cols else "Temp_C"

        now = datetime.now()
        for server in range(1, 5):
            cursor.execute(
                f"""
                SELECT TOP ({history_points})
                    CPU_Percent, RAM_Percent, Disk_Percent, Temperature_C,
                    Network_Mbps, Latency_ms, Status
                FROM dbo.ITSystemDataset
                WHERE ServerNumber = ?
                ORDER BY Id
                """,
                (server,),
            )
            hist = list(reversed(cursor.fetchall()))  # oldest → newest for timestamps
            for i, h in enumerate(hist):
                ts = now - timedelta(seconds=45 * (len(hist) - 1 - i))
                cursor.execute(
                    """
                    INSERT INTO dbo.ServerHistory
                        (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                         Temperature_C, Network_Mbps, Latency_ms, Status, RecordedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (server, h[0], h[1], h[2], h[3], h[4], h[5], h[6], ts),
                )
                cursor.execute(
                    f"""
                    INSERT INTO dbo.ServerMonitoringHistory
                        (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent,
                         {mon_temp_col}, Network_Mbps, Latency_ms, Status, RecordedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (server, h[0], h[1], h[2], h[3], h[4], h[5], h[6], ts),
                )

        cursor.execute("SELECT COUNT(*) FROM dbo.ITSystemDataset")
        total = cursor.fetchone()[0]
        print(f"Done. ITSystemDataset rows: {total}")


def main() -> None:
    if not SOURCE_CSV.exists():
        raise SystemExit(f"Missing source CSV: {SOURCE_CSV}")

    print(f"Reading {SOURCE_CSV.name}…")
    raw = pd.read_csv(SOURCE_CSV)
    print(f"Source rows: {len(raw)} | columns: {list(raw.columns)}")

    renamed = transform(raw)
    renamed.to_csv(OUTPUT_CSV, index=False)
    print(f"Wrote renamed CSV -> {OUTPUT_CSV.name}")
    print("Column map:")
    print("  cpu_utilization      -> CPU_Percent")
    print("  memory_usage         -> RAM_Percent")
    print("  disk_io * 2          -> Disk_Percent")
    print("  temperature          -> Temperature_C / Temp_C")
    print("  network_latency      -> Latency_ms")
    print("  power_consumption*0.65 -> Network_Mbps (derived)")
    print("  status (1=fault)     -> Status/Down_Alarm")
    print("  thresholds           -> CPU_Alarm / Temp_Alarm")

    load_to_sql(renamed)
    print("SQL Express DataCenterKPI is ready for live playback (no InTouch required).")


if __name__ == "__main__":
    main()
