USE DataCenterKPI;
GO

SELECT
    ServerNumber,
    CPU_Percent,
    UpdatedAt
FROM dbo.ServerCPUWorkbench
ORDER BY ServerNumber;