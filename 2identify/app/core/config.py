import os

from dotenv import load_dotenv


# Carrega as variáveis existentes no arquivo .env
load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")


if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não foi encontrada no arquivo .env."
    )