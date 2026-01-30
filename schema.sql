-- Meeting Intelligence Database Schema
-- Azure SQL Database: meeting-intelligence

-- Meeting table
CREATE TABLE Meeting (
    MeetingId INT IDENTITY(1,1) PRIMARY KEY,
    Title NVARCHAR(255) NOT NULL,
    MeetingDate DATETIME2 NOT NULL,
    RawTranscript NVARCHAR(MAX),
    Summary NVARCHAR(MAX),
    Attendees NVARCHAR(MAX),
    Source NVARCHAR(50) DEFAULT 'Manual',
    SourceMeetingId NVARCHAR(255),
    Tags NVARCHAR(MAX),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    CreatedBy NVARCHAR(128) NOT NULL,
    UpdatedAt DATETIME2 DEFAULT GETUTCDATE(),
    UpdatedBy NVARCHAR(128) NOT NULL
);

-- Index for searching by date and source
CREATE INDEX IX_Meeting_MeetingDate ON Meeting(MeetingDate DESC);
CREATE INDEX IX_Meeting_SourceMeetingId ON Meeting(SourceMeetingId);

-- Decision table
CREATE TABLE Decision (
    DecisionId INT IDENTITY(1,1) PRIMARY KEY,
    MeetingId INT NOT NULL,
    DecisionText NVARCHAR(MAX) NOT NULL,
    Context NVARCHAR(MAX),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    CreatedBy NVARCHAR(128) NOT NULL,
    CONSTRAINT FK_Decision_Meeting FOREIGN KEY (MeetingId) REFERENCES Meeting(MeetingId)
);

CREATE INDEX IX_Decision_MeetingId ON Decision(MeetingId);

-- Action table
CREATE TABLE Action (
    ActionId INT IDENTITY(1,1) PRIMARY KEY,
    MeetingId INT,
    ActionText NVARCHAR(MAX) NOT NULL,
    Owner NVARCHAR(128) NOT NULL,
    DueDate DATE,
    Status NVARCHAR(20) DEFAULT 'Open' CHECK (Status IN ('Open', 'Complete', 'Parked')),
    Notes NVARCHAR(MAX),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    CreatedBy NVARCHAR(128) NOT NULL,
    UpdatedAt DATETIME2 DEFAULT GETUTCDATE(),
    UpdatedBy NVARCHAR(128) NOT NULL,
    CONSTRAINT FK_Action_Meeting FOREIGN KEY (MeetingId) REFERENCES Meeting(MeetingId)
);

CREATE INDEX IX_Action_Status ON Action(Status);
CREATE INDEX IX_Action_Owner ON Action(Owner);
CREATE INDEX IX_Action_DueDate ON Action(DueDate);
CREATE INDEX IX_Action_MeetingId ON Action(MeetingId);
