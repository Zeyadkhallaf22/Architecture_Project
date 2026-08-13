USE DataCenterKPI;
GO

SELECT
    ServerNumber,
    CPU_Percent,
    UpdatedAt
FROM dbo.ServerCPUWorkbench
ORDER BY ServerNumber;

USE DataCenterKPI;
GO

SELECT TOP 100
    Id,
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
ORDER BY Id DESC;

--- IMPORTANT TO RETRIEVE LATEST
SELECT TOP 100
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
WHERE ServerNumber = 1
ORDER BY RecordedAt DESC;