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