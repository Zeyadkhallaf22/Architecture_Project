USE DataCenter;
GO

-- Drop the user if it exists (to start fresh)
IF EXISTS (SELECT * FROM sys.database_principals WHERE name = 'MicrosoftAccount\mohamadamin1982@gmail.com')
BEGIN
    DROP USER [MicrosoftAccount\mohamadamin1982@gmail.com];
END
GO

-- Create the user from the login
CREATE USER [MicrosoftAccount\mohamadamin1982@gmail.com] 
FOR LOGIN [MicrosoftAccount\mohamadamin1982@gmail.com];
GO

-- Grant db_owner role
EXEC sp_addrolemember 'db_owner', 'MicrosoftAccount\mohamadamin1982@gmail.com';
GO

-- Verify
SELECT 
    dp.name AS UserName,
    r.name AS RoleName
FROM sys.database_role_members rm
INNER JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
INNER JOIN sys.database_principals dp ON rm.member_principal_id = dp.principal_id
WHERE dp.name = 'MicrosoftAccount\mohamadamin1982@gmail.com';
GO