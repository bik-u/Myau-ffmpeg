from dataclasses import dataclass
from enum import Enum


class CodecType(Enum):
    VIDEO='video'
    AUDIO='audio'


@dataclass
class Video:
    pass