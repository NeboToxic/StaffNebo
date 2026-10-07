import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from domain import worker_client


class _Response:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class WorkerClientTests(unittest.TestCase):
    def test_log_post_uses_secret_and_does_not_send_bot_tokens(self):
        response = _Response(200, '{"ok": true}')
        with patch("domain.worker_client.requests.post", return_value=response) as post:
            worker_client.send_tg_log("Блюститель: <code>Nick</code>")

        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], worker_client.WORKER_URL)
        self.assertEqual(kwargs["json"]["action"], "tg_log")
        self.assertEqual(kwargs["json"]["text"], "Блюститель: <code>Nick</code>")
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            f"Bearer {worker_client.APP_SECRET}",
        )
        body = str(kwargs["json"])
        self.assertNotIn("VK_TOKEN", body)
        self.assertNotIn("TELEGRAM_REDIR", body)

    def test_vk_text_post_has_peer_and_no_photo(self):
        response = _Response(200, '{"ok": true}')
        with patch("domain.worker_client.requests.post", return_value=response) as post:
            worker_client.send_vk_message("42", "мут")

        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["action"], "vk_message")
        self.assertEqual(kwargs["json"]["peer_id"], "42")
        self.assertEqual(kwargs["json"]["text"], "мут")
        self.assertNotIn("files", kwargs)

    def test_vk_photo_is_sent_as_file(self):
        response = _Response(200, '{"ok": true}')
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            handle.write(b"png")
            path = handle.name
        try:
            with patch("domain.worker_client.requests.post", return_value=response) as post:
                worker_client.send_vk_message("7", "скрин", path)
            _, kwargs = post.call_args
            self.assertEqual(kwargs["data"]["action"], "vk_message")
            self.assertEqual(kwargs["data"]["peer_id"], "7")
            self.assertIn("photo", kwargs["files"])
            self.assertNotIn("json", kwargs)
        finally:
            os.remove(path)

    def test_worker_error_is_raised(self):
        response = _Response(401, "unauthorized")
        with patch("domain.worker_client.requests.post", return_value=response):
            with self.assertRaises(RuntimeError) as caught:
                worker_client.send_tg_log("текст")
        self.assertIn("401", str(caught.exception))
        self.assertIn("unauthorized", str(caught.exception))


class NotifierTests(unittest.TestCase):
    def _payload(self, event_type, photoid="1"):
        from domain.events import PunishmentType
        from domain.notifier import SendPayload

        return SendPayload(
            event_type=event_type,
            user_id="100",
            moderator_html="<code>Mod</code>",
            target_html="<code>Bad</code>",
            reason="причина",
            dating="01.01.2026",
            timing="12:00:00",
            photoid=photoid,
        )

    def test_telegram_kick_sends_text_and_log_without_photo(self):
        from domain.events import PunishmentType
        from domain.notifier import TelegramNotifier

        bot = MagicMock()
        with patch("domain.notifier.g") as globals_mod, \
                patch("domain.notifier.telebot.TeleBot", return_value=bot), \
                patch("domain.notifier.send_tg_log") as log:
            globals_mod.bot_id = "1:token"
            ok, message = TelegramNotifier().send_punishment(self._payload(PunishmentType.KICK))

        self.assertTrue(ok)
        self.assertIn("Кик", message)
        bot.send_message.assert_called_once()
        bot.send_photo.assert_not_called()
        log.assert_called_once()
        self.assertEqual(bot.send_message.call_args[0][0], 100)

    def test_telegram_mute_sends_log_and_photo(self):
        from domain.events import PunishmentType
        from domain.notifier import TelegramNotifier

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            handle.write(b"png")
            path = handle.name
        bot = MagicMock()
        try:
            with patch("domain.notifier.screenshot_path", return_value=path), \
                    patch("domain.notifier.g") as globals_mod, \
                    patch("domain.notifier.telebot.TeleBot", return_value=bot), \
                    patch("domain.notifier.send_tg_log") as log:
                globals_mod.bot_id = "1:token"
                ok, _message = TelegramNotifier().send_punishment(self._payload(PunishmentType.MUTE))
            self.assertTrue(ok)
            log.assert_called_once()
            bot.send_photo.assert_called_once()
            self.assertFalse(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_vk_kick_does_not_attach_photo(self):
        from domain.events import PunishmentType
        from domain.notifier import VkNotifier

        with patch("domain.notifier.send_vk_message") as send:
            ok, message = VkNotifier().send_punishment(self._payload(PunishmentType.KICK), vk_user_id="55")
        self.assertTrue(ok)
        self.assertIn("Кик", message)
        peer_id, _text, photo = send.call_args[0]
        self.assertEqual(peer_id, "55")
        self.assertIsNone(photo)

    def test_vk_screenshot_failure_retries_three_times(self):
        from domain.notifier import VkNotifier

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            path = handle.name
        try:
            with patch("domain.notifier.send_vk_message", side_effect=RuntimeError("нет сети")) as send, \
                    patch("domain.notifier.tm.sleep"):
                ok, message = VkNotifier().send_screenshot(path, vk_user_id="9")
            self.assertFalse(ok)
            self.assertIn("нет сети", message)
            self.assertEqual(send.call_count, 3)
        finally:
            if os.path.exists(path):
                os.remove(path)


class QueueTests(unittest.TestCase):
    def _event(self, reason="флуд"):
        from domain.events import ModerationEvent, PunishmentType

        return ModerationEvent(
            event_type=PunishmentType.MUTE,
            line=f"line {reason}",
            moderator_html="<code>Mod</code>",
            target_html="<code>Bad</code>",
            reason=reason,
            needs_screenshot=True,
        )

    def test_duplicate_event_is_ignored(self):
        from services.operation_queue import OperationQueue

        queue = OperationQueue(processing_delay=0)
        queue._process_next = lambda: None
        event = self._event()
        queue.enqueue(event)
        queue.enqueue(event)
        self.assertEqual(len(queue._queue), 1)
        self.assertFalse(queue.is_busy)

    def test_different_reasons_are_both_queued(self):
        from services.operation_queue import OperationQueue

        queue = OperationQueue(processing_delay=0)
        queue._process_next = lambda: None
        queue.enqueue(self._event("флуд"))
        queue.enqueue(self._event("спам"))
        self.assertEqual(len(queue._queue), 2)


if __name__ == "__main__":
    unittest.main()
