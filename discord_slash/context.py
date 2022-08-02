import datetime
import typing
from warnings import warn

import discord
from discord.ext import commands
from discord.utils import snowflake_time

from . import error, http, model
from .dpy_overrides import ComponentMessage


class InteractionContext:
    """
    Base context for interactions.\n
    In some ways similar with discord.ext.commands.Context.

    .. warning::
        Do not manually init this model.

    :ivar message: Message that invoked the slash command.
    :ivar interaction_id: Interaction ID of the command message.
    :ivar bot: discord.py client.
    :ivar _http: :class:`.http.SlashCommandRequest` of the client.
    :ivar _logger: Logger instance.
    :ivar deferred: Whether the command is current deferred (loading state)
    :ivar _deferred_hidden: Internal var to check that state stays the same
    :ivar responded: Whether you have responded with a message to the interaction.
    :ivar guild_id: Guild ID of the command message. If the command was invoked in DM, then it is ``None``
    :ivar author_id: User ID representing author of the command message.
    :ivar channel_id: Channel ID representing channel of the command message.
    :ivar author: User or Member instance of the command invoke.
    """

    def __init__(
        self,
        _http: http.SlashCommandRequest,
        _json: dict,
        _discord: typing.Union[discord.Client, commands.Bot],
        logger,
    ):
        self._token = _json["token"]
        self.message = None  # Should be set later.
        self.interaction_id = _json["id"]
        self._http = _http
        self.bot = _discord
        self._logger = logger
        self.deferred = False
        self.responded = False
        self._deferred_hidden = False  # To check if the patch to the deferred response matches
        self.guild_id = int(_json["guild_id"]) if "guild_id" in _json else None
        self.author_id = int(
            _json["member"]["user"]["id"]
            if "member" in _json
            else _json["user"]["id"]
        )

        self.channel_id = int(_json["channel_id"])
        if self.guild:
            self.author = discord.Member(
                data=_json["member"], state=self.bot._connection, guild=self.guild
            )
        elif self.guild_id:
            self.author = discord.User(data=_json["member"]["user"], state=self.bot._connection)
        else:
            self.author = discord.User(data=_json["user"], state=self.bot._connection)
        self.created_at: datetime.datetime = snowflake_time(int(self.interaction_id))

    @property
    def _deffered_hidden(self):
        warn(
            "`_deffered_hidden` as been renamed to `_deferred_hidden`.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._deferred_hidden

    @_deffered_hidden.setter
    def _deffered_hidden(self, value):
        warn(
            "`_deffered_hidden` as been renamed to `_deferred_hidden`.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._deferred_hidden = value

    @property
    def deffered(self):
        warn("`deffered` as been renamed to `deferred`.", DeprecationWarning, stacklevel=2)
        return self.deferred

    @deffered.setter
    def deffered(self, value):
        warn("`deffered` as been renamed to `deferred`.", DeprecationWarning, stacklevel=2)
        self.deferred = value

    @property
    def guild(self) -> typing.Optional[discord.Guild]:
        """
        Guild instance of the command invoke. If the command was invoked in DM, then it is ``None``

        :return: Optional[discord.Guild]
        """
        return self.bot.get_guild(self.guild_id) if self.guild_id else None

    @property
    def channel(self) -> typing.Optional[typing.Union[discord.TextChannel, discord.DMChannel]]:
        """
        Channel instance of the command invoke.

        :return: Optional[Union[discord.abc.GuildChannel, discord.abc.PrivateChannel]]
        """
        return self.bot.get_channel(self.channel_id)

    async def defer(self, hidden: bool = False):
        """
        'Defers' the response, showing a loading state to the user

        :param hidden: Whether the deferred response should be ephemeral . Default ``False``.
        """
        if self.deferred or self.responded:
            raise error.AlreadyResponded("You have already responded to this command!")
        base = {"type": 5}
        if hidden:
            base["data"] = {"flags": 64}
            self._deferred_hidden = True
        await self._http.post_initial_response(base, self.interaction_id, self._token)
        self.deferred = True

    async def send(
        self,
        content: str = "",
        *,
        embed: discord.Embed = None,
        embeds: typing.List[discord.Embed] = None,
        tts: bool = False,
        file: discord.File = None,
        files: typing.List[discord.File] = None,
        allowed_mentions: discord.AllowedMentions = None,
        hidden: bool = False,
        delete_after: float = None,
        components: typing.List[dict] = None,
    ) -> model.SlashMessage:
        """
        Sends response of the interaction.

        .. warning::
            - Since Release 1.0.9, this is completely changed. If you are migrating from older version, please make sure to fix the usage.
            - You can't use both ``embed`` and ``embeds`` at the same time, also applies to ``file`` and ``files``.
            - If you send files in the initial response, this will defer if it's not been deferred, and then PATCH with the message

        :param content:  Content of the response.
        :type content: str
        :param embed: Embed of the response.
        :type embed: discord.Embed
        :param embeds: Embeds of the response. Maximum 10.
        :type embeds: List[discord.Embed]
        :param tts: Whether to speak message using tts. Default ``False``.
        :type tts: bool
        :param file: File to send.
        :type file: discord.File
        :param files: Files to send.
        :type files: List[discord.File]
        :param allowed_mentions: AllowedMentions of the message.
        :type allowed_mentions: discord.AllowedMentions
        :param hidden: Whether the message is hidden, which means message content will only be seen to the author.
        :type hidden: bool
        :param delete_after: If provided, the number of seconds to wait in the background before deleting the message we just sent. If the deletion fails, then it is silently ignored.
        :type delete_after: float
        :param components: Message components in the response. The top level must be made of ActionRows.
        :type components: List[dict]
        :return: Union[discord.Message, dict]
        """
        if embed and embeds:
            raise error.IncorrectFormat("You can't use both `embed` and `embeds`!")
        if embed:
            embeds = [embed]
        if embeds:
            if not isinstance(embeds, list):
                raise error.IncorrectFormat("Provide a list of embeds.")
            elif len(embeds) > 10:
                raise error.IncorrectFormat("Do not provide more than 10 embeds.")
        if file and files:
            raise error.IncorrectFormat("You can't use both `file` and `files`!")
        if file:
            files = [file]
        if delete_after and hidden:
            raise error.IncorrectFormat("You can't delete a hidden message!")
        if components and any(comp.get("type") != 1 for comp in components):
            raise error.IncorrectFormat(
                "The top level of the components list must be made of ActionRows!"
            )

        base = {
            "content": content,
            "tts": tts,
            "embeds": [x.to_dict() for x in embeds] if embeds else [],
            "allowed_mentions": allowed_mentions.to_dict()
            if allowed_mentions
            else self.bot.allowed_mentions.to_dict()
            if self.bot.allowed_mentions
            else {},
            "components": components or [],
        }
        if hidden:
            base["flags"] = 64

        initial_message = False
        if not self.responded:
            initial_message = True
            if files and not self.deferred:
                await self.defer(hidden=hidden)
            if self.deferred:
                if self._deferred_hidden != hidden:
                    self._logger.warning(
                        "Deferred response might not be what you set it to! (hidden / visible) "
                        "This is because it was deferred in a different state."
                    )
                resp = await self._http.edit(base, self._token, files=files)
                self.deferred = False
            else:
                json_data = {"type": 4, "data": base}
                await self._http.post_initial_response(json_data, self.interaction_id, self._token)
                resp = {} if hidden else await self._http.edit({}, self._token)
            self.responded = True
        else:
            resp = await self._http.post_followup(base, self._token, files=files)
        if files:
            for file in files:
                file.close()
        if hidden:
            return resp
        smsg = model.SlashMessage(
            state=self.bot._connection,
            data=resp,
            channel=self.channel or discord.Object(id=self.channel_id),
            _http=self._http,
            interaction_token=self._token,
        )
        if delete_after:
            self.bot.loop.create_task(smsg.delete(delay=delete_after))
        if initial_message:
            self.message = smsg
        return smsg


class SlashContext(InteractionContext):
    """
    Context of a slash command. Has all attributes from :class:`InteractionContext`, plus the slash-command-specific ones below.

    :ivar name: Name of the command.
    :ivar args: List of processed arguments invoked with the command.
    :ivar kwargs: Dictionary of processed arguments invoked with the command.
    :ivar subcommand_name: Subcommand of the command.
    :ivar subcommand_group: Subcommand group of the command.
    :ivar command_id: ID of the command.
    """

    def __init__(
        self,
        _http: http.SlashCommandRequest,
        _json: dict,
        _discord: typing.Union[discord.Client, commands.Bot],
        logger,
    ):
        self.name = self.command = self.invoked_with = _json["data"]["name"]
        self.args = []
        self.kwargs = {}
        self.subcommand_name = self.invoked_subcommand = self.subcommand_passed = None
        self.subcommand_group = self.invoked_subcommand_group = self.subcommand_group_passed = None
        self.command_id = _json["data"]["id"]

        super().__init__(_http=_http, _json=_json, _discord=_discord, logger=logger)


class ComponentContext(InteractionContext):
    """
    Context of a component interaction. Has all attributes from :class:`InteractionContext`, plus the component-specific ones below.

    :ivar custom_id: The custom ID of the component (has alias component_id).
    :ivar component_type: The type of the component.
    :ivar component: Component data retrieved from the message. Not available if the origin message was ephemeral.
    :ivar origin_message: The origin message of the component. Not available if the origin message was ephemeral.
    :ivar origin_message_id: The ID of the origin message.

    """

    def __init__(
        self,
        _http: http.SlashCommandRequest,
        _json: dict,
        _discord: typing.Union[discord.Client, commands.Bot],
        logger,
    ):
        self.custom_id = self.component_id = _json["data"]["custom_id"]
        self.component_type = _json["data"]["component_type"]
        super().__init__(_http=_http, _json=_json, _discord=_discord, logger=logger)
        self.origin_message = None
        self.origin_message_id = (
            int(_json["message"]["id"]) if "message" in _json else None
        )


        self.component = None

        self._deferred_edit_origin = False

        if self.origin_message_id and (_json["message"]["flags"] & 64) != 64:
            self.origin_message = ComponentMessage(
                state=self.bot._connection, channel=self.channel, data=_json["message"]
            )
            self.component = self.origin_message.get_component(self.custom_id)

    async def defer(self, hidden: bool = False, edit_origin: bool = False):
        """
        'Defers' the response, showing a loading state to the user

        :param hidden: Whether the deferred response should be ephemeral . Default ``False``.
        :param edit_origin: Whether the type is editing the origin message. If ``False``, the deferred response will be for a follow up message. Defaults ``False``.
        """
        if self.deferred or self.responded:
            raise error.AlreadyResponded("You have already responded to this command!")

        base = {"type": 6 if edit_origin else 5}

        if hidden:
            if edit_origin:
                raise error.IncorrectFormat(
                    "'hidden' and 'edit_origin' flags are mutually exclusive"
                )
            base["data"] = {"flags": 64}
            self._deferred_hidden = True

        self._deferred_edit_origin = edit_origin

        await self._http.post_initial_response(base, self.interaction_id, self._token)
        self.deferred = True

    async def send(
        self,
        content: str = "",
        *,
        embed: discord.Embed = None,
        embeds: typing.List[discord.Embed] = None,
        tts: bool = False,
        file: discord.File = None,
        files: typing.List[discord.File] = None,
        allowed_mentions: discord.AllowedMentions = None,
        hidden: bool = False,
        delete_after: float = None,
        components: typing.List[dict] = None,
    ) -> model.SlashMessage:
        if self.deferred and self._deferred_edit_origin:
            self._logger.warning(
                "Deferred response might not be what you set it to! (edit origin / send response message) "
                "This is because it was deferred with different response type."
            )
        return await super().send(
            content,
            embed=embed,
            embeds=embeds,
            tts=tts,
            file=file,
            files=files,
            allowed_mentions=allowed_mentions,
            hidden=hidden,
            delete_after=delete_after,
            components=components,
        )

    async def edit_origin(self, **fields):
        """
        Edits the origin message of the component.
        Refer to :meth:`discord.Message.edit` and :meth:`InteractionContext.send` for fields.
        """
        _resp = {}

        if content := fields.get("content"):
            _resp["content"] = str(content)

        embed = fields.get("embed")
        embeds = fields.get("embeds")
        file = fields.get("file")
        files = fields.get("files")
        if components := fields.get("components"):
            _resp["components"] = components

        if embed and embeds:
            raise error.IncorrectFormat("You can't use both `embed` and `embeds`!")
        if file and files:
            raise error.IncorrectFormat("You can't use both `file` and `files`!")
        if file:
            files = [file]
        if embed:
            embeds = [embed]
        if embeds:
            if not isinstance(embeds, list):
                raise error.IncorrectFormat("Provide a list of embeds.")
            elif len(embeds) > 10:
                raise error.IncorrectFormat("Do not provide more than 10 embeds.")
            _resp["embeds"] = [x.to_dict() for x in embeds]

        allowed_mentions = fields.get("allowed_mentions")
        _resp["allowed_mentions"] = (
            allowed_mentions.to_dict()
            if allowed_mentions
            else self.bot.allowed_mentions.to_dict()
            if self.bot.allowed_mentions
            else {}
        )

        if self.responded:
            raise error.IncorrectFormat("Already responded")

        if files and not self.deferred:
            await self.defer(edit_origin=True)
        if self.deferred:
            if not self._deferred_edit_origin:
                self._logger.warning(
                    "Deferred response might not be what you set it to! (edit origin / send response message) "
                    "This is because it was deferred with different response type."
                )
            _json = await self._http.edit(_resp, self._token, files=files)
            self.deferred = False
        else:  # noqa: F841
            json_data = {"type": 7, "data": _resp}
            _json = await self._http.post_initial_response(  # noqa: F841
                json_data, self.interaction_id, self._token
            )
        self.responded = True
        if files:
            for file in files:
                file.close()

        # Commented out for now as sometimes (or at least, when not deferred) _json is an empty string?
        # self.origin_message = ComponentMessage(state=self.bot._connection, channel=self.channel,
        #                                        data=_json)
