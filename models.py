from datetime import datetime, timezone

from sqlalchemy import (BigInteger, Column, DateTime, ForeignKey, String, Table,
                        Text, UniqueConstraint)
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return datetime.now(timezone.utc)


chat_participants = Table(
    "chat_participants", Base.metadata,
    Column("chat_id", ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    phone = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(64), nullable=False)
    code = Column(String(6), nullable=True)
    code_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class Chat(Base):
    __tablename__ = "chats"
    id = Column(BigInteger, primary_key=True)
    is_group = Column(default=False)
    title = Column(String(64), nullable=True)  # для групп; для личных — None
    created_at = Column(DateTime, default=utcnow)
    participants = relationship("User", secondary=chat_participants, lazy="selectin")
    messages = relationship("Message", back_populates="chat",
                            order_by="Message.id", lazy="selectin")


class Message(Base):
    __tablename__ = "messages"
    id = Column(BigInteger, primary_key=True)
    chat_id = Column(ForeignKey("chats.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    chat = relationship("Chat", back_populates="messages")


class ReadState(Base):
    """Какое сообщение пользователь прочитал в чате — для счётчика непрочитанных."""
    __tablename__ = "read_states"
    __table_args__ = (UniqueConstraint("chat_id", "user_id"),)
    id = Column(BigInteger, primary_key=True)
    chat_id = Column(ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    last_read_message_id = Column(BigInteger, default=0)
