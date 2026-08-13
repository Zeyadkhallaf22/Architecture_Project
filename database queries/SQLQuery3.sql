-- At the server level
USE master;
GO

-- Create the login if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.server_principals WHERE name = 'MicrosoftAccount\mohamadamin1982@gmail.com')
BEGIN
    CREATE LOGIN [MicrosoftAccount\mohamadamin1982@gmail.com] FROM WINDOWS;
END
GO

-- Then go back to the database and grant permissions
USE DataCenter;
GO

CREATE USER [MicrosoftAccount\mohamadamin1982@gmail.com] FOR LOGIN [MicrosoftAccount\mohamadamin1982@gmail.com];
GO

EXEC sp_addrolemember 'db_owner', 'MicrosoftAccount\mohamadamin1982@gmail.com';
GO