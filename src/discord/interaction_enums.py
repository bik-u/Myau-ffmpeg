from enum import Enum
from dataclasses import dataclass


class MessageFlags(Enum):
    CROSSPOSTED = 1 << 0
    IS_CROSSPOST = 1 << 1
    SUPPRESS_EMBEDS = 1 << 2
    SOURCE_MESSAGE_DELETED = 1 << 3
    URGENT = 1 << 4
    HAS_THREAD = 1 << 5
    EPHEMERAL = 1 << 6
    LOADING = 1 << 7
    FAILED_TO_MENTION_SOME_ROLES_IN_THREAD= 1 << 8
    SUPPRESS_NOTIFICATIONS = 1 << 9
    IS_VOICE_MESSAGE = 1 << 10


def message_flag(*args):
    return sum([x.value for x in args])


class InteractionType(Enum):
    PING=1
    APPLICATION_COMMAND=2
    MESSAGE_COMPONENT=3
    APPLICATION_COMMAND_AUTOCOMPLETE=4
    MODAL_SUBMIT=5
    

class InteractionCallbackType(Enum):
    PONG=1
    CHANNEL_MESSAGE_WITH_SOURCE=4
    DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE=5
    DEFERRED_UPDATE_MESSAGE=6
    UPDATE_MESSAGE=7
    APPLICATION_COMMAND_AUTOCOMPLETE_RESULT=8
    MODAL=9
    PREMIUM_REQUIRED=10

    
class ApplicationCommandOptionType(Enum):
    SUB_COMMAND = 1
    SUB_COMMAND_GROUP = 2
    STRING = 3
    INTEGER = 4
    BOOLEAN = 5
    USER = 6
    CHANNEL = 7
    ROLE = 8
    MENTIONABLE = 9
    NUMBER = 10
    ATTACHMENT = 11

class ComponentTypes(Enum):
    ACTION_ROW = 1
    BUTTON = 2
    STRING_SELECT = 3
    TEXT_INPUT = 4
    USER_SELECT = 5
    ROLE_SELECT = 6
    MENTIONABLE_SELECT = 7
    CHANNEL_SELECT = 8
    
class ButtonStyles(Enum):
    PRIMARY = 1
    SECONDARY = 2
    SUCCESS = 3
    DANGER = 4
    LINK = 5

@dataclass
class AutocompleteChoices:
    name: str
    value: str
