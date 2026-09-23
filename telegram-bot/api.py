"""The game API. The bot holds no game rules and no Supabase key: everything
goes through the same endpoints the PWA uses, with BOT_API_TOKEN.
"""

from __future__ import annotations

import httpx


class ApiError(RuntimeError):
    def __init__(self, status: int, code: str, message: str | None = None, data: dict | None = None) -> None:
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message
        self.data = data or {}


class GameApi:
    def __init__(self, base_url: str, token: str) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}", "User-Agent": "mrtnav-telegram-bot"},
            timeout=15,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        try:
            res = await self._http.request(method, path, json=body)
        except httpx.HTTPError as err:
            raise ApiError(0, "unreachable", "The game server could not be reached.") from err
        try:
            data = res.json()
        except ValueError:
            data = {}
        if res.status_code >= 400:
            raise ApiError(res.status_code, data.get("error", "error"), data.get("message"), data)
        return data

    @staticmethod
    def key(user_id: int) -> str:
        return f"tg:{user_id}"

    async def new_run(self, user_id: int) -> dict:
        return await self._call("POST", "/api/run/new", {"client_key": self.key(user_id)})

    async def run_state(self, user_id: int, run_id: str) -> dict:
        return await self._call("POST", "/api/run/state", {"client_key": self.key(user_id), "run_id": run_id})

    async def question(self, user_id: int, run_id: str) -> dict:
        return await self._call("POST", "/api/question/new", {"client_key": self.key(user_id), "run_id": run_id})

    async def answer(self, user_id: int, question_id: str, choice: int) -> dict:
        return await self._call(
            "POST",
            "/api/question/answer",
            {"client_key": self.key(user_id), "question_id": question_id, "choice": choice},
        )

    async def submit(self, run_id: str, name: str) -> dict:
        return await self._call("POST", "/api/leaderboard/submit", {"run_id": run_id, "name": name})

    async def check_name(self, name: str) -> dict:
        return await self._call("POST", "/api/leaderboard/name", {"name": name})

    async def leaderboard(self, board: str = "best") -> dict:
        return await self._call("GET", f"/api/leaderboard?board={board}")
