"""
    Module for discord connections
"""
import traceback
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
API_LINK = "https://discord.com/api/"
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

    network_se = None

    def __init__(self):
        pass

    @staticmethod
    async def create_session():
        _network.network_se = ClientSession(connector=TCPConnector())

    async def get_request(self, url, **kwargs):
        """make a get request and return results"""
        if not self.network_se:
            return

        async with self.network_se.get(url, **kwargs) as response:
            status = response.status
            if status == HTTP_OK:
                try:
                    return status, await response.text()
                except UnicodeDecodeError:
                    return status, await response.read()
            else:
                return status, await response.read()

    async def put_request(self, url, **kwargs):
        """make a put request and return results"""
        if not self.network_se:
            return

        async with self.network_se.put(url, **kwargs) as response:
            status = response.status
            return status, await response.read()

    async def post_request(self, url, **kwargs):
        """make a post request"""
        if not self.network_se:
            return "No session"

        async with self.network_se.post(url, **kwargs) as response:
            return response.status, await response.text()

    async def patch_request(self, url, **kwargs):
        async with self.network_se.patch(url, **kwargs) as response:
            return response.status, await response.text()

class _websocket(_network):
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
                    await cmd(Context(self, msg))
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
            if k == (data['type'], data['data']['name']):
                await v(InterContext(self, msg))

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
            if not inter_type or name:
                pass
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


@dataclass
class Embed:
    fields: int


class Context(_network):
    """general class for op 0 gateway events types"""

    def __init__(self, bot, msg):
        super().__init__()
        self.bot = bot
        self.data = msg

    async def get_hdr(self):
        """return a default authorization header"""
        return {
            "Authorization": f"Bot {self.bot.token}",
            "Content-Type": "multipart/form-data",
        }


    async def send_msg(
        self, txt=None, file=None, file_name='cat.png',
        channel_id=None, embeds=None, mention_object=None,
        reference=None
    ):
        """create & send message to the channel in context"""
        data = FormData()
        pload = Atrdict()
        pload.content = txt
        pload.embeds = embeds
        pload.message_reference = reference
        pload.allowed_mentions = mention_object
        if not mention_object:
            pload.allowed_mentions = {"parse": []}
        if not reference:
            m_data = self.data['d']
            pload.message_reference = {
                "message_id": m_data['id'],
                "guild_id": m_data['guild_id'],
                "channel_id": m_data['channel_id']
            }
        hdrs = await self.get_hdr()
        if file:
            del hdrs["Content-Type"]
            data.add_field(
                "file", file, filename=file_name, content_type="multipart/formdata"
            )
            data.add_field("payload_json", json.dumps(pload))
        else:
            hdrs["Content-Type"] = "application/json"
            data = json.dumps(pload)
        ch_id = channel_id if channel_id else self.data["d"]["channel_id"]
        r = await self.post_request(
            API_LINK + f"channels/{ch_id}/messages", headers=hdrs, data=data
        )
        return r
    
    
    async def send_response_msg(
        self, txt=None, file=None, file_name="cat.png", inter_type=7
    ):
        """ Create and send a reponse to interaction with a message """

        inter_id = self.data['d']['id']
        inter_token = self.data['d']['token']
        data = FormData()
        hdrs = await self.get_hdr()
        del hdrs["Content-Type"]
        data.add_field("payload_json", json.dumps({
            "type": inter_type,
            "data": {
                "content": txt
            }
        }))
        if file:
            data.add_field("file", file,
                filename=file_name,
                content_type="multipart/formdata"
            )
        r = await self.post_request(
            API_LINK + f"interactions/{inter_id}/{inter_token}/callback",
            headers=hdrs, data=data 
        )

        return r

    async def send_autocomplete_result(self, choices):
        """ Create auto complete results and respond to interaction """
        inter_id = self.data['d']['id']
        inter_token = self.data['d']['token']
        data = FormData()
        hdrs = await self.get_hdr()
        hdrs['Content-Type'] = 'application/json'
        # del hdrs['Content-Type']
        data = {
            "type": 8,
            "data": {
                "choices": choices
            }
        }

        r = await self.post_request(
            API_LINK + f"interactions/{inter_id}/{inter_token}/callback",
            headers=hdrs, json=data
        )
        
        return r


    async def trigger_typing(self, channel_id=None):
        """Fire a typing event"""
        hdrs = await self.get_hdr()
        if not channel_id:
            ch_id = self.data["d"]["channel_id"]
        else:
            ch_id = channel_id
        url = f"{API_LINK}channels/{ch_id}/typing"
        return await self.post_request(url, headers=hdrs)

    def embed(self, title="", description=""):
        return

    async def create_dm(self, rec_id=None):
        """Create a dm channel and return it"""
        url = API_LINK + "users/@me/channels"
        if rec_id is None:
            authour = self.data["d"]["author"]
            rec_id = authour["id"]
        hdrs = await self.get_hdr()
        hdrs["Content-Type"] = "application/json"
        data = json.dumps({"recipient_id": rec_id})
        status, resul = await self.post_request(url, headers=hdrs, data=data)
        if resul:
            return Dm_channel(self.bot, self.data, json.loads(resul))
        else:
            return None

    async def create_reaction(self, emoji, channel_id=None, message_id=None):
        data = self.data["d"]
        url = API_LINK + "channels/"
        if channel_id and message_id:
            url += f"{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
        else:
            url += f"{data['channel_id']}/messages/{data['id']}/reactions/{emoji}/@me"

        hdrs = await self.get_hdr()
        await self.put_request(url, headers=hdrs)

    async def get_guild(self, gid=None):
        if not gid:
            gid = self.data["d"]["guild_id"]
        url = API_LINK + "guilds/" + gid
        return await self.get_request(url, headers=await self.get_hdr())

    async def get_guild_members(self, gid=None, limit=1000, after=0):
        data = self.data["d"]
        d2 = {"limit": limit, "after": after}
        gid = gid or data["guild_id"]
        url = API_LINK + "guilds/" + gid + "/members"
        return await self.get_request(
            url, headers=await self.get_hdr(), data=json.dumps(d2)
        )

    async def get_guild_member(self, gid=None, uid=None):
        data = self.data["d"]
        if not uid:
            uid = data["author"]["id"]
        if not gid:
            gid = data["guild_id"]
        url = API_LINK + "guilds/" + gid + "/members/" + uid
        return await self.get_request(url, headers=await self.get_hdr())

    async def get_user(self, uid=None):
        if not uid:
            uid = self.data['d']['author']['id']
        url = f"{API_LINK}users/{uid}"
        return await self.get_request(url, headers=await self.get_hdr())

    async def get_user_avatar(self, hash=None, uid=None, format='.png'):
        user = uid or self.data['d']['author']['id']
        if not hash:
            hash = json.loads((await self.get_user(uid=uid))[1])['avatar']
        return f"{CND_LINK}avatars/{user}/{hash}{format}"

    async def edit_orig_response(self, txt=None, file=None,
        embeds=None, file_name="cat.png"):
        data = FormData()
        token = self.data['d']['token']
        hdrs = await self.get_hdr()
        del hdrs['Content-Type']
        data.add_field("payload_json", json.dumps({
                "content": txt,
                "embeds": embeds
            }))
        if file:
            data.add_field("file", file,
                    filename=file_name,
                    content_type="img"
            )
        r = await self.patch_request(
                f"{API_LINK}webhooks/{self.bot.user_id}/{token}/messages/@original",
                headers=hdrs, data=data
                )
        return r


class Dm_channel(Context):
    """Dm channel"""

    def __init__(self, bot, msg, dm_channel):
        super().__init__(bot, msg)
        self.dm_channel = dm_channel

    async def send_msg(
        self, txt=None, file=None, channel_id=None, embeds=None, mention_object=None
    ):
        """Send msg to the dm channel"""
        if not channel_id:
            ch_id = self.dm_channel["id"]
        else:
            ch_id = channel_id
        return await super().send_msg(
            txt=txt,
            file=file,
            channel_id=ch_id,
            embeds=embeds,
            mention_object=mention_object,
        )


class InterContext(Context):
    
    def __init__(self, bot, msg):
        super().__init__(bot, msg)
        data = msg['d']
        self.gid = data['guild_id']
        self.user_data = data['member']['user']
        self.uid = self.user_data['id']
        self.username = self.user_data['username']
        self.options = data['data'].get('options')