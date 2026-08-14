import bcrypt


def gerar_hash_senha(senha: str) -> str:
    """
    Recebe uma senha em texto normal e retorna
    o hash seguro utilizando bcrypt.
    """

    senha_bytes = senha.encode("utf-8")

    salt = bcrypt.gensalt()

    senha_hash = bcrypt.hashpw(
        senha_bytes,
        salt,
    )

    return senha_hash.decode("utf-8")


def verificar_senha(
    senha: str,
    senha_hash: str,
) -> bool:
    """
    Verifica se a senha informada corresponde
    ao hash armazenado no banco.
    """

    senha_bytes = senha.encode("utf-8")

    hash_bytes = senha_hash.encode("utf-8")

    return bcrypt.checkpw(
        senha_bytes,
        hash_bytes,
    )
