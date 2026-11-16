import asyncio
import os

from sqlalchemy import ForeignKey, Integer, create_engine, inspect, select, update
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.orm import Mapped, mapped_column

database_url = os.getenv("DATABASE_URL", "sqlite:///shortit.db")
engine_options = {"connect_args": {"check_same_thread": False}} if database_url.startswith("sqlite:") else {}
engine = create_engine(database_url, **engine_options)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        unique=True,
        nullable=False
    )
    google_sub: Mapped[str | None] = mapped_column(
        unique=True,
        nullable=True
    )
    password_hash: Mapped[str | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True
    )
    created_at: Mapped[str] = mapped_column(
        nullable=False
    )

    def __repr__(self) -> str:
        return f"User(id={self.id}, email={self.email!r})"

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    token_hash: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[str] = mapped_column(nullable=False, index=True)
    family_id: Mapped[str | None] = mapped_column(nullable=True, index=True)
    revoked_at: Mapped[str | None] = mapped_column(nullable=True)
    reuse_detected_at: Mapped[str | None] = mapped_column(nullable=True, index=True)

    def __repr__(self) -> str:
        return f"RefreshToken(user_id={self.user_id}, expires_at={self.expires_at!r})"

class Address(Base):
    __tablename__ = "address"

    id: Mapped[str] = mapped_column(primary_key=True)
    url: Mapped[str]
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    def __repr__(self) -> str:
        return f"Address(id={self.id}, url={self.url})"

def get_session():
    with Session(engine) as session:
        yield session

def initialize_database() -> None:
    Base.metadata.create_all(engine)

    tables = set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        if "address" in tables:
            address_columns = {
                column["name"] for column in inspect(engine).get_columns("address")
            }
            if "user_id" not in address_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE address ADD COLUMN user_id INTEGER REFERENCES users(id)"
                )
            if "clicks" not in address_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE address ADD COLUMN clicks INTEGER NOT NULL DEFAULT 0"
                )

        if "refresh_tokens" in tables:
            refresh_columns = {
                column["name"]
                for column in inspect(engine).get_columns("refresh_tokens")
            }
            for column in ("family_id", "revoked_at", "reuse_detected_at"):
                if column not in refresh_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE refresh_tokens ADD COLUMN {column} VARCHAR"
                    )

            # Keep legacy tokens independently revocable when their family is unknown.
            connection.exec_driver_sql(
                "UPDATE refresh_tokens SET family_id = token_hash WHERE family_id IS NULL"
            )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_family_id "
                "ON refresh_tokens (family_id)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_reuse_detected_at "
                "ON refresh_tokens (reuse_detected_at)"
            )

class Database:
    async def insert_link(self, code: str, url: str, user_id: int) -> Address:
        return await asyncio.to_thread(self._insert_link, code, url, user_id)

    @staticmethod
    def _insert_link(code: str, url: str, user_id: int) -> Address:
        with Session(engine) as session:
            link = Address(id=code, url=url, user_id=user_id)
            session.add(link)
            session.commit()
            session.refresh(link)
            return link

    async def get_link(self, code: str) -> Address | None:
        return await asyncio.to_thread(self._get_link, code)

    @staticmethod
    def _get_link(code: str) -> Address | None:
        with Session(engine) as session:
            return session.get(Address, code)

    async def get_links(self, user_id: int) -> list[Address]:
        return await asyncio.to_thread(self._get_links, user_id)

    @staticmethod
    def _get_links(user_id: int) -> list[Address]:
        with Session(engine) as session:
            return list(
                session.scalars(
                    select(Address)
                    .where(Address.user_id == user_id)
                    .order_by(Address.id)
                )
            )

    async def increment_clicks(self, code: str) -> bool:
        return await asyncio.to_thread(self._increment_clicks, code)

    @staticmethod
    def _increment_clicks(code: str) -> bool:
        with Session(engine) as session:
            result = session.execute(
                update(Address)
                .where(Address.id == code)
                .values(clicks=Address.clicks + 1)
            )
            session.commit()
            return result.rowcount == 1


db = Database()
