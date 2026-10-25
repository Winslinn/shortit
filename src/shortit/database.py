from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.orm import Mapped, mapped_column

engine = create_engine("sqlite:///shortit.db", connect_args={"check_same_thread": False})

class Base(DeclarativeBase):
    pass

class Address(Base):
    __tablename__ = "address"

    id: Mapped[str] = mapped_column(primary_key=True)
    url: Mapped[str]

    def __repr__(self) -> str:
        return f"Address(id={self.id}, url={self.url})"

def get_session():
    with Session(engine) as session:
        yield session