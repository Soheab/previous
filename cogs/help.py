from __future__ import annotations
from typing import Any, Callable, Coroutine, Dict, Literal, NamedTuple, Optional, Union
from re import I, L, search
from nextcord import utils
from nextcord.errors import Forbidden, HTTPException, NotFound
from nextcord.iterators import OT

from nextcord.utils import escape_markdown as escma
from typing import Dict, NamedTuple, Optional


from nextcord.ext import commands
from nextcord.abc import GuildChannel
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

from .utils.split_txtfile import split_txtfile


HELP_CHANNEL_ID: int = 890674348313157703  # 881965127031722004
HELP_LOGS_CHANNEL_ID: int = 890674366776475769  # 883035085434142781
HELPER_ROLE_ID: int = 916051595794448396  # 882192899519954944
HELP_MOD_ID: int = 916051618187870280  # 881119384528105523
CUSTOM_ID_PREFIX: str = "help:"


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

    log_embed = Embed(
        title=f"Help thread {state.lower()}",
        colour=Colour.dark_theme(),
        description=f"**Thread:** {thread.mention}\n**Author:** {escma(str(thread_author))} ({thread_author.id})",
    )
    if closed_by:
        log_embed.description += f"\n\n**Closed by:** {escma(str(closed_by))} ({closed_by.id}) from the {method.lower()}\n"  # type: ignore

    log_embed.set_footer(text=f"ID: {thread.id}")
    await thread.guild.get_channel(HELP_LOGS_CHANNEL_ID).send(embed=log_embed, view=HelpLogView(state, thread)) 


async def close_help_thread(method: str, thread_channel, thread_author, closed_by: Member, send_log: bool = True) -> None:
    """Closes a help thread. Is called from either the close button or the
    =close command.
    """
    if not thread_channel.last_message or not thread_channel.last_message_id:

        _last_msg = (await thread_channel.history(limit=1).flatten())[0]
    else:
        _last_msg = thread_channel.get_partial_message(thread_channel.last_message_id)

    thread_jump_url = _last_msg.jump_url

    dm_embed_thumbnail = str(thread_channel.guild.icon) if thread_channel.guild.icon else Embed.Empty
    embed_reply = Embed(
        title="This thread has now been closed", description=closing_message, colour=Colour.dark_theme()
    )

    await thread_channel.send(embed=embed_reply)  # Send the closing message to the help thread
    await thread_channel.edit(locked=True, archived=True)  # Lock thread

    if send_log:
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


class HelpLogButton(ui.Button["HelpLogView"]):
    CUSTOM_ID_PREFIX = "help_log:"
    def __init__(self, label: str, *, style: ButtonStyle, custom_id: str) -> None:
        super().__init__(label=label, style=style, custom_id=f"{self.CUSTOM_ID_PREFIX}{custom_id}")
        
    async def _get_thread(self, thread_id: int, thread: Optional[Thread] = None) -> Optional[Thread]:
        assert self.view is not None
        
        if thread is not None:
            return thread

        if not self.view.bot:
            return None

        help_channel = self.view.bot.get_channel(HELP_CHANNEL_ID)
        get_thread = help_channel.get_thread(thread_id) or help_channel.guild.get_thread(thread_id)
        if not get_thread:
            active_threads = await help_channel.guild.active_threads()
            return utils.get(active_threads, id=thread_id)
        else:
            return get_thread
        
    async def check(self, button: HelpLogButton, interaction: Interaction) -> None:
        assert isinstance(interaction.user, Member) and button.label is not None

        if button.custom_id != f"{HelpLogButton.CUSTOM_ID_PREFIX}view_thread":
            if not interaction.user.get_role(HELP_MOD_ID):
                await interaction.send(f"You do not have permission to {button.label.lower()} this thread.", ephemeral=True)
                return
        
        pass

    async def callback(self, interaction: Interaction) -> None:
        assert self.view is not None and isinstance(interaction.user, Member)

        thread_id = int(interaction.message.embeds[0].footer.text.split("ID:")[1]) # type: ignore
        self.view.thread = await self._get_thread(thread_id, self.view.thread)

        if not self.view.thread:
            for x in self.view.children:
                x.disabled = True
            
            await interaction.send("I can not find the thread associated with this log.", ephemeral=True)
            await interaction.message.edit(view=self.view)
            return

        await self.check(self, interaction)

        if self.custom_id == f"{self.CUSTOM_ID_PREFIX}close_thread":
            thread_author = await get_thread_author(self.view.thread)
            self.label = "Re-open"
            self.style = ButtonStyle.green
            self.custom_id = f"{self.CUSTOM_ID_PREFIX}reopen_thread"
            org_embed = interaction.message.embeds[0]
            org_embed.title = "Help thread closed" # type: ignore
            orginial_description = org_embed.description.split("**Re-opened by**: ")
            print(orginial_description)
            org_embed.description = (
                f"{orginial_description[0].strip()}\n\n**Closed by**: {interaction.user.mention} ({interaction.user.id}) using the button in logs"
            )

            await interaction.edit(view=self.view, embed=org_embed)
            await close_help_thread("BUTTON", self.view.thread, thread_author, interaction.user, send_log = False)

        elif self.custom_id == f"{self.CUSTOM_ID_PREFIX}reopen_thread":
            self.label = "Close"
            self.custom_id = f"{self.CUSTOM_ID_PREFIX}close_thread"
            self.style = ButtonStyle.danger

            org_embed = interaction.message.embeds[0]
            org_embed.title = "Help thread re-opened" # type: ignore
            orginial_description = org_embed.description.split("**Closed by**: ")
            print(orginial_description)
            org_embed.description = (
                f"{orginial_description[0].strip()}\n\n**Re-opened by**: {interaction.user.mention} ({interaction.user.id}) using the button in logs"
            )
            await interaction.edit(view=self.view, embed=org_embed)

            thread_messages = await self.view.thread.history(limit=4, oldest_first=True).flatten()
            closed_message = filter(
                lambda msg: msg.embeds and msg.embeds[0].title == "This thread has now been closed", thread_messages
            )

            await self.view.thread.edit(locked=False, archived=False)
            try:
                await list(closed_message)[0].delete()
            except (IndexError, NotFound, HTTPException):
                pass

        elif self.custom_id == f"{self.CUSTOM_ID_PREFIX}view_thread":
            if self.view.thread.permissions_for(interaction.user).read_messages:
                await interaction.send(f"You can already access that thread -> {self.view.thread.mention}", ephemeral=True)
            else:
                await self.view.thread.add_user(interaction.user)  #type: ignore
                await interaction.send(f"You have been added to the thread -> {self.view.thread.mention}", ephemeral=True)

class HelpLogView(ui.View):
    def __init__(self, state: Literal["OPENED", "CLOSED"], thread: Thread = None, /, *, bot: commands.Bot = None) -> None:
        super().__init__(timeout=None)
        # dirty way of making this a persistent view.
        # thread is optional because we can get it from the embed footer.
        # bot is optional because that's only needed to get the thread from the id.
        self.bot: Optional[commands.Bot] = bot
        self.thread = thread

        self.add_item(ui.Button(label="yes", url=f"discord://-/channels/423828791098605578/{self.thread.id}"))
        self.add_item(HelpLogButton("View", style=ButtonStyle.primary, custom_id="view_thread"))
        if state == "OPENED":
            self.add_item(HelpLogButton("Close", style=ButtonStyle.danger, custom_id="close_thread"))
        else:
            self.add_item(HelpLogButton("Re-open", style=ButtonStyle.green, custom_id="reopen_thread"))

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
        super().__init__(timeout = None)
        self.add_item(HelpButton("Nextcord", style = ButtonStyle.red, custom_id = "nextcord"))
        self.add_item(HelpButton("Python", style = ButtonStyle.green, custom_id = "python"))


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
        if interaction.channel.archived or interaction.channel.locked:
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

        return interaction.user.id == self._thread_author.id or interaction.user.get_role(HELP_MOD_ID)


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.create_views())

    async def create_views(self):
        if getattr(self.bot, "help_view_set", False) is False:
            self.bot.help_view_set = True
            self.bot.add_view(HelpView())
            self.bot.add_view(ThreadCloseView())
            for state in ("OPENED", "CLOSED"):
                self.bot.add_view(HelpLogView(state, bot=self.bot))

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
        await ctx.send("**:white_check_mark:  If you've read the guidelines "
                       "above, click a button to create a help thread!**",
                       view = HelpView())

    @commands.command()
    async def close(self, ctx):
        if not isinstance(ctx.channel, Thread) or ctx.channel.parent_id != HELP_CHANNEL_ID:
            return
        thread_author = await get_thread_author(ctx.channel)
        await close_help_thread("COMMAND", ctx.channel, thread_author, ctx.author)

    @commands.command()
    @commands.has_role(HELP_MOD_ID)
    async def topic(self, ctx, *, topic):
        if not ctx.channel.type == ChannelType.private_thread:
            return await ctx.send("This command can only be used in help threads!")
        if ctx.message.channel.parent.id != HELP_CHANNEL_ID:
            return await ctx.send("This command can only be used in help threads!")
        author = await get_thread_author(ctx.channel)
        await ctx.channel.edit(name=f"{topic} ({author})")


def setup(bot):
    bot.add_cog(HelpCog(bot))
