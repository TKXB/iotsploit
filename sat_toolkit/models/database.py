from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

db_path = os.path.join(os.path.dirname(__file__), 'iotsploit_database.sqlite')
engine = create_engine(f'sqlite:///{db_path}', echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()