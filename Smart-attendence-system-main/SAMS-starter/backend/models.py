from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import datetime, os

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "sams.db")
DATABASE_URI = f"sqlite:///{DB_PATH}"

Base = declarative_base()
engine = create_engine(DATABASE_URI, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    student_id = Column(String, unique=True, index=True)
    name = Column(String)
    # embedding_path etc.

class ClassRoom(Base):
    __tablename__ = "classes"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)        
    name = Column(String)
    teacher = Column(String, nullable=True)

class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True)
    student_id = Column(String, ForeignKey("students.student_id"))
    class_code = Column(String, ForeignKey("classes.code"))
    # optional fields
    # relationships not strictly needed for simple queries

class Period(Base):
    __tablename__ = "periods"
    id = Column(Integer, primary_key=True)
    class_code = Column(String, ForeignKey("classes.code"))
    start_time = Column(DateTime)  # scheduled time
    end_time = Column(DateTime)
    weekday = Column(String, nullable=True)  
    active = Column(Boolean, default=False)  
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True)
    student_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String, default="camera")  
    class_code = Column(String, nullable=True)
    period_id = Column(Integer, nullable=True)  
    note = Column(Text, nullable=True)

Base.metadata.create_all(bind=engine)

# models.py
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

Base = declarative_base()

class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True)
    student_id = Column(String, unique=True, nullable=False)
    name = Column(String)
    embedding_path = Column(String)

class Attendance(Base):
    __tablename__ = 'attendance'
    id = Column(Integer, primary_key=True)
    student_id = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String)  # e.g., 'camera'

def get_session(db_path='sqlite:///sams.db'):
    engine = create_engine(db_path, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()
