USE DataCenterKPI;
GO

DECLARE @ConstraintName NVARCHAR(200);

SELECT @ConstraintName = dc.name
FROM sys.default_constraints dc
JOIN sys.columns c
    ON dc.parent_object_id = c.object_id
   AND dc.parent_column_id = c.column_id
WHERE OBJECT_NAME(dc.parent_object_id) = 'ServerMonitoringHistory'
  AND c.name = 'RecordedAt';

IF @ConstraintName IS NOT NULL
BEGIN
    EXEC('ALTER TABLE dbo.ServerMonitoringHistory DROP CONSTRAINT ' + @ConstraintName);
END
GO

ALTER TABLE dbo.ServerMonitoringHistory
ADD CONSTRAINT DF_ServerMonitoringHistory_RecordedAt
DEFAULT SYSDATETIME() FOR RecordedAt;
GO


SELECT TOP (10)
    HistoryID,
    ServerNumber,
    RecordedAt
FROM dbo.ServerMonitoringHistory
ORDER BY HistoryID DESC;


SELECT
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'ServerMonitoringHistory';

EXEC sp_help 'dbo.ServerMonitoringHistory';