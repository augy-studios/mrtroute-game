"""Commands, answer buttons, names and the leaderboard.

A run is ten question cards in a row. Tapping an answer redraws that card
as answered, with its buttons gone, and sends the next card below it; the
tenth sends the result.
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

    def name_for(self, user_id: int) -> tuple[str | None, bool]:
        """The name to offer: the one last used, else the Telegram first name.
        The second value says it is the Telegram default."""
        saved = db.saved_name(self.conn, user_id)
        return (saved, False) if saved else (self.first_names.get(user_id), True)

    async def send(self, chat_id: int, built) -> int | None:
        rich, buttons = built
        return r.sent_message_id(await r.send_rich_message(self.client, chat_id, rich, buttons))

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
        db.set_live(self.conn, chat_id, user_id, run["run_id"])
        await self.ask(chat_id, user_id, run["run_id"])

    async def ask(self, chat_id: int, user_id: int, run_id: str) -> None:
        """The run's open question, or its next. If the API cannot be reached,
        a button to try again, since the answered card above has none."""
        try:
            q = await self.api.question(user_id, run_id)
        except ApiError as err:
            if err.code == "run_finished":
                await self.finish(chat_id, user_id, run_id)
                return
            if err.code in GONE or err.status == 429:
                raise
            log.warning("next question failed %s %s", err.status, err.code)
            await self.client.send_message(
                chat_id,
                "The next question did not load.",
                buttons=[[self.button("resume", "Try again", run_id=run_id, user_id=user_id)]],
            )
            return
        db.remember_question(self.conn, q)
        await self.send(chat_id, views.question_card(q, self.button, user_id, run_id))

    async def answer(self, event, user_id: int, payload: dict) -> None:
        chat_id = event.chat_id
        run_id = payload["run_id"]
        live = db.get_live(self.conn, chat_id)
        if live is None or live["run_id"] != run_id:
            # A card from a run that /play has since replaced.
            await r.strip_buttons(self.client, chat_id, event.query.msg_id)
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

        if q is not None:
            rich, _ = views.answered_card(q, result, choice)
            await r.edit_rich_message_at(self.client, chat_id, event.query.msg_id, rich, None)
        if result["finished"]:
            await self.finish(chat_id, user_id, run_id)
        else:
            await self.ask(chat_id, user_id, run_id)

    async def finish(self, chat_id: int, user_id: int, run_id: str) -> None:
        db.clear_live(self.conn, chat_id)
        state = await self.api.run_state(user_id, run_id)
        name, _ = self.name_for(user_id)
        await self.send(chat_id, views.result_card(state, self.button, user_id, run_id, name))

    async def leaderboard(self, chat_id: int, user_id: int) -> None:
        data = await self.api.leaderboard()
        await self.send(chat_id, views.leaderboard_card(data.get("entries", []), self.button, user_id))

    # Names.

    async def submit_name(self, chat_id: int, user_id: int, run_id: str, name: str) -> None:
        """Adds a run under a name, typed or offered. A refused name reopens
        the prompt. A name that goes through is remembered, except the
        Telegram name, which stays a default that follows the account."""
        try:
            result = await self.api.submit(run_id, name)
        except ApiError as err:
            if err.status == 400:
                db.set_prompt(self.conn, chat_id, run_id)
                await self.client.send_message(chat_id, f"{err.message or 'That name will not work.'} Send another.")
                return
            db.clear_prompt(self.conn, chat_id)
            await self.client.send_message(chat_id, err.message or "Could not add that run.")
            return
        db.clear_prompt(self.conn, chat_id)
        offered, is_default = self.name_for(user_id)
        if not (is_default and result["name"] == offered):
            db.save_name(self.conn, user_id, result["name"])
        buttons = [[self.button("leaderboard", "Leaderboard", user_id=user_id), self.button("play", "Play again", user_id=user_id)]]
        await self.send(chat_id, (views.submitted_line(result), buttons))

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
        elif name == "play":
            await self.run_locked(chat_id, lambda: self.start_run(chat_id, user_id))
        elif name == "leaderboard":
            await self.run_locked(chat_id, lambda: self.leaderboard(chat_id, user_id))

    async def on_text(self, event, text: str) -> None:
        chat_id, user_id = event.chat_id, event.sender_id
        await self.remember_sender(event)
        run_id = db.get_prompt(self.conn, chat_id)
        if run_id is not None:
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
        elif kind == "leaderboard":
            await self.run_locked(chat_id, lambda: self.leaderboard(chat_id, user_id))
        elif kind == "submit" and payload.get("name"):
            name = payload["name"]
            await self.run_locked(chat_id, lambda: self.submit_name(chat_id, user_id, payload["run_id"], name))
        elif kind == "submit":
            db.set_prompt(self.conn, chat_id, payload["run_id"])
            await self.client.send_message(chat_id, NAME_PROMPT)
