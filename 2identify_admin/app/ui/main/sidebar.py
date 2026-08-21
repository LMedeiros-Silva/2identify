from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class Sidebar(QFrame):
    """
    Menu lateral principal do 2Identify.

    Todas as páginas do sistema serão acessadas
    através desta barra.
    """

    pagina_selecionada = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("sidebar")

        self.botoes: dict[str, QPushButton] = {}

        self.criar_interface()

    def criar_interface(self) -> None:

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            20,
            25,
            20,
            20,
        )

        layout.setSpacing(8)

        # ==================================================
        # LOGO
        # ==================================================

        logo = QLabel("2Identify")

        logo.setObjectName("sidebar_logo")

        layout.addWidget(logo)

        subtitulo = QLabel(
            "Industrial Safety"
        )

        subtitulo.setObjectName(
            "sidebar_subtitulo"
        )

        layout.addWidget(subtitulo)

        layout.addSpacing(35)

        # ==================================================
        # MENU
        # ==================================================

        self.adicionar_botao(
            layout,
            "dashboard",
            "Dashboard",
        )

        self.adicionar_botao(
            layout,
            "epis",
            "Gestão de EPIs",
        )

        self.adicionar_botao(
            layout,
            "alertas",
            "Alertas",
        )

        self.adicionar_botao(
            layout,
            "relatorios",
            "Relatórios",
        )

        layout.addStretch()

        # ==================================================
        # CONFIGURAÇÕES
        # ==================================================

        self.adicionar_botao(
            layout,
            "configuracoes",
            "Configurações",
        )

        self.adicionar_botao(
            layout,
            "sair",
            "Sair",
        )

        self.selecionar(
            "dashboard"
        )

    def adicionar_botao(
        self,
        layout: QVBoxLayout,
        identificador: str,
        texto: str,
    ) -> None:

        botao = QPushButton(
            texto
        )

        botao.setObjectName(
            "menu_botao"
        )

        botao.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        botao.setCheckable(True)

        botao.clicked.connect(
            lambda: self.selecionar(
                identificador
            )
        )

        layout.addWidget(
            botao
        )

        self.botoes[
            identificador
        ] = botao

    def selecionar(
        self,
        identificador: str,
    ) -> None:

        for nome, botao in self.botoes.items():

            botao.setChecked(
                nome == identificador
            )

        self.pagina_selecionada.emit(
            identificador
        )
        
