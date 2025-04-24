from sqlalchemy import Column, Integer, String, Float, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
import json

DATABASE_URL = "sqlite+aiosqlite:///./bot.db"

Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id = Column(Integer, primary_key=True, index=True)
    base = Column(String, nullable=True)
    amount = Column(Float, default=1.0)
    selected = Column(String, nullable=False, default="[]")  # JSON сериализованный список
    msg_id = Column(Integer, nullable=True)

    def as_dict(self):
        return {
            "base": self.base,
            "amount": self.amount,
            "selected": json.loads(self.selected),
            "msg_id": self.msg_id
        }

    def update_from_dict(self, data: dict):
        self.base = data.get("base")
        self.amount = data.get("amount", 1.0)
        self.selected = json.dumps(data.get("selected", []))
        self.msg_id = data.get("msg_id")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def load_user_settings(user_id: int) -> dict:
    async with SessionLocal() as session:
        result = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        row = result.scalar_one_or_none()
        if row:
            return row.as_dict()
        else:
            return {"base": None, "amount": 1.0, "selected": [], "msg_id": None}


async def save_user_settings(user_id: int, data: dict):
    async with SessionLocal() as session:
        result = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        row = result.scalar_one_or_none()
        if not row:
            row = UserSettings(user_id=user_id)
            session.add(row)
        row.update_from_dict(data)
        await session.commit()
