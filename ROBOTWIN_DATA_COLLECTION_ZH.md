# RoboTwin Docker 环境启动与数据采集

本文档对应当前仓库中的 `stack_plate` 任务，使用 Docker Compose 服务
`robotwin`、镜像 `robotwin:cuda12.1` 和 0 号 GPU。项目在容器中的路径为
`/workspace/RoboTwin`。

## 1. 文件与参数对应关系

- 任务实现：`envs/stack_plate.py`
- 任务配置：`task_config/stack_plate.yml`
- 启动脚本：`collect_data.sh`
- 采集入口：`script/collect_data.py`
- 默认输出：`data/stack_plate/stack_plate/`

采集命令的三个参数依次为：

```text
bash collect_data.sh <任务名> <配置名> <GPU 编号>
```

因此当前任务使用：

```bash
bash collect_data.sh stack_plate stack_plate 0
```

注意：任务名和配置名均为 `stack_plate`。

## 2. 启动前检查

在宿主机执行：

```bash
nvidia-smi
docker --version
docker compose version
```

`nvidia-smi` 应能看到目标 GPU。Docker 还需要安装 NVIDIA Container
Toolkit，使容器可以使用 `--gpus all`。

进入项目目录：

```bash
cd /home/ubuntu/Desktop/Liutong/RoboTwin
```

如果需要打开 SAPIEN 可视化窗口，先确认宿主机存在 `DISPLAY`：

```bash
echo "$DISPLAY"
xhost +local:docker
```

纯后台采集时，`task_config/stack_plate.yml` 中的 `render_freq: 0` 不会打开
交互式 Viewer，不需要操作窗口。

## 3. 启动 RoboTwin 容器

已有镜像时直接启动：

```bash
docker compose up -d robotwin
```

如果镜像不存在或 Dockerfile 已修改，则构建并启动：

```bash
docker compose up -d --build robotwin
```

检查容器状态和 GPU：

```bash
docker compose ps
docker compose exec robotwin nvidia-smi
```

检查 Python、SAPIEN、PyTorch、Warp 和兼容入口：

```bash
docker compose exec robotwin bash -lc '
cd /workspace/RoboTwin
python - <<"PY"
import sapien
import torch
import warp

print("SAPIEN:", sapien.__version__)
print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("Warp:", warp.__version__)
print("warp.torch available:", hasattr(warp, "torch"))
PY
'
```

当前 `compose.yaml` 会把 `compat/` 加入 `PYTHONPATH`。其中的
`sitecustomize.py` 为镜像内的 cuRobo 提供 Warp 1.15 兼容命名空间，因此不应
再依赖容器 `/tmp` 中的临时补丁。

## 4. 配置采集规模与数据内容

编辑 `task_config/stack_plate.yml`。常用字段如下：

- `episode_num`：成功样本数量，当前为 50。
- `use_seed`：`false` 表示先规划并筛选成功种子；`true` 表示直接使用已有
  `seed.txt`。
- `collect_data`：`true` 表示种子规划结束后继续回放轨迹并写 HDF5。
- `render_freq`：`0` 为后台运行；非零值用于调试 Viewer。
- `save_freq`：图像/状态保存频率。
- `camera.collect_head_camera`：是否采集顶部相机。
- `camera.collect_wrist_camera`：是否采集腕部相机。
- `data_type.rgb`、`depth`、`pointcloud`、`endpose`、`qpos`：控制各类数据。
- `save_path`：输出根目录，当前为 `./data`。

为了快速调试，可复制一份配置并将 `episode_num` 改成 1、
`collect_data` 改成 `false`。不要直接用小规模配置覆盖正式配置。

## 5. 处理旧采集结果

采集器支持断点续跑：如果输出目录已有 `seed.txt`，它会从现有种子数量继续。
但是修改任务动作代码后，旧 `_traj_data/*.pkl` 与新工作流不兼容。此时应先保留
旧目录，再开始一次干净采集：

```bash
cd /home/ubuntu/Desktop/Liutong/RoboTwin
mv data/stack_plate/stack_plate \
  data/stack_plate/stack_plate_backup_$(date +%Y%m%d_%H%M%S)
```

如果目录不存在，可忽略该步骤。确认旧数据不再需要时，也可以自行删除备份。

## 6. 开始正式数据采集

推荐从宿主机一条命令启动：

```bash
cd /home/ubuntu/Desktop/Liutong/RoboTwin
docker compose exec robotwin bash -lc '
cd /workspace/RoboTwin
bash collect_data.sh stack_plate stack_plate 0
'
```

也可以先进入容器再运行：

```bash
docker compose exec robotwin bash
cd /workspace/RoboTwin
bash collect_data.sh stack_plate stack_plate 0
```

程序分为两个阶段：

1. `Start Seed and Pre Motion Data Collection`：逐个尝试随机种子，只保存规划
   和物理成功的轨迹。
2. `Start Data Collection`：按成功种子回放轨迹，采集相机与机器人状态并写入
   HDF5。

单个随机种子失败是正常现象，程序会继续尝试，直到成功数量达到
`episode_num`。看到以下形式的日志才表示该样本通过：

```text
simulate data episode N success! (seed = S)
```

当前 `stack_plate` 的成功条件包括：移动盘准确叠到左侧盘堆、碗底位于
桌面高度附近，并且碗的平面投影不与任一盘子重叠。碗不要求落在固定 XY
坐标。

## 7. 输出目录说明

默认目录结构为：

```text
data/stack_plate/stack_plate/
├── seed.txt
├── _traj_data/
│   ├── episode0.pkl
│   └── ...
├── data/
│   ├── episode0.hdf5
│   └── ...
└── scene_info.json
```

- `seed.txt`：已通过的仿真随机种子。
- `_traj_data/episodeN.pkl`：规划阶段生成的左右臂关节轨迹。
- `data/episodeN.hdf5`：正式回放阶段采集的数据。
- `scene_info.json`：每个 episode 的对象与任务信息。

查看进度：

```bash
wc -w data/stack_plate/stack_plate/seed.txt
find data/stack_plate/stack_plate/data -name 'episode*.hdf5' | wc -l
```

## 8. 停止、恢复与日志排查

前台运行时按 `Ctrl+C` 可停止。只要保留输出目录，再次执行相同命令就会根据
`seed.txt` 和已有 HDF5 继续。

检查是否仍有采集进程：

```bash
docker compose exec robotwin bash -lc \
  'pgrep -af "collect_data.py|collect_data.sh" || true'
```

查看容器日志：

```bash
docker compose logs --tail=200 robotwin
```

停止容器但保留数据和缓存：

```bash
docker compose stop robotwin
```

重新启动：

```bash
docker compose start robotwin
```

如果出现 cuRobo 找不到 URDF 或碰撞球配置，检查以下文件中的路径是否为
`/workspace/RoboTwin/...`：

```text
assets/embodiments/aloha-agilex/curobo_left.yml
assets/embodiments/aloha-agilex/curobo_right.yml
```

如果修改了任务动作流程，应重新生成种子和 `_traj_data`，不要用新代码回放旧
轨迹。
