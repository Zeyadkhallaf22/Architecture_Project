/* =========================================================
   DATA CENTER KPI DATABASE
   Clean installation for another laptop
   ========================================================= */

USE master;
GO

/* Create the database only if it does not already exist */
IF DB_ID('DataCenterKPI') IS NULL
BEGIN
    CREATE DATABASE DataCenterKPI;
END;
GO

USE DataCenterKPI;
GO


/* =========================================================
   DROP OLD TABLES
   ========================================================= */

DROP TABLE IF EXISTS dbo.AlarmEvents;
DROP TABLE IF EXISTS dbo.CurrentServerState;
DROP TABLE IF EXISTS dbo.LatestTagValues;
DROP TABLE IF EXISTS dbo.ServerCPUWorkbench;
DROP TABLE IF EXISTS dbo.ServerHistory;
DROP TABLE IF EXISTS dbo.ServerMetrics;
GO


/* =========================================================
   TABLE 1: ALARM EVENTS
   ========================================================= */

CREATE TABLE dbo.AlarmEvents
(
    Id INT IDENTITY(1,1) NOT NULL
        CONSTRAINT PK_AlarmEvents PRIMARY KEY,

    ServerNumber INT NULL,

    EventName VARCHAR(150) NULL,

    Severity VARCHAR(20) NULL,

    EventTime DATETIME NULL
        CONSTRAINT DF_AlarmEvents_EventTime
        DEFAULT GETDATE()
);
GO


/* =========================================================
   TABLE 2: CURRENT SERVER STATE

   Keeps one latest row for each server.
   ========================================================= */

CREATE TABLE dbo.CurrentServerState
(
    ServerNumber INT NOT NULL
        CONSTRAINT PK_CurrentServerState PRIMARY KEY,

    CPU_Percent FLOAT NULL,

    RAM_Percent FLOAT NULL,

    Disk_Percent FLOAT NULL,

    Temperature_C FLOAT NULL,

    Network_Mbps FLOAT NULL,

    Latency_ms FLOAT NULL,

    Status BIT NULL
);
GO


/* Insert the four initial server rows */

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

   Keeps one latest value for each InTouch tag.
   ========================================================= */

CREATE TABLE dbo.LatestTagValues
(
    TagName NVARCHAR(100) NOT NULL
        CONSTRAINT PK_LatestTagValues PRIMARY KEY,

    Value NVARCHAR(100) NOT NULL,

    UpdatedAt DATETIME NOT NULL
        CONSTRAINT DF_LatestTagValues_UpdatedAt
        DEFAULT GETDATE()
);
GO


/* =========================================================
   TABLE 4: SERVER CPU WORKBENCH

   Stores CPU values entered through the APPLY buttons.
   ========================================================= */

CREATE TABLE dbo.ServerCPUWorkbench
(
    ServerNumber INT NOT NULL
        CONSTRAINT PK_ServerCPUWorkbench PRIMARY KEY,

    CPU_Percent FLOAT NOT NULL,

    UpdatedAt DATETIME NOT NULL
        CONSTRAINT DF_ServerCPUWorkbench_UpdatedAt
        DEFAULT GETDATE()
);
GO


/* Initial Workbench values */

INSERT INTO dbo.ServerCPUWorkbench
(
    ServerNumber,
    CPU_Percent
)
VALUES
    (1, 35),
    (2, 58),
    (3, 22),
    (4, 44);
GO


/* Automatically update timestamp when APPLY changes CPU */

CREATE TRIGGER dbo.TR_ServerCPUWorkbench_UpdatedAt
ON dbo.ServerCPUWorkbench
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE target
    SET UpdatedAt = GETDATE()
    FROM dbo.ServerCPUWorkbench AS target
    INNER JOIN inserted AS changed
        ON target.ServerNumber = changed.ServerNumber;
END;
GO


/* =========================================================
   TABLE 5: SERVER HISTORY

   Stores every server value with its timestamp.
   A new row is inserted every second.
   ========================================================= */

CREATE TABLE dbo.ServerHistory
(
    Id INT IDENTITY(1,1) NOT NULL
        CONSTRAINT PK_ServerHistory PRIMARY KEY,

    ServerNumber INT NOT NULL,

    CPU_Percent FLOAT NULL,

    RAM_Percent FLOAT NULL,

    Disk_Percent FLOAT NULL,

    Temperature_C FLOAT NULL,

    Network_Mbps FLOAT NULL,

    Latency_ms FLOAT NULL,

    Status BIT NULL,

    RecordedAt DATETIME NULL
        CONSTRAINT DF_ServerHistory_RecordedAt
        DEFAULT GETDATE()
);
GO


CREATE INDEX IX_ServerHistory_ServerTime
ON dbo.ServerHistory
(
    ServerNumber,
    RecordedAt DESC
);
GO


/* =========================================================
   TABLE 6: SERVER METRICS

   Stores server KPIs and alarm states.
   ========================================================= */

CREATE TABLE dbo.ServerMetrics
(
    Id INT IDENTITY(1,1) NOT NULL
        CONSTRAINT PK_ServerMetrics PRIMARY KEY,

    ServerNumber INT NOT NULL,

    CPU_Percent FLOAT NULL,

    RAM_Percent FLOAT NULL,

    Disk_Percent FLOAT NULL,

    Temperature_C FLOAT NULL,

    Network_Mbps FLOAT NULL,

    Latency_ms FLOAT NULL,

    Status BIT NULL,

    CPU_Alarm BIT NULL,

    Temp_Alarm BIT NULL,

    Down_Alarm BIT NULL,

    RecordedAt DATETIME NULL
        CONSTRAINT DF_ServerMetrics_RecordedAt
        DEFAULT GETDATE()
);
GO


CREATE INDEX IX_ServerMetrics_ServerTime
ON dbo.ServerMetrics
(
    ServerNumber,
    RecordedAt DESC
);
GO


/* =========================================================
   INITIAL HISTORY VALUES
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
   INITIAL SERVER METRICS VALUES
   ========================================================= */

INSERT INTO dbo.ServerMetrics
(
    ServerNumber,
    CPU_Percent,
    RAM_Percent,
    Disk_Percent,
    Temperature_C,
    Network_Mbps,
    Latency_ms,
    Status,
    CPU_Alarm,
    Temp_Alarm,
    Down_Alarm
)
VALUES
    (1, 35, 45, 52, 48, 110, 10, 1, 0, 0, 0),
    (2, 58, 62, 68, 60, 150, 14, 1, 0, 0, 0),
    (3, 22, 35, 41, 40, 75, 8, 1, 0, 0, 0),
    (4, 44, 50, 57, 52, 125, 12, 1, 0, 0, 0);
GO


/* =========================================================
   FINAL VERIFICATION
   ========================================================= */

SELECT *
FROM dbo.CurrentServerState
ORDER BY ServerNumber;

SELECT *
FROM dbo.ServerCPUWorkbench
ORDER BY ServerNumber;

SELECT TOP 20 *
FROM dbo.ServerHistory
ORDER BY Id DESC;

SELECT TOP 20 *
FROM dbo.ServerMetrics
ORDER BY Id DESC;
GO

