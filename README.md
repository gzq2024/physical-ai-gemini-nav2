# Physical AI 最終課題 | Starter v8.0（10/27～29の処理シーケンス・全日ターミナル統一）

## v8.0 ターミナルの固定責務（全日共通）

| 区分 | 責務 | 使う作業 |
| --- | --- | --- |
| Windows PS | ZIP・Docker管理 | 10/27 |
| Windows Browser | noVNC/RViz操作、動画・提出 | 10/28以降 |
| Terminal A | Gazebo Classic／TurtleBot3／Nav2／RVizの起動と常駐 | 10/28・10/31 |
| Terminal B | Scenario Server：棚状態の保持・`/shelf_state`の発行 | 10/30・10/31 |
| Terminal C | Agent：Nav2単体走行、Gemini実API、統合Agent | 10/27 API／10/28移動／10/29 API／10/31実行 |
| Terminal D | 状態変更CLI：`--set SHELF_A=blocked` | 10/30・10/31 |
| Terminal E | APT・venv・座標／Action／Topic確認、モック・ログ監査 | 10/27～11/1 |

**重要：** 複数のTerminalは同じDockerコンテナ内の独立したBashです。`source`は別Bashへ引き継がれません。`GEMINI_API_KEY`はCにだけ入力し、実測した`config/destinations.json`をZIPの雛形で上書きしません。長いPythonスクリプトはファイルとして保存してから実行すると貼り付け表示の乱れを避けられます。実環境で確認済みのT01/T02/T03ログと、今回行うモックテストは区別してください。


**設計**：L0 ユーザー自然言語指示 → `robot_agent.py` → Gemini Robotics ER 2のFunction Call → PythonでNav2 Simple Commanderを実行 → ROS 2 Action / Nav2 → Gazebo Classic 11のTurtleBot3 → Action結果・棚状態イベント → Gemini再計画 → 最終応答。

独立したTask Manager / Gateway / Execution Supervisor / Nav2 Adapter / World State Storeは**作らない**。代わりに`robot_agent.py`一個に必要な検証・状態遷移・取消制御を持たせる。`scenario_event.py`が棚の論理状態を保持して配信する（物体認識ではない）。`logic.py`はROSに依存しない**共通検証モジュール**です。実行エージェントやScenario Serverからimportされますが、独立サービスではありません。

## v8.0における実行順序・重要事項

**10/27**：Windows PowerShell＝WSL/Docker/ZIP操作、Terminal E＝APT署名修復・E04一括導入・venv準備とテスト、Terminal C＝Gemini実API疎通。

**10/28**：Terminal A＝Gazebo/Nav2/RVizの常駐、Terminal E＝Action Server確認・Publish Point座標取得・JSON検証、Terminal C＝Nav2 Simple CommanderでSHELF_A成功→SHELF_B成功。

**10/29**：Terminal C＝Google GenAI SDK 2.xで実Gemini Function Callを取得、Terminal E＝コード／Function Result／18件の単体・模擬テストを確認。実Nav2走行は10/29に実施しない。

**10/30**：Terminal B＝Scenario Server、D＝棚状態変更CLI、E＝Topic監視・単体テスト。Bを起動→Eで初期状態v1→Dで `SHELF_A=blocked` →Bでv2確認→Eで変更後の状態を確認。Agent／Gemini／Gazeboはこの日の必須対象外です。

**10/31**：Terminal A＝Gazebo／Nav2／RViz、B＝Scenario Server、C＝Agent／Gemini、D＝T02イベント送信、E＝実行ログ確認／任意のrosbag録画。T01/T02/T03の各開始前にBを再起動して初期状態をリセット。T02では**移動中**にDからイベントを送信し、BのSTATE→CのWORLD_UPDATED→CANCEL_TERMINAL→Gemini再計画→B到着の順を検証します。

**修正版テストが同梱されています**：`tests/test_logic.py`（実座標とは独立した一時JSONを使用）と `tests/test_agent_runtime.py`（T01/T02/T03のAgentモック）に加え、`tests/test_gemini_protocol.py`。18件成功を確認しています。既存の `/workspace/config/destinations.json` を<strong>上書きしない</strong>でください。修正済みテストを既存コンテナへ適用するコマンドはHTMLの **10/30 Step 04** にあります。

## v8.0における実行順序・重要事項

**10/27**：Windows PowerShell＝WSL/Docker/ZIP操作、Terminal E＝APT署名修復・E04一括導入・venv準備とテスト、Terminal C＝Gemini実API疎通。

**10/28**：Terminal A＝Gazebo/Nav2/RVizの常駐、Terminal E＝Action Server確認・Publish Point座標取得・JSON検証、Terminal C＝Nav2 Simple CommanderでSHELF_A成功→SHELF_B成功。

**10/29**：Terminal C＝Google GenAI SDK 2.xで実Gemini Function Callを取得、Terminal E＝コード／Function Result／18件の単体・模擬テストを確認。実Nav2走行は10/29に実施しない。

**10/30**：Terminal B＝Scenario Server、D＝棚状態変更CLI、E＝Topic監視・単体テスト。Bを起動→Eで初期状態v1→Dで `SHELF_A=blocked` →Bでv2確認→Eで変更後の状態を確認。Agent／Gemini／Gazeboはこの日の必須対象外です。

**10/31**：Terminal A＝Gazebo／Nav2／RViz、B＝Scenario Server、C＝Agent／Gemini、D＝T02イベント送信、E＝実行ログ確認／任意のrosbag録画。T01/T02/T03の各開始前にBを再起動して初期状態をリセット。T02では**移動中**にDからイベントを送信し、BのSTATE→CのWORLD_UPDATED→CANCEL_TERMINAL→Gemini再計画→B到着の順を検証します。

**修正版テストが同梱されています**：`tests/test_logic.py`（実座標とは独立した一時JSONを使用）と `tests/test_agent_runtime.py`（T01/T02/T03のAgentモック）に加え、`tests/test_gemini_protocol.py`。18件成功を確認しています。既存の `/workspace/config/destinations.json` を<strong>上書きしない</strong>でください。修正済みテストを既存コンテナへ適用するコマンドはHTMLの **10/30 Step 04** にあります。

## 動作検証状況

- Python構文・ROSに依存しない単体テスト：作成環境で確認。`python3 -m unittest discover -s tests -v`。
- **ユーザー環境で確認済み**：10/27のAPT復旧、10/28のNav2による棚A/B移動、10/29のGemini `--api-check` でSDK 2.33.0・`start_navigation(SHELF_A)`・終了コード0。**T02についてはキャンセル結果CANCELED→Gemini棚B選択→棚B到着SUCCEEDEDというユーザー提供ログを確認済み**。完成品・安全認証済みロボットではない。
- ユーザー側DockerにはROS 2 Humble、Nav2、TurtleBot3、Gazebo Classic 11.10.2のパッケージが存在したが、新規コンテナでの動作は別途確認すること。

## 構成

```text
scripts/robot_agent.py    唯一の実行エージェント（Gemini API + Nav2 + イベント）
scripts/scenario_event.py 棚状態の発行元（--server）／変更指示（--set）
scripts/nav2_test.py      Nav2単体の走行テスト
scripts/logic.py          ロジック検証用の純粋関数
config/destinations.json  棚A/Bのマップ座標（初期値null・必ず設定）
tests/test_logic.py       論理検証のテスト
tests/test_agent_runtime.py ROS2/Nav2/GeminiをモックしたT01/T02/T03のAgentフロー検証
logs/events_v4.jsonl      判断・Action・状態の証跡
```

## ゼロからの環境構築（唯一の正式手順）

**HTMLマニュアル「10/27 Step 01〜12」**を順番に実行してください。`Physical_AI_最終課題_日別実装マニュアル_v8.0.html`。

- Step 01〜03：WSL 2／Docker Desktop、ZIP展開、新規コンテナ作成（必須）
- Step 04〜06：APT状態確認、E03署名鍵修復（EXPKEYSIGが出た場合は公式ros2-apt-source 1.3.0）
- Step 07：E04 APT一括導入（`ros-humble-turtlebot3-gazebo`の候補があれば含める、`python3.10-venv`を含む）
- Step 08〜09：Gazebo/TurtleBot3/ROS 2認識確認（ソース構築はAPT候補がないときのみ）
- Step 10：Ubuntu HOME内に`--system-site-packages`付きvenvを作成
- Step 11〜12：`google-genai==2.33.0`、18件テスト、APIキー設定／Gemini接続検証

`ensurepip`、`activate`、`python`、APT署名、SDK旧スキーマHTTP 400の障害別対処は**10/27章末の一覧**に統合しました。READMEに同一セットアップコマンドを重複掲載しません。

## 2026-10-27 Gemini Interactions API移行（重要）

実際にHTTP 400 `The legacy Interactions API schema is no longer supported` が発生しました。原因は旧 `requirements.txt` の `google-genai>=1.40,<2` です。旧APIの `outputs` は2026-06-08に廃止されました。新SDK 2.xでは `interaction.steps`（`function_call`）、`interaction.output_text`、`previous_interaction_id`付きの `function_result` を利用します。スターターの `robot_agent.py` はv2形式を用い、起動前にSDKメジャーバージョンも検証します。

```bash
source "$HOME/.venvs/physical_ai_final/bin/activate"
cd /workspace
# 旧版から更新する場合、編集済みファイルを先にバックアップ
cp requirements.txt "requirements.txt.bak.$(date +%Y%m%d%H%M%S)"
# v8.0 ZIPを新規環境に展開した後で実施（既存設定を上書きしない）
grep 'google-genai' requirements.txt   # google-genai==2.33.0
python -m pip install --upgrade -r requirements.txt
python -m pip check
python -m pip show google-genai    # Version: 2.33.0
python -m unittest discover -s tests -v
```

`--api-check` はAPIキーを設定した同じBashで実行してください。SDK更新のみではAPIキーの権限やモデル利用可否は保証しません。移行詳細は付録Bを参照。

## Docker内での実行

環境構築は同梱HTMLの **10/27 Step 01〜12** を実行してください。Gazebo起動・ROS 2 Topic・Agentの順序は **10/31** の4ターミナル手順を参照。新規構築コマンドをREADMEに重複掲載しません。

## 通信責務と正しい方向

| 起点 | 終点 | 方式 | 内容 |
|---|---|---|---|
| ユーザー | `robot_agent.py` | CLI文字列 | 自然言語タスク |
| `robot_agent.py` | Gemini ER 2 | HTTPS/Interactions API | 指示＋棚状態＋ツール宣言 |
| Gemini ER 2 | `robot_agent.py` | Function Call | `start_navigation`/`stop_task` **要求** |
| `robot_agent.py` | Simple Commander | Python API | `goToPose`/`cancelTask`/`getResult` |
| Simple Commander | Nav2 BT Navigator | ROS 2 Action | `NavigateToPose` |
| Nav2 Planner/Controller | Gazebo ROSプラグイン | ROS 2 Topic `/cmd_vel` | 走行速度指令 |
| Gazebo内プラグイン | Nav2 / RViz | ROS 2 Topic | `/odom`/`/scan`/TF等 |
| Scenario Server | `robot_agent.py` | ROS 2 Topic `/shelf_state` | 棚状態スナップショット |
| `robot_agent.py` | Gemini ER 2 | Function Result | `SUCCEEDED`や`CANCELED_OR_TERMINATED`と最新棚状態 |
| `robot_agent.py` | ユーザー | コンソール | 最終結果 |

`TurtleBot3`はGazebo内のモデルであり、Gazeboから独立したROS 2 Action Serverではない。`ros_gz_bridge`はGazebo Sim用で、ClassicとROS 2は通常`gazebo_ros`を用いる。

## API実装上の考慮事項

- Google公式のER 2 **Interactions API**で`client.interactions.create`、`interaction.steps`からFunction Callを取得。前回Function結果は`previous_interaction_id`＋`function_result`で渡す。モデルはツールを直接実行しない。
- 移動中はAPI応答を長く待たず、Nav2のAction状態とROS 2 Topicを監視。棚A停止時は**Nav2 Goal取消の終了を確認してから**Geminiに再計画を要求。
- 再計画時は最新棚状態に基づくホワイトリスト再検証を必須とする。上限は1回。
- `403 Forbidden`が出たらGoogle公式のAPIキー制限設定を確認。Previewモデルは利用可能性が変わる。

## 誠実なデモ表示

棚状態は**Scenario Serverからの論理イベント**。LiDARやカメラによる棚の利用不可検知、物品の把持・輸送、画像に基づく空間推論はMVPで実装していない。実動作の動画とログのみを成果として示す。講義資料の無断公開や、APIキー／個人情報のGitHub掲載は避ける。

## 参照先

- https://ai.google.dev/gemini-api/docs/robotics-orchestration
- https://ai.google.dev/gemini-api/docs/robotics-overview
- https://api.nav2.org/nav2-humble/html/md_nav2_simple_commander_README.html
- https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html

## GEMINI_API_KEYの取得と設定（v4.1付録A）

新しい付録AにGoogle AI Studioからのキー取得、Docker Bashへの非表示入力、API疎通検証、認証・クォータエラー対処を追加。詳細は同梱マニュアルの「付録A」を参照。

