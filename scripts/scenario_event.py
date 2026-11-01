"""棚状態の唯一の発行主体。ROS 2 Topicで初期スナップショットと変更を配信する。

Terminal B: python3 scripts/scenario_event.py --server
Terminal D: python3 scripts/scenario_event.py --set SHELF_A=blocked
"""
import argparse
import json
import time
import rclpy
from std_msgs.msg import String
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from logic import initial_world, parse_set_arg, update_world, validate_world

STATE_TOPIC='/shelf_state'
COMMAND_TOPIC='/shelf_state_command'

def run_server(args):
    rclpy.init()
    node=rclpy.create_node('shelf_scenario_server')
    qos=QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                   durability=DurabilityPolicy.TRANSIENT_LOCAL)
    state_pub=node.create_publisher(String, STATE_TOPIC, qos)
    world=initial_world(args.initial_a,args.initial_b)
    def emit():
        msg=String();msg.data=json.dumps(world,ensure_ascii=False)
        state_pub.publish(msg)
        node.get_logger().info('STATE '+msg.data)
    def command(msg):
        nonlocal world
        try:
            name,status=parse_set_arg(msg.data)
            world=update_world(world,name,status)
            emit()
        except ValueError as exc:
            node.get_logger().error(str(exc))
    sub=node.create_subscription(String,COMMAND_TOPIC,command,10)
    timer=node.create_timer(1.0,emit)  # 再配信; state保持はこのプロセスが行う
    emit()
    print('SERVER READY: 変更操作は別ターミナルで --set SHELF_A=blocked')
    try:rclpy.spin(node)
    finally:
        node.destroy_node();rclpy.shutdown()

def publish_command(value):
    parse_set_arg(value)
    rclpy.init()
    node=rclpy.create_node('shelf_scenario_command')
    pub=node.create_publisher(String,COMMAND_TOPIC,10)
    try:
        deadline=time.monotonic()+5
        while pub.get_subscription_count()==0 and time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=0.1)
        if pub.get_subscription_count()==0:
            raise RuntimeError('Scenario Serverが起動していません。--serverを先に実行')
        msg=String();msg.data=value;pub.publish(msg)
        rclpy.spin_once(node,timeout_sec=0.5)
        time.sleep(0.3)
        print('UPDATE SENT:',value,'（サーバー側のSTATEログも確認）')
    finally:
        node.destroy_node();rclpy.shutdown()

def main():
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--server',action='store_true')
    group.add_argument('--set',dest='set_value',metavar='SHELF_A=blocked')
    p.add_argument('--initial-a',choices=['available','blocked'],default='available')
    p.add_argument('--initial-b',choices=['available','blocked'],default='available')
    a=p.parse_args()
    if a.server:run_server(a)
    else:publish_command(a.set_value)
if __name__=='__main__':main()
