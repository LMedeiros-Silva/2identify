from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import DATABASE_URL


# Cria a conexão principal com o PostgreSQL
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


# Cria o gerenciador de sessões
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_session():
    """
    Cria uma sessão com o banco de dados.

    A sessão deve ser fechada depois que terminar de ser utilizada.
    """

    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        