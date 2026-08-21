from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.domain import AdminCredentials


class LoginWindow(QWidget):
    """
    Tela principal de login do 2Identify.
    """

    login_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("2Identify - Login")

        self.setMinimumSize(1100, 700)

        self.setStyleSheet(
            self.estilos()
        )

        self.criar_interface()

    # ========================================================
    # INTERFACE
    # ========================================================

    def criar_interface(self) -> None:

        layout_principal = QHBoxLayout(self)

        layout_principal.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout_principal.setSpacing(0)

        # ====================================================
        # LADO ESQUERDO
        # ====================================================

        painel_esquerdo = QFrame()

        painel_esquerdo.setObjectName(
            "painel_esquerdo"
        )

        painel_esquerdo.setMinimumWidth(520)

        layout_esquerdo = QVBoxLayout(
            painel_esquerdo
        )

        layout_esquerdo.setContentsMargins(
            60,
            50,
            60,
            50,
        )

        layout_esquerdo.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        # Logo / nome

        logo = QLabel("2Identify")

        logo.setObjectName("logo")

        logo.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        layout_esquerdo.addWidget(
            logo
        )

        subtitulo_logo = QLabel(
            "Inteligência para Segurança Industrial"
        )

        subtitulo_logo.setObjectName(
            "subtitulo_logo"
        )

        subtitulo_logo.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        layout_esquerdo.addWidget(
            subtitulo_logo
        )

        layout_esquerdo.addStretch()

        descricao = QLabel(
            "Monitoramento inteligente de EPIs,\n"
            "segurança e conformidade operacional."
        )

        descricao.setObjectName(
            "descricao"
        )

        descricao.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        descricao.setWordWrap(True)

        layout_esquerdo.addWidget(
            descricao
        )

        layout_esquerdo.addStretch()

        rodape = QLabel(
            "2Identify • Industrial Safety"
        )

        rodape.setObjectName(
            "rodape"
        )

        rodape.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        layout_esquerdo.addWidget(
            rodape
        )

        # ====================================================
        # LADO DIREITO
        # ====================================================

        painel_direito = QFrame()

        painel_direito.setObjectName(
            "painel_direito"
        )

        layout_direito = QVBoxLayout(
            painel_direito
        )

        layout_direito.setContentsMargins(
            80,
            70,
            80,
            70,
        )

        layout_direito.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        # Container do formulário

        formulario = QFrame()

        formulario.setObjectName(
            "formulario"
        )

        formulario.setMaximumWidth(
            430
        )

        layout_formulario = QVBoxLayout(
            formulario
        )

        layout_formulario.setSpacing(
            18
        )

        # Título

        titulo = QLabel(
            "Bem-vindo de volta"
        )

        titulo.setObjectName(
            "titulo"
        )

        layout_formulario.addWidget(
            titulo
        )

        subtitulo = QLabel(
            "Entre com suas credenciais para acessar o sistema."
        )

        subtitulo.setObjectName(
            "subtitulo"
        )

        subtitulo.setWordWrap(True)

        layout_formulario.addWidget(
            subtitulo
        )

        layout_formulario.addSpacing(
            18
        )

        # ----------------------------------------------------
        # USUÁRIO
        # ----------------------------------------------------

        label_usuario = QLabel(
            "Usuário"
        )

        label_usuario.setObjectName(
            "label_campo"
        )

        layout_formulario.addWidget(
            label_usuario
        )

        self.campo_usuario = QLineEdit()

        self.campo_usuario.setPlaceholderText(
            "Digite seu usuário"
        )

        self.campo_usuario.setMinimumHeight(
            52
        )

        self.campo_usuario.setMaxLength(100)

        self.campo_usuario.returnPressed.connect(
            self.fazer_login
        )

        layout_formulario.addWidget(
            self.campo_usuario
        )

        # ----------------------------------------------------
        # SENHA
        # ----------------------------------------------------

        label_senha = QLabel(
            "Senha"
        )

        label_senha.setObjectName(
            "label_campo"
        )

        layout_formulario.addWidget(
            label_senha
        )

        self.campo_senha = QLineEdit()

        self.campo_senha.setPlaceholderText(
            "Digite sua senha"
        )

        self.campo_senha.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        self.campo_senha.setMinimumHeight(
            52
        )

        self.campo_senha.setMaxLength(1024)

        self.campo_senha.returnPressed.connect(
            self.fazer_login
        )

        layout_formulario.addWidget(
            self.campo_senha
        )

        # ----------------------------------------------------
        # MENSAGEM DE ERRO
        # ----------------------------------------------------

        self.mensagem_erro = QLabel()

        self.mensagem_erro.setObjectName(
            "mensagem_erro"
        )

        self.mensagem_erro.setWordWrap(
            True
        )

        self.mensagem_erro.hide()

        layout_formulario.addWidget(
            self.mensagem_erro
        )

        # ----------------------------------------------------
        # BOTÃO
        # ----------------------------------------------------

        self.botao_entrar = QPushButton(
            "Entrar"
        )

        self.botao_entrar.setObjectName(
            "botao_entrar"
        )

        self.botao_entrar.setMinimumHeight(
            54
        )

        self.botao_entrar.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.botao_entrar.clicked.connect(
            self.fazer_login
        )

        layout_formulario.addWidget(
            self.botao_entrar
        )

        layout_direito.addWidget(
            formulario
        )

        layout_principal.addWidget(
            painel_esquerdo,
            1,
        )

        layout_principal.addWidget(
            painel_direito,
            1,
        )

    # ========================================================
    # LOGIN
    # ========================================================

    def fazer_login(self) -> None:

        username = (
            self.campo_usuario
            .text()
            .strip()
        )

        senha = self.campo_senha.text()

        self.mensagem_erro.hide()

        if not username:

            self.mostrar_erro(
                "Digite seu usuário."
            )

            self.campo_usuario.setFocus()

            return

        if not senha:

            self.mostrar_erro(
                "Digite sua senha."
            )

            self.campo_senha.setFocus()

            return

        self.login_requested.emit(
            AdminCredentials(
                username=username,
                password=senha,
            )
        )

    # ========================================================
    # ERRO
    # ========================================================

    def show_error(
        self,
        mensagem: str,
    ) -> None:

        self.mensagem_erro.setText(
            mensagem
        )

        self.mensagem_erro.show()

    mostrar_erro = show_error

    def set_authenticating(self, authenticating: bool) -> None:
        self.botao_entrar.setEnabled(not authenticating)
        self.campo_usuario.setEnabled(not authenticating)
        self.campo_senha.setEnabled(not authenticating)
        self.botao_entrar.setText("Entrando..." if authenticating else "Entrar")

    def clear_password(self) -> None:
        self.campo_senha.clear()

    def reset(self, *, message: str | None = None) -> None:
        self.set_authenticating(False)
        self.clear_password()
        if message:
            self.show_error(message)
        else:
            self.mensagem_erro.clear()
            self.mensagem_erro.hide()
        self.campo_usuario.setFocus()
    # ========================================================
    # ESTILOS
    # ========================================================

    @staticmethod
    def estilos() -> str:

        return """
        QWidget {
            font-family: "Segoe UI";
            color: #172033;
        }

        #painel_esquerdo {
            background-color: #0B1F3A;
        }

        #painel_direito {
            background-color: #F7F9FC;
        }

        #logo {
            color: white;
            font-size: 42px;
            font-weight: 800;
        }

        #subtitulo_logo {
            color: #B8C7DC;
            font-size: 14px;
            margin-top: 5px;
        }

        #descricao {
            color: #D7E1EF;
            font-size: 16px;
            line-height: 1.5;
        }

        #rodape {
            color: #8195B1;
            font-size: 12px;
        }

        #formulario {
            background-color: white;
            border-radius: 18px;
            padding: 36px;
        }

        #titulo {
            color: #172033;
            font-size: 30px;
            font-weight: 700;
        }

        #subtitulo {
            color: #718096;
            font-size: 14px;
            line-height: 1.5;
        }

        #label_campo {
            color: #344054;
            font-size: 13px;
            font-weight: 600;
        }

        QLineEdit {
            background-color: #F8FAFC;
            border: 1px solid #D9E1EC;
            border-radius: 10px;
            padding: 0 15px;
            font-size: 14px;
            color: #172033;
        }

        QLineEdit:focus {
            border: 2px solid #2563EB;
            background-color: white;
        }

        QLineEdit:hover {
            border: 1px solid #AAB8CC;
        }

        #botao_entrar {
            background-color: #2563EB;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 15px;
            font-weight: 700;
        }

        #botao_entrar:hover {
            background-color: #1D4ED8;
        }

        #botao_entrar:pressed {
            background-color: #1E40AF;
        }

        #botao_entrar:disabled {
            background-color: #93B4F4;
        }

        #mensagem_erro {
            color: #DC2626;
            background-color: #FEF2F2;
            border: 1px solid #FECACA;
            border-radius: 8px;
            padding: 10px;
            font-size: 13px;
        }
        """
    
