USE DataCenterKPI;
go

-- Show ServerCPUWorkbench with formatted output
SELECT 
    ServerNumber AS 'Server',
    CPU_Percent AS 'CPU %',
    UpdatedAt AS 'Last Updated'
FROM ServerCPUWorkbench
ORDER BY ServerNumber;
GO
