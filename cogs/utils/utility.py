from nextcord.ext import commands
from nextcord.channel import Thread

from cogs.help import HELPER_ROLE_ID, STAFF_ROLE_ID, HELP_CHANNEL_ID


class CannotClose(commands.CheckFailure):
    pass


class NotInThread(commands.CheckFailure):
    pass


def can_close():
    def predicate(ctx):
        if not (ctx.author.get_role(HELPER_ROLE_ID) or ctx.author.get_role(STAFF_ROLE_ID)):
            raise CannotClose()
        return True
    return commands.check(predicate)


def is_thread():
    def predicate(ctx):
        if not isinstance(ctx.channel, Thread) or ctx.channel.parent_id != HELP_CHANNEL_ID:
            raise NotInThread()
        return True
    return commands.check(predicate)