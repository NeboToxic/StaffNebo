import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from domain import worker_client
from domain.notifier import TelegramNotifier, VkNotifier, SendPayload, build_telegram_user_text, build_vk_text
from domain.events import PunishmentType
from core.settings import AppSettings


def response(value, status=200):
    r = MagicMock(); r.status_code = status; r.json.return_value = value
    return r


class WorkerClientTests(unittest.TestCase):
    def test_vk_text_direct_api(self):
        session = MagicMock(); session.post.return_value = response({'response': 42})
        with patch('domain.worker_client.requests.Session', return_value=session):
            self.assertEqual(worker_client.send_vk_message('token', '9', 'text', random_id=123), 42)
        args, kw = session.post.call_args
        self.assertEqual(args[0], worker_client.VK_API + 'messages.send')
        self.assertEqual(kw['data']['access_token'], 'token')
        self.assertEqual(kw['data']['random_id'], 123)
        self.assertEqual(kw['data']['peer_id'], '9')
        session.close.assert_called_once()

    def test_vk_photo_upload_and_attachment(self):
        session = MagicMock()
        session.post.side_effect = [response({'response': {'upload_url': 'https://upload.test'}}),
            response({'photo': 'photo-json', 'server': 1, 'hash': 'hash'}),
            response({'response': [{'id': 2, 'owner_id': 3}]}), response({'response': 44})]
        with tempfile.TemporaryDirectory() as d:
            photo = Path(d)/'photo.png'; photo.write_bytes(b'fake')
            with patch('domain.worker_client.requests.Session', return_value=session):
                self.assertEqual(worker_client.send_vk_message('token','9','text',str(photo),random_id=77),44)
        self.assertIn('photo', session.post.call_args_list[1].kwargs['files'])
        self.assertEqual(session.post.call_args_list[3].kwargs['data']['attachment'],'photo3_2')

    def test_vk_api_error(self):
        session=MagicMock(); session.post.return_value=response({'error': {'error_code': 5}})
        with patch('domain.worker_client.requests.Session', return_value=session):
            with self.assertRaises(RuntimeError): worker_client.send_vk_message('token','9','text')
        session.close.assert_called_once()

    def test_missing_token_or_peer(self):
        for token, peer in [('', '9'), ('token', '')]:
            with self.assertRaises(RuntimeError): worker_client.send_vk_message(token,peer,'text')


class NotifierTests(unittest.TestCase):
    def setUp(self):
        self.settings = AppSettings(bot_id='123456:secret', chat_id='-100123', vk_token='vk-secret',retain_screenshots=False)
        self.patchers = [patch('domain.notifier.load_settings', return_value=self.settings),
            patch('domain.notifier.g.bot_id', self.settings.bot_id),
            patch('domain.notifier._pause', return_value=False)]
        for p in self.patchers: p.start(); self.addCleanup(p.stop)

    def payload(self, kind=PunishmentType.KICK, reason='test'):
        return SendPayload(kind,'-100123','<code>Mod</code>','<code>Bad</code>',reason,'09.10.2026','12:00:00','1')

    def test_telegram_kick_direct_text(self):
        with patch('domain.notifier.requests.post', return_value=response({'ok': True})) as post:
            ok,_=TelegramNotifier().send_punishment(self.payload())
        self.assertTrue(ok); self.assertEqual(post.call_count,1)
        self.assertTrue(post.call_args.args[0].endswith('/sendMessage'))
        self.assertEqual(post.call_args.kwargs['data']['chat_id'],-100123)
        self.assertIn('timeout', post.call_args.kwargs)

    def test_telegram_mute_photo_deleted_on_success(self):
        with tempfile.TemporaryDirectory() as d:
            photo=Path(d)/'photo.png'; photo.write_bytes(b'fake')
            with patch('domain.notifier.screenshot_path',return_value=str(photo)), patch('domain.notifier.requests.post',return_value=response({'ok':True})) as post:
                ok,_=TelegramNotifier().send_punishment(self.payload(PunishmentType.MUTE))
            self.assertTrue(ok); self.assertFalse(photo.exists())
            self.assertIn('photo',post.call_args.kwargs['files'])

    def test_telegram_failure_preserves_file_and_redacts_token(self):
        with tempfile.TemporaryDirectory() as d:
            photo=Path(d)/'photo.png'; photo.write_bytes(b'fake')
            with patch('domain.notifier.screenshot_path',return_value=str(photo)), patch('domain.notifier.requests.post',side_effect=RuntimeError('URL bot123456:secret/sendPhoto')):
                ok,message=TelegramNotifier().send_punishment(self.payload(PunishmentType.MUTE))
            self.assertFalse(ok); self.assertTrue(photo.exists()); self.assertNotIn('123456:secret',message)

    def test_delete_failure_does_not_resend(self):
        with patch('domain.notifier._send_telegram_photo') as send, patch('domain.notifier.os.remove',side_effect=PermissionError()):
            ok,_=TelegramNotifier().send_punishment(self.payload(PunishmentType.MUTE))
        self.assertTrue(ok); self.assertEqual(send.call_count,1)

    def test_long_reason_uses_plain_chunks_and_photo_only_once(self):
        with patch('domain.notifier._send_telegram_photo') as photo, patch('domain.notifier._send_telegram_text') as text:
            ok,_=TelegramNotifier().send_punishment(self.payload(PunishmentType.MUTE,'a<&'*3000))
        self.assertTrue(ok); self.assertEqual(photo.call_count,1)
        self.assertGreater(text.call_count,1)
        self.assertTrue(all(len(c.args[2])<=4000 and c.kwargs['parse_mode'] is None for c in text.call_args_list))

    def test_long_reason_text_retry_does_not_repeat_confirmed_photo(self):
        with patch('domain.notifier._send_telegram_photo') as photo, patch('domain.notifier._send_telegram_text',side_effect=[RuntimeError('offline'), None]) as text:
            ok,_=TelegramNotifier().send_punishment(self.payload(PunishmentType.MUTE,'x'*1500))
        self.assertTrue(ok); self.assertEqual(photo.call_count,1); self.assertEqual(text.call_count,2)

    def test_html_escaped_vk_plain(self):
        payload=self.payload(reason='<tag> & text')
        self.assertIn('&lt;tag&gt; &amp; text',build_telegram_user_text(payload))
        self.assertIn('<tag> & text',build_vk_text(payload))

    def test_vk_kick_and_stable_retry_id(self):
        with patch('domain.notifier.send_vk_message',side_effect=[RuntimeError('timeout'),42]) as send:
            ok,_=VkNotifier().send_punishment(self.payload(),'9')
        self.assertTrue(ok)
        self.assertEqual(send.call_args.args[:2],('vk-secret','9'))
        self.assertIsNone(send.call_args.args[3])
        ids=[c.kwargs['random_id'] for c in send.call_args_list]
        self.assertEqual(ids[0],ids[1]); self.assertTrue(0<ids[0]<2**31)

    def test_vk_screenshot_three_attempts_preserves_file(self):
        with tempfile.TemporaryDirectory() as d:
            photo=Path(d)/'photo.png'; photo.write_bytes(b'fake')
            with patch('domain.notifier.send_vk_message',side_effect=RuntimeError('offline')) as send:
                ok,_=VkNotifier().send_screenshot(str(photo),'9')
            self.assertFalse(ok); self.assertEqual(send.call_count,3); self.assertTrue(photo.exists())
            self.assertEqual(len({c.kwargs['random_id'] for c in send.call_args_list}),1)

    def test_cancellation_does_not_send(self):
        with patch('domain.notifier.requests.post') as tg, patch('domain.notifier.send_vk_message') as vk:
            self.assertFalse(TelegramNotifier().send_punishment(self.payload(),should_stop=lambda:True)[0])
            self.assertFalse(VkNotifier().send_punishment(self.payload(),should_stop=lambda:True)[0])
        tg.assert_not_called(); vk.assert_not_called()
