import unittest

from app.application.ports.slot import Slot


class SlotTests(unittest.TestCase):
    def test_factory_runs_once_on_first_use(self):
        calls = []
        slot = Slot()
        slot.provide(lambda: calls.append(1) or "구현")
        self.assertEqual(calls, [])
        self.assertEqual(slot(), "구현")
        self.assertEqual(slot(), "구현")
        self.assertEqual(calls, [1])

    def test_configure_replaces_factory(self):
        slot = Slot()
        slot.provide(lambda: "구현")
        slot.configure("대역")
        self.assertEqual(slot(), "대역")

    def test_provide_replaces_configured_value(self):
        slot = Slot()
        slot.configure("대역")
        slot.provide(lambda: "구현")
        self.assertEqual(slot(), "구현")
