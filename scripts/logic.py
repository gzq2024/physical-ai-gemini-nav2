"""ROS 2 / SDKに依存しない入力検証。LLM出力は信頼しない。"""
import json
import math
from pathlib import Path

SHELVES = ('SHELF_A', 'SHELF_B')
STATES = ('available', 'blocked')

def initial_world(a='available', b='available'):
    return {'version': 1, 'SHELF_A': a, 'SHELF_B': b}

def validate_world(world):
    if not isinstance(world, dict) or not isinstance(world.get('version'), int) or world['version'] < 1:
        raise ValueError('world.version は1以上の整数にしてください')
    if any(world.get(s) not in STATES for s in SHELVES):
        raise ValueError('棚状態はavailable/blockedのいずれかです')
    return dict(world)

def parse_world_event(raw):
    return validate_world(json.loads(raw))

def update_world(world, target, status):
    validate_world(world)
    if target not in SHELVES or status not in STATES:
        raise ValueError('未定義の棚または状態')
    nxt = dict(world)
    nxt[target] = status
    nxt['version'] += 1
    return nxt

def parse_set_arg(text):
    name, sep, state = text.partition('=')
    if not sep or name not in SHELVES or state not in STATES:
        raise ValueError('--set SHELF_A=blocked の形式で指定')
    return name, state

def validate_tool_call(name, arguments, world):
    validate_world(world)
    if not isinstance(arguments, dict):
        raise ValueError('Function Callの引数はオブジェクト')
    if name == 'stop_task':
        return ('STOP', None)
    if name != 'start_navigation':
        raise ValueError(f'許可されていないツール: {name}')
    dest = arguments.get('destination')
    if dest not in SHELVES:
        raise ValueError(f'許可されていない配送先: {dest}')
    if world[dest] != 'available':
        raise ValueError(f'利用不可の配送先: {dest}')
    return ('NAVIGATE', dest)

def load_config(path, *, require_positions=True):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('frame_id') != 'map':
        raise ValueError('今回のMVPはframe_id=mapに限定')
    destinations = data.get('destinations', {})
    for shelf in SHELVES:
        pose = destinations.get(shelf)
        if not isinstance(pose, dict):
            raise ValueError(f'{shelf}の設定がありません')
        if require_positions:
            for key in ('x','y','yaw'):
                val = pose.get(key)
                if not isinstance(val,(int,float)) or isinstance(val,bool) or not math.isfinite(val):
                    raise ValueError(f'{shelf}.{key}未設定または数値が不正。RVizで確認して入力してください')
    for key in ('navigate_timeout_sec','cancel_timeout_sec','world_wait_sec','api_timeout_ms'):
        if float(data.get(key,0)) <= 0:
            raise ValueError(f'{key}は正の値が必要')
    if data.get('max_replans') != 1:
        raise ValueError('MVPはmax_replans=1固定')
    return data
