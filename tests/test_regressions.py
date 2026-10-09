import ast
import datetime
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.settings import AppSettings, load_settings, save_settings
from core import globals as g
from domain.parser import parse_moderation_line
from domain.events import ModerationEvent, PunishmentType
from threads.action_threads import CaptureThread, ScreenshotThread
from threads.log_monitor import LogMonitorThread
from threads.validation import ValidationThread
from services.operation_queue import OperationQueue


class RegressionTests(unittest.TestCase):
    def test_other_nickname_prefix_ignored_all_punishments(self):
        for verb in ('замутил','предупредил','кикнул'):
            line=f'[12:00:00] 㰳 ADMIN Helper MyNickOther {verb} игрока Bad по причине: test'
            self.assertIsNone(parse_moderation_line(line,'MyNick'))

    def test_parser_escapes_target_and_moderator(self):
        e=parse_moderation_line('[12:00:00] 㰳 ADMIN Helper My<Nick> замутил игрока Bad&Guy ┃ <tag> по причине: x','My<Nick>')
        self.assertIn('My&lt;Nick&gt;',e.moderator_html)
        self.assertIn('Bad&amp;Guy',e.target_html)
        self.assertIn('&lt;tag&gt;',e.target_html)

    def test_log_partial_utf8_line_and_truncation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'latest.log'; path.write_bytes(b'old\n')
            monitor=LogMonitorThread(str(path)); lines=[]; monitor.log_line_signal.connect(lines.append)
            monitor._check_logs()
            data='[CHAT] Мод предупредил игрока Bad по причине: тест\n'.encode('utf-8')
            split=data.index('М'.encode('utf-8'))+1
            with path.open('ab') as f: f.write(data[:split])
            monitor._check_logs(); self.assertEqual(lines,[])
            with path.open('ab') as f: f.write(data[split:])
            monitor._check_logs(); self.assertEqual(lines,[data.decode().strip()])
            path.write_bytes(b'new\n'); monitor._check_logs(); self.assertEqual(lines[-1],'new')

    def test_log_replacement_larger_than_old_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'latest.log'; path.write_bytes(b'old\n')
            monitor=LogMonitorThread(str(path)); lines=[]; monitor.log_line_signal.connect(lines.append); monitor._check_logs()
            other=Path(d)/'replacement'; other.write_bytes(b'new longer line\n'); other.replace(path)
            monitor._check_logs(); self.assertEqual(lines,['new longer line'])

    def test_log_rewrite_same_size(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'latest.log'; path.write_bytes(b'old\n')
            monitor=LogMonitorThread(str(path)); lines=[]; monitor.log_line_signal.connect(lines.append); monitor._check_logs()
            path.write_bytes(b'new\n'); monitor._check_logs(); self.assertEqual(lines,['new'])

    def test_log_missing_then_recreated(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'latest.log'; path.write_bytes(b'old\n')
            monitor=LogMonitorThread(str(path)); lines=[]; monitor.log_line_signal.connect(lines.append); monitor._check_logs()
            path.unlink(); monitor._check_logs(); path.write_bytes(b'new\n'); monitor._check_logs()
            self.assertEqual(lines,['new'])

    def event(self):
        return ModerationEvent(PunishmentType.MUTE,'[12:00:00] line','mod','bad','reason',True)

    def test_capture_failure_signals_and_queue_recovers(self):
        queue=OperationQueue(); queue._busy=True; queue._process_next=MagicMock()
        worker=CaptureThread(self.event()); errors=[]
        worker.error_signal.connect(errors.append); worker.error_signal.connect(queue._on_prepare_error)
        with patch.object(worker,'pause',return_value=False), patch('threads.action_threads.pressing_key'), patch('threads.action_threads.capture_image',side_effect=OSError('capture failed')):
            worker.run()
        self.assertEqual(len(errors),1); self.assertFalse(queue.is_busy); queue._process_next.assert_called_once()

    def test_stop_queue_prevents_pending_start_and_new_events(self):
        queue=OperationQueue(); queue._process_next=MagicMock(); queue.enqueue(self.event()); queue.stop(); queue.enqueue(self.event())
        self.assertFalse(queue.is_busy); self.assertEqual(queue._queue,[])
        with patch('services.operation_queue.CaptureThread') as worker:
            queue._start(self.event())
        worker.assert_not_called()

    def test_queue_deduplication(self):
        queue=OperationQueue(); queue._process_next=MagicMock()
        queue.enqueue(self.event()); queue.enqueue(self.event()); self.assertEqual(len(queue._queue),1)

    def test_vk_validation_never_calls_telegram(self):
        parent=MagicMock(); thread=ValidationThread({'nick':'Mod','bot_id':'123:old','chat_id':'9','platform':'ВКонтакте'},'','','','',None)
        thread.owner=parent; result=[]; thread.finished.connect(lambda ok,msg:result.append(ok)); thread.run()
        self.assertEqual(result,[True]); parent.check_bot_and_chat.assert_not_called()

    def test_group_id_roundtrip(self):
        save_settings(AppSettings(chat_id='-100123',bot_id='123:secret'))
        self.assertEqual(load_settings().chat_id,'-100123'); self.assertEqual(g.my_id,-100123)

    def test_success_capture_unique_ids(self):
        ids=[]
        for _ in range(2):
            worker=CaptureThread(self.event()); worker.finished_signal.connect(lambda payload:ids.append(payload.photoid))
            with patch.object(worker,'pause',return_value=False), patch('threads.action_threads.pressing_key'), patch('threads.action_threads.capture_image'):
                worker.run()
        self.assertEqual(len(set(ids)),2)

    def test_capture_stop_no_keyboard_or_image(self):
        worker=CaptureThread(self.event()); worker.stop()
        with patch('threads.action_threads.pressing_key') as key, patch('threads.action_threads.capture_image') as shot:
            worker.run()
        key.assert_not_called(); shot.assert_not_called()

    def test_cleanup_keeps_unsent_screenshot(self):
        from core.helpers import cleanup
        with tempfile.TemporaryDirectory() as d:
            photo=Path(d)/'screenshot_unsent.png'; photo.write_bytes(b'fake')
            with patch('core.helpers.SCREENSHOTS_DIR',d), patch('core.helpers.g.main_window',None): cleanup()
            self.assertTrue(photo.exists())

    def test_tray_creation_and_bounded_retries(self):
        # Execute actual method bodies with lightweight Qt doubles; GUI smoke is separate.
        file=Path(__file__).parents[1]/'ui'/'setup_window.py'
        tree=ast.parse(file.read_text(encoding='utf-8')); cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('_setup_tray','_exit_from_tray','_ensure_tray_if_needed')]
        ns={n:MagicMock() for n in ('QSystemTrayIcon','QIcon','QMenu','QAction','QTimer','load_settings','set_taskbar_hidden')}
        ns['QIcon'].return_value.isNull.return_value=False
        ns.update(os=__import__('os'),resource_path=lambda _:str(file))
        exec(compile(ast.Module(body=methods,type_ignores=[]),str(file),'exec'),ns)
        dummy=types.SimpleNamespace(tray_icon=None,tray_menu=None,_closing=False,_tray_retry_count=0,
            _restore_from_tray=lambda:None,_exit_from_tray=lambda:None,_tray_activated=lambda _:None)
        self.assertTrue(ns['_setup_tray'](dummy)); self.assertIsNotNone(dummy.tray_icon)
        self.assertIn('_exit_from_tray',ns)
        dummy.apply_taskbar_mode=lambda _:False; dummy.tray_icon=None; dummy._ensure_tray_if_needed=lambda:None
        for _ in range(10): ns['_ensure_tray_if_needed'](dummy)
        self.assertEqual(ns['QTimer'].singleShot.call_count,5)

    def test_unavailable_tray_preserves_taskbar(self):
        file=Path(__file__).parents[1]/'ui'/'setup_window.py'
        cls=next(n for n in ast.parse(file.read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='apply_taskbar_mode')
        ns={'set_taskbar_hidden':MagicMock()}
        exec(compile(ast.Module(body=[method],type_ignores=[]),str(file),'exec'),ns)
        dummy=types.SimpleNamespace(_closing=False,_setup_tray=lambda:False)
        self.assertFalse(ns['apply_taskbar_mode'](dummy,True)); ns['set_taskbar_hidden'].assert_called_once_with(dummy,False)


