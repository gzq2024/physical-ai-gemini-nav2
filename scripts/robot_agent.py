"""Gemini ER 2 Function Calling <-> ROS 2/Nav2 の最小接続アプリ。

ROS 2: initial shelf snapshot -> request AI -> nav goal -> event triggers cancellation
-> tool result to Gemini -> new nav goal -> result to Gemini -> user output.
モデルはツールの「選択」のみを行う。実行・検証・停止はローカル実装。
"""
import argparse
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from logic import load_config, parse_world_event, validate_tool_call, validate_world

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_TASK='棚Aへ移動してください。移動中に棚Aが使えなくなれば、利用できる別の棚へ変更してください。'

def check_sdk_compatibility(version_text):
    """Interactions APIの2026-06以降のSDK major versionを検査する。"""
    try:
        major=int(version_text.split('.',1)[0])
    except (ValueError, AttributeError, TypeError):
        return False
    return major >= 2


def current_sdk_version():
    try:
        sdk_version=distribution_version('google-genai')
    except PackageNotFoundError as exc:
        raise RuntimeError('google-genai未導入です: python -m pip install -r requirements.txt') from exc
    if not check_sdk_compatibility(sdk_version):
        raise RuntimeError(
            f'google-genai {sdk_version} は旧Interactions APIです。'
            ' /workspace/requirements.txt の google-genai==2.33.0 を適用し、'
            'python -m pip install --upgrade -r requirements.txt を実行してください。'
        )
    return sdk_version


TOOLS=[
    {'type':'function','name':'start_navigation',
     'description':'指定した利用可能な棚へナビゲーションを開始する。到着したことは意味しない。',
     'parameters':{'type':'object','properties':{
         'destination':{'type':'string','enum':['SHELF_A','SHELF_B']}},
         'required':['destination']}},
    {'type':'function','name':'stop_task',
     'description':'利用可能な配送先がない場合、タスクを終了する。',
     'parameters':{'type':'object','properties':{'reason':{'type':'string'}},'required':['reason']}}
]

def client_for(cfg):
    key=os.environ.get('GEMINI_API_KEY')
    if not key:raise RuntimeError('GEMINI_API_KEY未設定（公開リポジトリへ保存禁止）')
    current_sdk_version()  # 旧SDKのHTTP 400をAPIリクエスト前に検知
    from google import genai
    from google.genai import types
    return genai.Client(api_key=key,http_options=types.HttpOptions(timeout=int(cfg['api_timeout_ms'])))

class GeminiCalls:
    def __init__(self,cfg):
        self.client=client_for(cfg)
        self.model=cfg['gemini_model']
        self.interaction=None
    def _extract(self, interaction):
        # Interactions API SDK v2: response.outputs ではなく response.steps
        calls=[s for s in interaction.steps if getattr(s,'type',None)=='function_call']
        if len(calls)!=1:
            raise RuntimeError(f'Function Callは1件必須: {len(calls)}件 / text={getattr(interaction,"output_text","")}')
        step=calls[0]
        if step.name not in ('start_navigation','stop_task'):
            raise RuntimeError('未許可のFunction Call: '+str(step.name))
        self.interaction=interaction
        args=step.arguments
        if hasattr(args,'model_dump'):args=args.model_dump()
        if not isinstance(args,dict):raise RuntimeError('Function Call引数がdictでない')
        return step.name,args,str(step.id)
    def begin(self,task,world):
        prompt=(
            'あなたはNav2移動ロボットの高レベルの計画者です。ローカル制御はツール実装が行います。'
            '初期状態は棚A優先、棚Aが利用不可なら棚B。利用可能な棚がなければstop_task。'
            '指定可能な行先はSHELF_AとSHELF_Bのみです。'
            'start_navigationは移動開始要求であり完了を意味しません。'
            '必ずツールを1つだけ呼んでください。\n'
            f'ユーザー指示: {task}\n現在の棚状態: {json.dumps(world,ensure_ascii=False)}'
        )
        res=self.client.interactions.create(
            model=self.model,
            input=[{'type':'user_input','content':[{'type':'text','text':prompt}]}],
            tools=TOOLS, generation_config={'thinking_level':'low'})
        return self._extract(res)
    def next_after_result(self, prior_name,call_id,result,*,expect_tool):
        if self.interaction is None:raise RuntimeError('前回interactionがありません')
        # v2仕様: step.idをcall_idにしprevious_interaction_idで会話を継続
        result_part={'type':'function_result','name':prior_name,'call_id':call_id,
                     'result':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}]}
        res=self.client.interactions.create(
            model=self.model,
            previous_interaction_id=self.interaction.id,
            tools=TOOLS,
            input=[result_part])
        if expect_tool:return self._extract(res)
        self.interaction=res
        # 最終応答は不確実性があるため、ユーザー向けには確定ログも出す
        return getattr(res,'output_text','') or '(AIによる最終説明なし)'

def make_pose(nav,frame,coords):
    from geometry_msgs.msg import PoseStamped
    msg=PoseStamped();msg.header.frame_id=frame
    msg.header.stamp=nav.get_clock().now().to_msg()
    msg.pose.position.x=float(coords['x']);msg.pose.position.y=float(coords['y'])
    yaw=float(coords.get('yaw',0))
    msg.pose.orientation.z=math.sin(yaw/2);msg.pose.orientation.w=math.cos(yaw/2)
    return msg

def write_log(run_id,kind,**extra):
    row={'run_id':run_id,'time_utc':datetime.now(timezone.utc).isoformat(),'type':kind,**extra}
    path=ROOT/'logs'/'events_v4.jsonl';path.parent.mkdir(exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    print('[LOG]',json.dumps(row,ensure_ascii=False),flush=True)

def run(cfg,task):
    import rclpy
    from std_msgs.msg import String
    from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
    from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    rclpy.init()
    nav=BasicNavigator()
    world=None
    qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,
                   durability=DurabilityPolicy.TRANSIENT_LOCAL)
    def status_callback(msg):
        nonlocal world
        try:
            next_world=parse_world_event(msg.data)
            if world is None or next_world['version']>world['version'] or (next_world['version']==world['version'] and next_world!=world):
                world=next_world
                write_log(run_id,'WORLD_UPDATED',world=world)
        except Exception as exc:
            write_log(run_id,'INVALID_WORLD',error=str(exc))
    sub=nav.create_subscription(String,'/shelf_state',status_callback,qos)
    active=False
    try:
        deadline=time.monotonic()+float(cfg['world_wait_sec'])
        while world is None and time.monotonic()<deadline:
            rclpy.spin_once(nav,timeout_sec=0.2)
        if world is None:
            raise RuntimeError('初期棚状態を取得できません。Scenario Serverを先に起動してください')
        if cfg.get('initial_pose'):
            nav.setInitialPose(make_pose(nav,cfg['frame_id'],cfg['initial_pose']))
        print('Nav2アクティブ待ち。RVizのInitial PoseとLifecycle設定を確認してください')
        nav.waitUntilNav2Active()
        ai=GeminiCalls(cfg)
        decision=ai.begin(task,world)
        attempt=0
        while True:
            name,args,call_id=decision
            world_at_decision=dict(world)
            kind,target=validate_tool_call(name,args,world)
            write_log(run_id,'AI_TOOL_CALL',name=name,args=args,world=world_at_decision)
            if kind=='STOP':
                write_log(run_id,'TASK_STOPPED',reason=args.get('reason','no available shelves'))
                try:
                    ai_text=ai.next_after_result(name,call_id,{'status':'STOPPED','world':world},expect_tool=False)
                    print('Gemini:',ai_text)
                except Exception as exc:
                    write_log(run_id,'AI_FINAL_SUMMARY_UNAVAILABLE',error=str(exc))
                print('USER: 利用できる目的地がないため停止しました。')
                return 0 if all(world[s]=='blocked' for s in ('SHELF_A','SHELF_B')) else 2

            # 不正・古いAI応答を拒否（API呼び出し中のイベントはNav2起動前に処理）
            rclpy.spin_once(nav,timeout_sec=0.05)
            validate_tool_call(name,args,world)
            write_log(run_id,'NAV_START',destination=target,world_version=world['version'])
            nav.goToPose(make_pose(nav,cfg['frame_id'],cfg['destinations'][target]))
            active=True
            deadline=time.monotonic()+float(cfg['navigate_timeout_sec'])
            interrupted=False
            while True:
                finished=nav.isTaskComplete()
                # ROS2 TopicイベントはNav2と同じノードのexecutorで受信する
                rclpy.spin_once(nav,timeout_sec=0.05)
                if world[target]=='blocked':
                    write_log(run_id,'TARGET_UNAVAILABLE',target=target,world=world)
                    interrupted=True
                    break
                if finished:
                    result=nav.getResult();active=False
                    write_log(run_id,'NAV_RESULT',target=target,result=str(result))
                    if result!=TaskResult.SUCCEEDED:
                        raise RuntimeError('Nav2移動が成功しませんでした: '+str(result))
                    if world[target]!='available':
                        interrupted=True;break
                    write_log(run_id,'TASK_SUCCEEDED',target=target)
                    try:
                        final_text=ai.next_after_result(name,call_id,
                            {'status':'SUCCEEDED','destination':target,'world':world},expect_tool=False)
                        print('Gemini:',final_text)
                    except Exception as exc:
                        write_log(run_id,'AI_FINAL_SUMMARY_UNAVAILABLE',error=str(exc))
                    print('USER: '+target+'への移動を完了しました。')
                    return 0
                if time.monotonic()>deadline:
                    raise TimeoutError('移動タイムアウト')

            if interrupted:
                write_log(run_id,'CANCEL_REQUEST',target=target)
                nav.cancelTask()
                cancel_by=time.monotonic()+float(cfg['cancel_timeout_sec'])
                while not nav.isTaskComplete() and time.monotonic()<cancel_by:
                    rclpy.spin_once(nav,timeout_sec=0.05)
                if not nav.isTaskComplete():
                    # 安全側で終了。物理的停止保証ではない
                    raise RuntimeError('Nav2取消完了を確認できません。新ゴールは送信しません')
                res=nav.getResult();active=False
                # 成功と取消の競合も記録。棚状態がblockedなら成功と認定しない。
                write_log(run_id,'CANCEL_TERMINAL',target=target,result=str(res))
                attempt+=1
                if attempt>cfg['max_replans']:
                    raise RuntimeError('再計画回数上限')
                # Function Resultに環境とキャンセル理由を返して、Geminiが次のツールを選ぶ
                decision=ai.next_after_result(name,call_id,
                    {'status':'CANCELED_OR_TERMINATED','destination':target,
                     'reason':'SHELF_BECAME_UNAVAILABLE','nav2_result':str(res),
                     'world':world,'user_task':task},expect_tool=True)
    except Exception as exc:
        write_log(run_id,'TASK_ABORTED',error=str(exc))
        if active:
            try:
                nav.cancelTask()
                until=time.monotonic()+float(cfg['cancel_timeout_sec'])
                while not nav.isTaskComplete() and time.monotonic()<until:
                    rclpy.spin_once(nav,timeout_sec=0.05)
                write_log(run_id,'FAILSAFE_CANCEL',confirmed=nav.isTaskComplete())
            except Exception as cancel_exc:
                write_log(run_id,'FAILSAFE_CANCEL_ERROR',error=str(cancel_exc))
        print('USER: タスクを安全側で中断しました。理由:',exc)
        return 2
    finally:
        nav.destroy_subscription(sub)
        nav.destroy_node()
        rclpy.shutdown()

def main():
    ap=argparse.ArgumentParser(description='Gemini Robotics ER 2 + Nav2 Agent')
    ap.add_argument('--config',default=str(ROOT/'config'/'destinations.json'))
    ap.add_argument('--task',default=DEFAULT_TASK,help='L0ユーザーの自然言語指示')
    ap.add_argument('--api-check',action='store_true',help='ROS2ナビゲーションを開始せずFunction Callだけ試す')
    args=ap.parse_args()
    cfg=load_config(args.config,require_positions=not args.api_check)
    if args.api_check:
        try:
            print('google-genai SDK:', current_sdk_version(),flush=True)
            ai=GeminiCalls(cfg)
            name,parms,call_id=ai.begin(args.task,{'version':1,'SHELF_A':'available','SHELF_B':'available'})
            print(json.dumps({'tool':name,'arguments':parms,'call_id':call_id},ensure_ascii=False,indent=2))
            print('API_CHECK: OK (ROS 2/Gazeboの実移動は未検証)')
            return 0
        except Exception as exc:
            # 公開ログにキーを出さないためエラー型と原因分類だけを表示する
            reason=str(exc)
            if 'legacy Interactions API schema' in reason:
                hint='旧SDKです。python -m pip install --upgrade -r requirements.txt を実行してください。'
            elif '404' in reason or 'not found' in reason.lower():
                hint='モデルIDと利用権限をGoogle AI Studio／公式モデル一覧で確認してください。'
            elif '401' in reason or '403' in reason:
                hint='APIキーの認証・アクセス権限を確認してください。'
            elif '429' in reason:
                hint='クォータ／レート制限を確認してください。'
            else:
                hint='SDKのバージョン、ネットワーク、Interactions APIスキーマを確認してください。'
            print(f'API_CHECK: FAILED ({type(exc).__name__}) {hint}',file=sys.stderr)
            return 2
    return run(cfg,args.task)
if __name__=='__main__':sys.exit(main())
