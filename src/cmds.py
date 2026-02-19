from discord.discord import Bot
from discord.contexts import InteractionContext as Context
from discord.interaction_enums import InteractionType

import random
import asyncio
import aiofiles
import settings
from os import unlink

FFMPEG_LOCATION = settings.FFMPEG_LOCATION
YT_DL_LOCATION = settings.YT_DL_LOCATION 


async def _get_frame_pic(frame: int, ):
    return ''


@Bot.on_interact(
   InteractionType.APPLICATION_COMMAND, 'edit')
async def _edit_files(ctx: Context):
    """edit file(s) with ffmpeg"""
    url = ctx.get_option('url')
    atchment = ctx.get_option('file')
    if not url or atchment:
        ctx.add_content('Please provide a url or an attachment!')
        return ctx.send_msg_src()
    if url and atchment:
        #url takes priority
        atchment = None
             

@Bot.command("ytdl")
async def _yt_dl(ctx):
    s = ctx.data['content'].split()
    cmds = []
    await ctx.trigger_typing()
    cmd_opts = ['-f']
    if len(s) < 2:
        await ctx.send_msg("Needs a link")
        return
    
    format = None

    if len(s) > 2:
        for i in range(2+(len(s)-2)):
            if s[i] in cmd_opts:
                try:
                    if s[i] == '-f':
                        format = s[i+1]                    
                except IndexError:
                    return await ctx.send_msg(
                        f"need format option after the {s[i]} flag.."
                    )

    await _yt_dl_res(ctx.send_msg, s[1], format=format)


async def _yt_dl_res(response_func, link, format=None):
    options = ['-f',]
    
    if format:
        options.append(format)
    else:
        options.append('bv[filesize<20M]+ba[filesize<5M] / bv[filesize_approx<25M] / bv / bv+ba / bv*[filesize_approx<25M]/ bv*[filesize<25M]')

    if link.find('tiktok') > -1:
        options.append('-S')
        options.append('vcodec:h264')

    file_id = random.randint(0, 30000000000000) 
    file_name = f"/tmp/{file_id}%(playlist_index)s.%(ext)s"
    proc = await asyncio.create_subprocess_exec(
            YT_DL_LOCATION, link, '--force-overwrites', '--ffmpeg-location',
            FFMPEG_LOCATION, '--no-warnings', *options, '-o', file_name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    if stdout:
        dst = stdout.decode().split('\n')
        if stderr:
            await response_func(stderr.decode())
        vids = 0
        for ln in dst:
            flc = None
            if ln[1:9] == 'download' and ln[11:22] == 'Destination':
                flc = ln.split(':')[1][1:]
            if ln[1:7] == 'Merger':
                flc = ln.split()[-1][1:-1]
            if ln.find('Aborting') > -1:
                await response_func(f"Sorry :( \n``{ln}``")
            if not flc: continue
            try:
                if vids >= 1:
                    return
                async with aiofiles.open(flc, mode='rb') as f:
                    c, m = await response_func(file=await f.read(), file_name=flc)
                    if c == 413:
                        await response_func("file too large it failed")
                    if c == 200:
                        vids+=1

                unlink(flc)
            except FileNotFoundError:
                continue
    elif stderr:
        return await response_func("internal error :(")