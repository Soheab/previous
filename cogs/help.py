from typing import Any, Callable, Coroutine, Dict, Literal, NamedTuple, Optional, Union
from re import L, search
from nextcord.errors import Forbidden, HTTPException

from nextcord.ext import commands
from nextcord.utils import escape_markdown as escma
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
    ui,
)

HELP_CHANNEL_ID: int = 890674348313157703  # 881965127031722004
HELP_LOGS_CHANNEL_ID: int = 890674366776475769  # 883035085434142781
HELPER_ROLE_ID: int = 916051595794448396  # 882192899519954944
STAFF_ROLE_ID: int = 916051618187870280  # 881119384528105523
CUSTOM_ID_PREFIX: str = "help:"

from .utils.split_txtfile import split_txtfile
from .utils.utility import can_close, is_thread

closing_message = (
    "If your question has not been answered or your issue not "
    "resolved, we suggest taking a look at [Python's Guide to "
    "Asking Good Questions](https://www.pythondiscord.com/pages/guides/pydis-guides/asking-good-questions/) "
    "to get more effective help."
)


async def get_thread_author(channel: Thread) -> Member:
    history = channel.history(oldest_first=True, limit=1)
    history_flat = await history.flatten()
    user = history_flat[0].mentions[0]
    return user


async def send_thread_log(
    state: Literal["OPENED", "CLOSED"], method: str, thread: Thread, thread_author: Member, closed_by: Member = None
) -> None:
    type_to_colour: Dict[str, Colour] = {"Nextcord": Colour.red(), "Python": Colour.green()}
    print(thread.name)
    thread_type = (search("(Python|Nextcord)", thread.name)).group()  # type: ignore
    thread_topic = search(".+?(?=Python|Nextcord)", thread.name)
    thread_topic = f"**Topic:** {thread_topic.group()}\n\n" if thread_topic else ""

    log_embed = Embed(
        title=f"{thread_type} Help thread {state.lower()}",
        colour=type_to_colour[thread_type],
        description=f"{thread_topic}**Thread:** {escma(str(thread.name.strip(thread_topic)))} ({thread.id})\n"
        f"**Author:** {escma(str(thread_author))} ({thread_author.id})",
    )
    if closed_by:
        log_embed.description += f"\n\n**Closed by:** {escma(str(closed_by))} ({closed_by.id}) from the {method.lower()}\n"  # type: ignore

    await thread.guild.get_channel(HELP_LOGS_CHANNEL_ID).send(embed=log_embed, view=LogView(state, thread))  # type: ignore


async def close_help_thread(method: str, thread_channel, thread_author, closed_by: Member):
    """Closes a help thread. Is called from either the close button or the
    =close command.
    """
    if not thread_channel.last_message or not thread_channel.last_message_id:

        _last_msg = ((await thread_channel.history(limit=1)).flatten())[0]
    else:
        _last_msg = thread_channel.get_partial_message(thread_channel.last_message_id)

    thread_jump_url = _last_msg.jump_url

    dm_embed_thumbnail = str(thread_channel.guild.icon) if thread_channel.guild.icon else Embed.Empty
    embed_reply = Embed(
        title="This thread has now been closed", description=closing_message, colour=Colour.dark_theme()
    )

    await thread_channel.send(embed=embed_reply)  # Send the closing message to the help thread
    await thread_channel.edit(locked=True, archived=True)  # Lock thread
    await send_thread_log("CLOSED", method, thread_channel, thread_author, closed_by)  # Send log

    # Make some slight changes to the previous thread-closer embed
    # to send to the user via DM.
    embed_reply.title = "Your help thread in the Nextcord server has been closed."
    embed_reply.description += (
        f"\n\nYou can use [**this link**]({thread_jump_url}) to " "access the archived thread for future reference"
    )
    embed_reply.set_thumbnail(url=dm_embed_thumbnail)
    try:
        await thread_author.send(embed=embed_reply)
    except (Forbidden, HTTPException):
        pass


class LogView(ui.View):
    def __init__(self, state: Literal["OPENED", "CLOSED"], thread: Thread, /):
        super().__init__(timeout=None)
        self.__state = state
        self.thread = thread
        self.visit_thread_button = ui.Button(
            label="Visit Thread", url=f"discord://-/channels/{thread.guild.id}/{thread.id}"
        )
        self.view_thread_button = ui.Button(label="View Thread", custom_id=f"{CUSTOM_ID_PREFIX}view_thread")
        self.close_thread_button = ui.Button(
            label="Close", style=ButtonStyle.danger, custom_id=f"{CUSTOM_ID_PREFIX}close_thread"
        )
        self.reopen_thread_button = ui.Button(
            label="Re-Open", style=ButtonStyle.green, custom_id=f"{CUSTOM_ID_PREFIX}reopen_thread"
        )

        self.add_buttons()

    def __gen_callback(self, _button: ui.Button) -> ui.Button:
        async def callback(interaction) -> None:
            if _button.custom_id == f"{CUSTOM_ID_PREFIX}close_thread":
                if interaction.user.get_role(STAFF_ROLE_ID) or interaction.user.get_role(HELPER_ROLE_ID):
                    thread_author = await get_thread_author(self.thread)
                    _button.disabled = True
                    await interaction.message.edit(view=self)
                    await close_help_thread("BUTTON", self.thread, thread_author, interaction.user)
                else:
                    await interaction.response.send_message(
                        "You do not have permission to close this thread.", ephermal=True
                    )

            elif _button.custom_id == f"{CUSTOM_ID_PREFIX}reopen_thread":
                if interaction.user.get_role(STAFF_ROLE_ID):
                    _button.disabled = True
                    await interaction.message.edit(view=self)
                    if not self.thread.last_message or not self.thread.last_message_id:
                        _last_msg = (await (self.thread.history(limit=1)).flatten())[0]
                    else:
                        _last_msg = self.thread.get_partial_message(self.thread.last_message_id)

                    await self.thread.edit(locked=False, archived=False)
                    await _last_msg.delete()
                else:
                    await interaction.response.send_message(
                        "You do not have permission to re-open this thread.", ephemeral=True
                    )

            elif _button.custom_id == f"{CUSTOM_ID_PREFIX}view_thread":
                if self.thread.permissions_for(interaction.user).read_messages:
                    await interaction.response.send_message("You can already access that thread.", ephemeral=True)
                else:
                    await self.thread.add_user(interaction.user)
                    await interaction.response.send_message("You have been added to the thread.", ephemeral=True)

        _button.callback = callback  # type: ignore
        return _button

    def add_buttons(self):
        self.add_item(self.visit_thread_button)
        self.add_item(self.__gen_callback(self.view_thread_button))
        if self.__state == "OPENED":
            self.add_item(self.__gen_callback(self.close_thread_button))
        else:
            self.add_item(self.__gen_callback(self.reopen_thread_button))


class HelpButton(ui.Button["HelpView"]):
    def __init__(self, help_type: str, *, style: ButtonStyle, custom_id: str):
        super().__init__(label=f"{help_type} help", style=style, custom_id=f"{CUSTOM_ID_PREFIX}{custom_id}")
        self._help_type = help_type

    async def create_help_thread(self, interaction: Interaction) -> None:
        channel_type = ChannelType.private_thread if interaction.guild.premium_tier >= 2 else ChannelType.public_thread
        thread = await interaction.channel.create_thread(
            name=f"{self._help_type} help ({interaction.user})", type=channel_type
        )

        await send_thread_log("OPENED", "BUTTON", thread, interaction.user)  # type: ignore # Send log
        close_button_view = ThreadCloseView()
        close_button_view._thread_author = interaction.user

        type_to_colour: Dict[str, Colour] = {"Nextcord": Colour.red(), "Python": Colour.green()}

        em = Embed(
            title=f"{self._help_type} Help needed!",
            description=f"Alright now that we are all here to help, what do you need help with?",
            colour=type_to_colour.get(self._help_type, Colour.blurple()),
        )
        em.set_footer(text="You and the helpers can close this thread with the button")

        msg = await thread.send(
            content=f"<@&{HELPER_ROLE_ID}> | {interaction.user.mention}", embed=em, view=ThreadCloseView()
        )
        await msg.pin(reason="First message in help thread with the close button.")

    async def callback(self, interaction: Interaction):
        if self.custom_id == f"{CUSTOM_ID_PREFIX}slashcmds":
            GIST_URL = "https://gist.github.com/TAG-Epic/68e05d98a89982bac827ad2c3a60c50a"
            ETA_WIKI = "https://en.wikipedia.org/wiki/Estimated_time_of_arrival"
            ETA_HYPER = f"[ETA]({ETA_WIKI} 'abbreviation for estimated time of arrival: the time you expect to arrive')"
            emb = Embed(
                title="Slash Commands",
                colour=Colour.blurple(),
                description="Slash commands aren't in the main library yet. You can use discord-interactions w/ nextcord for now. "
                f"To check on the progress (or contribute) see the pins of <#881191158531899392>. No {ETA_HYPER} for now.\n\n"
                f"(PS: If you are using discord-interactions for slash, please add [this cog]({GIST_URL} 'gist.github.com') "
                "(link). It restores the `on_socket_response` removed in d.py v2.)",
            )
            await interaction.response.send_message(embed=emb, ephemeral=True)
            return

        confirm_view = ConfirmView()

        def disable_all_buttons():
            for _item in confirm_view.children:
                _item.disabled = True

        confirm_content = "Are you really sure you want to make a help thread?"
        await interaction.response.send_message(content=confirm_content, ephemeral=True, view=confirm_view)
        await confirm_view.wait()
        if confirm_view.value is False or confirm_view.value is None:
            disable_all_buttons()
            content = "Ok, cancelled." if confirm_view.value is False else f"~~{confirm_content}~~ I guess not..."
            await interaction.edit_original_message(content=content, view=confirm_view)
        else:
            disable_all_buttons()
            await interaction.edit_original_message(content="Created!", view=confirm_view)
            await self.create_help_thread(interaction)


class HelpView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(HelpButton("Nextcord", style=ButtonStyle.red, custom_id="nextcord"))
        self.add_item(HelpButton("Python", style=ButtonStyle.green, custom_id="python"))
        self.add_item(HelpButton("Slash Commands", style=ButtonStyle.blurple, custom_id="slashcmds"))


class ConfirmButton(ui.Button["ConfirmView"]):
    def __init__(self, label: str, style: ButtonStyle, *, custom_id: str):
        super().__init__(label=label, style=style, custom_id=f"{CUSTOM_ID_PREFIX}{custom_id}")

    async def callback(self, interaction: Interaction):
        self.view.value = True if self.custom_id == f"{CUSTOM_ID_PREFIX}confirm_button" else False
        self.view.stop()


class ConfirmView(ui.View):
    def __init__(self):
        super().__init__(timeout=10.0)
        self.value = None
        self.add_item(ConfirmButton("Yes", ButtonStyle.green, custom_id="confirm_button"))
        self.add_item(ConfirmButton("No", ButtonStyle.red, custom_id="decline_button"))


class ThreadCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self._thread_author: Optional[Member] = None

    async def _get_thread_author(self, channel: Thread) -> None:
        self._thread_author = await get_thread_author(channel)

    @ui.button(label="Close", style=ButtonStyle.red, custom_id=f"{CUSTOM_ID_PREFIX}thread_close")
    async def thread_close_button(self, button: Button, interaction: Interaction):
        if interaction.channel.archived:
            button.disabled = True
            await interaction.message.edit(view=self)
            return

        if not self._thread_author:
            await self._get_thread_author(interaction.channel)  # type: ignore

        await close_help_thread("BUTTON", interaction.channel, self._thread_author, interaction.user)  # type: ignore

        button.disabled = True
        await interaction.message.edit(view=self)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if not self._thread_author:
            await self._get_thread_author(interaction.channel)  # type: ignore

        # because we aren't assigning the persistent view to a message_id.
        if not isinstance(interaction.channel, Thread) or interaction.channel.parent_id != HELP_CHANNEL_ID:
            return False

        return interaction.user.id == self._thread_author.id or interaction.user.get_role(HELPER_ROLE_ID)


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.create_views())

    async def create_views(self):
        if getattr(self.bot, "help_view_set", False) is False:
            self.bot.help_view_set = True
            self.bot.add_view(HelpView())
            self.bot.add_view(ThreadCloseView())

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id == HELP_CHANNEL_ID and message.type is MessageType.thread_created:
            await message.delete(delay=5)
        if (
            isinstance(message.channel, Thread)
            and message.channel.parent_id == HELP_CHANNEL_ID
            and message.type is MessageType.pins_add
        ):
            await message.delete(delay=10)

    @commands.Cog.listener()
    async def on_thread_member_remove(self, member: ThreadMember):
        thread = member.thread
        if thread.parent_id != HELP_CHANNEL_ID or thread.archived:
            return

        thread_author = await get_thread_author(thread)
        if member.id != thread_author.id:
            return

        await close_help_thread("EVENT", thread, thread_author, self.bot.user)  # type: ignore

    @commands.command()
    @commands.is_owner()
    async def help_menu(self, ctx):
        for section in split_txtfile("helpguide.txt"):
            await ctx.send(embed=Embed(description=section))
        await ctx.send(
            "**:white_check_mark:  If you've read the guidelines " "above, click a button to create a help thread!**",
            view=HelpView(),
        )

    @commands.command()
    @is_thread()
    @can_close()
    async def close(self, ctx):
        thread_author = await get_thread_author(ctx.channel)
        await close_help_thread("COMMAND", ctx.channel, thread_author, ctx.author)  # type: ignore

    @commands.command()
    @is_thread()
    @can_close()
    async def helptopic(self, ctx, *, topic: str):
        """Set the topic of this help thread. This is only available to staff and helpers.

        Please use keywords. Example: `=helptopic migrating`
        """
        # thread_type = (match("^(Python|Nextcord)", ctx.channel.name)).group()  # type: ignore
        await ctx.channel.edit(name=f"{topic} {ctx.channel.name}")
        await ctx.send(f"Topic set to: `{topic}` by {ctx.author.mention}.")

    @close.error
    @helptopic.error  # type: ignore
    async def help_thread_command_error(self, _: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            return
        else:
            raise error


def setup(bot):
    bot.add_cog(HelpCog(bot))
