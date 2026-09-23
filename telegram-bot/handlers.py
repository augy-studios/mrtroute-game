"""Commands, answer buttons, names, settings and the leaderboard.

A run is ten questions. Tapping an answer shows how it went and brings the
next question. With "remove old cards" on (the default) that all happens in
one card, edited in place, with how the last question went at its top. Off,
each answered card stays in the chat without its buttons and the next card
arrives below it.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from telethon import Button

import db
import reply as r
import views
from api import ApiError, GameApi

log = logging.getLogger("bot.handlers")

GONE = {"run_not_found", "run_expired", "run_finished", "question_not_found"}

NAME_PROMPT = (
    "Send the name to show on the leaderboard, up to 20 characters. "
    "Names are shared: anyone who picks the same one shares its entry."
)


class Game:
    def __init__(self, client, conn, api: GameApi, config) -> None:
        self.client = client
        self.conn = conn
        self.api = api
        self.config = config
        self.locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        # user_id -> Telegram first name, cleaned. Memory only: every action
        # starts from one of the user's own updates, which fills it again.
        self.first_names: dict[int, str | None] = {}

    def button(self, kind: str, label: str, **payload):
        return Button.inline(label, db.register_button(self.conn, kind, **payload))

    async def remember_sender(self, event) -> None:
        try:
            sender = await event.get_sender()
        except Exception as err:  # noqa: BLE001 - no default name is the worst of it
            log.info("could not read the sender of %s: %r", event.chat_id, err)
            return
        self.first_names[event.sender_id] = views.clean_name(getattr(sender, "first_name", None))

    def settings(self, user_id: int) -> dict:
        """Saved settings. A leaderboard name never set, or cleared, is the
        user's Telegram first name; `name_is_default` says which it is."""
        prefs = db.get_settings(self.conn, user_id)
        prefs["name_is_default"] = not prefs["name"]
        if not prefs["name"]:
            prefs["name"] = self.first_names.get(user_id)
        return prefs

    async def send(self, chat_id: int, built) -> int | None:
        rich, buttons = built
        return r.sent_message_id(await r.send_rich_message(self.client, chat_id, rich, buttons))

    async def edit(self, chat_id: int, msg_id: int, built) -> None:
        rich, buttons = built
        await r.edit_rich_message_at(self.client, chat_id, msg_id, rich, buttons)

    async def delete(self, chat_id: int, msg_id: int | None) -> None:
        if not msg_id:
            return
        try:
            await self.client.delete_messages(chat_id, [msg_id])
        except Exception as err:  # noqa: BLE001 - a message left behind is harmless
            log.info("could not delete %s in %s: %r", msg_id, chat_id, err)

    async def retire_card(self, chat_id: int, user_id: int, msg_id: int | None) -> None:
        """An old run's card goes, or with tidy chat off, stays without buttons."""
        if not msg_id:
            return
        if self.settings(user_id)["tidy_chat"]:
            await self.delete(chat_id, msg_id)
            return
        try:
            await r.strip_buttons(self.client, chat_id, msg_id)
        except Exception as err:  # noqa: BLE001 - its buttons already refuse an old run
            log.info("could not strip buttons from %s in %s: %r", msg_id, chat_id, err)

    async def api_failed(self, chat_id: int, err: ApiError) -> None:
        if err.code in GONE:
            db.clear_live(self.conn, chat_id)
            await self.client.send_message(chat_id, "That run is over. Send /play for another.")
        elif err.status == 429 and err.message:
            await self.client.send_message(chat_id, err.message)
        else:
            log.warning("api error %s %s: %s", err.status, err.code, err.message)
            await self.client.send_message(chat_id, "The game server did not answer. Try again in a moment.")

    # A run.

    async def start_run(self, chat_id: int, user_id: int) -> None:
        db.clear_prompt(self.conn, chat_id)
        run = await self.api.new_run(user_id)
        old = db.get_live(self.conn, chat_id)
        if old:
            await self.retire_card(chat_id, user_id, old["msg_id"])
        db.set_live(self.conn, chat_id, user_id, run["run_id"])
        await self.ask(chat_id, user_id, run["run_id"])

    async def ask(self, chat_id: int, user_id: int, run_id: str, into: int | None = None, note=None) -> None:
        """The run's open question, or its next: into message `into` when
        given, else as a new card. If the API cannot be reached, a button to
        try again, since the card above has no buttons left."""
        try:
            q = await self.api.question(user_id, run_id)
        except ApiError as err:
            if err.code == "run_finished":
                await self.finish(chat_id, user_id, run_id, into=into, last=note)
                return
            if err.code in GONE or err.status == 429:
                raise
            log.warning("next question failed %s %s", err.status, err.code)
            if into:
                await r.strip_buttons(self.client, chat_id, into)
            await self.client.send_message(
                chat_id,
                "The next question did not load.",
                buttons=[[self.button("resume", "Try again", run_id=run_id, user_id=user_id)]],
            )
            return
        db.remember_question(self.conn, q)
        card = views.question_card(q, self.button, user_id, run_id, note)
        if into:
            await self.edit(chat_id, into, card)
            db.set_live_card(self.conn, chat_id, into)
        else:
            db.set_live_card(self.conn, chat_id, await self.send(chat_id, card))

    async def answer(self, event, user_id: int, payload: dict) -> None:
        chat_id = event.chat_id
        msg_id = event.query.msg_id
        run_id = payload["run_id"]
        live = db.get_live(self.conn, chat_id)
        if live is None or live["run_id"] != run_id:
            # A card from a run that /play has since replaced.
            await r.strip_buttons(self.client, chat_id, msg_id)
            await self.client.send_message(chat_id, "That run is over. Send /play for another.")
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

        tidy = self.settings(user_id)["tidy_chat"] and q is not None
        if tidy:
            # One card per run: this one becomes the next question, or the result.
            note = views.answer_note(q, result, choice)
            if result["finished"]:
                await self.finish(chat_id, user_id, run_id, into=msg_id, last=note)
            else:
                await self.ask(chat_id, user_id, run_id, into=msg_id, note=note)
            return

        if q is not None:
            await self.edit(chat_id, msg_id, views.answered_card(q, result, choice))
        if result["finished"]:
            await self.finish(chat_id, user_id, run_id)
        else:
            await self.ask(chat_id, user_id, run_id)

    async def finish(self, chat_id: int, user_id: int, run_id: str, into: int | None = None, last=None) -> None:
        db.clear_live(self.conn, chat_id)
        state = await self.api.run_state(user_id, run_id)
        prefs = self.settings(user_id)
        submitted, note = None, None
        if prefs["auto_submit"] and prefs["name"] and not state.get("submitted") and not state.get("expired"):
            try:
                submitted = await self.api.submit(run_id, prefs["name"])
            except ApiError as err:
                which = "Telegram name" if prefs["name_is_default"] else "saved name"
                note = (
                    f"Your {which} was refused, so this run was not added. Set another in /settings."
                    if err.status == 400
                    else "This run could not be added automatically. Try the button."
                )
        card = views.result_card(state, self.button, user_id, run_id, prefs["name"], submitted, note, last)
        if into:
            await self.edit(chat_id, into, card)
        else:
            await self.send(chat_id, card)

    async def leaderboard(self, chat_id: int, user_id: int, board: str = "best", event=None) -> None:
        """A new leaderboard message, or from its own switch button, the same
        message redrawn as the other board."""
        data = await self.api.leaderboard(board)
        rich, buttons = views.leaderboard_card(board, data.get("entries", []), self.button, user_id)
        if event is not None:
            await r.edit_rich_message(self.client, event, rich, buttons)
        else:
            await self.send(chat_id, (rich, buttons))

    # Names.

    async def submit_name(self, chat_id: int, user_id: int, run_id: str, name: str) -> None:
        """Adds a run under a name, typed or offered. A refused name reopens
        the prompt. A name that goes through is remembered, except the
        Telegram name, which stays a default that follows the account."""
        try:
            result = await self.api.submit(run_id, name)
        except ApiError as err:
            if err.status == 400:
                db.set_prompt(self.conn, chat_id, "submit", run_id)
                await self.client.send_message(chat_id, f"{err.message or 'That name will not work.'} Send another.")
                return
            db.clear_prompt(self.conn, chat_id)
            await self.client.send_message(chat_id, err.message or "Could not add that run.")
            return
        db.clear_prompt(self.conn, chat_id)
        prefs = self.settings(user_id)
        if not (prefs["name_is_default"] and result["name"] == prefs["name"]):
            db.save_settings(self.conn, user_id, name=result["name"])
        buttons = [[self.button("leaderboard", "Leaderboard", user_id=user_id), self.button("play", "Play again", user_id=user_id)]]
        await self.send(chat_id, (views.submitted_line(result), buttons))

    async def set_name(self, chat_id: int, user_id: int, name: str) -> None:
        try:
            result = await self.api.check_name(name)
        except ApiError as err:
            if err.status == 400:
                await self.client.send_message(chat_id, f"{err.message or 'That name will not work.'} Send another.")
                return
            raise
        db.clear_prompt(self.conn, chat_id)
        db.save_settings(self.conn, user_id, name=result["name"])
        await self.send(
            chat_id, views.settings_card(self.settings(user_id), self.button, user_id, note=f"Saved {result['name']}.")
        )

    async def change_setting(self, event, user_id: int, payload: dict) -> None:
        """A toggle on the settings card. The card is redrawn in place."""
        key = payload.get("key")
        prefs = self.settings(user_id)
        if key == "name":
            db.save_settings(self.conn, user_id, name=None)
        elif key in ("auto_submit", "tidy_chat"):
            if key == "auto_submit" and not prefs["name"]:
                await event.answer("Set a leaderboard name first.", alert=True)
                return
            db.save_settings(self.conn, user_id, **{key: not prefs[key]})
        else:
            await event.answer()
            return
        await event.answer("Saved.")
        rich, buttons = views.settings_card(self.settings(user_id), self.button, user_id)
        await r.edit_rich_message(self.client, event, rich, buttons)

    # Entry points.

    async def run_locked(self, chat_id: int, action) -> None:
        async with self.locks[chat_id]:
            try:
                await action()
            except ApiError as err:
                await self.api_failed(chat_id, err)

    async def on_command(self, event, name: str) -> None:
        chat_id, user_id = event.chat_id, event.sender_id
        await self.remember_sender(event)
        db.clear_prompt(self.conn, chat_id)

        if name == "start":
            await self.send(
                chat_id, views.start_card(self.button, user_id, self.config.site_url, self.config.donation_url)
            )
        elif name == "settings":
            await self.send(chat_id, views.settings_card(self.settings(user_id), self.button, user_id))
        elif name == "play":
            await self.run_locked(chat_id, lambda: self.start_run(chat_id, user_id))
        elif name == "leaderboard":
            await self.run_locked(chat_id, lambda: self.leaderboard(chat_id, user_id))

    async def on_text(self, event, text: str) -> None:
        chat_id, user_id = event.chat_id, event.sender_id
        await self.remember_sender(event)
        prompt = db.get_prompt(self.conn, chat_id)
        if prompt is not None and prompt["kind"] == "setname":
            await self.run_locked(chat_id, lambda: self.set_name(chat_id, user_id, text))
        elif prompt is not None and prompt["run_id"]:
            run_id = prompt["run_id"]
            await self.run_locked(chat_id, lambda: self.submit_name(chat_id, user_id, run_id, text))
        elif db.get_live(self.conn, chat_id) is not None:
            await event.respond("Tap an answer on the question card.")
        else:
            await event.respond("Send /play to start a run.")

    async def on_button(self, event, kind: str, payload: dict) -> None:
        chat_id, user_id = event.chat_id, event.sender_id
        if payload.get("user_id") not in (None, user_id):
            await event.answer("That button belongs to someone else.", alert=True)
            return
        await self.remember_sender(event)

        if kind == "setting":
            await self.change_setting(event, user_id, payload)
            return
        await event.answer()

        if kind == "answer":
            await self.run_locked(chat_id, lambda: self.answer(event, user_id, payload))
        elif kind == "resume":
            live = db.get_live(self.conn, chat_id)
            if live is None or live["run_id"] != payload.get("run_id"):
                await self.client.send_message(chat_id, "That run is over. Send /play for another.")
                return
            await self.run_locked(chat_id, lambda: self.ask(chat_id, user_id, payload["run_id"]))
        elif kind == "play":
            await self.run_locked(chat_id, lambda: self.start_run(chat_id, user_id))
        elif kind == "leaderboard" and payload.get("board") in ("best", "total"):
            board = payload["board"]
            await self.run_locked(chat_id, lambda: self.leaderboard(chat_id, user_id, board, event))
        elif kind == "leaderboard":
            await self.run_locked(chat_id, lambda: self.leaderboard(chat_id, user_id))
        elif kind == "submit" and payload.get("name"):
            name = payload["name"]
            await self.run_locked(chat_id, lambda: self.submit_name(chat_id, user_id, payload["run_id"], name))
        elif kind == "submit":
            db.set_prompt(self.conn, chat_id, "submit", payload["run_id"])
            await self.client.send_message(chat_id, NAME_PROMPT)
        elif kind == "setname":
            db.set_prompt(self.conn, chat_id, "setname")
            await self.client.send_message(chat_id, NAME_PROMPT)
