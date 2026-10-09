"""GUI smoke check with isolated storage and no actual network or input."""
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from PyQt5.QtCore import QTimer, QThread
from PyQt5.QtWidgets import QSystemTrayIcon
from core.paths import DATA_DIR, ensure_data_dir
from core.settings import AppSettings, save_settings, load_settings
from ui.setup_window import SetupWindow


def run(app):
    ensure_data_dir()
    result = Path(DATA_DIR) / 'smoke-result.txt'
    window = None
    try:
        log = Path(DATA_DIR) / 'latest.log'
        log.write_text('old\n', encoding='utf-8')
        save_settings(AppSettings(nick='MyNick', logs=str(log), platform='vk',
                                  vk_user_id='9', vk_token='fake', use_sound=False))
        with patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP forbidden')), \
             patch('pynput.keyboard.Listener') as listener, \
             patch('ui.setup_window.set_startup_enabled', return_value=True), \
             patch('ui.setup_window.set_taskbar_hidden', return_value=True), \
             patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=True):
            window = SetupWindow()
            window.show(); app.processEvents()
            assert window._setup_tray() and window.tray_icon.isVisible(), 'Tray creation failed'
            window.apply_taskbar_mode(True)
            window.hide(); window._restore_from_tray(); app.processEvents()
            assert window.isVisible(), 'Tray restoration failed'
            # Exercise a real validation QThread and successful settings commit.
            candidate = load_settings()
            candidate.nick = 'ValidatedNick'
            window._pending_settings = candidate
            window.validation_data = {'nick': candidate.nick, 'platform': 'ВКонтакте',
                                      'bot_id': '', 'chat_id': ''}
            window._start_validation()
            deadline = time.monotonic() + 5
            while getattr(window, '_main_screen', None) is None and time.monotonic() < deadline:
                app.processEvents(); time.sleep(0.01)
            assert load_settings().nick == 'ValidatedNick', 'Settings were not committed'
            assert getattr(window, '_main_screen', None) is not None, 'Validation did not open main screen'
            app.processEvents()
            main = window._main_screen
            assert main.log_monitor.isRunning(), 'Log monitor not running'
            main.log_message('[CHAT] text <test> & value')
            assert '<test> & value' in main.log_output.toPlainText(), 'Log HTML not escaped'
            # A failing screenshot must release the queue and allow the next event.
            from domain.events import ModerationEvent, PunishmentType
            main.ops.processing_delay = 0
            messages = []
            main.ops.log_signal.connect(messages.append)
            with patch('threads.action_threads.pressing_key'), \
                 patch('threads.action_threads.capture_image', side_effect=OSError('simulated capture failure')), \
                 patch('threads.message_sender.VkNotifier.send_punishment', return_value=(True, 'kick delivered')):
                main.ops.enqueue(ModerationEvent(PunishmentType.MUTE, 'mute', 'mod', 'bad', 'reason', True))
                main.ops.enqueue(ModerationEvent(PunishmentType.KICK, 'kick', 'mod', 'bad', 'reason', False))
                deadline = time.monotonic() + 5
                while 'kick delivered' not in messages and time.monotonic() < deadline:
                    app.processEvents(); time.sleep(0.01)
                assert 'kick delivered' in messages and not main.ops.is_busy, 'Queue did not recover'
            window.grab().save(str(Path(DATA_DIR) / 'main-window.png'))
            # Verify a signal emitted on another thread reaches the GUI thread.
            calls=[]
            main.screenshot_requested.disconnect()
            main.screenshot_requested.connect(lambda: calls.append(QThread.currentThread() == app.thread()))
            import threading
            t=threading.Thread(target=main.screenshot_requested.emit); t.start(); t.join()
            app.processEvents(); assert calls == [True], 'Hotkey dispatched outside GUI thread'
            # Verify every new page with actual Qt widgets, and a live profile switch.
            from core import profiles,history
            from core.settings import clear_saved_secrets
            from services.diagnostics import export_diagnostics
            window.open_control_center();app.processEvents();center=window._control_center
            assert center.tabs.count()==9,'Missing control-center pages'
            center_errors=[]
            with patch('ui.control_center.QMessageBox.warning',side_effect=lambda *args:center_errors.append(str(args[-1]))), \
                 patch('ui.control_center.QMessageBox.information'), \
                 patch('ui.control_center.QMessageBox.question',return_value=__import__('PyQt5.QtWidgets',fromlist=['QMessageBox']).QMessageBox.Yes):
                for index in range(center.tabs.count()):
                    center.tabs.setCurrentIndex(index);app.processEvents();center.refresh()
                    center.grab().save(str(Path(DATA_DIR)/f'center-{index}.png'))
                # Real background-job signals must update widgets and release ownership.
                with patch('ui.control_center.check_connection',return_value=(True,'Connection checked')):
                    center.test_connection()
                    deadline=time.monotonic()+5
                    while center.has_running_threads() and time.monotonic()<deadline:
                        app.processEvents();time.sleep(0.01)
                    app.processEvents()
                    assert center.connection_button.isEnabled(),'Connection job did not finish'
                    assert 'Connection checked' in center.connection_result.toPlainText(),'Connection result missing'
                update={'new':False,'tag':'v1.3.0','notes':'test','asset':None,'checksums':None,'repository':'example/project'}
                with patch('ui.control_center.check_update',return_value=update):
                    center.repository.setText('example/project');center.check_updates()
                    deadline=time.monotonic()+5
                    while center.has_running_threads() and time.monotonic()<deadline:
                        app.processEvents();time.sleep(0.01)
                    app.processEvents()
                    assert center.update_check.isEnabled(),'Update job did not finish'
                    assert center._update==update and not center.update_download.isEnabled(),'Update result missing'
                cfg=load_settings();cfg.notification_template='{target}: {reason}'
                center.template.setPlainText(cfg.notification_template);center.save_notifications()
                center.capture_mode.setCurrentIndex(center.capture_mode.findData('screen'));center.hide_capture.setChecked(True);center.save_capture()
                alternate=AppSettings(nick='SecondNick',logs=str(log),platform='vk',vk_token='fake',vk_user_id='10')
                key=profiles.save_profile('Второй сервер',alternate);center.refresh_profiles()
                center.profile_list.setCurrentIndex(center.profile_list.findData(key));center.activate_editor();app.processEvents()
                assert load_settings().nick=='SecondNick','Profile switch failed'
                assert main.log_monitor.isRunning(),'Profile monitor did not restart'
                center.tabs.setCurrentIndex(0);center.refresh_history()
                assert center.history_table.rowCount()>=2,'History is empty'
                history.export_csv(str(Path(DATA_DIR)/'history-export.csv'))
                export_diagnostics(str(Path(DATA_DIR)/'diagnostics.json'),{'running':True})
                assert not center_errors, 'ControlCenter error: '+str(center_errors)
                center.hide()
            # The close handler must wait for running workers, then close.
            window.close()
            deadline=time.monotonic()+5
            while window.isVisible() and time.monotonic()<deadline:
                app.processEvents(); time.sleep(0.01)
            assert not main.has_running_threads(), 'Workers did not stop'
            assert not window.isVisible(), 'Window did not close'
            result.write_text('PASS: setup, main window, tray, restoration, log monitor, HTML, validation, queue recovery, cross-thread signal, 9 control-center pages, profile switching, connection/update jobs, CSV, diagnostics, graceful shutdown\n',encoding='utf-8')
        return 0
    except Exception:
        import traceback
        result.write_text(traceback.format_exc(),encoding='utf-8')
        if window is not None:
            window.close()
        return 1
