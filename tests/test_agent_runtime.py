"""ROS2/Geminiに接続せずAgentのT01/T02/T03制御順序を再現するモック試験。"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import robot_agent


class FakeResult:
    SUCCEEDED = 'SUCCEEDED'
    CANCELED = 'CANCELED'
    FAILED = 'FAILED'


class FakeNav:
    current_scenario = 'T01'

    def __init__(self):
        self.callback = None
        self.goal = None
        self.goal_ticks = 0
        self.canceled = False
        self.goal_history = []

    def create_subscription(self, _msg_type, _topic, callback, _qos):
        self.callback = callback
        return object()

    def destroy_subscription(self, _sub):
        pass

    def destroy_node(self):
        pass

    def waitUntilNav2Active(self):
        pass

    def goToPose(self, pose):
        self.goal = pose
        self.goal_history.append(pose)
        self.goal_ticks = 0
        self.canceled = False

    def isTaskComplete(self):
        if self.canceled:
            return True
        self.goal_ticks += 1
        if self.current_scenario == 'T02' and self.goal == 'SHELF_A':
            return False
        return self.goal_ticks >= 2

    def cancelTask(self):
        self.canceled = True

    def getResult(self):
        return FakeResult.CANCELED if self.canceled else FakeResult.SUCCEEDED


class FakeGemini:
    current_scenario = 'T01'

    def __init__(self, _cfg):
        pass

    def begin(self, _task, _world):
        if self.current_scenario == 'T03':
            return 'stop_task', {'reason': 'both unavailable'}, 'c1'
        return 'start_navigation', {'destination': 'SHELF_A'}, 'c1'

    def next_after_result(self, _name, _cid, result, *, expect_tool):
        if expect_tool:
            assert result['world']['SHELF_A'] == 'blocked'
            return 'start_navigation', {'destination': 'SHELF_B'}, 'c2'
        return 'AI summary'


class AgentRuntimeTests(unittest.TestCase):
    def simulate(self, case):
        FakeNav.current_scenario = case
        FakeGemini.current_scenario = case
        nav_holder = {}
        # Run uses rclpy, std_msgs and nav2 modules only when actually executing.
        rclpy = types.ModuleType('rclpy')
        rclpy.init = lambda: None
        rclpy.shutdown = lambda: None
        def fake_spin(nav, timeout_sec=0):
            if not hasattr(nav, 'initial_sent'):
                nav.initial_sent = True
                state = {'version': 1,
                         'SHELF_A': 'blocked' if case == 'T03' else 'available',
                         'SHELF_B': 'blocked' if case == 'T03' else 'available'}
                nav.callback(types.SimpleNamespace(data=json.dumps(state)))
            elif case == 'T02' and nav.goal == 'SHELF_A' and nav.goal_ticks >= 1 and not hasattr(nav, 'blocked_sent'):
                nav.blocked_sent = True
                state = {'version': 2, 'SHELF_A': 'blocked', 'SHELF_B': 'available'}
                nav.callback(types.SimpleNamespace(data=json.dumps(state)))
        rclpy.spin_once = fake_spin
        qos = types.ModuleType('rclpy.qos')
        qos.QoSProfile = lambda **kwargs: object()
        qos.DurabilityPolicy = types.SimpleNamespace(TRANSIENT_LOCAL=1)
        qos.ReliabilityPolicy = types.SimpleNamespace(RELIABLE=1)
        std_msgs = types.ModuleType('std_msgs')
        std_msgs_msg = types.ModuleType('std_msgs.msg')
        std_msgs_msg.String = type('String', (), {})
        std_msgs.msg = std_msgs_msg
        nav_pkg = types.ModuleType('nav2_simple_commander')
        nav_module = types.ModuleType('nav2_simple_commander.robot_navigator')
        def new_nav():
            nav = FakeNav()
            nav_holder['nav'] = nav
            return nav
        nav_module.BasicNavigator = new_nav
        nav_module.TaskResult = FakeResult
        modules = {'rclpy': rclpy, 'rclpy.qos': qos,
                   'std_msgs': std_msgs, 'std_msgs.msg': std_msgs_msg,
                   'nav2_simple_commander': nav_pkg,
                   'nav2_simple_commander.robot_navigator': nav_module}
        config = {'initial_pose': None, 'frame_id': 'map',
                  'world_wait_sec': 2, 'navigate_timeout_sec': 150,
                  'cancel_timeout_sec': 2, 'max_replans': 1,
                  'destinations': {'SHELF_A': {'x': 1, 'y': 1, 'yaw': 0},
                                   'SHELF_B': {'x': -1, 'y': 1, 'yaw': 0}}}
        with tempfile.TemporaryDirectory() as td, \
                patch.dict(sys.modules, modules), \
                patch.object(robot_agent, 'ROOT', Path(td)), \
                patch.object(robot_agent, 'GeminiCalls', FakeGemini), \
                patch.object(robot_agent, 'make_pose', lambda nav, frame, coords: 'SHELF_A' if coords['x'] > 0 else 'SHELF_B'), \
                contextlib.redirect_stdout(io.StringIO()):
            exitcode = robot_agent.run(config, 'test task')
            logs = [json.loads(line) for line in (Path(td) / 'logs' / 'events_v4.jsonl').read_text().splitlines()]
        return exitcode, logs, nav_holder['nav']

    def test_t01_arrives_at_shelf_a(self):
        rc, events, nav = self.simulate('T01')
        self.assertEqual(rc, 0)
        self.assertEqual(nav.goal_history, ['SHELF_A'])
        self.assertIn('TASK_SUCCEEDED', [e['type'] for e in events])

    def test_t02_cancel_before_shelf_b_replan(self):
        rc, events, nav = self.simulate('T02')
        self.assertEqual(rc, 0)
        self.assertEqual(nav.goal_history, ['SHELF_A', 'SHELF_B'])
        kinds = [e['type'] for e in events]
        for k in ['TARGET_UNAVAILABLE', 'CANCEL_REQUEST', 'CANCEL_TERMINAL', 'TASK_SUCCEEDED']:
            self.assertIn(k, kinds)
        self.assertLess(kinds.index('CANCEL_TERMINAL'), kinds.index('TASK_SUCCEEDED'))
        self.assertEqual([e['destination'] for e in events if e['type'] == 'NAV_START'], ['SHELF_A', 'SHELF_B'])

    def test_t03_stops_without_nav_goal(self):
        rc, events, nav = self.simulate('T03')
        self.assertEqual(rc, 0)
        self.assertEqual(nav.goal_history, [])
        kinds = [e['type'] for e in events]
        self.assertIn('TASK_STOPPED', kinds)
        self.assertNotIn('NAV_START', kinds)


if __name__ == '__main__':
    unittest.main()
