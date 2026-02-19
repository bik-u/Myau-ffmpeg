import json
from aiohttp import FormData
from discord.links import API_LINK
from discord.network import _network

from discord.interaction_enums import InteractionType, InteractionCallbackType, ComponentTypes, \
    ButtonStyles, AutocompleteChoices, message_flag


async def _send_msg(url=None, file=None, filename=None, data=None, headers=None):
    pload = FormData()
    if file:
        pload.add_field('file', file, filename=filename,
            content_type="multipart/formdata")
    pload.add_field('payload_json', json.dumps(data), content_type="multipart/formdata")
    return await _network.network_se.post(
        url, data=pload, headers=headers
    )


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

    async def send_msg_src(self, file=None, filename=None):
        pload = {}
        if self.content:
            pload['content'] = self.content
        if self.flags:
            pload['flags'] = self.flags
        if len(self.components) > 0:
            pload['components'] = self.components
        return await _send_msg(
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
    

class MessageContext:

    def __init__(self, bot, msg):
        self.bot = bot
        self.data = msg.get('d')
        self.channel_id = self.data.get('channel_id')

    def get_headers(self):
        return {
            "Authorization": f"Bot {self.bot.token}"
        }

    async def send_msg(self, msg=None, file=None, file_name=None):
        data =  {
            "content": msg,
        }
        return await _send_msg(
            url = f"{API_LINK}channels/{self.channel_id}/messages",
            data=data, headers=self.get_headers(), file=file, filename=None)

    async def trigger_typing(self):
        return await _send_msg(
            url = f"{API_LINK}channels/{self.channel_id}/typing",
            headers=self.get_headers()
        )
