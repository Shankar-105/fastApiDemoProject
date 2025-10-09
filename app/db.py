from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQL_ALCHEMY_URL="postgresql://postgres:iota143@localhost/fastApi"

engine=create_engine(SQL_ALCHEMY_URL)

SessionLocal=sessionmaker(autocommit=False,autoflush=False,bind=engine)

Base=declarative_base()

def getDb():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()
        