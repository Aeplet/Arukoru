from enum import Enum, auto

class ActionType(Enum):
    Ban = auto()
    Kick = auto()
    Unban = auto()
    Timeout = auto()
    TimeoutRemoval = auto()
    ScamKick = auto()
    Warn = auto()
    WarnRemove = auto()

class ServerAction(Enum):
    Join = auto()
    Leave = auto()
    Ban = auto()
    Unban = auto()
    KillboxTrigger = auto()

class MessageLog(Enum):
    Delete = auto()
    Edit = auto()

class Restriction(Enum):
    NoHelp = auto()

class LogChannelType(Enum):
    ModLogs = auto()
    ServerLogs = auto()
    MessageLogs = auto()