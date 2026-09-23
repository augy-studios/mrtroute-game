"""Commands, answer buttons, names, settings and the leaderboard.

A run is ten questions, per player per channel, so a server channel can hold
several players' runs at once. With "remove old cards" on (the default), a
run is one card: each answer turns it into the next question, with how the
last one went at its top. Off, each answered card stays, its buttons disabled
and coloured, and the next card arrives below it.

Every slash command and button answers Discord within three seconds by
deferring first; the API call and the card follow.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

import discord

import db
import views
from api import ApiError, GameApi
from buttons import RegistryButton, make_view

log = logging.getLogger("bot.handlers")

GONE = {"run_not_found", "run_expired", "run_finished", "question_not_found"}

# An interaction token works for 15 minutes; a minute spare for slow calls.
HOOK_LIFE_S = 14 * 60

# (channel id, user id): whose run, where.
Key = tuple[int, int]


class NameModal(discord.ui.Modal):
    """A leaderboard name, either for one finished run or for settings."""

    name = discord.ui.TextInput(label="Name on the leaderboard", min_length=1, max_length=20)

    def __init__(self, game: "Game", run_id: str | None) -> None:
        super().__init__(title="Add to the leaderboard" if run_id else "Leaderboard name", timeout=600)
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

    def settings(self, user_id: int) -> dict:
        """Saved settings. A leaderboard name never set, or cleared, is the
        user's Discord display name; `name_is_default` says which it is."""
        prefs = db.get_settings(self.conn, user_id)
        prefs["name_is_default"] = not prefs["name"]
        if not prefs["name"]:
            prefs["name"] = self.display_names.get(user_id)
        return prefs

    # Sending. A target is an interaction that has already been answered or
    # deferred, whose followup makes the new message, or a channel.

    async def send(self, target, built) -> db.Card:
        """Sends a message and returns it as a card: its id and, when an
        interaction sent it, that interaction's token and issue time."""
        embed, rows = built
        kw = {"embed": embed}
        view = make_view(rows)
        if view is not None:
            kw["view"] = view
        if isinstance(target, discord.Interaction):
            msg = await target.followup.send(wait=True, **kw)
            return msg.id, target.token, target.created_at.timestamp()
        msg = await target.send(**kw)
        return msg.id, None, None

    async def edit_card(self, interaction: discord.Interaction, built) -> None:
        """Redraw the message the button was on."""
        embed, rows = built
        await interaction.edit_original_response(embed=embed, view=make_view(rows))

    async def notice(self, target, text: str) -> None:
        """A one-line answer: only the player sees it when Discord allows."""
        if isinstance(target, discord.Interaction):
            if target.response.is_done():
                await target.followup.send(text, ephemeral=True)
            else:
                await target.response.send_message(text, ephemeral=True)
        else:
            await target.send(text)

    def card_hook(self, live) -> discord.Webhook | None:
        """The webhook of the interaction that sent the card, while its token
        lasts. Through a user install the bot is often not in the channel, so
        its own token cannot touch the card, but the interaction's can."""
        token, at = live["hook_token"], live["hook_at"]
        if token and at and time.time() - at < HOOK_LIFE_S:
            return discord.Webhook.partial(self.client.application_id, token, client=self.client)
        return None

    async def retire_card(self, key: Key, live) -> None:
        """An old run's card goes, or with tidy chat off, stays without buttons."""
        msg_id = live["msg_id"]
        if not msg_id:
            return
        tidy = self.settings(live["user_id"])["tidy_chat"]
        hook = self.card_hook(live)
        try:
            if hook is not None:
                await (hook.delete_message(msg_id) if tidy else hook.edit_message(msg_id, view=None))
            else:
                message = self.client.get_partial_messageable(key[0]).get_partial_message(msg_id)
                await (message.delete() if tidy else message.edit(view=None))
        except discord.HTTPException as err:  # a card left behind is harmless
            log.info("could not retire %s in %s: %r", msg_id, key[0], err)

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
        old = db.get_live(self.conn, *key)
        if old:
            await self.retire_card(key, old)
        db.set_live(self.conn, key[0], user_id, run["run_id"])
        await self.ask(key, user_id, run["run_id"], target)

    async def ask(self, key: Key, user_id: int, run_id: str, target, in_place: bool = False, note=None) -> None:
        """The run's open question, or its next: redrawn into the button's own
        message when `in_place`, else as a new card. If the API cannot be
        reached, a button to try again."""
        try:
            q = await self.api.question(user_id, run_id)
        except ApiError as err:
            if err.code == "run_finished":
                await self.finish(key, user_id, run_id, target, in_place=in_place, last=note)
                return
            if err.code in GONE or err.status == 429:
                raise
            log.warning("next question failed %s %s", err.status, err.code)
            if in_place:
                await target.edit_original_response(view=None)
            embed = discord.Embed(description="The next question did not load.", colour=views.BRAND)
            await self.send(target, (embed, [[self.button("resume", "Try again", views.PRIMARY, run_id=run_id, user_id=user_id)]]))
            return
        db.remember_question(self.conn, q)
        card = views.question_card(q, self.button, user_id, run_id, note)
        if in_place:
            await self.edit_card(target, card)
        else:
            db.set_live_card(self.conn, *key, await self.send(target, card))

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

        if self.settings(user_id)["tidy_chat"] and q is not None:
            # One card per run: this one becomes the next question, or the result.
            note = views.answer_note(q, result, choice)
            if result["finished"]:
                await self.finish(key, user_id, run_id, interaction, in_place=True, last=note)
            else:
                await self.ask(key, user_id, run_id, interaction, in_place=True, note=note)
            return

        if q is not None:
            embed, view = views.answered_card(q, result, choice)
            await interaction.edit_original_response(embed=embed, view=view)
        if result["finished"]:
            await self.finish(key, user_id, run_id, interaction)
        else:
            await self.ask(key, user_id, run_id, interaction)

    async def finish(self, key: Key, user_id: int, run_id: str, target, in_place: bool = False, last=None) -> None:
        db.clear_live(self.conn, *key)
        state = await self.api.run_state(user_id, run_id)
        prefs = self.settings(user_id)
        submitted, note = None, None
        if prefs["auto_submit"] and prefs["name"] and not state.get("submitted") and not state.get("expired"):
            try:
                submitted = await self.api.submit(run_id, prefs["name"])
            except ApiError as err:
                which = "Discord name" if prefs["name_is_default"] else "saved name"
                note = (
                    f"Your {which} was refused, so this run was not added. Set another in /settings."
                    if err.status == 400
                    else "This run could not be added automatically. Try the button."
                )
        card = views.result_card(state, self.button, user_id, run_id, prefs["name"], submitted, note, last)
        if in_place:
            await self.edit_card(target, card)
        else:
            await self.send(target, card)

    async def leaderboard(self, user_id: int, target, board: str = "best", in_place: bool = False) -> None:
        """A new leaderboard message, or from its own switch button, the same
        message redrawn as the other board."""
        data = await self.api.leaderboard(board)
        card = views.leaderboard_card(board, data.get("entries", []), self.button, user_id)
        if in_place:
            await self.edit_card(target, card)
        else:
            await self.send(target, card)

    # Names.

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
        prefs = self.settings(user_id)
        if not (prefs["name_is_default"] and result["name"] == prefs["name"]):
            db.save_settings(self.conn, user_id, name=result["name"])
        await self.send(target, views.submitted_card(result, self.button, user_id))

    async def set_name(self, user_id: int, name: str, interaction: discord.Interaction) -> None:
        """From the settings card's name box. The card is redrawn in place."""
        try:
            result = await self.api.check_name(name)
        except ApiError as err:
            if err.status == 400:
                await self.notice(interaction, f"{err.message or 'That name will not work.'} Press Change name to try again.")
                return
            raise
        db.save_settings(self.conn, user_id, name=result["name"])
        await self.edit_card(
            interaction, views.settings_card(self.settings(user_id), self.button, user_id, note=f"Saved {result['name']}.")
        )

    async def change_setting(self, interaction: discord.Interaction, user_id: int, payload: dict) -> None:
        """A toggle on the settings card. The card is redrawn in place."""
        key = payload.get("key")
        prefs = self.settings(user_id)
        if key == "name":
            db.save_settings(self.conn, user_id, name=None)
        elif key in ("auto_submit", "tidy_chat"):
            if key == "auto_submit" and not prefs["name"]:
                await self.notice(interaction, "Set a leaderboard name first.")
                return
            db.save_settings(self.conn, user_id, **{key: not prefs[key]})
        else:
            await interaction.response.defer()
            return
        embed, rows = views.settings_card(self.settings(user_id), self.button, user_id)
        await interaction.response.edit_message(embed=embed, view=make_view(rows))

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

    async def cmd_settings(self, interaction: discord.Interaction) -> None:
        self.remember(interaction.user)
        uid = interaction.user.id
        embed, rows = views.settings_card(self.settings(uid), self.button, uid)
        await interaction.response.send_message(embed=embed, view=make_view(rows), ephemeral=True)

    async def cmd_help(self, interaction: discord.Interaction) -> None:
        self.remember(interaction.user)
        embed, rows = views.help_card(self.button, self.config.site_url, self.config.donation_url)
        await interaction.response.send_message(embed=embed, view=make_view(rows))

    async def on_dm_text(self, message: discord.Message) -> None:
        key = (message.channel.id, message.author.id)
        if db.get_live(self.conn, *key) is not None:
            await message.channel.send("Tap an answer on the question card.")
        else:
            await message.channel.send("Send /play to start a run.")

    async def on_name_modal(self, interaction: discord.Interaction, run_id: str | None, name: str) -> None:
        self.remember(interaction.user)
        uid = interaction.user.id
        key = self.key_of(interaction)
        if run_id:
            await interaction.response.defer(thinking=True)
            await self.run_locked(key, interaction, lambda: self.submit_name(uid, run_id, name.strip(), interaction))
        else:
            await interaction.response.defer()
            await self.run_locked(key, interaction, lambda: self.set_name(uid, name.strip(), interaction))

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
        elif kind == "setting":
            await self.change_setting(interaction, uid, payload)
        elif kind == "setname":
            await interaction.response.send_modal(NameModal(self, None))
        elif kind == "play":
            await interaction.response.defer(thinking=True)
            await self.run_locked(key, interaction, lambda: self.start_run(key, uid, interaction))
        elif kind == "leaderboard" and payload.get("board") in ("best", "total"):
            await interaction.response.defer()
            board = payload["board"]
            await self.run_locked(key, interaction, lambda: self.leaderboard(uid, interaction, board, in_place=True))
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
