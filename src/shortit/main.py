import string

from shortit.database import Base, engine, get_session, Address
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl
from secrets import choice
from sqlalchemy import select
from sqlalchemy.orm import Session

alphabet = string.ascii_letters + string.digits

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield

app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,    
)

class ShortenRequest(BaseModel):
    url: HttpUrl

@app.get("/")
async def read_root():
    return {"message": "Congratulations, you've found the most boring endpoint on the internet"}

@app.get("/s/{code}")
def redirect_url(code: str, session: Session = Depends(get_session)):
    address = session.scalars(select(Address).where(Address.id == code)).first()

    if address is None:
        raise HTTPException(
            status_code=404,
            detail="Short URL not found"
        )

    return RedirectResponse(
        url=address.url,
        status_code=302
    )

@app.post("/api/shorten")
def shorten_url(data: ShortenRequest, session: Session = Depends(get_session)):
    code = ''.join(choice(alphabet) for _ in range(8))
    link = Address(id=code, url=str(data.url))
    session.add(link)
    session.commit()
    return {"short_url": f"https://winslinn.dpdns.org/s/{code}"}