"""2Identify Admin stylesheets built on the shared design tokens.

Colors and type sizes are written as ``{{token}}`` and resolved by
``app.ui.theme.apply_theme``. Blue is the brand color; green, yellow and red are
reserved for safety and alert states.
"""

from __future__ import annotations

from pathlib import Path

from app.ui.theme import TOKENS, apply_theme

_ICONS = Path(__file__).resolve().parents[2] / "assets" / "icons"
_STYLE_TOKENS = {
    **TOKENS,
    "icon_chevron_down": (_ICONS / "chevron-down.svg").as_posix(),
    "icon_chevron_up": (_ICONS / "chevron-up.svg").as_posix(),
}

_FOUNDATION = """
* {
    font-family: {{font_family}};
}

QWidget {
    color: {{ink_900}};
    font-size: {{font_small}};
}

QToolTip {
    color: {{surface_1}};
    background-color: {{nav_800}};
    border: 1px solid {{nav_600}};
    border-radius: {{radius_sm}};
    padding: 6px 8px;
    font-size: {{font_label}};
}

/* Buttons without a specific rule use the secondary style. */
QPushButton {
    color: {{ink_800}};
    background-color: {{surface_1}};
    border: 1px solid {{line_300}};
    border-radius: {{radius_md}};
    min-height: 34px;
    padding: 0 16px;
    font-size: {{font_small}};
    font-weight: 600;
}

QPushButton:hover {
    background-color: {{brand_50}};
    border-color: {{brand_300}};
}

QPushButton:pressed {
    background-color: {{brand_100}};
}

QPushButton:focus {
    border-color: {{brand_500}};
}

QPushButton:disabled {
    color: {{ink_400}};
    background-color: {{surface_3}};
    border-color: {{line_200}};
}

QLineEdit,
QTextEdit,
QPlainTextEdit,
QAbstractSpinBox,
QComboBox {
    color: {{ink_900}};
    background-color: {{surface_1}};
    border: 1px solid {{line_300}};
    border-radius: {{radius_md}};
    min-height: 22px;
    padding: 6px 10px;
    font-size: {{font_body}};
    selection-color: {{ink_900}};
    selection-background-color: {{brand_200}};
}

QLineEdit:hover,
QTextEdit:hover,
QPlainTextEdit:hover,
QAbstractSpinBox:hover,
QComboBox:hover {
    border-color: {{ink_300}};
}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QAbstractSpinBox:focus,
QComboBox:focus {
    border-color: {{brand_500}};
}

QLineEdit:disabled,
QTextEdit:disabled,
QPlainTextEdit:disabled,
QAbstractSpinBox:disabled,
QComboBox:disabled {
    color: {{ink_400}};
    background-color: {{surface_3}};
    border-color: {{line_200}};
}

QComboBox::drop-down,
QDateEdit::drop-down,
QDateTimeEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    border: none;
    width: 28px;
}

QComboBox::down-arrow,
QDateEdit::down-arrow,
QDateTimeEdit::down-arrow,
QAbstractSpinBox::down-arrow {
    image: url({{icon_chevron_down}});
    width: 12px;
    height: 12px;
}

QAbstractSpinBox::up-arrow {
    image: url({{icon_chevron_up}});
    width: 12px;
    height: 12px;
}

QAbstractSpinBox::up-button,
QAbstractSpinBox::down-button {
    subcontrol-origin: border;
    border: none;
    width: 24px;
}

QAbstractSpinBox::up-button {
    subcontrol-position: top right;
}

QAbstractSpinBox::down-button {
    subcontrol-position: bottom right;
}

QComboBox QAbstractItemView {
    background-color: {{surface_1}};
    border: 1px solid {{line_300}};
    selection-color: {{ink_900}};
    selection-background-color: {{brand_100}};
    outline: 0;
}

QCheckBox,
QRadioButton {
    color: {{ink_800}};
    spacing: 8px;
    font-size: {{font_body}};
}

QCheckBox:disabled,
QRadioButton:disabled {
    color: {{ink_400}};
}

QListView,
QTreeView,
QTableView {
    color: {{ink_900}};
    background-color: {{surface_1}};
    alternate-background-color: {{surface_2}};
    border: 1px solid {{line_200}};
    border-radius: {{radius_md}};
    gridline-color: {{line_100}};
    selection-color: {{ink_900}};
    selection-background-color: {{brand_100}};
    font-size: {{font_body}};
    outline: 0;
}

QListView::item,
QTreeView::item,
QTableView::item {
    padding: 6px 8px;
    border-bottom: 1px solid {{line_100}};
}

QListView::item:hover,
QTreeView::item:hover,
QTableView::item:hover {
    background-color: {{brand_50}};
}

QListView::item:selected,
QTreeView::item:selected,
QTableView::item:selected {
    color: {{ink_900}};
    background-color: {{brand_100}};
}

QHeaderView::section {
    color: {{ink_600}};
    background-color: {{surface_2}};
    border: none;
    border-bottom: 1px solid {{line_200}};
    padding: 8px;
    font-size: {{font_label}};
    font-weight: 700;
}

QScrollArea {
    background: transparent;
    border: none;
}

QScrollArea > #qt_scrollarea_viewport,
QScrollArea > #qt_scrollarea_viewport > QWidget {
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {
    background-color: {{line_300}};
    border-radius: 3px;
    min-height: 32px;
    min-width: 32px;
}

QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {
    background-color: {{ink_300}};
}

QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {
    background: transparent;
    border: none;
    width: 0;
    height: 0;
}

QProgressBar {
    color: {{ink_600}};
    background-color: {{surface_3}};
    border: none;
    border-radius: {{radius_sm}};
    text-align: center;
    font-size: {{font_label}};
}

QProgressBar::chunk {
    background-color: {{brand_600}};
    border-radius: {{radius_sm}};
}

QSplitter::handle {
    background-color: transparent;
}

QMessageBox QLabel {
    color: {{ink_900}};
    font-size: {{font_body}};
}
"""

_MAIN = """
QMainWindow,
#central,
#area_direita,
#conteudo {
    background-color: {{surface_0}};
}

/* Sidebar */

#sidebar {
    background-color: {{nav_950}};
    border-right: 1px solid {{nav_800}};
}

#sidebar QLabel {
    background: transparent;
}

#sidebar_marca {
    color: {{surface_1}};
    background-color: {{brand_500}};
    border-radius: {{radius_md}};
    font-size: {{font_panel}};
    font-weight: 800;
}

#sidebar_logo {
    color: {{surface_1}};
    font-size: {{font_section}};
    font-weight: 800;
}

#sidebar_subtitulo {
    color: #8FB4E2;
    font-size: {{font_label}};
}

#sidebar_secao {
    color: {{nav_muted}};
    font-size: {{font_label}};
    padding-left: 10px;
}

#sidebar_separador {
    background-color: {{nav_800}};
    border: none;
}

#menu_botao,
#menu_sair {
    background-color: transparent;
    color: {{nav_text}};
    border: none;
    border-left: 3px solid transparent;
    border-radius: {{radius_md}};
    text-align: left;
    min-height: 22px;
    padding: 9px 12px;
    font-size: {{font_body}};
    font-weight: 600;
}

#menu_botao:hover,
#menu_sair:hover {
    background-color: {{nav_800}};
    color: {{surface_1}};
}

#menu_botao:checked {
    background-color: {{nav_800}};
    border-left: 3px solid {{brand_400}};
    color: {{surface_1}};
    font-weight: 700;
}

#menu_botao:pressed,
#menu_sair:pressed {
    background-color: {{nav_850}};
}

#menu_sair:hover {
    color: {{crit_300}};
}

#sidebar #menu_badge {
    color: {{surface_1}};
    background-color: {{crit_600}};
    border-radius: 9px;
    min-width: 18px;
    max-height: 18px;
    padding: 0 6px;
    font-size: {{font_badge}};
    font-weight: 800;
}

/* Header */

#header {
    background-color: {{surface_1}};
    border-bottom: 1px solid {{line_200}};
}

#header_contexto {
    color: {{ink_500}};
    font-size: {{font_small}};
}

#header_titulo {
    color: {{ink_900}};
    font-size: 20px;
    font-weight: 600;
}

#header_conexao {
    color: {{warn_700}};
    background-color: {{warn_50}};
    border: 1px solid {{warn_300}};
    border-radius: 13px;
    padding: 4px 12px;
    font-size: {{font_label}};
    font-weight: 700;
}

#header_conexao[state="connected"] {
    color: {{safe_700}};
    background-color: {{safe_50}};
    border-color: {{safe_300}};
}

#header_conexao[state="connecting"] {
    color: {{brand_700}};
    background-color: {{brand_50}};
    border-color: {{brand_200}};
}

#header_divisor {
    background-color: {{line_200}};
    border: none;
}

#usuario_avatar {
    color: {{surface_1}};
    background-color: {{nav_800}};
    border-radius: 18px;
    font-size: {{font_small}};
    font-weight: 800;
}

#usuario_nome {
    color: {{ink_900}};
    font-size: {{font_small}};
    font-weight: 700;
}

#usuario_perfil {
    color: {{ink_500}};
    font-size: {{font_label}};
}

/* Page scaffolding shared by every screen */

#dashboard_page,
#dashboard_conteudo,
QScrollArea > #qt_scrollarea_viewport > #dashboard_conteudo,
#alerts_page,
#settings_page,
#operations_page,
#employees_page,
#reports_page {
    background-color: {{surface_0}};
}

#pagina_titulo {
    color: {{ink_900}};
    font-size: {{font_title}};
    font-weight: 700;
}

#pagina_subtitulo {
    color: {{ink_600}};
    font-size: {{font_body}};
}

#placeholder {
    color: {{ink_500}};
    font-size: {{font_kpi}};
    font-weight: 700;
}

/* Buttons */

#primary_action,
#dashboard_retry,
#alerts_refresh,
#alert_confirm,
#employee_save_button,
#reports_export_button {
    background-color: {{brand_600}};
    color: {{surface_1}};
    border: 1px solid {{brand_600}};
    border-radius: {{radius_md}};
    min-height: 36px;
    padding: 0 18px;
    font-size: {{font_small}};
    font-weight: 700;
}

#primary_action:hover,
#dashboard_retry:hover,
#alerts_refresh:hover,
#alert_confirm:hover,
#employee_save_button:hover,
#reports_export_button:hover {
    background-color: {{brand_700}};
    border-color: {{brand_700}};
}

#primary_action:pressed,
#dashboard_retry:pressed,
#alerts_refresh:pressed,
#alert_confirm:pressed,
#employee_save_button:pressed,
#reports_export_button:pressed {
    background-color: {{brand_800}};
}

#primary_action:focus,
#dashboard_retry:focus,
#alerts_refresh:focus,
#alert_confirm:focus,
#employee_save_button:focus,
#reports_export_button:focus {
    border: 2px solid {{brand_800}};
}

#employee_face_button {
    color: {{brand_700}};
    background-color: {{brand_50}};
    border: 1px solid {{brand_300}};
    border-radius: {{radius_md}};
    min-height: 36px;
    padding: 0 18px;
    font-size: {{font_small}};
    font-weight: 700;
}

#employee_face_button:hover {
    background-color: {{brand_100}};
    border-color: {{brand_500}};
}

#employee_face_button:focus {
    border: 2px solid {{brand_500}};
}

#alert_close {
    color: {{ink_900}};
    background-color: {{surface_1}};
    border: 1px solid {{line_300}};
    border-radius: {{radius_md}};
    min-height: 36px;
    padding: 0 16px;
    font-size: {{font_small}};
    font-weight: 600;
}

#alert_close:hover {
    background-color: {{brand_50}};
    border-color: {{brand_300}};
}

#alert_close:focus {
    border: 2px solid {{brand_500}};
}

#primary_action:disabled,
#dashboard_retry:disabled,
#alerts_refresh:disabled,
#alert_confirm:disabled,
#alert_close:disabled,
#employee_save_button:disabled,
#employee_face_button:disabled,
#reports_export_button:disabled {
    color: {{ink_400}};
    background-color: {{surface_3}};
    border: 1px solid {{line_200}};
}

/* Status, loading and error messages */

#dashboard_status,
#realtime_status,
#employee_face_status,
#employee_feedback,
#reports_status {
    color: {{ink_600}};
    font-size: {{font_small}};
}

#dashboard_status[state="loading"],
#employee_feedback[state="loading"],
#reports_status[state="loading"],
#realtime_status[state="connecting"] {
    color: {{brand_700}};
}

#dashboard_status[state="ready"],
#employee_feedback[state="success"],
#reports_status[state="success"],
#realtime_status[state="connected"] {
    color: {{safe_700}};
}

#dashboard_status[state="error"],
#employee_feedback[state="error"],
#reports_status[state="error"] {
    color: {{crit_700}};
    font-weight: 600;
}

#realtime_status[state="offline"] {
    color: {{warn_700}};
    font-weight: 600;
}

#alerts_feedback,
#operations_feedback {
    color: {{brand_800}};
    background-color: {{brand_50}};
    border: 1px solid {{brand_200}};
    border-radius: {{radius_md}};
    padding: 8px 12px;
    font-size: {{font_small}};
}

#alerts_feedback[state="error"],
#operations_feedback[state="error"] {
    color: {{crit_700}};
    background-color: {{crit_50}};
    border-color: {{crit_300}};
}

#alerts_feedback[state="success"],
#operations_feedback[state="success"] {
    color: {{safe_700}};
    background-color: {{safe_50}};
    border-color: {{safe_300}};
}

#realtime_alert_banner,
#alert_banner {
    color: {{warn_800}};
    background-color: {{warn_100}};
    border: 1px solid {{warn_300}};
    border-left: 4px solid {{warn_500}};
    border-radius: {{radius_md}};
    padding: 10px 12px;
    font-size: {{font_body}};
}

#realtime_alert_banner[severity="critical"],
#alert_banner[severity="critical"] {
    color: {{crit_800}};
    background-color: {{crit_100}};
    border-color: {{crit_300}};
    border-left: 4px solid {{crit_600}};
}

#alert_banner_text {
    color: {{warn_800}};
    font-weight: 600;
}

#alert_banner[severity="critical"] #alert_banner_text {
    color: {{crit_800}};
}

/* Cards and panels */

#dashboard_card,
#dashboard_painel,
#dashboard_grafico_painel,
#alerts_list_panel,
#alert_detail_scroll,
#operations_panel {
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    border-radius: {{radius_lg}};
}

#dashboard_painel {
    min-height: 300px;
}

#dashboard_grafico_painel {
    min-height: 240px;
}

/* Dashboard: one KPI instrument strip */

#dashboard_kpis {
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    border-radius: {{radius_lg}};
}

#dashboard_kpis #dashboard_card {
    background-color: transparent;
    border: none;
    border-left: 1px solid {{line_100}};
    border-radius: 0;
}

#dashboard_kpis #dashboard_card[first="true"] {
    border-left: none;
}

#dashboard_kpis #dashboard_card[tone="hero"] {
    background-color: {{nav_950}};
    border-top-left-radius: {{radius_lg}};
    border-bottom-left-radius: {{radius_lg}};
}

#dashboard_card[tone="hero"] #card_titulo {
    color: #A9C3E6;
}

#dashboard_card[tone="hero"] #card_valor {
    color: {{surface_1}};
}

#dashboard_card[tone="hero"] #card_descricao {
    color: #C7D6EC;
}

#dashboard_card[tone="warn"] #card_valor {
    color: {{ink_900}};
}

#dashboard_card[tone="crit"] #card_valor {
    color: {{crit_600}};
}

#dashboard_secao {
    color: {{ink_900}};
    font-size: {{font_panel}};
    font-weight: 600;
}

#dashboard_link {
    color: {{ink_900}};
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    border-radius: {{radius_md}};
    min-height: 32px;
    padding: 0 12px;
    font-size: {{font_small}};
    font-weight: 600;
}

#dashboard_link:hover {
    background-color: {{brand_50}};
    border-color: {{brand_200}};
}

#dashboard_link:focus {
    border: 2px solid {{brand_500}};
}

#dashboard_vazio {
    color: {{ink_500}};
    background-color: {{surface_2}};
    border: 1px dashed {{line_300}};
    border-radius: {{radius_md}};
    padding: 22px;
    font-size: {{font_small}};
}

/* Dashboard: live rows separated by hairlines, state stripe on the left */

#dashboard_operacao,
#dashboard_alerta {
    background-color: transparent;
    border: none;
    border-top: 1px solid {{line_100}};
    border-left: 4px solid {{line_300}};
    border-radius: 0;
}

#dashboard_operacao:hover,
#dashboard_alerta:hover {
    background-color: {{surface_2}};
}

#dashboard_operacao[tone="safe"] {
    border-left: 4px solid {{safe_700}};
}

#dashboard_operacao[tone="warn"],
#dashboard_alerta[tone="warn"] {
    border-left: 4px solid {{warn_500}};
}

#dashboard_operacao[tone="crit"],
#dashboard_alerta[tone="crit"] {
    border-left: 4px solid {{crit_600}};
}

#dashboard_alerta[tone="inc"] {
    border-left: 4px solid {{inc_700}};
}

#dashboard_operacao QWidget,
#dashboard_alerta QWidget {
    background: transparent;
}

#linha_avatar {
    color: {{surface_1}};
    background-color: {{nav_900}};
    border-radius: 16px;
    font-size: {{font_label}};
    font-weight: 700;
}

#dashboard_operacao #linha_avatar {
    background-color: {{nav_900}};
}

#linha_titulo {
    color: {{ink_900}};
    font-size: {{font_body}};
    font-weight: 600;
}

#linha_valor {
    color: {{ink_800}};
    font-size: {{font_small}};
    font-weight: 700;
}

#linha_tempo {
    color: {{ink_900}};
    font-size: 17px;
    font-weight: 600;
}

#linha_texto {
    color: {{ink_500}};
    font-size: {{font_label}};
}

#linha_texto[stale="true"] {
    color: {{warn_700}};
    font-weight: 700;
}

#linha_alerta {
    color: {{crit_700}};
    font-size: {{font_label}};
    font-weight: 700;
}

#status_chip {
    border-radius: 11px;
    padding: 3px 10px;
    font-size: {{font_label}};
    font-weight: 700;
}

#dashboard_painel #realtime_status {
    border-radius: 11px;
    padding: 3px 10px;
    font-size: {{font_label}};
    font-weight: 700;
    color: {{warn_700}};
    background-color: {{warn_50}};
}

#dashboard_painel #realtime_status[state="connected"] {
    color: {{safe_700}};
    background-color: {{safe_50}};
}

#dashboard_painel #realtime_status[state="connecting"] {
    color: {{brand_700}};
    background-color: {{brand_50}};
}

#card_titulo {
    color: {{ink_600}};
    font-size: {{font_small}};
    font-weight: 600;
}

#card_valor {
    color: {{ink_900}};
    font-size: {{font_kpi}};
    font-weight: 800;
    margin-top: 6px;
}

#card_descricao {
    color: {{ink_500}};
    font-size: {{font_label}};
    margin-top: 3px;
}

#dashboard_page #card_titulo {
    font-size: {{font_small}};
    font-weight: 500;
}

#dashboard_page #card_valor {
    font-size: 32px;
    font-weight: 600;
    margin-top: 2px;
}

#grafico_titulo,
#painel_titulo,
#alert_section_title,
#operations_section_title,
#risk_editor_title {
    color: {{ink_900}};
    font-size: {{font_panel}};
    font-weight: 700;
}

#grafico_descricao,
#painel_texto {
    color: {{ink_500}};
    font-size: {{font_label}};
}

#painel_texto {
    font-size: {{font_small}};
}

#indicador_conformidade {
    color: {{safe_700}};
    background-color: {{safe_100}};
    border: 1px solid {{safe_300}};
    border-radius: {{radius_md}};
    padding: 5px 9px;
    font-size: {{font_body}};
    font-weight: 700;
}

#sem_alertas,
#alert_muted,
#alert_detail_placeholder {
    color: {{ink_500}};
    font-size: {{font_small}};
}

/* Alerts */

#employees_list {
    padding: 4px;
}

#alert_list {
    background-color: transparent;
    border: none;
    border-top: 1px solid {{line_100}};
    border-radius: 0;
    padding: 0;
}

#alert_list::item {
    border: none;
    padding: 0;
}

#alert_list::item:hover,
#alert_list::item:selected {
    background-color: transparent;
}

#alert_row {
    background-color: {{surface_1}};
    border: none;
    border-bottom: 1px solid {{line_100}};
    border-left: 4px solid {{line_300}};
}

#alert_row[tone="crit"] {
    border-left: 4px solid {{crit_600}};
}

#alert_row[tone="warn"] {
    border-left: 4px solid {{warn_500}};
}

#alert_row[tone="inc"] {
    border-left: 4px solid {{inc_700}};
}

#alert_row[selected="true"] {
    background-color: {{brand_50}};
}

#alert_row QLabel {
    background: transparent;
}

#alert_row_title {
    color: {{ink_900}};
    font-size: {{font_body}};
    font-weight: 600;
}

#alert_row_meta {
    color: {{ink_500}};
    font-size: {{font_label}};
}

#alert_filter {
    color: {{ink_600}};
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    border-radius: 15px;
    min-height: 28px;
    padding: 0 11px;
    font-size: {{font_small}};
    font-weight: 500;
}

#alert_filter:checked {
    color: {{surface_1}};
    background-color: {{nav_900}};
    border-color: {{nav_900}};
    font-weight: 600;
}

#alerts_list_panel #alerts_refresh {
    color: {{ink_900}};
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    min-height: 32px;
    padding: 0 12px;
}

#alerts_list_panel #alerts_refresh:hover {
    background-color: {{brand_50}};
    border-color: {{brand_200}};
}

#alert_detail_container,
QScrollArea > #qt_scrollarea_viewport > #alert_detail_container {
    background-color: {{surface_1}};
    border: none;
    border-radius: {{radius_lg}};
}

#alert_detail_header {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {{line_100}};
}

#alert_detail_kicker {
    color: {{ink_600}};
    font-size: {{font_small}};
    font-weight: 600;
}

#alert_detail_title {
    color: {{ink_900}};
    font-size: {{font_page}};
    font-weight: 600;
}

#alert_detail_status {
    color: {{ink_500}};
    font-size: {{font_small}};
}

#alert_detail_summary {
    color: {{ink_700}};
    font-size: {{font_body}};
}

#alert_detail_section {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {{line_100}};
    border-radius: 0;
}

#alert_detail_section[column="left"] {
    border-right: 1px solid {{line_100}};
}

#alert_detail_section[last="true"] {
    border-bottom: none;
}

#alert_detail_section QFrame,
#alert_detail_section QWidget {
    background: transparent;
}

#alert_detail_section #alert_section_title {
    font-size: {{font_body}};
    font-weight: 600;
}

#alert_why {
    color: {{ink_900}};
    font-size: 15px;
}

#alert_no_evidence {
    color: {{ink_500}};
    border: 1px dashed {{line_300}};
    border-radius: {{radius_md}};
    padding: 10px 12px;
    font-size: {{font_small}};
}

#alert_detail_key {
    color: {{ink_500}};
    font-size: {{font_small}};
}

#alert_detail_value {
    color: {{ink_900}};
    font-size: {{font_small}};
    font-weight: 500;
}

/* Gestão de EPIs: filter chips and one card per active operation */

#ppe_page,
#ppe_cards,
QScrollArea > #qt_scrollarea_viewport > #ppe_cards {
    background-color: {{surface_0}};
}

#ppe_filter {
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    border-radius: 17px;
    min-height: 34px;
    max-height: 34px;
}

#ppe_filter[checked="true"] {
    background-color: {{nav_900}};
    border-color: {{nav_900}};
}

#ppe_filter:focus {
    border: 2px solid {{brand_500}};
}

#ppe_filter QLabel {
    background: transparent;
}

#ppe_filter_text {
    color: {{ink_600}};
    font-size: {{font_small}};
    font-weight: 500;
}

#ppe_filter_count {
    color: {{ink_900}};
    font-size: {{font_small}};
    font-weight: 700;
}

#ppe_filter[checked="true"] #ppe_filter_text,
#ppe_filter[checked="true"] #ppe_filter_count {
    color: {{surface_1}};
}

#ppe_filter_dot {
    border-radius: 4px;
    background-color: {{ink_400}};
}

#ppe_filter_dot[tone="crit"] {
    background-color: {{crit_600}};
}

#ppe_filter_dot[tone="warn"] {
    background-color: {{warn_500}};
}

#ppe_filter_dot[tone="safe"] {
    background-color: {{safe_700}};
}

#ppe_search {
    min-height: 22px;
}

#ppe_refresh {
    min-height: 34px;
}

#ppe_card {
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    border-left: 4px solid {{line_300}};
    border-radius: {{radius_lg}};
}

#ppe_card[tone="crit"] {
    border-color: {{crit_300}};
    border-left: 4px solid {{crit_600}};
}

#ppe_card[tone="warn"] {
    border-color: {{warn_300}};
    border-left: 4px solid {{warn_500}};
}

#ppe_card[tone="safe"] {
    border-left: 4px solid {{safe_700}};
}

#ppe_card QFrame,
#ppe_card QLabel {
    background: transparent;
}

#ppe_card #ppe_card_head {
    border: none;
    border-bottom: 1px solid {{line_100}};
}

#ppe_card #ppe_card_foot {
    border: none;
    border-top: 1px solid {{line_100}};
}

#ppe_card #linha_avatar {
    background-color: {{nav_900}};
    border-radius: 17px;
}

#ppe_card_name {
    color: {{ink_900}};
    font-size: 15px;
    font-weight: 600;
}

#ppe_item_name {
    color: {{ink_900}};
    font-size: {{font_body}};
}

#ppe_card_foot_text {
    color: {{ink_500}};
    font-size: {{font_label}};
}

#ppe_card_foot_text[stale="true"] {
    color: {{warn_700}};
    font-weight: 700;
}

/* Relatórios */

#reports_panel {
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    border-radius: {{radius_lg}};
}

#reports_panel QLabel {
    background: transparent;
}

#reports_panel_title {
    color: {{ink_900}};
    font-size: {{font_panel}};
    font-weight: 600;
    padding-bottom: 6px;
}

#reports_field_label {
    color: {{ink_600}};
    font-size: {{font_small}};
    font-weight: 600;
    padding-top: 8px;
}

#reports_choice {
    color: {{ink_600}};
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    border-radius: 15px;
    min-height: 30px;
    padding: 0 12px;
    font-size: {{font_small}};
    font-weight: 500;
}

#reports_choice:checked {
    color: {{surface_1}};
    background-color: {{nav_900}};
    border-color: {{nav_900}};
    font-weight: 600;
}

#reports_summary {
    color: {{ink_900}};
    font-size: 17px;
    font-weight: 500;
}

#reports_column {
    color: {{ink_600}};
    font-size: {{font_small}};
}

#reports_hint {
    color: {{ink_500}};
    font-size: {{font_label}};
}

#reports_panel #reports_export_button {
    min-height: 42px;
    font-size: {{font_body}};
}

#reports_panel #reports_status {
    border-radius: {{radius_md}};
    padding: 10px 12px;
    background-color: {{brand_50}};
    border: 1px solid {{brand_200}};
}

#reports_panel #reports_status[state="error"] {
    color: {{crit_800}};
    background-color: {{crit_100}};
    border: 1px solid {{crit_300}};
}

#reports_panel #reports_status[state="success"] {
    color: {{safe_800}};
    background-color: {{safe_100}};
    border: 1px solid {{safe_300}};
}

/* Configurações */

#settings_panel {
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    border-radius: {{radius_lg}};
}

#settings_panel QLabel {
    background: transparent;
}

#settings_row {
    background: transparent;
    border: none;
    border-bottom: 1px solid {{line_100}};
}

#settings_title {
    color: {{ink_900}};
    font-size: {{font_panel}};
    font-weight: 600;
}

#settings_key {
    color: {{ink_500}};
    font-size: {{font_small}};
}

#settings_value {
    color: {{ink_900}};
    font-size: {{font_body}};
}

#settings_muted {
    color: {{ink_500}};
    font-size: {{font_body}};
}

#settings_code {
    color: {{ink_900}};
    background-color: {{surface_3}};
    border: 1px solid {{line_200}};
    border-radius: {{radius_sm}};
    padding: 4px 8px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: {{font_small}};
}

#settings_button {
    min-height: 32px;
}

#settings_logout {
    color: {{crit_600}};
    border-color: {{crit_300}};
    min-height: 32px;
}

#settings_logout:hover {
    background-color: {{crit_50}};
    border-color: {{crit_600}};
}

/* Safety state language: colour + shape + word */

#state_chip {
    border: 1px solid {{line_300}};
    border-radius: 12px;
    min-height: 24px;
    max-height: 24px;
    background-color: {{surface_3}};
}

#state_chip[size="big"] {
    border-radius: 17px;
    min-height: 34px;
    max-height: 34px;
}

#state_chip QLabel {
    background: transparent;
    border: none;
}

#state_chip_text {
    color: {{ink_600}};
    font-size: {{font_label}};
    font-weight: 700;
}

#state_chip[size="big"] #state_chip_text {
    font-size: {{font_body}};
}

#state_chip[tone="crit"] {
    background-color: {{crit_100}};
    border-color: {{crit_300}};
}

#state_chip[tone="crit"] #state_chip_text {
    color: {{crit_600}};
}

#state_chip[tone="warn"] {
    background-color: {{warn_100}};
    border-color: {{warn_300}};
}

#state_chip[tone="warn"] #state_chip_text {
    color: {{warn_700}};
}

#state_chip[tone="safe"] {
    background-color: {{safe_100}};
    border-color: {{safe_300}};
}

#state_chip[tone="safe"] #state_chip_text {
    color: {{safe_700}};
}

#state_chip[tone="inc"] {
    background-color: {{inc_100}};
    border: 1px dashed {{inc_300}};
}

#state_chip[tone="inc"] #state_chip_text {
    color: {{inc_700}};
}

#ppe_chip {
    max-height: 26px;
    color: {{ink_600}};
    background-color: {{surface_3}};
    border: 1px solid {{line_300}};
    border-radius: {{radius_sm}};
    min-height: 24px;
    padding: 0 8px;
    font-size: {{font_label}};
    font-weight: 600;
}

#ppe_chip[tone="safe"] {
    color: {{safe_700}};
    background-color: {{safe_100}};
    border-color: {{safe_300}};
}

#ppe_chip[tone="crit"] {
    color: {{crit_600}};
    background-color: {{crit_100}};
    border-color: {{crit_300}};
}

#ppe_chip[tone="warn"] {
    color: {{warn_700}};
    background-color: {{warn_100}};
    border-color: {{warn_300}};
}

#ppe_chip[tone="inc"] {
    color: {{inc_700}};
    background-color: {{inc_100}};
    border: 1px dashed {{inc_300}};
}
"""

_LOGIN = """
QWidget {
    font-family: {{font_family}};
    color: {{ink_900}};
}

#painel_esquerdo {
    background-color: {{nav_900}};
}

#painel_direito {
    background-color: {{surface_0}};
}

#logo {
    color: {{surface_1}};
    font-size: 42px;
    font-weight: 800;
}

#subtitulo_logo {
    color: {{brand_400}};
    font-size: {{font_body}};
    font-weight: 600;
    margin-top: 5px;
}

#descricao {
    color: {{nav_text}};
    font-size: {{font_panel}};
}

#rodape {
    color: {{nav_muted}};
    font-size: {{font_label}};
}

#formulario {
    background-color: {{surface_1}};
    border: 1px solid {{line_200}};
    border-radius: {{radius_lg}};
    padding: 36px;
}

#titulo {
    color: {{ink_900}};
    font-size: 30px;
    font-weight: 700;
}

#subtitulo {
    color: {{ink_600}};
    font-size: {{font_body}};
}

#label_campo {
    color: {{ink_700}};
    font-size: {{font_small}};
    font-weight: 600;
}

QLineEdit {
    background-color: {{surface_2}};
    border: 1px solid {{line_300}};
    border-radius: {{radius_md}};
    min-height: 48px;
    padding: 0 15px;
    font-size: {{font_body}};
    color: {{ink_900}};
    selection-background-color: {{brand_200}};
}

QLineEdit:hover {
    border: 1px solid {{ink_300}};
}

QLineEdit:focus {
    border: 2px solid {{brand_500}};
    background-color: {{surface_1}};
}

QLineEdit:disabled {
    color: {{ink_400}};
    background-color: {{surface_3}};
}

#botao_entrar {
    background-color: {{brand_600}};
    color: {{surface_1}};
    border: none;
    min-height: 54px;
    border-radius: {{radius_md}};
    font-size: {{font_panel}};
    font-weight: 700;
}

#botao_entrar:hover {
    background-color: {{brand_700}};
}

#botao_entrar:pressed {
    background-color: {{brand_800}};
}

#botao_entrar:focus {
    border: 2px solid {{brand_800}};
}

#botao_entrar:disabled {
    color: {{surface_1}};
    background-color: {{brand_300}};
}

#mensagem_erro {
    color: {{crit_700}};
    background-color: {{crit_50}};
    border: 1px solid {{crit_300}};
    border-left: 4px solid {{crit_600}};
    border-radius: {{radius_md}};
    padding: 10px;
    font-size: {{font_small}};
}
"""


def main_window_stylesheet() -> str:
    """Design-system foundation plus the Admin shell and page rules."""

    return apply_theme(_FOUNDATION + _MAIN, _STYLE_TOKENS)


def login_stylesheet() -> str:
    return apply_theme(_FOUNDATION + _LOGIN, _STYLE_TOKENS)
