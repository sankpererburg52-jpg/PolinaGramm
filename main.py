import random
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import (Depends, FastAPI, HTTPException, WebSocket,
                     WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_token, get_current_user, get_session
from database import CODE_TTL, DEV_RETURN_CODE, engine
from models import Base, Chat, Message, ReadState, User, chat_participants, utcnow
from ws import manager

app = FastAPI(title="PolinaGram API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # в проде — список доменов вашего приложения
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------- схемы ----------

class PhoneIn(BaseModel):
    phone: str = Field(pattern=r"^\+?[0-9]{7,15}$")


class VerifyIn(BaseModel):
    phone: str
    code: str
    name: str | None = None


class TokenOut(BaseModel):
    token: str
    user_id: int
    name: str
    dev_code: str | None = None  # только в DEV-режиме


class UserOut(BaseModel):
    id: int
    name: str
    phone: str


class ChatOut(BaseModel):
    id: int
    title: str
    is_group: bool
    last_message: str | None
    last_time: datetime | None
    unread: int
    peer_id: int | None = None


class MessageOut(BaseModel):
    id: int
    chat_id: int
    user_id: int
    author: str
    text: str
    created_at: datetime


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


# ---------- авторизация ----------

@app.post("/auth/request-code")
async def request_code(body: PhoneIn, db: AsyncSession = Depends(get_session)):
    user = (await db.execute(select(User).where(User.phone == body.phone))).scalar_one_or_none()
    if user is None:
        user = User(phone=body.phone, name=f"User{random.randint(1000, 9999)}")
        db.add(user)
    user.code = f"{secrets.randbelow(1_000_000):06d}"
    user.code_expires = datetime.now(timezone.utc) + timedelta(seconds=CODE_TTL)
    await db.commit()
    # В проде: отправить user.code через SMS-шлюз (Twilio, sms.ru, Twilio и т.п.)
    return {"ok": True, "dev_code": user.code if DEV_RETURN_CODE else None}


@app.post("/auth/verify", response_model=TokenOut)
async def verify(body: VerifyIn, db: AsyncSession = Depends(get_session)):
    user = (await db.execute(select(User).where(User.phone == body.phone))).scalar_one_or_none()
    if user is None or not user.code or user.code != body.code:
        raise HTTPException(400, "Неверный код")
    if user.code_expires and user.code_expires < datetime.now(timezone.utc):
        raise HTTPException(400, "Код истёк, запросите новый")
    if body.name:
        user.name = body.name[:64]
    user.code = None
    await db.commit()
    return TokenOut(token=create_token(user.id), user_id=user.id,
                    name=user.name, dev_code=None)


@app.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, name=user.name, phone=user.phone)


@app.get("/users", response_model=list[UserOut])
async def search_users(q: str, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(
        select(User).where(User.id != user.id, User.name.ilike(f"%{q[:32]}%")).limit(20)
    )).scalars().all()
    return [UserOut(id=u.id, name=u.name, phone=u.phone) for u in rows]


# ---------- чаты ----------

async def _get_or_create_direct_chat(db: AsyncSession, a: User, b: User) -> Chat:
    q = (select(Chat)
         .join(chat_participants, Chat.id == chat_participants.c.chat_id)
         .where(Chat.is_group == False)  # noqa: E712
         .group_by(Chat.id)
         .having(func.count(chat_participants.c.user_id) == 2))
    for chat in (await db.execute(q)).scalars().all():
        ids = {p.id for p in chat.participants}
        if ids == {a.id, b.id}:
            return chat
    chat = Chat(is_group=False)
    chat.participants = [a, b]
    db.add(chat)
    await db.flush()
    return chat


async def _chat_for_user(db: AsyncSession, chat_id: int, user: User) -> Chat:
    chat = await db.get(Chat, chat_id)
    if chat is None or user.id not in {p.id for p in chat.participants}:
        raise HTTPException(404, "Чат не найден")
    return chat


async def _serialize_chat(db: AsyncSession, chat: Chat, user: User) -> ChatOut:
    last = chat.messages[-1] if chat.messages else None
    peer = next((p for p in chat.participants if p.id != user.id), None)
    read = (await db.execute(
        select(ReadState).where(ReadState.chat_id == chat.id, ReadState.user_id == user.id)
    )).scalar_one_or_none()
    last_read = read.last_read_message_id if read else 0
    unread = sum(1 for m in chat.messages if m.id > last_read and m.user_id != user.id)
    return ChatOut(
        id=chat.id,
        title=chat.title or (peer.name if peer else "Избранное"),
        is_group=chat.is_group,
        last_message=last.text[:120] if last else None,
        last_time=last.created_at if last else None,
        unread=unread,
        peer_id=peer.id if peer else None,
    )


@app.post("/chats", response_model=ChatOut)
async def open_chat(peer_id: int, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_session)):
    peer = await db.get(User, peer_id)
    if peer is None:
        raise HTTPException(404, "Пользователь не найден")
    chat = await _get_or_create_direct_chat(db, user, peer)
    await db.commit()
    return await _serialize_chat(db, chat, user)


@app.get("/chats", response_model=list[ChatOut])
async def list_chats(user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_session)):
    chats = (await db.execute(
        select(Chat).join(chat_participants, Chat.id == chat_participants.c.chat_id)
        .where(chat_participants.c.user_id == user.id)
    )).scalars().unique().all()
    out = [await _serialize_chat(db, c, user) for c in chats]
    out.sort(key=lambda c: c.last_time or datetime.min.replace(tzinfo=timezone.utc),
             reverse=True)
    return out


@app.get("/chats/{chat_id}/messages", response_model=list[MessageOut])
async def messages(chat_id: int, limit: int = 50, before: int = 0,
                   user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_session)):
    chat = await _chat_for_user(db, chat_id, user)
    msgs = [m for m in chat.messages if not before or m.id < before][-limit:]
    return [MessageOut(id=m.id, chat_id=m.chat_id, user_id=m.user_id,
                       author=next((p.name for p in chat.participants if p.id == m.user_id), "?"),
                       text=m.text, created_at=m.created_at) for m in msgs]


@app.post("/chats/{chat_id}/messages", response_model=MessageOut)
async def send_message(chat_id: int, body: SendIn,
                       user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_session)):
    chat = await _chat_for_user(db, chat_id, user)
    msg = Message(chat_id=chat.id, user_id=user.id, text=body.text)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    await manager.broadcast(chat_id, {
        "type": "message",
        "id": msg.id, "chat_id": chat.id, "user_id": user.id,
        "author": user.name, "text": msg.text,
        "created_at": msg.created_at.isoformat(),
    })
    return MessageOut(id=msg.id, chat_id=msg.chat_id, user_id=user.id,
                      author=user.name, text=msg.text, created_at=msg.created_at)


@app.post("/chats/{chat_id}/read")
async def mark_read(chat_id: int, up_to: int,
                    user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_session)):
    chat = await _chat_for_user(db, chat_id, user)
    state = (await db.execute(
        select(ReadState).where(ReadState.chat_id == chat.id, ReadState.user_id == user.id)
    )).scalar_one_or_none()
    if state is None:
        state = ReadState(chat_id=chat.id, user_id=user.id, last_read_message_id=0)
        db.add(state)
    state.last_read_message_id = max(state.last_read_message_id, up_to)
    await db.commit()
    return {"ok": True}


# ---------- realtime ----------

@app.websocket("/ws/{chat_id}")
async def ws_chat(ws: WebSocket, chat_id: int, token: str):
    import jwt as _jwt
    from database import JWT_SECRET, Session as S
    try:
        payload = _jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except Exception:
        await ws.close(code=4401)
        return
    async with S() as db:
        chat = await db.get(Chat, chat_id)
        if chat is None or user_id not in {p.id for p in chat.participants}:
            await ws.close(code=4403)
            return
    await manager.connect(chat_id, ws)
    try:
        while True:
            await ws.receive_text()  # клиент может слать ping/typing — игнорируем
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(chat_id, ws)


@app.get("/health")
async def health():
    return {"ok": True}
