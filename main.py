import sys
import os
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QMetaType
from PyQt5.QtGui import QTextCursor, QIcon

from config import check_config
from core.paths import ensure_data_dir, resource_path
from core.helpers import cleanup, init_local_storage
import core.globals as g
from ui.setup_window import SetupWindow


if __name__ == "__main__":
    try:
        ensure_data_dir()

        app = QApplication(sys.argv)

        try:
            icon_path = resource_path(os.path.join('path', 'icon.ico'))
            if os.path.exists(icon_path):
                app.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"[WARNING] Файл иконки не найден: {e}")

        try:
            check_config()
        except Exception as config_error:
            QMessageBox.critical(
                None,
                "Ошибка конфигурации",
                f"Не удалось запустить NeboProject.\n\n{config_error}"
            )
            sys.exit(1)

        try:
            if not QMetaType.isRegistered(QMetaType.type('QTextCursor')):
                QMetaType.registerType(QTextCursor)
        except Exception:
            pass

        init_local_storage()

        g.gui_ready = True

        setup_window = SetupWindow()
        setup_window.show()

        exit_code = app.exec_()
        if g.main_window and hasattr(g.main_window, 'log_monitor'):
            g.main_window.log_monitor.stop()

        sys.exit(exit_code)

    except Exception as e:
        print(f"[ERROR] GUI crashed: {e}")
        import traceback
        traceback.print_exc()
        try:
            QMessageBox.critical(None, "NeboProject — ошибка запуска",
                                  f"Не удалось запустить приложение.\n\n{type(e).__name__}: {e}")
        except Exception:
            pass
        cleanup()
