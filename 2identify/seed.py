from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.usuario import Usuario
from app.models.setor import Setor
from app.models.epi import EPI
from app.models.funcionario import Funcionario
from app.models.funcionario_epi import FuncionarioEPI

import bcrypt


# ============================================================
# CONFIGURAÇÕES INICIAIS
# ============================================================

USUARIO_ADMIN = "admin"
SENHA_ADMIN = "admin123"


# ============================================================
# FUNÇÃO PARA CRIPTOGRAFAR SENHA
# ============================================================

def gerar_hash_senha(senha: str) -> str:
    """
    Recebe uma senha normal e retorna o hash bcrypt.
    """

    senha_bytes = senha.encode("utf-8")

    salt = bcrypt.gensalt()

    senha_hash = bcrypt.hashpw(
        senha_bytes,
        salt,
    )

    return senha_hash.decode("utf-8")


# ============================================================
# CRIAÇÃO DO USUÁRIO ADMINISTRADOR
# ============================================================

def criar_usuario_admin(session):
    """
    Cria o usuário administrador caso ele ainda não exista.
    """

    usuario_existente = session.scalar(
        select(Usuario).where(
            Usuario.username == USUARIO_ADMIN
        )
    )

    if usuario_existente:
        print("✓ Usuário administrador já existe.")
        return usuario_existente

    senha_hash = gerar_hash_senha(
        SENHA_ADMIN
    )

    usuario = Usuario(
        nome="Administrador",
        username=USUARIO_ADMIN,
        senha_hash=senha_hash,
        perfil="administrador",
        ativo=True,
    )

    session.add(usuario)

    session.flush()

    print("✓ Usuário administrador criado.")

    return usuario


# ============================================================
# CRIAÇÃO DOS SETORES
# ============================================================

def criar_setores(session):
    """
    Cria os setores iniciais do sistema.
    """

    setores = [
        {
            "nome": "Produção",
            "descricao": "Área de produção industrial.",
        },
        {
            "nome": "Almoxarifado",
            "descricao": "Área de armazenamento e controle de materiais.",
        },
        {
            "nome": "Manutenção",
            "descricao": "Área responsável pela manutenção dos equipamentos.",
        },
        {
            "nome": "Expedição",
            "descricao": "Área de separação e expedição de produtos.",
        },
    ]

    setores_criados = []

    for dados in setores:

        setor = session.scalar(
            select(Setor).where(
                Setor.nome == dados["nome"]
            )
        )

        if setor:
            print(
                f"✓ Setor já existe: {dados['nome']}"
            )

        else:

            setor = Setor(
                nome=dados["nome"],
                descricao=dados["descricao"],
                ativo=True,
            )

            session.add(setor)

            print(
                f"✓ Setor criado: {dados['nome']}"
            )

        setores_criados.append(setor)

    session.flush()

    return setores_criados


# ============================================================
# CRIAÇÃO DOS EPIs
# ============================================================

def criar_epis(session):
    """
    Cria os EPIs iniciais do sistema.
    """

    epis = [
        {
            "nome": "Capacete",
            "codigo": "EPI-001",
            "descricao": "Capacete de segurança.",
        },
        {
            "nome": "Luvas",
            "codigo": "EPI-002",
            "descricao": "Luvas de proteção.",
        },
        {
            "nome": "Botas",
            "codigo": "EPI-003",
            "descricao": "Botas de segurança.",
        },
        {
            "nome": "Mangote",
            "codigo": "EPI-004",
            "descricao": "Mangote de proteção.",
        },
        {
            "nome": "Óculos de proteção",
            "codigo": "EPI-005",
            "descricao": "Óculos de proteção ocular.",
        },
        {
            "nome": "Protetor auricular",
            "codigo": "EPI-006",
            "descricao": "Proteção auditiva.",
        },
    ]

    epis_criados = []

    for dados in epis:

        epi = session.scalar(
            select(EPI).where(
                EPI.nome == dados["nome"]
            )
        )

        if epi:
            print(
                f"✓ EPI já existe: {dados['nome']}"
            )

        else:

            epi = EPI(
                nome=dados["nome"],
                codigo=dados["codigo"],
                descricao=dados["descricao"],
                ativo=True,
            )

            session.add(epi)

            print(
                f"✓ EPI criado: {dados['nome']}"
            )

        epis_criados.append(epi)

    session.flush()

    return epis_criados


# ============================================================
# CRIAÇÃO DE FUNCIONÁRIOS DE TESTE
# ============================================================

def criar_funcionarios_teste(session):
    """
    Cria alguns funcionários apenas para testar a interface.

    Posteriormente esses dados serão cadastrados
    pela própria aplicação.
    """

    setor_producao = session.scalar(
        select(Setor).where(
            Setor.nome == "Produção"
        )
    )

    setor_almoxarifado = session.scalar(
        select(Setor).where(
            Setor.nome == "Almoxarifado"
        )
    )

    if not setor_producao:
        raise RuntimeError(
            "Setor Produção não encontrado."
        )

    if not setor_almoxarifado:
        raise RuntimeError(
            "Setor Almoxarifado não encontrado."
        )

    funcionarios = [
        {
            "nome": "João Silva",
            "matricula": "FUNC001",
            "cargo": "Operador de Produção",
            "turno": "Manhã",
            "setor": setor_producao,
        },
        {
            "nome": "Maria Souza",
            "matricula": "FUNC002",
            "cargo": "Auxiliar de Almoxarifado",
            "turno": "Tarde",
            "setor": setor_almoxarifado,
        },
        {
            "nome": "Carlos Oliveira",
            "matricula": "FUNC003",
            "cargo": "Operador de Produção",
            "turno": "Noite",
            "setor": setor_producao,
        },
    ]

    funcionarios_criados = []

    for dados in funcionarios:

        funcionario = session.scalar(
            select(Funcionario).where(
                Funcionario.matricula == dados["matricula"]
            )
        )

        if funcionario:

            print(
                f"✓ Funcionário já existe: {dados['nome']}"
            )

        else:

            funcionario = Funcionario(
                nome=dados["nome"],
                matricula=dados["matricula"],
                cargo=dados["cargo"],
                turno=dados["turno"],
                setor=dados["setor"],
                ativo=True,
            )

            session.add(funcionario)

            print(
                f"✓ Funcionário criado: {dados['nome']}"
            )

        funcionarios_criados.append(funcionario)

    session.flush()

    return funcionarios_criados


# ============================================================
# ASSOCIAR EPIs AOS FUNCIONÁRIOS
# ============================================================

def associar_epis(session):
    """
    Associa EPIs aos funcionários de teste.
    """

    funcionarios = session.scalars(
        select(Funcionario)
    ).all()

    epis = {
        epi.nome: epi
        for epi in session.scalars(
            select(EPI)
        ).all()
    }

    # --------------------------------------------------------
    # EPIs padrão obrigatórios
    # --------------------------------------------------------

    epis_padrao = [
        "Capacete",
        "Luvas",
        "Botas",
        "Mangote",
    ]

    for funcionario in funcionarios:

        for nome_epi in epis_padrao:

            epi = epis.get(nome_epi)

            if not epi:
                continue

            relacao_existente = session.scalar(
                select(FuncionarioEPI).where(
                    FuncionarioEPI.funcionario_id
                    == funcionario.id,
                    FuncionarioEPI.epi_id
                    == epi.id,
                )
            )

            if relacao_existente:
                continue

            relacao = FuncionarioEPI(
                funcionario=funcionario,
                epi=epi,
                obrigatorio=True,
                entregue=True,
            )

            session.add(relacao)

            print(
                f"✓ EPI '{nome_epi}' associado a "
                f"{funcionario.nome}"
            )

    session.flush()


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

def main():

    print()
    print("=" * 60)
    print("        2IDENTIFY - CONFIGURAÇÃO INICIAL")
    print("=" * 60)
    print()

    session = SessionLocal()

    try:

        print("1. Criando usuário administrador...")
        criar_usuario_admin(session)

        print()
        print("2. Criando setores...")
        criar_setores(session)

        print()
        print("3. Criando EPIs...")
        criar_epis(session)

        print()
        print("4. Criando funcionários de teste...")
        criar_funcionarios_teste(session)

        print()
        print("5. Associando EPIs...")
        associar_epis(session)

        session.commit()

        print()
        print("=" * 60)
        print("CONFIGURAÇÃO CONCLUÍDA COM SUCESSO")
        print("=" * 60)
        print()
        print("LOGIN ADMINISTRADOR")
        print()
        print(f"Usuário: {USUARIO_ADMIN}")
        print(f"Senha:   {SENHA_ADMIN}")
        print()
        print("⚠️ Altere essa senha posteriormente.")
        print()

    except Exception as erro:

        session.rollback()

        print()
        print("=" * 60)
        print("ERRO DURANTE A CONFIGURAÇÃO")
        print("=" * 60)
        print()
        print(erro)

        raise

    finally:

        session.close()


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()