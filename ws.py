"""Менеджер WebSocket-подключений.

ВАЖНО ДЛЯ ПРОДА (1000+ пользователей): словарь подключений живёт в памяти
одного процесса. Если запустите несколько воркеров uvicorn — сообщения не
дойдут между ними. Тогда замените broadcast на публикацию в Redis pub/sub
(канал f"chat:{chat_id}") и подписку на неё в каждом воркере.
Логика менеджера при этом не меняется — только transport.
"""

import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, chat_id: int, ws: WebSocket):
        await ws.accept()
        self._rooms[chat_id].add(ws)

    def disconnect(self, chat_id: int, ws: WebSocket):
        self._rooms[chat_id].discard(ws)
        if not self._rooms[chat_id]:
            self._rooms.pop(chat_id, None)

    async def broadcast(self, chat_id: int, event: dict):
        dead = []
        payload = json.dumps(event, ensure_ascii=False)
        for ws in list(self._rooms.get(chat_id, ())):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(chat_id, ws)


manager = ConnectionManager()
