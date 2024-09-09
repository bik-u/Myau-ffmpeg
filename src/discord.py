"""
    Module for discord connections
"""
import traceback
from enum import Enum
import json
from dataclasses import dataclass
import asyncio
from zlib import decompressobj

from asyncio.tasks import wait
from tools import Atrdict
import websockets
from aiohttp import ClientSession, TCPConnector, FormData

RECV_TIMEOUT = 40
PING_TIMEOUT = 0.5
API_LINK = "https://discord.com/api/v10/"
GATE_WAY = "wss://gateway.discord.gg/?v=8&encoding=json&compress=zlib-stream"
ZLIB_SUFFIX = b"\x00\x00\xff\xff"
CND_LINK = "https://cdn.discordapp.com/"

# Close code events
ATTEMPT_RESUMING = 1002
INVALID_SEQ = 4007

# Http status codes
HTTP_OK = 200
HTTP_PUT_OK = 204


class _network:
    """abstract network class"""

    network_se: ClientSession = None

    def __init__(self):
        pass

    @staticmethod
    async def create_session():
        _network.network_se = ClientSession(connector=TCPConnector())


class _websocket:
    """general websocket class"""

    def __init__(self):
        self.inflator = None
        self.buffer = None

    async def _connect(self, uri):
        """create a websocket connection with simple error handlers"""
        self.inflator = decompressobj()
        self.buffer = bytearray()
        async with websockets.connect(
            uri, read_limit=2**512, max_size=2**512
        ) as self.socket:
            while True:
                try:
                    recv = await self.socket.recv()
                    asyncio.create_task(self.on_message(recv))
                except websockets.exceptions.ConnectionClosed as err:
                    await self.err_code_handler(err, uri)
                    break
                except websockets.exceptions.ConnectionClosedOK:
                    print("socket closed normally")
                    break
                except Exception as x:
                    print(x)

    async def err_code_handler(self, err, uri):
        """handle err code properly"""
        pass

    async def disconnect(self):
        pass

    async def on_message(self, msg):
        pass

    async def decode(self, msg):
        """Compress out of zlib and start correct op"""
        self.buffer.extend(msg)
        if len(msg) < 4 or msg[-4:] != ZLIB_SUFFIX:
            return
        msg = self.inflator.decompress(self.buffer)
        self.buffer = bytearray()
        return msg


class Bot(_websocket):
    """Main bot class"""

    def __init__(self, intents, token="", cmd_prefix="!"):
        super().__init__()
        self.token = token
        self.intents = intents
        self.prefix = cmd_prefix
        self.seq_num = None
        self.session = None
        self.socket = None
        self.heart_task = None
        self.ack = False
        self.user_id = None
        # Used for caching voice states for bot
        self.cache = {}
        self.cache["voice_states"] = {}
        self.cache["voice_connections"] = {}
        self.cache["users"] = {}
        # Used for caching guild prefix
        self.cache_prefix = {}

    async def err_code_handler(self, err, uri):
        """handle err code"""
        code = err.code
        if code == INVALID_SEQ:
            self.session = None
            self.seq_num = None
        await self._connect(uri)

    async def on_message(self, msg):
        """decode and send to correct"""
        data = await super().decode(msg)
        data = json.loads(data)
        op = data["op"]
        try:
            await self.ops[op](self, data)
        except KeyError:
            # traceback.print_exc()
            pass

    async def start(self):
        """Start the bot session"""
        asyncio.create_task(_network.create_session())
        await self._connect(GATE_WAY)

    async def close(self):
        """Close the bot session"""
        if self.heatr_task:
            self.heart_task.cancel()
        if self.socket:
            await self.socket.close()

    async def heart_beat(self, interval):
        """start beat interval"""
        while self.socket:
            op1 = {"op": 1, "d": self.seq_num}
            await self.socket.send(json.dumps(op1))
            await asyncio.sleep(interval / 1000)
            if self.ack:
                self.ack = False
            else:
                # Attempt resuming
                await self.socket.close(
                    code=ATTEMPT_RESUMING,
                    reason="No heartack/zombied \
                                       connection.",
                )
                break

    async def on_ready(self, msg):
        """update session id"""
        self.user_id = msg["d"]["user"]["id"]
        self.session = msg["d"]["session_id"]

    async def on_resume(self, msg):
        """keep resumed"""
        pass

    async def on_message_crt(self, msg):
        """await couroutines and check for commands"""
        data = msg["d"]
        try:
            is_bot = data["author"]["bot"]
        except KeyError:
            is_bot = False
        finally:
            if is_bot:
                return
        ct = data["content"]
        try:
            p = self.cache_prefix[data["guild_id"]]
            if p == None or p == "":
                p = self.prefix
        except KeyError:
            p = self.prefix

        p_len = len(p)
        if not ct[:p_len] == p:
            return
        ct = ct.split()[0]
        for cmd_name, cmd_lst in Bot.commands.items():
            if ct[p_len:] == cmd_name:
                for cmd in cmd_lst:
                    await cmd(self, msg)
        pass

    async def on_voice_state_update(self, msg):
        """update cache or update bot"""
        data = msg["d"]
        v_s = self.cache["voice_states"]
        uid = data["user_id"]
        v_s[uid] = msg

    async def on_voice_server_update(self, msg):
        """start the connect process"""
        data = msg["d"]
        v_cs = self.cache["voice_connections"]
        bot = BotVoice(self, data)
        v_cs[data["guild_id"]] = bot
        await bot.start()

    async def on_interact_crt(self, msg):
        data = msg['d']
        for k, v in Bot.interactions.items():
            if k == (data['type'], data['data'].get('name')):
                await v(InteractionContext(self, msg))

    ts = {
        "INTERACTION_CREATE": on_interact_crt,
        "READY": on_ready,
        "MESSAGE_CREATE": on_message_crt,
        "VOICE_STATE_UPDATE": on_voice_state_update,
        "VOICE_SERVER_UPDATE": on_voice_server_update,
    }

    async def op_0(self, msg):
        """distribute types from op 0 type"""
        typ = msg["t"]
        self.seq_num = msg["s"]
        try:
            for func in Bot.listeners[typ]:
                await func(self, msg)
        except KeyError:
            pass

        try:
            await self.ts[typ](self, msg)
        except KeyError:
            pass

    async def op_1(self, msg):
        """send back heart beat"""
        op1 = {"op": 1, "d": self.seq_num}
        await self.socket.send(json.dumps(op1))

    async def send_resume(self):
        op6 = {
            "op": 6,
            "d": {"token": self.token, "session_id": self.session, "seq": self.seq_num},
        }
        await self.socket.send(json.dumps(op6))

    async def self_identify(self):
        op2 = {
            "op": 2,
            "d": {
                "token": self.token,
                "properties": {
                    "$os": "linux",
                    "$browser": "discordlib",
                    "$device": "discordlib",
                },
                "compress": True,
                "presence": {
                    "since": None,
                    "activities": [{"name": "nyaaing~", "type": 2}],
                    "status": "online",
                    "afk": False,
                },
                "intents": self.intents,
            },
        }
        await self.socket.send(json.dumps(op2))

    async def op_7(self, msg):
        """atempt reconnection"""
        await self.socket.close(code=ATTEMPT_RESUMING)

    async def op_9(self, msg):
        """reconnect properly based on d"""
        resumable = msg["d"]
        if not resumable:
            self.session = None
            self.seq_num = None
            await self.self_identify()
        else:
            await self.send_resume()

    async def op_10(self, msg):
        """send hello message back"""
        if self.heart_task:
            print("heart task cancel")
            self.heart_task.cancel()
        hbt_int = msg["d"]["heartbeat_interval"]
        self.heart_task = asyncio.create_task(self.heart_beat(hbt_int))
        if not self.session:
            # send indentification
            await self.self_identify()
        else:
            await self.send_resume()

    async def op_11(self, msg):
        """set ack to true"""
        self.ack = True

    @staticmethod
    def command(*args):
        """decorator for adding commands"""

        def add_command(func):
            """add command that looks for message"""
            if len(args) == 0:
                Bot.commands[func.__name__] = [
                    func,
                ]
            for cmd in args:
                try:
                    # append if command already exist
                    arr = Bot.commands[cmd]
                    arr.append(func)
                except KeyError:
                    Bot.commands[cmd] = [
                        func,
                    ]

        return add_command


    @staticmethod
    def on_interact(inter_type=None, name=None):
        
        def add_interaction(func):
            Bot.interactions[(inter_type, name)] = func
            
        return add_interaction

    @staticmethod
    def listener(t, *args):
        """decorator for adding listeners"""

        def add_listener(func):
            ts = [t, *args]
            for typ in ts:
                try:
                    arr = Bot.listeners[typ]
                    arr.append(func)
                except KeyError as e:
                    Bot.listeners[typ] = [
                        func,
                    ]

        return add_listener

    ops = {10: op_10, 11: op_11, 9: op_9, 1: op_1, 0: op_0}

    commands = {}
    listeners = {}
    interactions = {}

    async def connect_voice(self, g_id, ch_id, mute=False, deaf=False):
        """Try to connect to voice based on
        guild and channel id"""
        data = {
            "op": 4,
            "d": {
                "guild_id": g_id,
                "channel_id": ch_id,
                "self_mute": mute,
                "self_deaf": deaf,
            },
        }

        await self.socket.send(json.dumps(data))


class BotVoice(_websocket):
    """voice connection for the bot"""

    def __init__(self, bot, data):
        super().__init__()
        self.bot = bot
        self.data = data

    async def start(self):
        """Starts the connection"""
        # wait for voice_status update
        print("Starying@")


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
    

def intents(
    GUILDS=False,
    GUILD_MEMBERS=False,
    GUILD_BANS=False,
    GUILD_EMOJIS=False,
    GUILD_INTEGRATIONS=False,
    GUILD_WEBHOOKS=False,
    GUILD_INVITES=False,
    GUILD_PRESENCES=False,
    GUILD_MESSAGES=False,
    GUILD_MESSAGE_REACTIONS=False,
    GUILD_MESSAGE_TYPING=False,
    DIRECT_MESSAGES=False,
    DIRECT_MESSAGE_REACTIONS=False,
    DIRECT_MESSAGE_TYPING=False,
    GUILD_VOICE_STATES=False,
):
    """create a correct intent number based on allowed intents"""
    intent = 0
    if GUILDS:
        intent += 1 << 0
    if GUILD_MEMBERS:
        intent += 1 << 1
    if GUILD_BANS:
        intent += 1 << 2
    if GUILD_EMOJIS:
        intent += 1 << 3
    if GUILD_INTEGRATIONS:
        intent += 1 << 4
    if GUILD_WEBHOOKS:
        intent += 1 << 5
    if GUILD_INVITES:
        intent += 1 << 6
    if GUILD_PRESENCES:
        intent += 1 << 8
    if GUILD_VOICE_STATES:
        intent += 1 << 7
    if GUILD_MESSAGES:
        intent += 1 << 9
    if GUILD_MESSAGE_REACTIONS:
        intent += 1 << 10
    if GUILD_MESSAGE_TYPING:
        intent += 1 << 11
    if DIRECT_MESSAGES:
        intent += 1 << 12
    if DIRECT_MESSAGE_REACTIONS:
        intent += 1 << 13
    if DIRECT_MESSAGE_TYPING:
        intent += 1 << 14
    return intent


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

class InteractionContext:
    """ A universal context class for interactions capable of doing random
        things that help simplify command making
    """
    
    def __init__(self, bot, interaction):
        self.bot = bot
        self.d = interaction['d']
        self.data = self.d.get('data')
        self.id = self.d.get('id')
        self.token = self.d.get('token')
        self.options = None
        if not self.data:
            return self
        if InteractionType(self.d['type']) in \
            [InteractionType.APPLICATION_COMMAND,
                InteractionType.APPLICATION_COMMAND_AUTOCOMPLETE]:
            self.options = self.data.get('options')
        self.user_id = None
        self.guild_id = self.d.get('guild_id')
        if self.d.get('member'):
            self.user_id = self.d['member']['user']['id']
        self.components = []
        self.content = None
        self.flags = None

    def add_button(self, style: ButtonStyles, label: str=None,
        emoji: str=None, custom_id: str=None, url: str=None,
        disabled:bool=False, layer:int=0) -> dict:
        button = {
            "type": ComponentTypes.BUTTON.value,
            "style": style.value,
            "disabled": disabled
        }
        if label:
            button['label'] = label
        if emoji:
            button['emoji'] = emoji
        if custom_id:
            button['custom_id'] = custom_id
        if url:
            button['url'] = url
        self.components[layer]['components'].append(button)
    
    def add_action_row(self):
        self.components.append({
            "type": ComponentTypes.ACTION_ROW.value,
            "components": [
                
            ]
        })

    def add_content(self, content: str):
        self.content = content
    
    def add_flags(self, *flags):
        self.flags = message_flag(*flags)                

    def get_subgroup(self):
        if not self.options:
            return
        
        return self.options[0]

    def get_option(self, *names, opts=None, layer=0):
        if not opts:
            opts = self.options
        if not opts:
            return
        for v in opts:
            if layer == 0:
                if v.get('name') in names:
                    return v
            elif v.get('options'):
                return self.get_option(*names,
                    opts=v['options'], layer=layer-1)
                
    def make_link(self, *args):
        return f"{API_LINK}interactions/{'/'.join(args)}" 
    
    async def _send_msg(self, url=None, file=None, filename=None, data=None):
        pload = FormData()
        if file:
            pload.add_field('file', file, filename=filename,
                content_type="multipart/formdata")
        pload.add_field('payload_json', json.dumps(data), content_type="multipart/formdata")
        return await _network.network_se.post(
            url, data=pload
        )

    async def send_msg_src(self, file=None, filename=None):
        pload = {}
        if self.content:
            pload['content'] = self.content
        if self.flags:
            pload['flags'] = self.flags
        if len(self.components) > 0:
            pload['components'] = self.components
        return await self._send_msg(
            self.make_link(self.id, self.token, 'callback'),
            file=file, filename=filename,
            data={"type": InteractionCallbackType.CHANNEL_MESSAGE_WITH_SOURCE.value,
                  "data": pload
            }
        )
    
    async def send_autocomplete(self, arr: list[AutocompleteChoices]):
        return await _network.network_se.post(self.make_link(
            self.d['id'], self.d['token'], 'callback'
        ), json={
            "type": InteractionCallbackType.APPLICATION_COMMAND_AUTOCOMPLETE_RESULT.value,
            "data": {'choices': [{'name': x.name, 'value': x.value} for x in arr]}
        })

    async def defer_msg_with_src(self):
        """ Ack an interaction, user sees a loading state """
        return await _network.network_se.post(self.make_link(
            self.application_id, self.token
        ), data={'type': InteractionCallbackType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE.value})
    
    async def defer_update_msg(self):
        """ Ack an interaction, but user does not see a loading state """
        return await _network.network_se.post(self.make_link(
            self.d['id'], self.d['token'], 'callback'
        ), data={'type': InteractionCallbackType.DEFERRED_UPDATE_MESSAGE.value})