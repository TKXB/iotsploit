from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from django.conf import settings

# Use Django's database file
db_path = settings.DATABASES['default']['NAME']
engine = create_engine(f'sqlite:///{db_path}', echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()