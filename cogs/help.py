from typing import Dict, NamedTuple, Optional, Pattern, Tuple, Union
from re import compile

from .utils.split_txtfile import split_txtfile

from nextcord.ext import commands
from nextcord.abc import GuildChannel, User
from nextcord import (
    Button,
    ButtonStyle,
    ChannelType,
    Colour,
    Embed,
    Forbidden,
    Guild,
    HTTPException,
    Interaction,
    Member,
    MessageType,
    Thread,
    ThreadMember,
    ui
)

HELP_CHANNEL_ID: int = 881965127031722004
HELP_LOGS_CHANNEL_ID: int = 883035085434142781
HELPER_AUTO_ADD_ROLE_ID_ID: int = 882192899519954944
HELPER_ROLE_ID: int = 896860382226956329
CUSTOM_ID_PREFIX: str = "help:"
THREAD_NAME_REGEX: Pattern[str] = compile(r"(.*?) (\(\d{18,21}\))")

closing_message = (
    "If your question has not been answered or your issue not resolved, we suggest taking a look at "
    "[Python's Guide to Asking Good Questions](https://www.pythondiscord.com/pages/guides/pydis-guides/asking-good-questions/) "
    "to get more effective help.")


async def get_thread_author(channel: Thread) -> Union[User, Member]:
    history = channel.history(oldest_first = True, limit = 1)
    history_flat = await history.flatten()
    user = history_flat[0].mentions[0]
    return user  # type: ignore


async def close_help_thread(thread: Thread, /, thread_author: Union[User, Member], author: Union[User, Member] = None):
    """ Closes a help thread. Is called from either the close button or the =close command. """
    if not thread.last_message or not thread.last_message_id:
        _last_msg = (await thread.history(limit = 1).flatten())[0]
    else:
        _last_msg = thread.get_partial_message(thread.last_message_id)  # type: ignore

    thread_jump_url = _last_msg.jump_url

    embed_reply = Embed(title="This thread has now been closed", description=closing_message, colour=Colour.dark_theme())

    await thread.send(embed=embed_reply)  # Send the closing message to the help thread
    await thread.edit(locked = True, archived = True)  # Lock thread
    closed_by = author.mention if author else "Unknown"
    await thread.guild.get_channel(HELP_LOGS_CHANNEL_ID).send(  # type: ignore
        f"Help thread: {thread.mention} by {thread_author.mention} has been closed by {closed_by}."
    )

    # Make some slight changes to the previous thread-closer embed
    # to send to the user via DM.
    embed_reply.title = "Your help thread in the Nextcord server has been closed."
    embed_reply.description += f"\n\nYou can use [**this link**]({thread_jump_url}) to access the archived thread for future reference."  # type: ignore
    if thread.guild.icon:
        embed_reply.set_thumbnail(url=thread.guild.icon.url)

    try:
        await thread_author.send(embed=embed_reply)  # type: ignore
    except (HTTPException, Forbidden):
        pass

class ConfirmButton(ui.Button):
    def __init__(self, label: str, style: ButtonStyle, *, custom_id: str):
        super().__init__(label = label, style = style, custom_id = f"{CUSTOM_ID_PREFIX}{custom_id}")

    async def callback(self, _: Interaction):
        self.view.value = True if self.custom_id == f"{CUSTOM_ID_PREFIX}confirm_button" else False  # type: ignore
        self.view.stop()  # type: ignore

class ThreadCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout = None)
        self._thread_author: Optional[Member] = None

    async def _get_thread_author(self, channel: Thread) -> None:
        self._thread_author = await get_thread_author(channel)  # type: ignore

    @ui.button(label = "Close", style = ButtonStyle.red, custom_id = f"{CUSTOM_ID_PREFIX}thread_close")  # type: ignore
    async def thread_close_button(self, button: Button, interaction: Interaction):
        if (interaction.channel.archived or interaction.channel.locked) and interaction.message:  # type: ignore
            button.disabled = True
            await interaction.message.edit(view = self)
            return

        if not self._thread_author:
            await self._get_thread_author(interaction.channel)  # type: ignore
        
        await close_help_thread(interaction.channel, thread_author=self._thread_author, author=interaction.user)  # type: ignore
        button.disabled = True
        if not interaction.response.is_done():
            await interaction.response.edit_message(view = self)
        elif interaction.message:
            await interaction.message.edit(view = self)  # type: ignore
        else:
            return

        return

    async def interaction_check(self, interaction: Interaction) -> bool:
        if not self._thread_author:
            await self._get_thread_author(interaction.channel)  # type: ignore

        # because we aren't assigning the persistent view to a message_id.
        if not isinstance(interaction.channel, Thread) or interaction.channel.parent_id != HELP_CHANNEL_ID:
            return False

        return interaction.user.id == self._thread_author.id or interaction.user.get_role(HELPERS_ROLE_ID)  # type: ignore


class HelpThreadView(ui.View):
    def __init__(self):
        super().__init__(timeout = None)

    async def open_help_thread(self, interaction: Interaction) -> Thread:
        thread = await interaction.channel.create_thread(  # type: ignore
            name=f"Help needed ({interaction.user.id})",  # type: ignore
            type=ChannelType.public_thread
        )  

        await interaction.guild.get_channel(HELP_LOGS_CHANNEL_ID).send(  # type: ignore
            content = f"Help thread opened by {interaction.user.mention}: {thread.mention}!"  # type: ignore
        )
        close_button_view = ThreadCloseView()
        close_button_view._thread_author = interaction.user  # type: ignore

        em = Embed(
            title=f"Help needed!",
            description=f"Alright now that we are all here to help, what do you need help with?",
            colour=Colour.blurple()
        )
        em.set_footer(text = "You can close this thread with the button below. You can also use the =close command.")

        msg = await thread.send(
            content = f"<@&{HELPER_AUTO_ADD_ROLE_ID}> | {interaction.user.mention}",  # type: ignore
            embed = em,
            view = ThreadCloseView()
        )
        await msg.pin(reason = "First message in help thread with the close button.")

        return thread

    async def send_confirmation_message(self, interaction: Interaction) -> bool:
        message = "Are you really sure you want to make a help thread?"
        confirm_view = ui.View(timeout=10.0)
        confirm_view.add_item(ConfirmButton("Yes", ButtonStyle.green, custom_id = "confirm_button"))
        confirm_view.add_item(ConfirmButton("No", ButtonStyle.red, custom_id = "decline_button"))

        await interaction.send(message, ephemeral = True, view = confirm_view)

        await confirm_view.wait()
        for item in confirm_view.children:  # type: ignore
            item.disabled = True  # type: ignore

        if not getattr(confirm_view, "value", None):
            content = "Cancelled!" if getattr(confirm_view, "value", False) is False else f"Timed out!"
            await interaction.edit(content = f"~~{message}~~ {content}", view = confirm_view)
            return False
        else:
            return True

    @ui.button(label="Create Thread", style=ButtonStyle.blurple, custom_id=f"{CUSTOM_ID_PREFIX}:create_thread")  # type: ignore
    async def create_thread(self, _: Button, interaction: Interaction):
        should_create = await self.send_confirmation_message(interaction)
        if should_create:
            await self.open_help_thread(interaction)


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.create_views())

    async def create_views(self):
        await self.bot.wait_until_ready()
        if getattr(self.bot, "help_views_set", False) is False:
            self.bot.help_views_set = True
            self.bot.add_view(HelpThreadView())
            self.bot.add_view(ThreadCloseView())

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id == HELP_CHANNEL_ID and message.type is MessageType.thread_created:
            await message.delete(delay = 5)

        if isinstance(message.channel, Thread) and \
                message.channel.parent_id == HELP_CHANNEL_ID and \
                message.type is MessageType.pins_add:
            await message.delete(delay = 10)

    @commands.Cog.listener()
    async def on_thread_member_remove(self, member: ThreadMember):
        thread = member.thread
        if thread.parent_id != HELP_CHANNEL_ID or thread.archived:
            return

        thread_author = await get_thread_author(thread)
        if member.id != thread_author.id:
            return

        await close_help_thread(thread, thread_author=thread_author, author=thread.guild.me)

    @commands.command()
    @commands.is_owner()
    async def help_menu(self, ctx):
        for section in split_txtfile("helpguide.txt"):
            await ctx.send(embed=Embed(description=section))
        await ctx.send(
            content="**:white_check_mark:  If you've read the guidelines above, click a button to create a help thread!**",
            view=HelpThreadView()
        )

    @commands.command()
    async def close(self, ctx):
        if not isinstance(ctx.channel, Thread) or ctx.channel.parent_id != HELP_CHANNEL_ID:
            return
        thread_author = await get_thread_author(ctx.channel)
        await close_help_thread(ctx.channel, thread_author=thread_author, author=ctx.author)

    @commands.command()
    @commands.has_role(HELPER_ROLE_ID)
    async def topic(self, ctx, *, topic: str):
        if ctx.channel.parent.id != HELP_CHANNEL_ID:
            return await ctx.send("This command can only be used in help threads!")

        topic, user_id = THREAD_NAME_REGEX.search(ctx.channel.name).groups()  # type: ignore
        await ctx.channel.edit(name=f"{topic} ({user_id})")

    @commands.command()
    @commands.has_role(HELPER_ROLE_ID)
    async def openthreads(self, ctx):
        all_active_threads = [
            thread for thread in await ctx.guild.active_threads()
            if thread.parent_id == HELP_CHANNEL_ID and not (thread.archived or thread.locked)
        ]
        def get_info(name: str) -> Tuple[str, str]:
            thread_name, user_id = THREAD_NAME_REGEX.search(name).groups()
            return thread_name, user_id

        text = ""
        for thread in all_active_threads:
            thread_name, user_id = get_info(thread.name)
            text += f"{thread_name} ({user_id})\n"

        embed = Embed(
            title="Active help threads",
            description="\n".join(str(x) for x in text)
        )
        await ctx.send(embed=embed)


    @topic.error
    async def topic_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Please specify a topic!")
            return
        elif isinstance(error, commands.MissingRole):
            await ctx.send("Only helpers can use this command!")
            return
        else:
            return

def setup(bot):
    bot.add_cog(HelpCog(bot))
