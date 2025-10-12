from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings as cg
SQL_ALCHEMY_URL=f"postgresql://{cg.database_user}:{cg.database_password}@{cg.database_host}/{cg.database_name}"

engine=create_engine(SQL_ALCHEMY_URL)

SessionLocal=sessionmaker(autocommit=False,autoflush=False,bind=engine)

Base=declarative_base()

def getDb():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()
        