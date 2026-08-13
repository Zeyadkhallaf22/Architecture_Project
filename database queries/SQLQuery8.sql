USE DataCenterKPI;
GO

CREATE OR ALTER TRIGGER dbo.TR_ServerCPUWorkbench_UpdatedAt
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