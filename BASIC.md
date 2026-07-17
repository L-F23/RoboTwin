
• Isaac Sim 已通过 robotwin:latest 成功启动。

- 容器名称：robotwin-isaac-sim
- 显卡：RTX 4090，Vulkan/CUDA 已识别
- 日志状态：app ready
- 图形界面：当前桌面 DISPLAY=:1
- 主机 Isaac Sim 5.1 以只读方式挂载，缓存使用独立 Docker volumes
- 原始 robotwin:latest 镜像未被修改

  常用命令：

  docker logs -f robotwin-isaac-sim
  docker restart robotwin-isaac-sim
  docker stop robotwin-isaac-sim

---

## `stack_blocks_two`：从采集数据到 Pi0.5 评测

以下内容记录 2026-07-16 在单张 RTX 4090 上完成的实际流程。所有命令默认从仓库根目录执行：

```bash
cd /home/ubuntu/Desktop/Liutong/RoboTwin
```

### 执行结果概览

| 项目 | 本次配置或结果 |
| --- | --- |
| 任务 | `stack_blocks_two` |
| 任务配置 | `demo_clean`、`aloha-agilex`、3 个 RGB 相机 |
| 采集数据 | 50 条成功示范，共 15,661 帧 |
| 训练方式 | Pi0.5 LoRA 轻量微调，不是全量微调 |
| 训练配置 | `pi05_base_aloha_lora` |
| 训练步数 | 5,000 steps |
| 最终训练 loss | 约 0.0022～0.0027 |
| 评测设置 | `instruction_type=unseen`，100 个随机种子 |
| 评测结果 | 54/100 成功，成功率 54.0% |

### 1. 使用 `collect_data` 采集 50 条示范

通过 RoboTwin Docker 环境在 GPU 0 上采集：

```bash
docker compose run --rm robotwin \
  bash collect_data.sh stack_blocks_two demo_clean 0
```

采集时先搜索可成功执行的随机种子。本次共尝试 51 个种子，得到 50 条成功轨迹、1 次失败尝试。

原始数据目录：

```text
/home/ubuntu/Desktop/Liutong/RoboTwin/data/stack_blocks_two/demo_clean
```

其中包含：

```text
data/           # 50 个 HDF5 轨迹
video/          # 专家演示视频
instructions/   # 语言指令
_traj_data/     # 轨迹中间数据
```

可用下面的命令确认轨迹数量：

```bash
find data/stack_blocks_two/demo_clean/data -name 'episode*.hdf5' | wc -l
# 50
```

### 2. 将采集数据转换为 Pi0.5 输入格式

进入 Pi0.5 目录并使用其 `uv` 环境运行转换脚本：

```bash
cd policy/pi05
uv run python scripts/process_data.py stack_blocks_two demo_clean 50
```

转换后的 50 条 episode 位于：

```text
policy/pi05/processed_data/stack_blocks_two-demo_clean-50
```

把数据放入生成 LeRobot 数据集所使用的目录：

```bash
mkdir -p training_data/stack_blocks_two_demo_clean
cp -a processed_data/stack_blocks_two-demo_clean-50 \
  training_data/stack_blocks_two_demo_clean/
```

### 3. 生成 LeRobot 数据集

仍在 `policy/pi05` 目录中执行：

```bash
bash generate.sh \
  ./training_data/stack_blocks_two_demo_clean/ \
  stack_blocks_two_demo_clean_repo
```

生成的数据集位置：

```text
~/.cache/huggingface/lerobot/stack_blocks_two_demo_clean_repo
```

本次生成结果为 50 个 episodes、15,661 帧、50 FPS，包含 38 种语言提示。

如果需要从头重新生成同名数据集，应先备份或删除上述缓存目录，避免旧缓存与新数据混用。

### 4. 配置 Pi0.5 LoRA 微调

单张 48 GB RTX 4090 不适合进行 Pi0.5 全量微调，因此本次使用 `pi05_base_aloha_lora` 轻量微调。配置位于：

```text
policy/pi05/src/openpi/training/config.py
```

本次使用的关键参数如下：

```python
name = "pi05_base_aloha_lora"
repo_id = "stack_blocks_two_demo_clean_repo"
batch_size = 4
num_train_steps = 5000
save_interval = 1000
warmup_steps = 500
decay_steps = 5000
fsdp_devices = 1
weight_loader = "gs://openpi-assets/checkpoints/pi05_base/params"
```

基础 Pi0.5 参数约 12.4 GB，本次缓存在：

```text
~/.cache/openpi/openpi-assets/checkpoints/pi05_base/params
```

说明：本次 checkpoint 的前约 1,000 steps 曾以 `batch_size=8` 运行，恢复训练后改为 `batch_size=4` 完成剩余步骤；仓库当前配置固定为 `batch_size=4`，更适合单卡复跑。

### 5. 计算 normalization statistics

```bash
cd /home/ubuntu/Desktop/Liutong/RoboTwin/policy/pi05
uv run scripts/compute_norm_stats.py \
  --config-name pi05_base_aloha_lora
```

统计文件位于：

```text
policy/pi05/assets/pi05_base_aloha_lora/
  stack_blocks_two_demo_clean_repo/norm_stats.json
```

### 6. 开始 LoRA 微调

如环境中还没有安装本地 CuRobo，可先执行一次：

```bash
cd /home/ubuntu/Desktop/Liutong/RoboTwin/policy/pi05
uv sync
uv pip install -e ../../envs/curobo
```

在 GPU 0 上启动训练。W&B 使用离线模式，不要求登录：

```bash
WANDB_MODE=offline \
  bash finetune.sh \
  pi05_base_aloha_lora \
  stack_blocks_two_demo_clean_pi05_lora \
  0
```

`finetune.sh` 默认带有 `--overwrite`，重复执行同名实验前应确认是否允许覆盖。需要从已有 checkpoint 恢复时，不要使用 `--overwrite`。

最终 5,000-step checkpoint 大约 15 GB，位置为：

```text
/home/ubuntu/Desktop/Liutong/RoboTwin/policy/pi05/checkpoints/
  pi05_base_aloha_lora/
  stack_blocks_two_demo_clean_pi05_lora/
  5000
```

checkpoint 内包含 `assets`、`params`、`train_state` 和 `_CHECKPOINT_METADATA`。

### 7. 配置并执行评测

`policy/pi05/deploy_policy.yml` 中使用：

```yaml
instruction_type: unseen
checkpoint_id: 5000
pi0_step: 50
```

本次从仓库根目录执行以下命令。`PYTHONPATH=compat:.` 用于加载当前 Warp/CuRobo 兼容层：

```bash
cd /home/ubuntu/Desktop/Liutong/RoboTwin

PYTHONPATH=compat:. \
CUDA_VISIBLE_DEVICES=0 \
XLA_PYTHON_CLIENT_MEM_FRACTION=0.4 \
PYTHONWARNINGS=ignore::UserWarning \
uv run --project policy/pi05 python script/eval_policy.py \
  --config policy/pi05/deploy_policy.yml \
  --overrides \
  --task_name stack_blocks_two \
  --task_config demo_clean \
  --train_config_name pi05_base_aloha_lora \
  --model_name stack_blocks_two_demo_clean_pi05_lora \
  --ckpt_setting stack_blocks_two_demo_clean_pi05_lora \
  --seed 0 \
  --policy_name pi05
```

评测共执行 100 条 rollout，对应种子 `100000`～`100099`。最终结果：

```text
Success: 54/100
Success rate: 54.0%
Instruction type: unseen
```

结果汇总文件：

```text
/home/ubuntu/Desktop/Liutong/RoboTwin/eval_result/stack_blocks_two/pi05/
  demo_clean/stack_blocks_two_demo_clean_pi05_lora/
  2026-07-16 20:56:43/_result.txt
```

同一目录内还保存了 `episode0.mp4`～`episode99.mp4` 共 100 个评测视频。

### 8. 本次运行涉及的兼容性处理

以下调整已经保存在当前工作区，复跑时无需再次手工修改：

- `policy/pi05/scripts/train.py`：适配当前 data loader 的参数接口。
- `policy/pi05/src/openpi/training/checkpoints.py`：适配当前 Orbax 的异步保存接口。
- `policy/pi05/src/openpi/policies/policy_config.py`：使用 `dataclasses.replace` 更新冻结的 data config。
- `assets/embodiments/aloha-agilex/curobo_left.yml` 和 `curobo_right.yml`：使用当前主机上的 RoboTwin 资源路径。
- 评测命令通过 `PYTHONPATH=compat:.` 提供当前 Warp 版本所需的兼容入口。
