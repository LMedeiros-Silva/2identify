from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.usuario import Usuario
from app.core.security import verificar_senha


class AuthService:
    """
    Responsável pelas regras de autenticação
    do sistema.
    """

    def __init__(self, session: Session):
        self.session = session

    def autenticar(
        self,
        username: str,
        senha: str,
    ) -> Usuario | None:
        """
        Procura o usuário no banco e verifica
        a senha informada.

        Retorna:
            Usuario -> login realizado
            None    -> login inválido
        """

        username = username.strip()

        if not username or not senha:
            return None

        usuario = self.session.scalar(
            select(Usuario).where(
                Usuario.username == username,
                Usuario.ativo.is_(True),
            )
        )

        if not usuario:
            return None

        senha_valida = verificar_senha(
            senha,
            usuario.senha_hash,
        )

        if not senha_valida:
            return None

        return usuario
    