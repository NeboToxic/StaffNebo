import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from core.database import connect,set_meta
from core.settings import AppSettings,load_settings,save_settings,clear_saved_secrets
from core import profiles,history
from core.secrets import protect,reveal
from domain.events import PunishmentType,ModerationEvent
from domain.notifier import SendPayload
from domain.templates import validate_template,render_template
from domain.capture import capture_image
from threads.delivery import DeliveryThread
from services.connections import check_connection
from services.updates import check_update,download_update
from services.diagnostics import export_diagnostics


def response(data,status=200):
    r=MagicMock();r.status_code=status;r.json.return_value=data;r.__enter__.return_value=r;return r


class FeatureTests(unittest.TestCase):
    def setUp(self):
        profiles.init_profiles();history.init_history()
        with connect() as conn:conn.execute('DELETE FROM events');conn.execute('DELETE FROM profiles')
        set_meta('active_profile','')
        self.cfg=AppSettings(nick='Moderator',bot_id='123456:private-secret',chat_id='-100123',
                             vk_token='vk-secret-long',vk_user_id='99',retain_screenshots=True)
        save_settings(self.cfg);profiles.ensure_default()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def payload(self,reason='reason',photo=False):
        return SendPayload(PunishmentType.MUTE,self.cfg.chat_id,'<code>Mod</code>','<code>Player</code>',reason,'09.10.2026','12:00:00',needs_photo=photo)
    def event(self,reason='reason',photo=False):return history.create_event(self.payload(reason,photo),self.cfg)

    def test_dpapi_roundtrip_ciphertext_and_database(self):
        value=protect('test-secret');self.assertTrue(value.startswith('dpapi:v1:'));self.assertEqual(reveal(value),'test-secret')
        with connect() as conn:row=conn.execute('SELECT bot_id,vk_token FROM settings').fetchone()
        self.assertNotIn('private-secret',row['bot_id']);self.assertTrue(row['vk_token'].startswith('dpapi:v1:'))
        self.assertEqual(load_settings().bot_id,self.cfg.bot_id)

    def test_plaintext_migration(self):
        with connect() as conn:conn.execute('UPDATE settings SET bot_id=? WHERE id=1',('123456:legacy-token',))
        self.assertEqual(load_settings().bot_id,'123456:legacy-token')
        with connect() as conn:stored=conn.execute('SELECT bot_id FROM settings').fetchone()[0]
        self.assertTrue(stored.startswith('dpapi:v1:'))

    def test_locked_secret_is_preserved_until_explicit_delete(self):
        with connect() as conn:conn.execute('UPDATE settings SET bot_id=? WHERE id=1',('dpapi:v1:invalid',))
        cfg=load_settings();self.assertEqual(cfg.bot_id,'');cfg.theme='Небо';save_settings(cfg)
        with connect() as conn:self.assertEqual(conn.execute('SELECT bot_id FROM settings').fetchone()[0],'dpapi:v1:invalid')
        clear_saved_secrets();self.assertEqual(load_settings().bot_id,'')

    def test_profiles_switch_independent_preferences(self):
        key=profiles.save_profile('Другой сервер',AppSettings(nick='Other',chat_id='77',notification_template='{target}',photo_mute=False))
        profiles.activate(key);cfg=load_settings();self.assertEqual(cfg.nick,'Other');self.assertFalse(cfg.photo_mute);self.assertEqual(cfg.notification_template,'{target}')
        cfg.capture_mode='monitor';save_settings(cfg);self.assertEqual(profiles.load_profile(key)[1].capture_mode,'monitor')

    def test_delete_active_profile_rejected(self):
        with self.assertRaises(ValueError):profiles.delete_profile(profiles.list_profiles()[0]['id'])

    def test_profile_and_history_snapshots_have_no_plaintext_secrets(self):
        key=self.event();row=history.get_event(key)
        with connect() as conn:profile=conn.execute('SELECT settings_json FROM profiles').fetchone()[0]
        for text in (profile,row['settings_json'],row['payload_json']):
            self.assertNotIn('private-secret',text);self.assertNotIn('vk-secret-long',text)
        self.assertEqual(history.event_settings(row).vk_token,self.cfg.vk_token)

    def test_history_search_filters_and_csv_formula_safety(self):
        first=self.event('=HYPERLINK("example")');second=self.event('spam')
        history.finish(second,True)
        self.assertEqual(len(history.list_events(query='spam',status='sent')),1)
        self.assertEqual(history.list_events(query='%'),[])
        file=self.root/'history.csv';count=history.export_csv(file,status='pending');self.assertEqual(count,1)
        rows=list(csv.DictReader(file.open(encoding='utf-8-sig')));self.assertTrue(rows[0]['reason'].startswith("'="))

    def test_restart_recovers_sending_and_claim_is_atomic(self):
        key=self.event();self.assertTrue(history.claim(key));self.assertFalse(history.claim(key))
        history.recover_interrupted();self.assertEqual(history.get_event(key)['status'],'pending');self.assertTrue(history.claim(key))

    def test_outbox_success_preserves_recipient_snapshot(self):
        key=self.event();save_settings(AppSettings(bot_id='888888:new-secret',chat_id='200'))
        with patch('threads.delivery.TelegramNotifier.send_punishment',return_value=(True,'ok')) as send:
            DeliveryThread(key).run()
        payload=send.call_args.args[0];self.assertEqual(payload.user_id,'-100123');self.assertEqual(payload.settings_override.bot_id,'123456:private-secret')
        self.assertEqual(history.get_event(key)['status'],'sent')
        with patch('threads.delivery.TelegramNotifier.send_punishment') as send:DeliveryThread(key).run()
        send.assert_not_called()

    def test_outbox_failure_retry_reuses_vk_id(self):
        self.cfg.platform='vk';key=self.event()
        with patch('threads.delivery.VkNotifier.send_punishment',return_value=(False,'offline')) as send:DeliveryThread(key).run();first=send.call_args.args[0].delivery_id
        with patch('threads.delivery.VkNotifier.send_punishment',return_value=(True,'ok')) as send:DeliveryThread(key).run();second=send.call_args.args[0].delivery_id
        self.assertEqual(first,second);self.assertEqual(history.get_event(key)['attempts'],2)

    def test_missing_photo_can_be_sent_explicitly_without_image(self):
        key=self.event(photo=True)
        with patch('threads.delivery.TelegramNotifier.send_punishment') as send:DeliveryThread(key).run()
        send.assert_not_called();self.assertEqual(history.get_event(key)['status'],'failed')
        with patch('threads.delivery.TelegramNotifier.send_punishment',return_value=(True,'ok')) as send:DeliveryThread(key,without_photo=True).run()
        self.assertFalse(send.call_args.args[0].needs_photo);self.assertFalse(json.loads(history.get_event(key)['payload_json'])['needs_photo'])

    def test_retry_may_adopt_corrected_recipient(self):
        key=self.event();cfg=AppSettings(bot_id='777777:correct',chat_id='999')
        history.replace_delivery_settings(key,cfg)
        with patch('threads.delivery.TelegramNotifier.send_punishment',return_value=(True,'ok')) as send:DeliveryThread(key).run()
        self.assertEqual(send.call_args.args[0].user_id,'999')

    def test_clearing_secrets_removes_all_snapshots(self):
        key=self.event();clear_saved_secrets()
        self.assertEqual(history.event_settings(history.get_event(key)).bot_id,'')
        self.assertEqual(profiles.load_profile(profiles.list_profiles()[0]['id'])[1].vk_token,'')

    def test_disabled_notification_is_still_recorded(self):
        from services.operation_queue import OperationQueue
        self.cfg.notify_mute=False;save_settings(self.cfg);queue=OperationQueue()
        queue.enqueue(ModerationEvent(PunishmentType.MUTE,'line','Mod','Bad','disabled test',True))
        self.assertEqual(history.list_events(query='disabled test')[0]['status'],'disabled');self.assertEqual(queue._queue,[])

    def test_statistics_survive_reload(self):
        key=self.event();history.claim(key);history.finish(key,True)
        self.event('spam');self.assertEqual(history.statistics()['day']['mute'],2)
        self.assertEqual(history.statistics()['week']['success_rate'],100)
        history.init_history();self.assertEqual(history.statistics()['day']['mute'],2)

    def test_template_variables_validation_and_html(self):
        self.cfg.notification_template='{target}: {reason} ({profile})'
        text=render_template(self.payload('<test>&'),self.cfg,True)
        self.assertEqual(text,'Player: &lt;test&gt;&amp; (Moderator)')
        for template in ('{target.__class__}','{unknown}','{reason!r}','{reason:20}'):
            with self.assertRaises(ValueError):validate_template(template)

    def test_selected_monitor_and_window_region(self):
        self.cfg.capture_mode='monitor';self.cfg.capture_monitor=1
        with patch('domain.capture.monitors',return_value=[(0,0,100,100),(-100,0,0,100)]),patch('domain.capture.ImageGrab.grab') as grab:capture_image(self.cfg)
        grab.assert_called_once_with(bbox=(-100,0,0,100),all_screens=True)
        self.cfg.capture_mode='window';self.cfg.capture_window_title='Missing'
        with patch('domain.capture.windows',return_value=[]):
            with self.assertRaises(RuntimeError):capture_image(self.cfg)

    def test_connection_vk_901_explained_without_token(self):
        self.cfg.platform='vk'
        with patch('services.connections.requests.post',return_value=response({'error':{'error_code':901,'error_msg':'permission'}})):
            ok,msg=check_connection(self.cfg)
        self.assertFalse(ok);self.assertIn('Проверьте VK ID',msg);self.assertNotIn(self.cfg.vk_token,msg)

    def test_connection_telegram_proxy_read_only(self):
        self.cfg.tg_proxy_type='http';self.cfg.tg_proxy_host='localhost';self.cfg.tg_proxy_port='3128'
        with patch('services.connections.requests.get',side_effect=[response({'ok':True,'result':{'id':1}}),response({'ok':True,'result':{'id':2}})]) as get:
            ok,msg=check_connection(self.cfg)
        self.assertTrue(ok);self.assertEqual(get.call_count,2);self.assertEqual(get.call_args.kwargs['proxies']['https'],'http://localhost:3128')

    def test_diagnostics_redacts_tokens_in_errors_and_reasons(self):
        key=self.event(self.cfg.bot_id);history.finish(key,False,'request '+self.cfg.vk_token)
        file=self.root/'diagnostics.json';export_diagnostics(file,{'running':True});text=file.read_text(encoding='utf-8')
        self.assertNotIn(self.cfg.bot_id,text);self.assertNotIn(self.cfg.vk_token,text);self.assertTrue(json.loads(text)['monitor']['running'])

    def update_info(self,content):
        asset={'name':'NeboProject-9.0.0-Windows.zip','size':len(content),'browser_download_url':'https://github.com/test/repo/releases/download/v9.0.0/NeboProject-9.0.0-Windows.zip'}
        return {'new':True,'asset':asset,'checksums':{'browser_download_url':'https://github.com/test/repo/releases/download/v9.0.0/SHA256SUMS.txt'}}
    def test_update_check_detects_new_and_rejects_external_asset(self):
        content=b'zip';info=self.update_info(content)
        release={'tag_name':'v9.0.0','assets':[info['asset'],dict(info['checksums'],name='SHA256SUMS.txt')]}
        with patch('services.updates.requests.get',return_value=response(release)):self.assertTrue(check_update('test/repo')['new'])
        release['assets'][0]['browser_download_url']='https://evil.test/file.zip'
        with patch('services.updates.requests.get',return_value=response(release)):
            with self.assertRaises(RuntimeError):check_update('test/repo')

    def test_update_verified_download_and_corruption(self):
        data=b'test-release';info=self.update_info(data);file=self.root/'update.zip'
        checksum=response({});checksum.text=hashlib.sha256(data).hexdigest()+'  '+info['asset']['name']
        download=response({});download.iter_content.return_value=[data]
        with patch('services.updates.requests.get',side_effect=[checksum,download]):download_update(info,file)
        self.assertEqual(file.read_bytes(),data)
        checksum.text='0'*64+'  '+info['asset']['name'];bad=self.root/'bad.zip'
        with patch('services.updates.requests.get',side_effect=[checksum,download]):
            with self.assertRaises(RuntimeError):download_update(info,bad)
        self.assertFalse(bad.exists());self.assertFalse(bad.with_name('bad.zip.part').exists())

    def test_update_cancel_preserves_existing_file(self):
        data=b'test-release';info=self.update_info(data);file=self.root/'existing.zip';file.write_bytes(b'old')
        checksum=response({});checksum.text=hashlib.sha256(data).hexdigest()+'  '+info['asset']['name']
        download=response({});download.iter_content.return_value=[data]
        with patch('services.updates.requests.get',side_effect=[checksum,download]):
            with self.assertRaises(RuntimeError):download_update(info,file,cancel=lambda:True)
        self.assertEqual(file.read_bytes(),b'old')
