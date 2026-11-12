"""SAM | 2026-10-13 09:06 +08:00 | Verify CAT1 release gates because bad inputs must preserve the previous usable set."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cat1_release import prepare


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        # SAM | 2026-10-13 09:07 +08:00 | Keep test fixtures inside the writable workspace because host TEMP is restricted.
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / 'tmp')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / 'Air780EGH'
        (self.source / 'soc').mkdir(parents=True)
        (self.source / 'soc/LuatOS-SoC_V2052_Air780EGH_113.soc').write_bytes(b'soc')
        (self.source / 'sample-6s.mp3').write_bytes(b'audio')
        (self.source / 'main.lua').write_text('local a = 1\n', encoding='utf-8')
        self.releases = root / 'releases'
        self.state = root / 'state'

    def test_repeat_change_and_existing_release_tamper(self):
        first = prepare(self.source, self.releases, self.state)
        self.assertEqual(first['release_directory'], prepare(self.source, self.releases, self.state)['release_directory'])
        (self.source / 'main.lua').write_text('local a = 2\n', encoding='utf-8')
        second = prepare(self.source, self.releases, self.state)
        self.assertNotEqual(first['release_directory'], second['release_directory'])
        self.assertEqual(second['changes_since_previous_ready']['changed'], ['main.lua'])
        (Path(second['release_directory']) / 'main.lua').write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'immutable release differs'):
            prepare(self.source, self.releases, self.state)

    def test_invalid_lua_and_size_keep_previous_pointer(self):
        first = prepare(self.source, self.releases, self.state)
        pointer = (self.state / 'latest_ready.json').read_bytes()
        (self.source / 'main.lua').write_text('local =\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Lua syntax'):
            prepare(self.source, self.releases, self.state)
        self.assertEqual(pointer, (self.state / 'latest_ready.json').read_bytes())
        (self.source / 'main.lua').write_text('local a = 2\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'size exceeds'):
            prepare(self.source, self.releases, self.state, capacity=20, reserve=10)
        self.assertEqual(pointer, (self.state / 'latest_ready.json').read_bytes())
        self.assertTrue(Path(first['release_directory']).exists())


if __name__ == '__main__':
    unittest.main()
