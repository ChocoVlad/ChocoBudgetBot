from sqlalchemy import Column, String, Float, DateTime, select, BigInteger
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from datetime import datetime
import json
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://bot_user:bot_password@db:5432/bot_db")

Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id = Column(BigInteger, primary_key=True, index=True)
    base = Column(String, nullable=True)
    amount = Column(Float, default=1.0)
    selected = Column(String, nullable=False, default="[]")
    msg_id = Column(BigInteger, nullable=True)
    message_sent_at = Column(DateTime, nullable=True)
    chat_id = Column(BigInteger, nullable=True)  # ✅ добавили

    def as_dict(self):
        return {
            "base": self.base,
            "amount": self.amount,
            "selected": json.loads(self.selected),
            "msg_id": self.msg_id,
            "message_sent_at": self.message_sent_at.isoformat() if self.message_sent_at else None,
            "chat_id": self.chat_id
        }

    def update_from_dict(self, data: dict):
        self.base = data.get("base")
        self.amount = data.get("amount", 1.0)
        self.selected = json.dumps(data.get("selected", []))
        self.msg_id = data.get("msg_id")
        self.chat_id = data.get("chat_id")
        sent_at = data.get("message_sent_at")
        if sent_at:
            self.message_sent_at = sent_at if isinstance(sent_at, datetime) else datetime.fromisoformat(sent_at)


async def init_db():
    os.makedirs("data", exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def load_user_settings(user_id: int) -> dict:
    async with SessionLocal() as session:
        result = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        row = result.scalar_one_or_none()
        if row:
            return row.as_dict()
        else:
            return {
                "base": None,
                "amount": 1.0,
                "selected": [],
                "msg_id": None,
                "message_sent_at": None,
                "chat_id": None
            }


async def save_user_settings(user_id: int, data: dict):
    async with SessionLocal() as session:
        result = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        row = result.scalar_one_or_none()
        if not row:
            row = UserSettings(user_id=user_id)
            session.add(row)
        row.update_from_dict(data)
        await session.commit()


async def get_all_users():
    async with SessionLocal() as session:
        result = await session.execute(select(UserSettings.user_id).distinct())
        return [{"user_id": row[0]} for row in result.all()]
