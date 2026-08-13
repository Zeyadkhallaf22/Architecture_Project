/* =========================================================
   CREATE DATABASE
   ========================================================= */

USE master;
GO

IF DB_ID('DataCenterKPI') IS NOT NULL
BEGIN
    ALTER DATABASE DataCenterKPI
    SET SINGLE_USER
    WITH ROLLBACK IMMEDIATE;

    DROP DATABASE DataCenterKPI;
END;
GO

CREATE DATABASE DataCenterKPI;
GO

USE DataCenterKPI1;
GO

/* =========================================================
   DATA CENTER KPI DATABASE
   AVEVA INTOUCH + SQL SERVER EXPRESS
   ========================================================= */

USE DataCenterKPI;
GO


/* =========================================================
   DELETE OLD PROJECT TABLES
   ========================================================= */

IF OBJECT_ID('dbo.TR_ServerHistory_UpdateLatest', 'TR') IS NOT NULL
    DROP TRIGGER dbo.TR_ServerHistory_UpdateLatest;
GO

IF OBJECT_ID('dbo.TR_ServerCPUWorkbench_UpdatedAt', 'TR') IS NOT NULL
    DROP TRIGGER dbo.TR_ServerCPUWorkbench_UpdatedAt;
GO

IF OBJECT_ID('dbo.ServerHistory', 'U') IS NOT NULL
    DROP TABLE dbo.ServerHistory;
GO

IF OBJECT_ID('dbo.CurrentServerState', 'U') IS NOT NULL
    DROP TABLE dbo.CurrentServerState;
GO

IF OBJECT_ID('dbo.LatestTagValues', 'U') IS NOT NULL
    DROP TABLE dbo.LatestTagValues;
GO

IF OBJECT_ID('dbo.ServerCPUWorkbench', 'U') IS NOT NULL
    DROP TABLE dbo.ServerCPUWorkbench;
GO

IF OBJECT_ID('dbo.AlarmEvents', 'U') IS NOT NULL
    DROP TABLE dbo.AlarmEvents;
GO


/* =========================================================
   TABLE 1: SERVER HISTORY

   A new row is inserted for every server every second.
   Old values are never overwritten.
   ========================================================= */

CREATE TABLE dbo.ServerHistory
(
    HistoryID BIGINT IDENTITY(1,1) NOT NULL
        CONSTRAINT PK_ServerHistory PRIMARY KEY,

    ServerNumber INT NOT NULL,

    CPU_Percent DECIMAL(6,2) NOT NULL,
    RAM_Percent DECIMAL(6,2) NOT NULL,
    Disk_Percent DECIMAL(6,2) NOT NULL,
    Temperature_C DECIMAL(6,2) NOT NULL,
    Network_Mbps DECIMAL(10,2) NOT NULL,
    Latency_ms DECIMAL(10,2) NOT NULL,

    Status BIT NOT NULL,

    RecordedAt DATETIME2(3) NOT NULL
        CONSTRAINT DF_ServerHistory_RecordedAt
        DEFAULT SYSDATETIME(),

    CONSTRAINT CK_ServerHistory_ServerNumber
        CHECK (ServerNumber BETWEEN 1 AND 4),

    CONSTRAINT CK_ServerHistory_CPU
        CHECK (CPU_Percent BETWEEN 0 AND 100),

    CONSTRAINT CK_ServerHistory_RAM
        CHECK (RAM_Percent BETWEEN 0 AND 100),

    CONSTRAINT CK_ServerHistory_Disk
        CHECK (Disk_Percent BETWEEN 0 AND 100)
);
GO


/* Improve queries by server and timestamp */

CREATE INDEX IX_ServerHistory_Server_Time
ON dbo.ServerHistory
(
    ServerNumber,
    RecordedAt DESC
);
GO


/* =========================================================
   TABLE 2: CURRENT SERVER STATE

   Contains exactly one row for each server.
   The latest history value replaces the previous value.
   ========================================================= */

CREATE TABLE dbo.CurrentServerState
(
    ServerNumber INT NOT NULL
        CONSTRAINT PK_CurrentServerState PRIMARY KEY,

    CPU_Percent DECIMAL(6,2) NOT NULL,
    RAM_Percent DECIMAL(6,2) NOT NULL,
    Disk_Percent DECIMAL(6,2) NOT NULL,
    Temperature_C DECIMAL(6,2) NOT NULL,
    Network_Mbps DECIMAL(10,2) NOT NULL,
    Latency_ms DECIMAL(10,2) NOT NULL,

    Status BIT NOT NULL,

    UpdatedAt DATETIME2(3) NOT NULL
        CONSTRAINT DF_CurrentServerState_UpdatedAt
        DEFAULT SYSDATETIME(),

    CONSTRAINT CK_CurrentServerState_ServerNumber
        CHECK (ServerNumber BETWEEN 1 AND 4)
);
GO


/* Initial current values */

INSERT INTO dbo.CurrentServerState
(
    ServerNumber,
    CPU_Percent,
    RAM_Percent,
    Disk_Percent,
    Temperature_C,
    Network_Mbps,
    Latency_ms,
    Status
)
VALUES
    (1, 35, 45, 52, 48, 110, 10, 1),
    (2, 58, 62, 68, 60, 150, 14, 1),
    (3, 22, 35, 41, 40, 75, 8, 1),
    (4, 44, 50, 57, 52, 125, 12, 1);
GO


/* =========================================================
   TABLE 3: LATEST TAG VALUES

   Contains the latest value of every AVEVA tag.
   One row per tag.
   ========================================================= */

CREATE TABLE dbo.LatestTagValues
(
    TagName NVARCHAR(100) NOT NULL
        CONSTRAINT PK_LatestTagValues PRIMARY KEY,

    NumericValue DECIMAL(18,4) NULL,

    TextValue NVARCHAR(100) NULL,

    UpdatedAt DATETIME2(3) NOT NULL
        CONSTRAINT DF_LatestTagValues_UpdatedAt
        DEFAULT SYSDATETIME()
);
GO


/* =========================================================
   TABLE 4: CPU WORKBENCH

   Stores the number entered by the operator in AVEVA.
   One row for each server.
   ========================================================= */

CREATE TABLE dbo.ServerCPUWorkbench
(
    ServerNumber INT NOT NULL
        CONSTRAINT PK_ServerCPUWorkbench PRIMARY KEY,

    CPU_Percent DECIMAL(6,2) NOT NULL,

    ApplyRequested BIT NOT NULL
        CONSTRAINT DF_ServerCPUWorkbench_ApplyRequested
        DEFAULT 0,

    UpdatedAt DATETIME2(3) NOT NULL
        CONSTRAINT DF_ServerCPUWorkbench_UpdatedAt
        DEFAULT SYSDATETIME(),

    CONSTRAINT CK_ServerCPUWorkbench_ServerNumber
        CHECK (ServerNumber BETWEEN 1 AND 4),

    CONSTRAINT CK_ServerCPUWorkbench_CPU
        CHECK (CPU_Percent BETWEEN 0 AND 100)
);
GO


/* Initial workbench values */

INSERT INTO dbo.ServerCPUWorkbench
(
    ServerNumber,
    CPU_Percent,
    ApplyRequested
)
VALUES
    (1, 35, 0),
    (2, 58, 0),
    (3, 22, 0),
    (4, 44, 0);
GO


/* =========================================================
   TABLE 5: ALARM EVENTS

   Stores active, acknowledged and historical alarms.
   ========================================================= */

CREATE TABLE dbo.AlarmEvents
(
    AlarmEventID BIGINT IDENTITY(1,1) NOT NULL
        CONSTRAINT PK_AlarmEvents PRIMARY KEY,

    ServerNumber INT NOT NULL,

    AlarmType NVARCHAR(50) NOT NULL,

    Severity NVARCHAR(20) NOT NULL,

    AlarmMessage NVARCHAR(255) NOT NULL,

    AlarmValue DECIMAL(10,2) NULL,

    IsActive BIT NOT NULL
        CONSTRAINT DF_AlarmEvents_IsActive
        DEFAULT 1,

    IsAcknowledged BIT NOT NULL
        CONSTRAINT DF_AlarmEvents_IsAcknowledged
        DEFAULT 0,

    OccurredAt DATETIME2(3) NOT NULL
        CONSTRAINT DF_AlarmEvents_OccurredAt
        DEFAULT SYSDATETIME(),

    AcknowledgedAt DATETIME2(3) NULL,

    CONSTRAINT CK_AlarmEvents_ServerNumber
        CHECK (ServerNumber BETWEEN 1 AND 4)
);
GO


CREATE INDEX IX_AlarmEvents_Server_Time
ON dbo.AlarmEvents
(
    ServerNumber,
    OccurredAt DESC
);
GO


/* =========================================================
   TRIGGER 1

   Updates UpdatedAt when AVEVA changes a workbench value.
   ========================================================= */

CREATE TRIGGER dbo.TR_ServerCPUWorkbench_UpdatedAt
ON dbo.ServerCPUWorkbench
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE target
    SET UpdatedAt = SYSDATETIME()
    FROM dbo.ServerCPUWorkbench AS target
    INNER JOIN inserted AS changed
        ON target.ServerNumber = changed.ServerNumber;
END;
GO


/* =========================================================
   TRIGGER 2

   Every time AVEVA inserts a history row:

   1. CurrentServerState is updated.
   2. LatestTagValues is updated.
   ========================================================= */

CREATE TRIGGER dbo.TR_ServerHistory_UpdateLatest
ON dbo.ServerHistory
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;


    /* Select the latest inserted row for each server */

    ;WITH LatestInserted AS
    (
        SELECT
            ServerNumber,
            CPU_Percent,
            RAM_Percent,
            Disk_Percent,
            Temperature_C,
            Network_Mbps,
            Latency_ms,
            Status,
            RecordedAt,

            ROW_NUMBER() OVER
            (
                PARTITION BY ServerNumber
                ORDER BY HistoryID DESC
            ) AS RowNumber
        FROM inserted
    )

    MERGE dbo.CurrentServerState AS target
    USING
    (
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
        FROM LatestInserted
        WHERE RowNumber = 1
    ) AS source

    ON target.ServerNumber = source.ServerNumber

    WHEN MATCHED THEN
        UPDATE SET
            target.CPU_Percent = source.CPU_Percent,
            target.RAM_Percent = source.RAM_Percent,
            target.Disk_Percent = source.Disk_Percent,
            target.Temperature_C = source.Temperature_C,
            target.Network_Mbps = source.Network_Mbps,
            target.Latency_ms = source.Latency_ms,
            target.Status = source.Status,
            target.UpdatedAt = source.RecordedAt

    WHEN NOT MATCHED THEN
        INSERT
        (
            ServerNumber,
            CPU_Percent,
            RAM_Percent,
            Disk_Percent,
            Temperature_C,
            Network_Mbps,
            Latency_ms,
            Status,
            UpdatedAt
        )
        VALUES
        (
            source.ServerNumber,
            source.CPU_Percent,
            source.RAM_Percent,
            source.Disk_Percent,
            source.Temperature_C,
            source.Network_Mbps,
            source.Latency_ms,
            source.Status,
            source.RecordedAt
        );


    /* Update LatestTagValues */

    ;WITH LatestInserted AS
    (
        SELECT
            ServerNumber,
            CPU_Percent,
            RAM_Percent,
            Disk_Percent,
            Temperature_C,
            Network_Mbps,
            Latency_ms,
            Status,
            RecordedAt,

            ROW_NUMBER() OVER
            (
                PARTITION BY ServerNumber
                ORDER BY HistoryID DESC
            ) AS RowNumber
        FROM inserted
    ),

    TagValues AS
    (
        SELECT
            CONCAT(
                'Server',
                source.ServerNumber,
                '_',
                valueset.TagSuffix
            ) AS TagName,

            valueset.NumericValue,

            source.RecordedAt AS UpdatedAt

        FROM LatestInserted AS source

        CROSS APPLY
        (
            VALUES
                (
                    'CPU_Percent',
                    CAST(source.CPU_Percent AS DECIMAL(18,4))
                ),
                (
                    'RAM_Percent',
                    CAST(source.RAM_Percent AS DECIMAL(18,4))
                ),
                (
                    'Disk_Percent',
                    CAST(source.Disk_Percent AS DECIMAL(18,4))
                ),
                (
                    'Temp_C',
                    CAST(source.Temperature_C AS DECIMAL(18,4))
                ),
                (
                    'Network_Mbps',
                    CAST(source.Network_Mbps AS DECIMAL(18,4))
                ),
                (
                    'Latency_ms',
                    CAST(source.Latency_ms AS DECIMAL(18,4))
                ),
                (
                    'Status',
                    CAST(source.Status AS DECIMAL(18,4))
                )
        ) AS valueset
        (
            TagSuffix,
            NumericValue
        )

        WHERE source.RowNumber = 1
    )

    MERGE dbo.LatestTagValues AS target
    USING TagValues AS source

    ON target.TagName = source.TagName

    WHEN MATCHED THEN
        UPDATE SET
            target.NumericValue = source.NumericValue,
            target.UpdatedAt = source.UpdatedAt

    WHEN NOT MATCHED THEN
        INSERT
        (
            TagName,
            NumericValue,
            UpdatedAt
        )
        VALUES
        (
            source.TagName,
            source.NumericValue,
            source.UpdatedAt
        );

END;
GO


/* =========================================================
   INITIAL HISTORY RECORDS
   ========================================================= */

INSERT INTO dbo.ServerHistory
(
    ServerNumber,
    CPU_Percent,
    RAM_Percent,
    Disk_Percent,
    Temperature_C,
    Network_Mbps,
    Latency_ms,
    Status
)
VALUES
    (1, 35, 45, 52, 48, 110, 10, 1),
    (2, 58, 62, 68, 60, 150, 14, 1),
    (3, 22, 35, 41, 40, 75, 8, 1),
    (4, 44, 50, 57, 52, 125, 12, 1);
GO


/* =========================================================
   FINAL CHECK
   ========================================================= */

SELECT
    ServerNumber,
    CPU_Percent,
    RAM_Percent,
    Disk_Percent,
    Temperature_C,
    Network_Mbps,
    Latency_ms,
    Status,
    UpdatedAt
FROM dbo.CurrentServerState
ORDER BY ServerNumber;
GO

SELECT TOP 20
    HistoryID,
    ServerNumber,
    CPU_Percent,
    RAM_Percent,
    Disk_Percent,
    Temperature_C,
    Network_Mbps,
    Latency_ms,
    Status,
    RecordedAt
FROM dbo.ServerHistory
ORDER BY HistoryID DESC;
GO

SELECT
    TagName,
    NumericValue,
    UpdatedAt
FROM dbo.LatestTagValues
ORDER BY TagName;
GO

SELECT
    ServerNumber,
    CPU_Percent,
    ApplyRequested,
    UpdatedAt
FROM dbo.ServerCPUWorkbench
ORDER BY ServerNumber;
GO
