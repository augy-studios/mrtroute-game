"""Commands, answer buttons, names and the leaderboard.

A run is ten question cards in a row, per player per channel, so a server
channel can hold several players' runs at once. Tapping an answer redraws
that card as answered, its buttons disabled and coloured, and sends the next
card below it; the tenth sends the result.

Every slash command and button answers Discord within three seconds by
deferring first; the API call and the card follow.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

import discord

import db
import views
from api import ApiError, GameApi
from buttons import RegistryButton, make_view

log = logging.getLogger("bot.handlers")

GONE = {"run_not_found", "run_expired", "run_finished", "question_not_found"}

# (channel id, user id): whose run, where.
Key = tuple[int, int]


class NameModal(discord.ui.Modal):
    name = discord.ui.TextInput(label="Name on the leaderboard", min_length=1, max_length=20)

    def __init__(self, game: "Game", run_id: str) -> None:
        super().__init__(title="Add to the leaderboard", timeout=600)
        self.game = game
        self.run_id = run_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.game.on_name_modal(interaction, self.run_id, self.name.value)


class Game:
    def __init__(self, client: discord.Client, conn, api: GameApi, config) -> None:
        self.client = client
        self.conn = conn
        self.api = api
        self.config = config
        self.locks: defaultdict[Key, asyncio.Lock] = defaultdict(asyncio.Lock)
        # user_id -> Discord display name, cleaned. Memory only: every action
        # starts from one of the user's own interactions, which fills it again.
        self.display_names: dict[int, str | None] = {}

    def button(self, kind: str, label: str, style=views.GREY, **payload):
        return RegistryButton(db.register_button(self.conn, kind, **payload), label, style)

    def remember(self, user: discord.abc.User) -> None:
        self.display_names[user.id] = views.clean_name(getattr(user, "global_name", None) or user.name)

    def name_for(self, user_id: int) -> tuple[str | None, bool]:
        """The name to offer: the one last used, else the Discord display
        name. The second value says it is the Discord default."""
        saved = db.saved_name(self.conn, user_id)
        return (saved, False) if saved else (self.display_names.get(user_id), True)

    # Sending. A target is an interaction that has already been answered or
    # deferred, whose followup makes the new message, or a channel.

    async def send(self, target, built) -> None:
        embed, rows = built
        kw = {"embed": embed}
        view = make_view(rows)
        if view is not None:
            kw["view"] = view
        if isinstance(target, discord.Interaction):
            await target.followup.send(**kw)
        else:
            await target.send(**kw)

    async def notice(self, target, text: str) -> None:
        """A one-line answer: only the player sees it when Discord allows."""
        if isinstance(target, discord.Interaction):
            if target.response.is_done():
                await target.followup.send(text, ephemeral=True)
            else:
                await target.response.send_message(text, ephemeral=True)
        else:
            await target.send(text)

    async def api_failed(self, key: Key, target, err: ApiError) -> None:
        if err.code in GONE:
            db.clear_live(self.conn, *key)
            await self.notice(target, "That run is over. Send /play for another.")
        elif err.status in (400, 429) and err.message:
            await self.notice(target, err.message)
        else:
            log.warning("api error %s %s: %s", err.status, err.code, err.message)
            await self.notice(target, "The game server did not answer. Try again in a moment.")

    # A run.

    async def start_run(self, key: Key, user_id: int, target) -> None:
        run = await self.api.new_run(user_id)
        db.set_live(self.conn, key[0], user_id, run["run_id"])
        await self.ask(key, user_id, run["run_id"], target)

    async def ask(self, key: Key, user_id: int, run_id: str, target) -> None:
        """The run's open question, or its next. If the API cannot be reached,
        a button to try again, since the answered card above has none left."""
        try:
            q = await self.api.question(user_id, run_id)
        except ApiError as err:
            if err.code == "run_finished":
                await self.finish(key, user_id, run_id, target)
                return
            if err.code in GONE or err.status == 429:
                raise
            log.warning("next question failed %s %s", err.status, err.code)
            embed = discord.Embed(description="The next question did not load.", colour=views.BRAND)
            await self.send(target, (embed, [[self.button("resume", "Try again", views.PRIMARY, run_id=run_id, user_id=user_id)]]))
            return
        db.remember_question(self.conn, q)
        await self.send(target, views.question_card(q, self.button, user_id, run_id))

    async def answer(self, interaction: discord.Interaction, key: Key, payload: dict) -> None:
        user_id = interaction.user.id
        run_id = payload["run_id"]
        live = db.get_live(self.conn, *key)
        if live is None or live["run_id"] != run_id:
            # A card from a run that /play has since replaced.
            await interaction.edit_original_response(view=None)
            await self.notice(interaction, "That run is over. Send /play for another.")
            return

        q = db.shown_question(self.conn, payload["question_id"])
        choice = int(payload["choice"])
        try:
            result = await self.api.answer(user_id, payload["question_id"], choice)
        except ApiError as err:
            if err.code == "already_answered":
                # A double tap. The first one already moved the run on.
                return
            raise

        if q is not None:
            embed, view = views.answered_card(q, result, choice)
            await interaction.edit_original_response(embed=embed, view=view)
        if result["finished"]:
            await self.finish(key, user_id, run_id, interaction)
        else:
            await self.ask(key, user_id, run_id, interaction)

    async def finish(self, key: Key, user_id: int, run_id: str, target) -> None:
        db.clear_live(self.conn, *key)
        state = await self.api.run_state(user_id, run_id)
        name, _ = self.name_for(user_id)
        await self.send(target, views.result_card(state, self.button, user_id, run_id, name))

    async def leaderboard(self, user_id: int, target) -> None:
        data = await self.api.leaderboard()
        await self.send(target, views.leaderboard_card(data.get("entries", []), self.button, user_id))

    async def submit_name(self, user_id: int, run_id: str, name: str, target) -> None:
        """Adds a run under a name, typed or offered. A name that goes through
        is remembered, except the Discord name, which stays a default that
        follows the account."""
        try:
            result = await self.api.submit(run_id, name)
        except ApiError as err:
            if err.status == 400:
                await self.notice(target, f"{err.message or 'That name will not work.'} Press Another name to try again.")
                return
            await self.notice(target, err.message or "Could not add that run.")
            return
        offered, is_default = self.name_for(user_id)
        if not (is_default and result["name"] == offered):
            db.save_name(self.conn, user_id, result["name"])
        await self.send(target, views.submitted_card(result, self.button, user_id))

    # Entry points.

    async def run_locked(self, key: Key, target, action) -> None:
        async with self.locks[key]:
            try:
                await action()
            except ApiError as err:
                await self.api_failed(key, target, err)
            except discord.HTTPException as err:
                log.warning("discord refused a reply in %s: %r", key[0], err)

    @staticmethod
    def key_of(interaction: discord.Interaction) -> Key:
        return (interaction.channel_id, interaction.user.id)

    async def cmd_play(self, interaction: discord.Interaction) -> None:
        self.remember(interaction.user)
        await interaction.response.defer(thinking=True)
        key = self.key_of(interaction)
        await self.run_locked(key, interaction, lambda: self.start_run(key, interaction.user.id, interaction))

    async def cmd_leaderboard(self, interaction: discord.Interaction) -> None:
        self.remember(interaction.user)
        await interaction.response.defer(thinking=True)
        key = self.key_of(interaction)
        await self.run_locked(key, interaction, lambda: self.leaderboard(interaction.user.id, interaction))

    async def cmd_help(self, interaction: discord.Interaction) -> None:
        self.remember(interaction.user)
        uid = interaction.user.id
        embed, rows = views.help_card(self.button, uid, self.config.site_url, self.config.donation_url)
        # Only the asker needs the rules in a server channel.
        await interaction.response.send_message(
            embed=embed, view=make_view(rows), ephemeral=interaction.guild_id is not None
        )

    async def on_dm_text(self, message: discord.Message) -> None:
        key = (message.channel.id, message.author.id)
        if db.get_live(self.conn, *key) is not None:
            await message.channel.send("Tap an answer on the question card.")
        else:
            await message.channel.send("Send /play to start a run.")

    async def on_name_modal(self, interaction: discord.Interaction, run_id: str, name: str) -> None:
        self.remember(interaction.user)
        uid = interaction.user.id
        key = self.key_of(interaction)
        await interaction.response.defer(thinking=True)
        await self.run_locked(key, interaction, lambda: self.submit_name(uid, run_id, name.strip(), interaction))

    async def on_button(self, interaction: discord.Interaction, button_id: str) -> None:
        record = db.read_button(self.conn, button_id)
        if record is None:
            await self.notice(interaction, "That button has expired. Send /play to start again.")
            return
        kind, payload = record
        uid = interaction.user.id
        if payload.get("user_id") not in (None, uid):
            await self.notice(interaction, "That button belongs to someone else.")
            return
        self.remember(interaction.user)
        key = self.key_of(interaction)

        if kind == "answer":
            await interaction.response.defer()
            await self.run_locked(key, interaction, lambda: self.answer(interaction, key, payload))
        elif kind == "resume":
            await interaction.response.defer()
            live = db.get_live(self.conn, *key)
            if live is None or live["run_id"] != payload.get("run_id"):
                await self.notice(interaction, "That run is over. Send /play for another.")
                return
            await self.run_locked(key, interaction, lambda: self.ask(key, uid, payload["run_id"], interaction))
        elif kind == "play":
            await interaction.response.defer(thinking=True)
            await self.run_locked(key, interaction, lambda: self.start_run(key, uid, interaction))
        elif kind == "leaderboard":
            await interaction.response.defer(thinking=True)
            await self.run_locked(key, interaction, lambda: self.leaderboard(uid, interaction))
        elif kind == "submit" and payload.get("name"):
            await interaction.response.defer(thinking=True)
            name = payload["name"]
            await self.run_locked(key, interaction, lambda: self.submit_name(uid, payload["run_id"], name, interaction))
        elif kind == "submit":
            await interaction.response.send_modal(NameModal(self, payload["run_id"]))
        else:
            await self.notice(interaction, "That button has expired. Send /play to start again.")
