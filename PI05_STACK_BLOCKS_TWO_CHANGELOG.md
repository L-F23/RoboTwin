# Pi0.5 `stack_blocks_two` 变更记录

本文记录本次 `stack_blocks_two` 数据采集、Pi0.5 LoRA 微调、基线评测和控制侧优化过程中产生的改动。

说明：

- 仅记录本次任务实际做出的改动，不包含工作区中原本存在的其他未提交修改。
- 代码改动会列出具体文件；改动较多时只概括核心逻辑。
- 数据、checkpoint 和视频属于运行生成物，也在文中单独记录。
- 后续每次继续修改或评测时，应在本文末尾追加记录。

---

## 2026-07-16：数据采集与转换

### 1. 采集 `stack_blocks_two` 专家数据

执行：

```bash
docker compose run --rm robotwin \
  bash collect_data.sh stack_blocks_two demo_clean 0
```

结果：

- 搜索 51 个随机种子，得到 50 条成功示范。
- 原始轨迹共 50 个 HDF5 文件。
- 原始数据约 858 MB。

生成物：

```text
data/stack_blocks_two/demo_clean/data/
data/stack_blocks_two/demo_clean/video/
data/stack_blocks_two/demo_clean/instructions/
data/stack_blocks_two/demo_clean/_traj_data/
```

本步骤没有修改采集脚本源码。

### 2. 转换为 Pi0.5/LeRobot 数据

执行：

```bash
cd policy/pi05
uv run python scripts/process_data.py stack_blocks_two demo_clean 50

mkdir -p training_data/stack_blocks_two_demo_clean
cp -a processed_data/stack_blocks_two-demo_clean-50 \
  training_data/stack_blocks_two_demo_clean/

bash generate.sh \
  ./training_data/stack_blocks_two_demo_clean/ \
  stack_blocks_two_demo_clean_repo
```

生成物：

```text
policy/pi05/processed_data/stack_blocks_two-demo_clean-50/
policy/pi05/training_data/stack_blocks_two_demo_clean/
~/.cache/huggingface/lerobot/stack_blocks_two_demo_clean_repo/
```

数据统计：

- 50 个 episodes。
- LeRobot 数据共 15,661 帧。
- 50 FPS。
- 38 种语言提示。

本步骤没有修改转换脚本源码。

---

## 2026-07-16：Pi0.5 LoRA 训练配置

### 3. 修改训练配置

改动文件：

```text
policy/pi05/src/openpi/training/config.py
```

改动摘要：

- 将 `pi05_base_aloha_lora` 的数据集从占位值改为
  `stack_blocks_two_demo_clean_repo`。
- 基础模型地址从 S3 改为可访问的 GCS：
  `gs://openpi-assets/checkpoints/pi05_base/params`。
- 单卡 batch size 从 32 调整为 4。
- 训练步数从 30,000 调整为 5,000。
- warmup 设置为 500 steps，cosine decay 设置为 5,000 steps。
- 每 1,000 steps 保存一次。
- 本轮只保留最终 checkpoint。

备注：

- 本次实际训练前约 1,000 steps 使用过 `batch_size=8`，恢复后使用
  `batch_size=4` 完成剩余步骤。
- 当前仓库配置固定为 `batch_size=4`，用于单张 RTX 4090。

### 4. 计算 normalization statistics

执行：

```bash
cd policy/pi05
uv run scripts/compute_norm_stats.py \
  --config-name pi05_base_aloha_lora
```

生成物：

```text
policy/pi05/assets/pi05_base_aloha_lora/
  stack_blocks_two_demo_clean_repo/norm_stats.json
```

### 5. 缓存基础模型

基础 Pi0.5 参数约 12.4 GB，缓存位置：

```text
~/.cache/openpi/openpi-assets/checkpoints/pi05_base/params/
```

本步骤没有修改模型源码。

---

## 2026-07-16：训练与 checkpoint 兼容处理

### 6. 适配 data loader 接口

改动文件：

```text
policy/pi05/scripts/train.py
```

改动摘要：

- 移除传给 `create_data_loader` 的重复 `num_workers` 参数。
- 当前 data loader 会直接从训练配置读取该值，重复传参会导致训练启动失败。

### 7. 适配 Orbax 0.11 checkpoint 保存接口

改动文件：

```text
policy/pi05/src/openpi/training/checkpoints.py
```

改动摘要：

- 移除新版本 Orbax 中已不存在的
  `orbax.checkpoint.future` 依赖。
- callback 元数据改为通过 `asyncio.to_thread` 完成写入。
- 写入结束后返回空 future 列表。

验证：

- checkpoint 在 100/200 steps 做过保存和恢复冒烟测试。
- 最终 5,000-step checkpoint 成功原子提交。

### 8. 安装本地 CuRobo

执行：

```bash
cd policy/pi05
uv pip install -e ../../envs/curobo
```

该操作修改 Pi0.5 的本地虚拟环境，没有修改 CuRobo 源码。

### 9. 执行 LoRA 轻量微调

训练方式：

- 配置：`pi05_base_aloha_lora`。
- 类型：LoRA 轻量微调，不是全量微调。
- GPU：单张 RTX 4090。
- 训练步数：5,000。
- 最终 loss：约 0.0022～0.0027。

生成物：

```text
policy/pi05/checkpoints/pi05_base_aloha_lora/
  stack_blocks_two_demo_clean_pi05_lora/5000/
```

checkpoint 大约 15 GB，包含：

```text
assets/
params/
train_state/
_CHECKPOINT_METADATA
```

---

## 2026-07-16：基线评测兼容处理

### 10. 修复冻结 DataConfig 的更新方式

改动文件：

```text
policy/pi05/src/openpi/policies/policy_config.py
```

改动摘要：

- `DataConfig` 是 frozen dataclass，不能直接修改 `asset_id`。
- 改为使用 `dataclasses.replace` 生成带新 `asset_id` 的配置。
- 该修改使评测能够加载 checkpoint 内对应数据集的 normalization statistics。

### 11. 修正 CuRobo 资源路径

改动文件：

```text
assets/embodiments/aloha-agilex/curobo_left.yml
assets/embodiments/aloha-agilex/curobo_right.yml
```

改动摘要：

- 将原 Docker `/workspace/RoboTwin/...` 资源路径改为当前主机仓库绝对路径。
- 修正 URDF、左臂 collision spheres 和右臂 collision spheres 路径。

当前路径前缀：

```text
/home/ubuntu/Desktop/Liutong/RoboTwin/
```

### 12. 更新部署 checkpoint

改动文件：

```text
policy/pi05/deploy_policy.yml
```

基线阶段改动：

- `checkpoint_id` 从默认 30,000 改为本次训练得到的 5,000。
- 基线评测时 `pi0_step=50`。

### 13. 改善评测异常日志

改动文件：

```text
script/eval_policy.py
```

改动摘要：

- 环境初始化异常时输出 `repr(e)`，使错误类型和消息可见。
- 该改动用于定位评测启动阶段的路径和依赖问题。

### 14. Warp/CuRobo 运行兼容

评测命令增加：

```bash
PYTHONPATH=compat:.
```

作用：

- 加载仓库中的 `compat/sitecustomize.py`。
- 恢复当前 Warp 版本下 CuRobo 所需的 `warp.torch` 兼容入口。

本项未修改 Pi0.5 模型代码。

---

## 2026-07-16：基线评测结果

基线配置：

```text
checkpoint: 5000
pi0_step: 50
temporal ensemble: disabled
instruction_type: unseen
test seeds: 100000～100099
```

结果：

```text
Success: 54/100
Success rate: 54.0%
```

结果目录：

```text
eval_result/stack_blocks_two/pi05/demo_clean/
  stack_blocks_two_demo_clean_pi05_lora/
  2026-07-16 20:56:43/
```

目录中包含 `_result.txt` 和 100 个评测视频。

---

## 2026-07-17：第一轮控制侧调整

目标：

- 保持 5,000-step checkpoint 不变。
- 只调整推理控制，隔离训练收敛程度与 action chunk 切换对结果的影响。
- 缩短开环执行长度，并降低重规划边界的动作跳变。

### 15. 实现 overlapping action-plan temporal ensemble

改动文件：

```text
policy/pi05/pi_model.py
```

改动摘要：

- `PI0` 新增 `temporal_ensemble` 和 `temporal_ensemble_decay` 配置。
- 新增 `get_action_chunk()`：
  - 保存仍覆盖当前控制时刻的历史 action plans；
  - 对新旧计划中指向同一未来时刻的机械臂关节目标进行指数加权；
  - 最新计划权重最高；
  - 左右夹爪使用最新计划，不参与平均；
  - 自动清除已经过期的历史计划。
- reset 时同时清空 action-plan 历史和控制步计数。
- 非 ensemble 模式仍兼容原来的截取行为。

### 16. 将部署入口接入 ensemble

改动文件：

```text
policy/pi05/deploy_policy.py
```

改动摘要：

- 从 YAML/CLI 读取 `temporal_ensemble` 和
  `temporal_ensemble_decay`。
- 执行动作时改为调用 `model.get_action_chunk()`。

### 17. 更新第一轮控制参数

改动文件：

```text
policy/pi05/deploy_policy.yml
```

当前配置：

```yaml
checkpoint_id: 5000
pi0_step: 20
temporal_ensemble: true
temporal_ensemble_decay: 0.5
test_num: 20
```

相对基线：

- 每次开环执行长度从 50 降为 20。
- 每 20 步基于最新观测重新推理。
- 启用重叠计划指数加权。

### 18. 支持可配置的评测次数

改动文件：

```text
script/eval_policy.py
```

改动摘要：

- `test_num` 从固定 100 改为从 YAML/CLI 读取。
- 未配置时仍默认 100。
- 对非正数增加参数校验。
- 便于先用固定 20 seeds 筛选，再对最佳配置执行 100 次正式评测。

### 19. 控制侧代码验证

已完成：

- Python 语法编译检查。
- temporal ensemble 数值单元测试。
- action chunk shape 检查。
- 新旧 action plan 权重检查。
- gripper 使用最新计划检查。
- reset 状态清理检查。

### 20. 相同前 20 seeds 对照结果

基线：

```text
pi0_step=50
temporal ensemble=false
Success: 11/20
Success rate: 55.0%
```

调整后：

```text
pi0_step=20
temporal ensemble=true
temporal_ensemble_decay=0.5
Success: 15/20
Success rate: 75.0%
```

初步成功率绝对提升 20 个百分点。

调整后结果目录：

```text
eval_result/stack_blocks_two/pi05/demo_clean/
  stack_blocks_two_demo_clean_pi05_lora_step20_te/
  2026-07-17 10:40:26/
```

### 21. 视频运动指标对照

使用相同前 20 个种子的评测视频，计算相邻帧灰度运动变化：

| 指标 | 基线 step50 | step20 + ensemble |
| --- | ---: | ---: |
| 整体运动变化均值 | 2.2962 | 2.1142 |
| 整体运动变化 p95 | 7.8786 | 7.3043 |
| chunk 边界运动均值 | 2.8846 | 2.2687 |
| chunk 边界运动 p50 | 1.7406 | 1.2534 |
| chunk 边界/普通位置均值比 | 1.2695 | 1.0818 |

结论：

- 整体运动变化均值下降约 7.9%。
- chunk 边界相对尖峰由约 1.27 倍下降到约 1.08 倍。
- 20-seed 筛选同时提高成功率并降低视频中的边界抖动。

---

## 2026-07-17：完整 100 次调整后评测

状态：已完成，评测进程正常退出。

配置：

```text
checkpoint: 5000
pi0_step: 20
temporal ensemble: enabled
temporal_ensemble_decay: 0.5
instruction_type: unseen
test_num: 100
```

结果目录：

```text
eval_result/stack_blocks_two/pi05/demo_clean/
  stack_blocks_two_demo_clean_pi05_lora_step20_te_full100/
  2026-07-17 11:02:17/
```

最终结果：

```text
Success: 84/100
Success rate: 84.0%
```

与基线对比：

| 配置 | 成功数 | 成功率 |
| --- | ---: | ---: |
| checkpoint 5000，step50，无 ensemble | 54/100 | 54.0% |
| checkpoint 5000，step20，temporal ensemble | 84/100 | 84.0% |

成功率绝对提升 30 个百分点。该对照没有重新训练模型，使用的是同一个
5,000-step checkpoint，因此提升来自本轮控制和重规划策略调整。

完整 100 条视频运动指标：

| 指标 | 基线 step50 | step20 + ensemble | 变化 |
| --- | ---: | ---: | ---: |
| 整体运动变化均值 | 2.4153 | 2.2077 | -8.6% |
| 整体运动变化 p95 | 7.9600 | 7.3832 | -7.2% |
| chunk 边界运动均值 | 2.8786 | 2.3561 | -18.2% |
| chunk 边界运动 p50 | 1.8641 | 1.3806 | -25.9% |
| chunk 边界运动 p95 | 7.9963 | 7.2818 | -8.9% |
| chunk 边界/普通位置均值比 | 1.2012 | 1.0752 | -10.5% |
| 平均 episode 帧数 | 550.06 | 387.06 | -29.6% |

完整性检查：

- `_result.txt` 已生成，内容为 `0.84`。
- `episode0.mp4`～`episode99.mp4` 共 100 个视频，数量检查通过。
- 结果目录和视频均与基线分开保存，没有覆盖原评测。

结论：

- 在不重新训练的前提下，成功率由 54% 提升到 84%。
- 整体运动变化和 chunk 边界运动尖峰均下降。
- 原抖动问题的主要来源之一确实是 50-step 开环执行及新旧 action
  chunk 的边界不连续，而不只是训练未收敛。

---

## 文档改动

### 22. 更新基础运行说明

改动文件：

```text
BASIC.md
```

改动摘要：

- 保留原 Isaac Sim 基础说明。
- 增加从 `collect_data`、数据转换、normalization statistics、LoRA 训练到
  100 次基线评测的完整可复现流程。
- 记录训练配置、checkpoint、结果文件和兼容性处理。

### 23. 新增本变更日志

新增文件：

```text
PI05_STACK_BLOCKS_TWO_CHANGELOG.md
```

作用：

- 按时间顺序记录每一次源码、配置和运行产物改动。
- 为后续训练延长、控制参数 ablation 和正式评测持续追加结果。
