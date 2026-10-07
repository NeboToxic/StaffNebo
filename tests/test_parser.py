import unittest

from domain.events import PunishmentType
from domain.parser import parse_moderation_line


class ParserTests(unittest.TestCase):
    def test_mute_with_tag(self):
        line = (
            '[12:34:56] 㰳 ADMIN Helper MyNick [Staff] замутил игрока BadGuy ┃ tag123 '
            'по причине: флуд в чате'
        )
        event = parse_moderation_line(line, 'MyNick')
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, PunishmentType.MUTE)
        self.assertTrue(event.needs_screenshot)
        self.assertIn('<code>MyNick</code>', event.moderator_html)
        self.assertIn('<code>tag123</code>', event.target_html)
        self.assertEqual(event.reason, 'флуд в чате')

    def test_warn_without_tag(self):
        line = (
            '[01:02:03] MOD Helper MyNick предупредил игрока PlayerOne '
            'по причине: токсик.'
        )
        event = parse_moderation_line(line, 'MyNick')
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, PunishmentType.WARN)
        self.assertEqual(event.target_html, '<code>PlayerOne</code>')
        self.assertEqual(event.reason, 'токсик.')

    def test_kick(self):
        line = (
            '[23:59:01] 㰳 ADMIN Helper MyNick кикнул игрока Cheater ┃ xyz '
            'по причине: читы'
        )
        event = parse_moderation_line(line, 'MyNick')
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, PunishmentType.KICK)
        self.assertFalse(event.needs_screenshot)
        self.assertIsNotNone(event.dating)
        self.assertIsNotNone(event.timing)

    def test_other_moderator_ignored(self):
        line = (
            '[12:00:00] 㰳 ADMIN Helper OtherNick замутил игрока BadGuy '
            'по причине: тест'
        )
        self.assertIsNone(parse_moderation_line(line, 'MyNick'))

    def test_empty_inputs(self):
        self.assertIsNone(parse_moderation_line('', 'MyNick'))
        self.assertIsNone(parse_moderation_line('something', ''))


if __name__ == '__main__':
    unittest.main()
