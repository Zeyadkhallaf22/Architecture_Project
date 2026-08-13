USE DataCenterKPI;
GO

SELECT TOP 100
    HistoryID,
    ServerNumber,
    CPU_Percent,
    RAM_Percent,
    Disk_Percent,
    Temp_C,
    Network_Mbps,
    Latency_ms,
    Status,
    RecordedAt
FROM dbo.ServerMonitoringHistory
WHERE ServerNumber = 1
ORDER BY HistoryID DESC;