from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship
import datetime
from pgvector.sqlalchemy import Vector
Base = declarative_base()


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    github_url = Column(String, unique=True, nullable=False)
    branch = Column(String, default="main")
    language = Column(String, default="python")
    status = Column(String, default="pending")  # pending|indexing|ready|failed
    last_commit = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    indexed_at = Column(DateTime, nullable=True)
    parser_version = Column(String, default="1.0.0")
    embedding_version = Column(String, nullable=True)

    files = relationship("File", back_populates="repository")


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    path = Column(String, nullable=False)
    language = Column(String, default="python")
    size_bytes = Column(Integer)
    checksum = Column(String)

    repository = relationship("Repository", back_populates="files")
    functions = relationship("Function", back_populates="file")
    imports = relationship("Import", back_populates="source_file")


class Function(Base):
    __tablename__ = "functions"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    name = Column(String, nullable=False)
    qualified_name = Column(String, nullable=True)
    parameters = Column(Text, nullable=True)
    docstring = Column(Text, nullable=True)
    start_line = Column(Integer)
    end_line = Column(Integer)
    source_snippet = Column(Text, nullable=True)

    file = relationship("File", back_populates="functions")

    calls_made = relationship(
        "FunctionCall",
        foreign_keys="FunctionCall.caller_function_id",
        back_populates="caller",
    )
    calls_received = relationship(
        "FunctionCall",
        foreign_keys="FunctionCall.callee_function_id",
        back_populates="callee",
    )


class Import(Base):
    __tablename__ = "imports"

    id = Column(Integer, primary_key=True)
    source_file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    target_module = Column(String, nullable=False)
    imported_symbol = Column(String, nullable=True)

    source_file = relationship("File", back_populates="imports")


class FunctionCall(Base):
    __tablename__ = "function_calls"

    id = Column(Integer, primary_key=True)
    caller_function_id = Column(Integer, ForeignKey("functions.id"), nullable=False)
    callee_function_id = Column(Integer, ForeignKey("functions.id"), nullable=True)  # nullable: unresolved calls
    callee_name = Column(String, nullable=False)

    caller = relationship("Function", foreign_keys=[caller_function_id], back_populates="calls_made")
    callee = relationship("Function", foreign_keys=[callee_function_id], back_populates="calls_received")


class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String, default="function")
    entity_id = Column(Integer, nullable=False)
    vector = Column(Vector(384), nullable=True)  # 384 = output dimension of all-MiniLM-L6-v2
    model_name = Column(String, nullable=True)