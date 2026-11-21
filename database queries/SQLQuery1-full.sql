-- ============================================================
-- DATA CENTER DATABASE - SQL EXPRESS 2022
-- ============================================================
-- Run this script in SQL Server Management Studio (SSMS)
-- ============================================================

-- ============================================================
-- 1. CREATE DATABASE
-- ============================================================

USE master;
GO

-- Drop database if it exists (BE CAREFUL - THIS DELETES ALL DATA!)
-- IF EXISTS (SELECT * FROM sys.databases WHERE name = 'DataCenter')
-- BEGIN
--     ALTER DATABASE DataCenter SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
--     DROP DATABASE DataCenter;
-- END
-- GO

-- Create the database
CREATE DATABASE DataCenter;
GO

USE DataCenter;
GO

-- ============================================================
-- 2. CREATE TABLES
-- ============================================================

-- Table 1: History - Stores historical server metrics
CREATE TABLE history (
    id INT IDENTITY(1,1) PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    server INT NOT NULL,
    cpu REAL NULL,
    ram REAL NULL,
    disk REAL NULL,
    temperature REAL NULL,
    network REAL NULL,
    latency REAL NULL,
    status BIT NULL,
    cpu_alarm BIT NULL,
    temp_alarm BIT NULL,
    down_alarm BIT NULL
);
GO

-- Table 2: Events - Stores alarm events
CREATE TABLE events (
    id INT IDENTITY(1,1) PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    server INT NULL,
    event NVARCHAR(50) NOT NULL,
    status NVARCHAR(20) NOT NULL,
    value REAL NULL
);
GO

-- Table 3: Latest Values - Stores current tag values
CREATE TABLE latest_values (
    tagname NVARCHAR(50) PRIMARY KEY,
    value NVARCHAR(MAX) NOT NULL,
    updated_at DATETIME NOT NULL
);
GO

-- ============================================================
-- 3. CREATE INDEXES FOR PERFORMANCE
-- ============================================================

-- Index for history table
CREATE INDEX idx_history_server_timestamp 
ON history (server, timestamp DESC);
GO

-- Index for events table
CREATE INDEX idx_events_timestamp 
ON events (timestamp DESC);
GO

-- Index for latest_values
CREATE INDEX idx_latest_values_updated 
ON latest_values (updated_at DESC);
GO

-- ============================================================
-- 4. INSERT INITIAL DATA
-- ============================================================

INSERT INTO latest_values (tagname, value, updated_at) VALUES
    ('Simulation_On', 'true', GETDATE()),
    ('Server1_CPU_Percent', '35.2', GETDATE()),
    ('Server1_RAM_Percent', '45.6', GETDATE()),
    ('Server1_Disk_Percent', '52.3', GETDATE()),
    ('Server1_Temp_C', '48.7', GETDATE()),
    ('Server1_Status', 'true', GETDATE()),
    ('Server1_Network_Mbps', '110.0', GETDATE()),
    ('Server1_Latency_ms', '10.0', GETDATE()),
    ('Server1_CPU_Alarm', 'false', GETDATE()),
    ('Server1_Temp_Alarm', 'false', GETDATE()),
    ('Server1_Down_Alarm', 'false', GETDATE()),
    ('Server2_CPU_Percent', '58.1', GETDATE()),
    ('Server2_RAM_Percent', '62.4', GETDATE()),
    ('Server2_Disk_Percent', '60.7', GETDATE()),
    ('Server2_Temp_C', '52.3', GETDATE()),
    ('Server2_Status', 'true', GETDATE()),
    ('Server2_Network_Mbps', '125.0', GETDATE()),
    ('Server2_Latency_ms', '14.0', GETDATE()),
    ('Server2_CPU_Alarm', 'false', GETDATE()),
    ('Server2_Temp_Alarm', 'false', GETDATE()),
    ('Server2_Down_Alarm', 'false', GETDATE()),
    ('Server3_CPU_Percent', '22.4', GETDATE()),
    ('Server3_RAM_Percent', '35.2', GETDATE()),
    ('Server3_Disk_Percent', '41.6', GETDATE()),
    ('Server3_Temp_C', '40.2', GETDATE()),
    ('Server3_Status', 'true', GETDATE()),
    ('Server3_Network_Mbps', '85.0', GETDATE()),
    ('Server3_Latency_ms', '8.0', GETDATE()),
    ('Server3_CPU_Alarm', 'false', GETDATE()),
    ('Server3_Temp_Alarm', 'false', GETDATE()),
    ('Server3_Down_Alarm', 'false', GETDATE()),
    ('Server4_CPU_Percent', '44.7', GETDATE()),
    ('Server4_RAM_Percent', '50.4', GETDATE()),
    ('Server4_Disk_Percent', '47.8', GETDATE()),
    ('Server4_Temp_C', '48.4', GETDATE()),
    ('Server4_Status', 'true', GETDATE()),
    ('Server4_Network_Mbps', '90.0', GETDATE()),
    ('Server4_Latency_ms', '12.0', GETDATE()),
    ('Server4_CPU_Alarm', 'false', GETDATE()),
    ('Server4_Temp_Alarm', 'false', GETDATE()),
    ('Server4_Down_Alarm', 'false', GETDATE()),
    ('DC_Servers_Up', '4', GETDATE()),
    ('DC_Avg_CPU', '0', GETDATE()),
    ('DC_Max_Temp', '0', GETDATE()),
    ('DC_Total_Network', '0', GETDATE());
GO

-- ============================================================
-- 5. VERIFY TABLES AND DATA (FIXED - Removed problematic queries)
-- ============================================================

-- Show all tables in the database
SELECT 
    TABLE_NAME,
    TABLE_SCHEMA
FROM 
    INFORMATION_SCHEMA.TABLES
WHERE 
    TABLE_TYPE = 'BASE TABLE'
ORDER BY 
    TABLE_NAME;
GO

-- Count rows in each table (FIXED - Removed the 'b' and simplified)
SELECT COUNT(*) AS history_count FROM history;
GO
SELECT COUNT(*) AS events_count FROM events;
GO
SELECT COUNT(*) AS latest_values_count FROM latest_values;
GO

-- Show sample data from latest_values
SELECT TOP 10 
    tagname, 
    value, 
    updated_at 
FROM latest_values
ORDER BY 
    updated_at DESC;
GO

-- ============================================================
-- 6. STORED PROCEDURES
-- ============================================================

-- Stored procedure to get latest values for a specific server
CREATE PROCEDURE sp_GetServerLatest
    @ServerNumber INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1
        cpu,
        ram,
        disk,
        temperature,
        network,
        latency,
        status,
        cpu_alarm,
        temp_alarm,
        down_alarm
    FROM history
    WHERE server = @ServerNumber
    ORDER BY timestamp DESC;
END
GO

-- Stored procedure to get history for a server
CREATE PROCEDURE sp_GetServerHistory
    @ServerNumber INT,
    @Limit INT = 60
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@Limit)
        timestamp,
        cpu,
        ram,
        disk,
        temperature,
        network,
        latency
    FROM history
    WHERE server = @ServerNumber
    ORDER BY timestamp DESC;
END
GO

-- Stored procedure to get recent events
CREATE PROCEDURE sp_GetRecentEvents
    @Limit INT = 25
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@Limit)
        timestamp,
        server,
        event,
        status,
        value
    FROM events
    ORDER BY timestamp DESC;
END
GO

-- ============================================================
-- 7. CLEANUP OLD DATA (Optional)
-- ============================================================

-- Procedure to clean old data (keep last 30 days)
CREATE PROCEDURE sp_CleanOldData
    @RetentionDays INT = 30
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @CutoffDate DATETIME;
    SET @CutoffDate = DATEADD(day, -@RetentionDays, GETDATE());
    
    DELETE FROM history WHERE timestamp < @CutoffDate;
    DELETE FROM events WHERE timestamp < @CutoffDate;
    
    -- Return number of rows deleted
    SELECT 
        @@ROWCOUNT AS RowsDeleted,
        @RetentionDays AS RetentionDays;
END
GO

-- ============================================================
-- 8. FINAL VERIFICATION
-- ============================================================

-- Show summary
SELECT 'Database Setup Complete!' AS Status;
SELECT 
    'Tables Created' AS Item,
    COUNT(*) AS Count
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE';
GO

SELECT 'Initial Data Loaded' AS Status, COUNT(*) AS TotalTags FROM latest_values;
GO

PRINT '============================================================';
PRINT '✅ Database setup completed successfully!';
PRINT '📊 Tables created: history, events, latest_values';
PRINT '📈 Total tags initialized: 45';
PRINT '🔍 Stored procedures created: 4';
PRINT '============================================================';
PRINT '   Database: DataCenter';
PRINT '   Server: MARIAM\SQLEXPRESS01';
PRINT '   Authentication: Windows Authentication';
PRINT '============================================================';
GO