# Physical AI 最終課題 — Gemini Robotics ER 2 × ROS 2 / Nav2

**自然言語で移動先を判断し、環境状態の変化に応じて再計画する自律移動ロボットのデモ**

Gemini Robotics ER 2が高レベルの行動（棚A／棚Bへの移動、停止）を選択し、Python Agentが判断結果を検証してROS 2／Nav2へ渡します。Gazebo Classic上のTurtleBot3が実際の走行をシミュレーションします。

## 目次

- [1. 環境構築（初回のみ）](#1-環境構築初回のみ)
- [2. シナリオ実行（各ケース独立）](#2-シナリオ実行各ケース独立)
  - [T01：通常移動](#t01通常移動)
  - [T02：移動中の利用不可と動的再計画](#t02移動中の利用不可と動的再計画)
  - [T03：両棚利用不可で停止](#t03両棚利用不可で停止)

| ケース | 初期状態 | 実行内容 | 合格判定 |
|---|---|---|---|
| **T01** | A=available、B=available | Geminiが棚Aを選択し、Nav2で移動 | `TASK_SUCCEEDED`（SHELF_A）、終了コード0 |
| **T02** | A=available、B=available | 棚Aへ走行中にAをblockedへ変更 → 取消 → Geminiが棚Bを再選択 | `CANCEL_TERMINAL` → 棚B `TASK_SUCCEEDED`、終了コード0 |
| **T03** | A=blocked、B=blocked | Geminiが停止を選択。移動Goalは送信しない | `TASK_STOPPED`、`NAV_START`なし、終了コード0 |

### 使用技術と処理経路

```text
ユーザー（自然言語）
    ↓ CLI --task
robot_agent.py ⇄ Gemini Robotics ER 2（HTTPS / Interactions API / Function Calling）
    │                ↑ 移動・取消結果をFunction Resultで返却
    ├← /shelf_state ── scenario_event.py（棚状態の正本）
    ↓ Nav2 Simple Commander → ROS 2 Action /navigate_to_pose
ROS 2 Humble / Nav2（経路計画・走行制御・Goal取消）
    ↕ ROS 2 Topic + gazebo_rosプラグイン
Gazebo Classic 11 / TurtleBot3 Waffle（走行・センサーのシミュレーション）
                           RViz：地図・位置・経路の可視化
```

主なソースは`robot_agent.py`（Gemini連携／Nav2制御）、`scenario_event.py`（棚状態）、`logic.py`（AI出力と設定の検証）、`nav2_test.py`（Nav2単独確認）です。

---

# 1. 環境構築（初回のみ）

この章を完了すれば、**T01・T02・T03のいずれからでも単独で開始**できます。以降の各ケースには、必要なTerminal A〜Dの起動コマンドをそれぞれ記載しています。

## 1.1 前提環境とリポジトリ

| 項目 | 使用環境 |
|---|---|
| ホスト | Windows 11、WSL 2、Docker Desktop（Linuxコンテナ） |
| コンテナ | Ubuntu 22.04、ROS 2 Humble |
| シミュレーター | Gazebo **Classic** 11、TurtleBot3 **Waffle** |
| ナビゲーション | Nav2、RViz 2 |
| Python | 3.10、仮想環境`~/.venvs/physical_ai_final` |
| AI | `gemini-robotics-er-2-preview`、`google-genai==2.33.0`、APIキー |

GitHubから本リポジトリを取得するか、配布されたソース一式をWindowsのプロジェクトディレクトリに配置します。以下では**例として**`D:\PhysicalAI\PAI_Final`を使用します。ファイルはフォルダの直下に`requirements.txt`、`scripts/`、`config/`が存在する構成にしてください。

```text
PAI_Final/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── config/destinations.json
├── scripts/
│   ├── robot_agent.py
│   ├── scenario_event.py
│   ├── nav2_test.py
│   └── logic.py
├── tests/
│   ├── test_logic.py
│   ├── test_gemini_protocol.py
│   └── test_agent_runtime.py
└── logs/                  # 実行時にevents_v4.jsonlを作成
```

**Windows PowerShell**で確認します。

```powershell
$Project = 'D:\PhysicalAI\PAI_Final'
if (-not (Test-Path -LiteralPath "$Project\scripts\robot_agent.py")) {
    throw 'ソースが見つかりません。配置先とフォルダ階層を確認してください。'
}
wsl --status
docker version
docker info
```

`docker info`でServer情報が取得できることを確認してください。WSL 2またはDocker Desktopが未導入の場合は先に公式手順で導入・起動します（`wsl --install`だけではDocker Desktopは導入されません）。

## 1.2 Dockerコンテナを作成・起動する

**Windows PowerShell**で実行します。`$Project`は1.1で指定したまま使用します。

```powershell
docker pull airobotbook/ros2-desktop-ai-robot-book-humble:latest

docker run -d --name pai_nav2_final `
  -p 6080:80 -p 9090:9090 -p 9876:9876 `
  --shm-size=1g `
  -v "${Project}:/workspace" `
  airobotbook/ros2-desktop-ai-robot-book-humble:latest

docker inspect pai_nav2_final --format '{{json .Mounts}}'
```

- コンテナ名`pai_nav2_final`が既に存在する場合は、**新規`docker run`を重複実行しない**でください。停止中なら`docker start pai_nav2_final`で再開します。
- 6080／9090／9876番ポートが使用中なら、既存のコンテナ／アプリを確認してからポート割当を調整してください。
- ブラウザーで`http://localhost:6080/`を開き、コンテナのデスクトップを確認します。

以降の**Terminal A〜E**は、**同じDockerコンテナに接続する別々のUbuntu Bash**です。Docker Desktopの対象コンテナのExec画面、またはWindows PowerShellから次のコマンドで開きます。

```powershell
docker exec -it --user ubuntu --workdir /workspace pai_nav2_final bash
```

コンテナごとに名前が違う場合は読み替えてください。以下のUbuntuコマンドは**Windows PowerShellでは実行しません**。`whoami`が`ubuntu`であることを確認し、以降は同じユーザーを使用します。

| 端末 | 役割 |
|---|---|
| **A** | Gazebo／TurtleBot3／Nav2／RVizを常駐起動 |
| **B** | Scenario Server（棚状態の保持・配信） |
| **C** | Gemini Agent（実API通信／Nav2移動） |
| **D** | T02で棚Aをblockedに変更する一回限りの操作 |
| **E** | 環境構築、座標設定、動作確認（必要時） |

## 1.3 ROS 2・Nav2・Gazebo・TurtleBot3を導入する

**Terminal E（Docker Ubuntu Bash）**で実行します。

```bash
cat /etc/os-release | grep -E '^(ID|VERSION_ID|VERSION_CODENAME)='
source /opt/ros/humble/setup.bash
echo "$ROS_DISTRO"
sudo apt-get update
```

**通常は次のAPT一括導入へ進みます。** `EXPKEYSIG F42ED6FBAB17C654`などROS 2リポジトリの署名エラーが出た場合に限り、古いROS 2 APT設定を確認し、該当設定だけを退避したうえで公式APT設定を修復してください。

```bash
# 署名エラー発生時のみ：ROS 2関連の旧定義を確認
# ファイルがなければ退避コマンドは実行しない
grep -RHn 'packages.ros.org/ros2/ubuntu' \
  /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null || true
if [ -f /etc/apt/sources.list.d/ros2.list ]; then
  sudo cat /etc/apt/sources.list.d/ros2.list
else
  echo "ros2.listなし：他の.list/.sourcesを確認"
fi
```

`/etc/apt/sources.list.d/ros2.list`が存在し、**旧ROS 2設定専用**であると確認できた場合だけ、次の退避コマンドを実行します。Ubuntu標準のAPT定義や正常な`.sources`は変更しないでください。

```bash
# 条件に該当する場合のみ（上のcatで内容を確認してから）
mkdir -p "$HOME/ros2-apt-backup"
sudo cp -a /etc/apt/sources.list.d/ros2.list "$HOME/ros2-apt-backup/ros2.list"
sudo mv /etc/apt/sources.list.d/ros2.list "$HOME/ros2-apt-backup/ros2.list.disabled"

curl -fL --retry 3 -o /tmp/ros2-apt-source.deb \
  https://github.com/ros-infrastructure/ros-apt-source/releases/download/1.3.0/ros2-apt-source_1.3.0.jammy_all.deb
dpkg-deb --info /tmp/ros2-apt-source.deb
sudo dpkg -i /tmp/ros2-apt-source.deb
sudo apt-get update
dpkg-query --no-pager -l ros2-apt-source
```

署名エラーが解消したら必要パッケージを導入します。

```bash
apt-cache policy ros-humble-nav2-bringup ros-humble-turtlebot3-gazebo
PKGS=(ros-humble-navigation2 ros-humble-nav2-bringup
  ros-humble-gazebo-ros-pkgs ros-humble-turtlebot3
  ros-humble-turtlebot3-msgs python3-colcon-common-extensions
  python3-rosdep python3.10-venv git curl ca-certificates)
if apt-cache show ros-humble-turtlebot3-gazebo >/dev/null 2>&1; then
  PKGS+=(ros-humble-turtlebot3-gazebo)
fi
sudo apt-get install -y "${PKGS[@]}"
source /opt/ros/humble/setup.bash
ros2 pkg prefix turtlebot3_gazebo
```

`ros2 pkg prefix turtlebot3_gazebo`が失敗する場合**のみ**、TurtleBot3のシミュレーションパッケージをソースから導入します。

```bash
# APTでturtlebot3_gazeboを導入できなかった場合のみ
source /opt/ros/humble/setup.bash
mkdir -p "$HOME/turtlebot3_ws/src"
cd "$HOME/turtlebot3_ws/src"
git clone -b humble-devel https://github.com/ROBOTIS-GIT/turtlebot3_simulations.git
cd "$HOME/turtlebot3_ws"
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then sudo rosdep init; fi
rosdep update
rosdep install --from-paths src --ignore-src --rosdistro humble -r -y
colcon build --symlink-install --packages-up-to turtlebot3_gazebo
source install/setup.bash
ros2 pkg prefix turtlebot3_gazebo
```

> 既に`~/airobot_ws`などで`TurtleBot3`パッケージを導入済みの場合は、二重導入せず既存ワークスペースを読み込んでください。

**Terminal Eでの導入確認：**

```bash
source /opt/ros/humble/setup.bash
[ -f "$HOME/turtlebot3_ws/install/setup.bash" ] && source "$HOME/turtlebot3_ws/install/setup.bash"
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
gazebo --version
for pkg in nav2_bringup nav2_simple_commander gazebo_ros turtlebot3_gazebo; do
  ros2 pkg prefix "$pkg" || exit 1
done
python3 -c 'import ensurepip; print("ensurepip: OK")'
```

期待結果：Gazebo Classic 11.x、4つのROS 2パッケージを認識。

## 1.4 Python仮想環境・Gemini SDKを準備する

**Terminal E（Docker Ubuntu Bash）**で実行します。

```bash
mkdir -p "$HOME/.venvs"
python3 -m venv --system-site-packages "$HOME/.venvs/physical_ai_final"
source /opt/ros/humble/setup.bash
source "$HOME/.venvs/physical_ai_final/bin/activate"
cd /workspace
python --version
python -m pip install --upgrade -r requirements.txt
python -m pip check
python -m pip show google-genai
python -c "import rclpy; from nav2_simple_commander.robot_navigator import BasicNavigator; from google import genai; print('ROS2/Nav2/Gemini: OK')"
python -m unittest discover -s tests -v
```

期待結果：Python 3.10、`google-genai==2.33.0`、テスト18件`OK`。仮想環境は`/workspace`の共有領域ではなく**Ubuntuユーザーのホームディレクトリ**に作成します。

Gemini APIキーはGoogle AI Studioで取得します。秘密情報のため**コード、README、Git、ログ、画面収録には記載しないでください**。Geminiを呼び出す**Terminal C**ごとに次を実行します（入力文字は表示されません）。

```bash
cd /workspace
source "$HOME/.venvs/physical_ai_final/bin/activate"
read -rs -p 'Gemini API key: ' GEMINI_API_KEY; echo
export GEMINI_API_KEY
python scripts/robot_agent.py --api-check
```

期待結果：有効なFunction Callが返り、`API_CHECK: OK`。この検査ではGazebo上のロボットは移動しません。401/403はキー・権限、404はモデル利用可否、429はクォータを確認してください。設定済みの同じBashではAPIキーの再入力は不要です。

## 1.5 目的地座標を設定し、Nav2を単独確認する

**Terminal A（Docker Ubuntu Bash）**で次を起動し、終了させず維持します。

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/turtlebot3_ws/install/setup.bash" ] && source "$HOME/turtlebot3_ws/install/setup.bash"
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
export TURTLEBOT3_MODEL=waffle
TB3_GAZEBO_PREFIX="$(ros2 pkg prefix turtlebot3_gazebo)"
export GAZEBO_MODEL_PATH="${GAZEBO_MODEL_PATH:+$GAZEBO_MODEL_PATH:}${TB3_GAZEBO_PREFIX}/share/turtlebot3_gazebo/models"
ros2 launch nav2_bringup tb3_simulation_launch.py headless:=False
```

Windowsブラウザーで`http://localhost:6080/`を開き、GazeboとRVizを表示します。**Terminal E**からNav2 Actionを確認します。

```bash
source /opt/ros/humble/setup.bash
ros2 action list -t | grep navigate_to_pose
ros2 action info /navigate_to_pose
```

RVizで次の順に設定します。

1. `Fixed Frame=map`、`Map`のTopic=`/map`を確認。Gazebo上のロボット実位置とRViz表示を照合し、**2D Pose Estimate**で初期姿勢を合わせます。
2. 地図・`/scan`・Global/Local Costmapを見て、障害物や壁際でない**到達可能な空き領域**を棚A／棚Bとして選びます（棚は仮想的なラベルです）。
3. Terminal Eで`ros2 topic echo /clicked_point`を実行。RVizの**Publish Point**でA、Bの順にクリックし、`map`座標系の`x`／`y`を記録します。
4. 既存の実測座標を上書きしないようバックアップし、`/workspace/config/destinations.json`の`SHELF_A`／`SHELF_B`の`x`／`y`に**実測値**を入れます。`frame_id="map"`、`max_replans=1`は維持します。`initial_pose:null`はRVizで設定する場合はそのままで構いません。`yaw`はラジアン値です。

**Terminal Eで編集・確認：**

```bash
cd /workspace
cp -n config/destinations.json config/destinations.json.bak
nano config/destinations.json
python3 -m json.tool config/destinations.json >/dev/null && echo 'JSON: OK'
python3 -c 'import json; c=json.load(open("config/destinations.json")); print(c["destinations"])'
```

> `x:null`／`y:null`のままでは、実移動モードのAgentは起動しません。サンプル座標をそのままコピーせず、利用するGazebo／RViz環境の地点を設定してください。**2D Pose Estimateは自己位置推定の設定であり、Gazebo内のロボットを物理的に移動させません。**

**Terminal C（先ほどAPIチェックに使用したBash、または新しいBash）**でNav2の単独移動を確認します。新しいBashの場合は次の`source`を実行してください。

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/turtlebot3_ws/install/setup.bash" ] && source "$HOME/turtlebot3_ws/install/setup.bash"
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
source "$HOME/.venvs/physical_ai_final/bin/activate"
python scripts/nav2_test.py --target SHELF_A
echo "SHELF_A exit code: $?"
# 棚AがTaskResult.SUCCEEDED／終了コード0の場合にのみ実行
python scripts/nav2_test.py --target SHELF_B
echo "SHELF_B exit code: $?"
```

両方で`NAV RESULT: TaskResult.SUCCEEDED`、終了コード0、Gazebo内の実際の移動を確認します。失敗する場合は座標・自己位置・障害物・Costmap・経路の可否を確認してください。**Nav2の動作確認が未完了のままシナリオへ進まないでください。**

**環境構築の完了条件**：DockerとnoVNC、ROS 2/Nav2/Gazebo、Python venv、Gemini `--api-check`、棚A/Bの実測座標、Nav2の棚A/B単独移動が確認済み。

---

# 2. シナリオ実行（各ケース独立）

**T01・T02・T03は実行順序に依存しません。** 1章の環境構築を完了していれば、どのケースからでも開始できます。コンテナが停止している場合は、Windows PowerShellで`docker start pai_nav2_final`を実行し、A〜D用のUbuntu Bashを開いてください。**各ケースでScenario Serverを新しい初期状態から起動**するため、別ケースの棚状態を引き継ぎません。

**各ケース共通の注意：**

- 既存のNav2／Gazebo（Terminal A）が動いていれば維持し、**二重起動しない**。停止している場合は各ケースのTerminal Aを起動する。
- Terminal Bに以前のScenario Serverがあれば`Ctrl+C`で停止し、**起動プロセスが1つだけ**になるようにする。
- Terminal Cで使うGemini APIキーは**そのBashセッションでのみ有効**。新しいBashでは再設定する。
- RVizの**2D Pose Estimateはロボットの物理移動ではない**。開始位置を変えるときは、Gazeboの位置リセットやNav2 Goalで**実際に再配置した後**に初期姿勢を合わせる。
- 合否は**ケースごとの終了コード＋同じ`run_id`のログ＋Gazebo上の動作**で判定する。ログは`/workspace/logs/events_v4.jsonl`に追記される。

## T01：通常移動

**目的**：棚A・棚Bが両方利用可能な状態で、Geminiが棚Aを選択し、Nav2で到着することを確認する。**T02・T03の実行履歴は不要**。

**A｜Gazebo・Nav2（停止している場合のみ起動して常駐）**

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/turtlebot3_ws/install/setup.bash" ] && source "$HOME/turtlebot3_ws/install/setup.bash"
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
export TURTLEBOT3_MODEL=waffle
TB3_GAZEBO_PREFIX="$(ros2 pkg prefix turtlebot3_gazebo)"
export GAZEBO_MODEL_PATH="${GAZEBO_MODEL_PATH:+$GAZEBO_MODEL_PATH:}${TB3_GAZEBO_PREFIX}/share/turtlebot3_gazebo/models"
ros2 launch nav2_bringup tb3_simulation_launch.py headless:=False
```

**RViz**：ロボットが棚Aから離れた到達可能な位置にいることを確認し、Gazeboの実位置に合わせて`2D Pose Estimate`を設定します。未完了のNav2 Goalがないことも確認します。

**B｜Scenario Server（新しいBash）**

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
python3 scripts/scenario_event.py --server --initial-a available --initial-b available
```

`SERVER READY`と`SHELF_A=available`／`SHELF_B=available`を確認します。Bは常駐のまま維持します。

**C｜Gemini Agent（新しいBash）**

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/turtlebot3_ws/install/setup.bash" ] && source "$HOME/turtlebot3_ws/install/setup.bash"
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
source "$HOME/.venvs/physical_ai_final/bin/activate"
read -rs -p 'Gemini API key: ' GEMINI_API_KEY; echo
export GEMINI_API_KEY
python scripts/robot_agent.py --task '棚Aへ移動してください'
echo "T01 exit code: $?"
```

**T01の合格条件**：

- 同じ`run_id`で`AI_TOOL_CALL`（SHELF_A）→`NAV_START`（SHELF_A）→`NAV_RESULT`（`TaskResult.SUCCEEDED`）→`TASK_SUCCEEDED`（SHELF_A）。
- `T01 exit code: 0`。Gazebo上のTurtleBot3が棚Aの地点へ移動している。
- **Terminal Dで棚状態を変更しない**。

## T02：移動中の利用不可と動的再計画

**目的**：棚Aへ移動している途中で棚Aを利用不可に変更し、**旧Goalのキャンセル完了後**にGeminiが棚Bを選択、Nav2が棚Bに到着することを確認する。**T01を先に実施する必要はありません**。

**A｜Gazebo・Nav2（停止している場合のみ起動して常駐）**

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/turtlebot3_ws/install/setup.bash" ] && source "$HOME/turtlebot3_ws/install/setup.bash"
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
export TURTLEBOT3_MODEL=waffle
TB3_GAZEBO_PREFIX="$(ros2 pkg prefix turtlebot3_gazebo)"
export GAZEBO_MODEL_PATH="${GAZEBO_MODEL_PATH:+$GAZEBO_MODEL_PATH:}${TB3_GAZEBO_PREFIX}/share/turtlebot3_gazebo/models"
ros2 launch nav2_bringup tb3_simulation_launch.py headless:=False
```

**RViz**：Gazeboのロボットを**棚Aから十分離れた、安全で棚Bにも到達可能な地点**に物理的に配置します。必要ならテスト開始前にNav2 Goalで再配置し、そのGoalが完了したことを確認します。`2D Pose Estimate`で実位置に一致させます。A/Bの座標・Costmapを再確認してください。

**B｜Scenario Server（新しいBash）**

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
python3 scripts/scenario_event.py --server --initial-a available --initial-b available
```

Bで`SERVER READY`／初期`version=1`／A・Bとも`available`を確認します。

**C｜Gemini Agent（新しいBash。走行中はこの画面を操作しない）**

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/turtlebot3_ws/install/setup.bash" ] && source "$HOME/turtlebot3_ws/install/setup.bash"
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
source "$HOME/.venvs/physical_ai_final/bin/activate"
read -rs -p 'Gemini API key: ' GEMINI_API_KEY; echo
export GEMINI_API_KEY
python scripts/robot_agent.py --task '棚Aへ移動。移動中に棚Aが利用不可になれば棚Bへ変更してください'
echo "T02 exit code: $?"
```

**D｜棚Aを利用不可へ変更（Cが棚Aへ実際に走行開始したら実行）**

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
python3 scripts/scenario_event.py --set SHELF_A=blocked
```

Dの`UPDATE SENT`だけでは棚状態反映の証明にはなりません。B側の`STATE`更新（`version=2`、A=`blocked`、B=`available`）とCの`WORLD_UPDATED`を確認します。**Cの`NAV_START`表示だけでなくGazebo/RVizで実移動を確認し、棚Aへ到着する前にDを実行**してください。

**T02の合格条件**：

- 同じ`run_id`で`NAV_START`（SHELF_A）→`WORLD_UPDATED`（A=blocked）→`TARGET_UNAVAILABLE`→`CANCEL_REQUEST`→`CANCEL_TERMINAL`（`TaskResult.CANCELED`）。
- Geminiから`AI_TOOL_CALL`（SHELF_B）、`NAV_START`（SHELF_B）→`NAV_RESULT`（`TaskResult.SUCCEEDED`）→`TASK_SUCCEEDED`（SHELF_B）。
- `T02 exit code: 0`。Gazebo上で棚Bへの実移動と到着を確認。
- **`TaskResult.FAILED`、`TASK_ABORTED`、終了コード2はT02不合格**。キャンセルできても棚Bへの走行が失敗した場合は、Costmap・障害物・自己位置・B座標を修正して**新しい`run_id`で再実行**します。

## T03：両棚利用不可で停止

**目的**：棚A・棚Bが開始時点で利用不可なら、Geminiが`stop_task`を選び、**Nav2の新規移動Goalなしで終了**することを確認する。**T01・T02の実行履歴は不要**。

**A｜Gazebo・Nav2（停止している場合のみ起動して常駐）**

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/turtlebot3_ws/install/setup.bash" ] && source "$HOME/turtlebot3_ws/install/setup.bash"
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
export TURTLEBOT3_MODEL=waffle
TB3_GAZEBO_PREFIX="$(ros2 pkg prefix turtlebot3_gazebo)"
export GAZEBO_MODEL_PATH="${GAZEBO_MODEL_PATH:+$GAZEBO_MODEL_PATH:}${TB3_GAZEBO_PREFIX}/share/turtlebot3_gazebo/models"
ros2 launch nav2_bringup tb3_simulation_launch.py headless:=False
```

**RViz**：Gazeboのロボットが停止しており、Nav2に未完了のGoalがないことを確認します。`2D Pose Estimate`で実位置と向きを合わせてください。**このケースのAgent実行後にNav2 Goalを送らない**でください。

**B｜Scenario Server（新しいBash）**

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
python3 scripts/scenario_event.py --server --initial-a blocked --initial-b blocked
```

Bで`SERVER READY`／初期`version=1`／A・Bとも`blocked`を確認します。

**C｜Gemini Agent（新しいBash）**

```bash
cd /workspace
source /opt/ros/humble/setup.bash
[ -f "$HOME/turtlebot3_ws/install/setup.bash" ] && source "$HOME/turtlebot3_ws/install/setup.bash"
[ -f "$HOME/airobot_ws/install/setup.bash" ] && source "$HOME/airobot_ws/install/setup.bash"
source "$HOME/.venvs/physical_ai_final/bin/activate"
read -rs -p 'Gemini API key: ' GEMINI_API_KEY; echo
export GEMINI_API_KEY
python scripts/robot_agent.py --task '使える棚へ移動。利用可能な棚がなければ停止してください'
echo "T03 exit code: $?"
```

**T03の合格条件**：

- 同じ`run_id`で`AI_TOOL_CALL`（`stop_task`）と`TASK_STOPPED`が記録され、`NAV_START`は**0件**。
- `T03 exit code: 0`。Gazeboのロボットは移動しない。
- T03では**Terminal Dは不要**。Nav2は起動している必要がありますが、移動Goalは出しません。
