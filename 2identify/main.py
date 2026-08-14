import sys

from PySide6.QtWidgets import QApplication

from app.ui.login.login_window import LoginWindow


def main():

    app = QApplication(sys.argv)

    app.setApplicationName(
        "2Identify"
    )

    app.setOrganizationName(
        "2Identify"
    )

    janela = LoginWindow()

    janela.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()