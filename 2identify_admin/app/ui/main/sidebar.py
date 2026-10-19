from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.ui.icons import line_icon
from app.ui.theme import TOKENS


class Sidebar(QFrame):
    """
    Menu lateral principal do 2Identify.

    Todas as páginas do sistema são acessadas por esta barra, agrupadas
    por finalidade: monitoramento, cadastros e análise.
    """

    pagina_selecionada = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("sidebar")

        self.botoes: dict[str, QPushButton] = {}
        self._badges: dict[str, QLabel] = {}

        self.criar_interface()

    def criar_interface(self) -> None:

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(2)

        # ==================================================
        # MARCA
        # ==================================================

        marca = QHBoxLayout()
        marca.setContentsMargins(6, 0, 0, 0)
        marca.setSpacing(10)

        simbolo = QLabel("2i")
        simbolo.setObjectName("sidebar_marca")
        simbolo.setFixedSize(38, 38)
        simbolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marca.addWidget(simbolo)

        nomes = QVBoxLayout()
        nomes.setSpacing(0)
        logo = QLabel("2Identify")
        logo.setObjectName("sidebar_logo")
        nomes.addWidget(logo)
        subtitulo = QLabel("INDUSTRIAL SAFETY")
        subtitulo.setObjectName("sidebar_subtitulo")
        nomes.addWidget(subtitulo)
        marca.addLayout(nomes, 1)
        layout.addLayout(marca)

        layout.addSpacing(26)

        # ==================================================
        # MENU
        # ==================================================

        self.adicionar_secao(layout, "MONITORAMENTO")
        self.adicionar_botao(layout, "dashboard", "Central de segurança")
        self.adicionar_botao(layout, "alertas", "Alertas")
        self.adicionar_botao(layout, "epis", "Gestão de EPIs")

        self.adicionar_secao(layout, "CADASTROS")
        self.adicionar_botao(layout, "operacoes", "Operações e Áreas")
        self.adicionar_botao(layout, "funcionarios", "Funcionários")

        self.adicionar_secao(layout, "ANÁLISE")
        self.adicionar_botao(layout, "relatorios", "Relatórios")

        layout.addStretch()

        # ==================================================
        # CONFIGURAÇÕES
        # ==================================================

        separador = QFrame()
        separador.setObjectName("sidebar_separador")
        separador.setFixedHeight(1)
        layout.addWidget(separador)
        layout.addSpacing(8)

        self.adicionar_botao(layout, "configuracoes", "Configurações")
        self.adicionar_botao(layout, "sair", "Sair", nome_objeto="menu_sair")

        self.selecionar("dashboard")

    def adicionar_secao(self, layout: QVBoxLayout, titulo: str) -> None:
        if self.botoes:
            layout.addSpacing(14)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("sidebar_secao")
        layout.addWidget(rotulo)
        layout.addSpacing(4)

    def adicionar_botao(
        self,
        layout: QVBoxLayout,
        identificador: str,
        texto: str,
        *,
        nome_objeto: str = "menu_botao",
    ) -> None:

        botao = QPushButton(texto)

        botao.setObjectName(nome_objeto)

        botao.setCursor(Qt.CursorShape.PointingHandCursor)

        botao.setCheckable(True)

        cor_ativa = TOKENS["crit_300"] if identificador == "sair" else TOKENS["surface_1"]
        botao.setIcon(line_icon(identificador, TOKENS["nav_muted"], active_color=cor_ativa))
        botao.setIconSize(QSize(18, 18))

        botao.clicked.connect(lambda: self.selecionar(identificador))

        if identificador == "alertas":
            interno = QHBoxLayout(botao)
            interno.setContentsMargins(0, 0, 10, 0)
            interno.addStretch()
            badge = QLabel()
            badge.setObjectName("menu_badge")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            badge.hide()
            interno.addWidget(badge)
            self._badges[identificador] = badge

        layout.addWidget(botao)

        self.botoes[identificador] = botao

    def set_badge(self, identificador: str, quantidade: int | None) -> None:
        """Mostra a contagem real informada pela API; oculta quando zero ou ausente."""

        badge = self._badges.get(identificador)
        if badge is None:
            return
        if not quantidade:
            badge.hide()
            return
        badge.setText("99+" if quantidade > 99 else str(quantidade))
        badge.show()

    def selecionar(
        self,
        identificador: str,
    ) -> None:

        for nome, botao in self.botoes.items():
            botao.setChecked(nome == identificador)

        self.pagina_selecionada.emit(identificador)
