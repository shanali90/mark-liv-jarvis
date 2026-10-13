import re
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000 
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

_LEVEL_FLOOR = 60.0
_LEVEL_FULL  = 2600.0
_TAIL_MARGIN = 0.25
_VIS_WIN = 1024
_VIS_HOP = 480
_FIRST_SOUND = CHUNK_SIZE / RECEIVE_SAMPLE_RATE
_CURSOR_SLACK = 0.15
_REPEAT_MIN = 12
SLEEP_VOICE_COMMANDS = (
    'wake up', 'wake up jarvis', 'jarvis wake up',
    'hello jarvis', 'are you there',
    'activate', 'listen to me', 'start listening'
)


class JarvisState:
    SLEEPING = "SLEEPING"
    AWAKE = "AWAKE"
    PROCESSING = "PROCESSING"

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)
