"""
    Module for discord connections
"""
import json
import asyncio

from discord.contexts import InteractionContext, MessageContext
from discord.network import _network, _websocket
from discord.intents import intents

RECV_TIMEOUT = 40
PING_TIMEOUT = 0.5
GATE_WAY = "wss://gateway.discord.gg/?v=8&encoding=json&compress=zlib-stream"
ZLIB_SUFFIX = b"\x00\x00\xff\xff"
CND_LINK = "https://cdn.discordapp.com/"

# Close code events
ATTEMPT_RESUMING = 1002
INVALID_SEQ = 4007

# Http status codes
HTTP_OK = 200
HTTP_PUT_OK = 204


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
                    await cmd(MessageContext(self, msg))
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

