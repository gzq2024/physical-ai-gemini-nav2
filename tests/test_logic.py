import json
import tempfile
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from logic import initial_world,update_world,validate_tool_call,parse_world_event,parse_set_arg,load_config

class LogicTests(unittest.TestCase):
    def test_t01_initial(self):
        w=initial_world();self.assertEqual(validate_tool_call('start_navigation',{'destination':'SHELF_A'},w),('NAVIGATE','SHELF_A'))
    def test_t02_change(self):
        w=update_world(initial_world(),'SHELF_A','blocked')
        self.assertEqual(w['version'],2)
        with self.assertRaises(ValueError):validate_tool_call('start_navigation',{'destination':'SHELF_A'},w)
        self.assertEqual(validate_tool_call('start_navigation',{'destination':'SHELF_B'},w)[1],'SHELF_B')
    def test_t03_stop(self):
        w=initial_world('blocked','blocked')
        self.assertEqual(validate_tool_call('stop_task',{'reason':'none'},w)[0],'STOP')
    def test_unapproved_tool(self):
        with self.assertRaises(ValueError):validate_tool_call('publish_cmd_vel',{},initial_world())
    def test_bad_json(self):
        with self.assertRaises(ValueError):parse_world_event('{}')
    def test_bad_event(self):
        with self.assertRaises(ValueError):parse_set_arg('SHELF_C=blocked')
    def test_good_event(self):
        self.assertEqual(parse_set_arg('SHELF_A=blocked'),('SHELF_A','blocked'))
    def test_snapshot(self):
        w=initial_world();self.assertEqual(parse_world_event(json.dumps(w)),w)
    @staticmethod
    def _config_data():
        # Use an independent fixture: user's 10/28 coordinates must not affect unit tests.
        return {
            'frame_id': 'map', 'initial_pose': None,
            'destinations': {
                'SHELF_A': {'x': None, 'y': None, 'yaw': 0.0},
                'SHELF_B': {'x': None, 'y': None, 'yaw': 0.0},
            },
            'navigate_timeout_sec': 150, 'cancel_timeout_sec': 10,
            'world_wait_sec': 12, 'max_replans': 1,
            'api_timeout_ms': 30000,
            'gemini_model': 'gemini-robotics-er-2-preview',
        }

    def _load_fixture(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'destinations.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            return load_config(path)

    def test_unset_coords(self):
        with self.assertRaises(ValueError):
            self._load_fixture(self._config_data())

    def test_configured_coords_are_accepted(self):
        data = self._config_data()
        data['destinations']['SHELF_A'].update(x=1.2, y=0.8)
        data['destinations']['SHELF_B'].update(x=-1.1, y=1.3)
        actual = self._load_fixture(data)
        self.assertEqual(actual['destinations']['SHELF_A']['x'], 1.2)
    def test_rejected_unknown_target(self):
        with self.assertRaises(ValueError):validate_tool_call('start_navigation',{'destination':'NONE'},initial_world())
if __name__=='__main__':unittest.main()
