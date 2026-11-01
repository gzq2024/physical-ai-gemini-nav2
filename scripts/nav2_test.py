"""Nav2単独の手動試験。AI APIは不要。座標設定後に実行。"""
import argparse
import time
from pathlib import Path
import rclpy
from nav2_simple_commander.robot_navigator import BasicNavigator,TaskResult
from robot_agent import make_pose
from logic import load_config

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--target',required=True,choices=['SHELF_A','SHELF_B'])
    p.add_argument('--config',default=str(Path(__file__).resolve().parents[1]/'config'/'destinations.json'))
    args=p.parse_args();cfg=load_config(args.config)
    rclpy.init();nav=BasicNavigator()
    try:
        if cfg.get('initial_pose'):
            nav.setInitialPose(make_pose(nav,cfg['frame_id'],cfg['initial_pose']))
        nav.waitUntilNav2Active()
        nav.goToPose(make_pose(nav,cfg['frame_id'],cfg['destinations'][args.target]))
        until=time.monotonic()+float(cfg['navigate_timeout_sec'])
        while not nav.isTaskComplete():
            if time.monotonic()>until:
                nav.cancelTask();print('timeout; cancellation requested')
                break
        result=nav.getResult()
        print('NAV RESULT:',result)
        return 0 if result==TaskResult.SUCCEEDED else 2
    finally:
        nav.destroy_node();rclpy.shutdown()
if __name__=='__main__':raise SystemExit(main())
