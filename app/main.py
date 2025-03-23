
from datetime import datetime, timedelta
import uuid

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy import create_engine, Column, String, Integer, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
app = FastAPI()

@app.get("/")
async def redirect_to_docs():
    return RedirectResponse(url="/docs")
# Настройка БД
SQLALCHEMY_DATABASE_URL = "sqlite:///./links.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

class Link(Base):
    __tablename__ = "links"
    short_code = Column(String, primary_key=True, index=True)
    original_url = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    redirect_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)

Base.metadata.create_all(bind=engine)

# Pydantic схемы
class LinkCreate(BaseModel):
    original_url: HttpUrl
    custom_alias: str | None = None
    expires_at: datetime | None = None

class LinkUpdate(BaseModel):
    original_url: HttpUrl

class LinkStats(BaseModel):
    original_url: HttpUrl
    created_at: datetime
    redirect_count: int
    last_used_at: datetime | None
    expires_at: datetime | None

# Зависимость для работы с БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()

# Генерация уникального короткого кода, если custom_alias не передан
def generate_short_code() -> str:
    return uuid.uuid4().hex[:6]

# Endpoint создания короткой ссылки
@app.post("/links/shorten")
def create_link(link: LinkCreate, db: Session = Depends(get_db)):
    # Проверка на уникальность кастомного alias, если он указан
    short_code = link.custom_alias if link.custom_alias else generate_short_code()
    existing_link = db.query(Link).filter(Link.short_code == short_code).first()
    if existing_link:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Такой alias уже существует. Попробуйте другой.")
    
    new_link = Link(
        short_code=short_code,
        original_url=str(link.original_url),  # Приводим к строке для БД
        expires_at=link.expires_at
    )
    db.add(new_link)
    db.commit()
    return {"short_code": short_code}

# Endpoint перенаправления
@app.get("/{short_code}")
def redirect_to_original(short_code: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.short_code == short_code).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена")
    
    # Проверка срока жизни ссылки
    if link.expires_at and datetime.utcnow() > link.expires_at:
        db.delete(link)
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Ссылка истекла")
    
    # Обновление статистики
    link.redirect_count += 1
    link.last_used_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=link.original_url)

# Endpoint удаления ссылки
@app.delete("/links/{short_code}")
def delete_link(short_code: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.short_code == short_code).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена")
    db.delete(link)
    db.commit()
    return {"message": "Ссылка удалена"}

# Endpoint обновления оригинального URL для существующей короткой ссылки
@app.put("/links/{short_code}")
def update_link(short_code: str, link_update: LinkUpdate, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.short_code == short_code).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена")
    link.original_url = str(link_update.original_url)
    db.commit()
    return {"message": "Ссылка обновлена"}

# Endpoint получения статистики по ссылке
@app.get("/links/{short_code}/stats", response_model=LinkStats)
def link_stats(short_code: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.short_code == short_code).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена")
    return LinkStats(
        original_url=link.original_url,
        created_at=link.created_at,
        redirect_count=link.redirect_count,
        last_used_at=link.last_used_at,
        expires_at=link.expires_at
    )

# Endpoint поиска ссылки по оригинальному URL
@app.get("/links/search")
def search_link(original_url: HttpUrl, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.original_url == str(original_url)).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена")
    return {"short_code": link.short_code, "original_url": link.original_url}