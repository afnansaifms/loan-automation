import uuid
from datetime import datetime

from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    applicant_name = Column(String, nullable=True)
    status = Column(String, default="intake")
    risk_score = Column(Float, nullable=True)
    eligibility_flag = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    statements = relationship("Statement", back_populates="application", cascade="all, delete-orphan")


class Statement(Base):
    __tablename__ = "statements"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    application_id = Column(UUID(as_uuid=False), ForeignKey("applications.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    parse_method = Column(String, nullable=True)
    status = Column(String, default="uploaded")
    raw_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("Application", back_populates="statements")
    transactions = relationship("Transaction", back_populates="statement", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    statement_id = Column(UUID(as_uuid=False), ForeignKey("statements.id"), nullable=False)
    position = Column(Integer, nullable=True)  # original row order within the statement
    txn_date = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    debit = Column(Float, nullable=True)
    credit = Column(Float, nullable=True)
    balance = Column(Float, nullable=True)
    category = Column(String, nullable=True)
    category_source = Column(String, nullable=True)

    statement = relationship("Statement", back_populates="transactions")


class LoanDocument(Base):
    __tablename__ = "loan_documents"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    application_id = Column(UUID(as_uuid=False), ForeignKey("applications.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    doc_type = Column(String, nullable=True)  # salary_slip / itr / form16 / kyc / unknown
    parse_method = Column(String, nullable=True)  # native_pdf / ocr
    status = Column(String, default="uploaded")  # uploaded -> classified -> extracted -> failed
    raw_text = Column(Text, nullable=True)
    extracted_fields = Column(Text, nullable=True)  # stored as JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("Application", backref="loan_documents")