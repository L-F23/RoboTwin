# RoboTwin 项目架构说明

本文整理 RoboTwin 的整体架构、运行链路、核心模块职责，以及如果要搭建新的测试环境，需要对接哪些接口。

## 1. 总体架构

RoboTwin 可以分成 5 层：

1. 基础资源层

   - 资产文件
   - 机器人 embodiment 配置
   - 相机配置
   - 任务配置
   - 文本描述模板
2. 仿真环境层

   - `envs/` 目录下的单个任务类
   - 负责搭建场景、摆放物体、执行动作、判定成功
3. 机器人 / 相机 / 工具层

   - `envs/robot/`
   - `envs/camera/`
   - `envs/utils/`
   - 负责机器人模型、相机观测、物体创建、随机化、动作编码等
4. 任务执行层

   - `script/collect_data.py`
   - `script/eval_policy.py`
   - 把环境、配置和策略串起来
5. 策略层

   - `policy/`
   - 负责训练、部署、推理，例如 RDT

## 2. 目录职责

### `envs/`

每个任务一个文件，例如：

- `open_laptop.py`
- `place_bread_basket.py`
- `beat_block_hammer.py`

这些任务文件通常都定义同名类，并实现：

- `setup_demo()`
- `load_actors()`
- `play_once()`
- `check_success()`

### `envs/_base_task.py`

这是所有任务环境的公共底座，负责：

- 创建桌子、墙、地面
- 加载机器人
- 加载相机
- 生成任务物体
- 处理随机化
- 采集观测
- 执行动作
- 保存轨迹和视频
- 判定任务成功

### `envs/robot/`

机器人封装层，负责：

- 机器人 URDF / 关节 / 末端执行器加载
- 规划器
- IK / 轨迹插值
- 夹爪控制

### `envs/camera/`

相机封装层，负责：

- head camera
- wrist camera
- third view
- 图像 / 深度 / 点云采集

### `envs/utils/`

通用工具，包括：

- 物体创建
- 坐标变换
- 动作封装
- 随机化采样
- 视频和 HDF5 处理

### `task_config/`

任务配置目录，通常包括：

- `_embodiment_config.yml`
- `_camera_config.yml`
- `_eval_step_limit.yml`
- `demo_clean.yml`
- `demo_randomized.yml`

### `script/`

任务运行入口：

- `collect_data.py`：采集数据
- `eval_policy.py`：评测策略
- `policy_model_server.py`：模型服务
- `add_annotation.py`、`create_object_data.py` 等辅助脚本

### `policy/`

策略实现层，包含：

- 训练
- 部署
- 推理
- 数据处理

以 RDT 为例，策略会通过统一接口和环境交互。

## 3. 运行链路

### 3.1 数据采集链路

典型流程：

```text
collect_data.sh
  -> script/collect_data.py
  -> envs/<task>.py
  -> Base_Task
  -> Robot / Camera / utils
```

`collect_data.py` 会：

1. 动态导入任务类
2. 读取任务配置
3. 读取 embodiment 配置
4. 先搜集一个能成功完成任务的 seed
5. 再回放 seed 采集正式数据
6. 导出 hdf5、mp4、scene_info 等

### 3.2 评测链路

典型流程：

```text
script/eval_policy.py
  -> policy/<policy_name>
  -> TASK_ENV.setup_demo()
  -> TASK_ENV.get_obs()
  -> policy.eval(...)
  -> TASK_ENV.take_action(...)
  -> TASK_ENV.check_success()
```

评测时，策略通过约定接口和环境交互，而不是直接耦合环境内部实现。

## 4. `Base_Task` 的核心职责

`envs/_base_task.py` 是整个系统最重要的基类之一。

### 初始化阶段

它负责：

- 创建 SAPIEN engine / scene / renderer
- 创建桌子和墙
- 加载机器人
- 加载相机
- 初始化 viewer

### 场景物体管理

它提供：

- `load_actors()`
- `get_cluttered_table()`
- `add_prohibit_area()`

### 观测与动作接口

它提供：

- `get_obs()`
- `take_action()`
- `together_close_gripper()`
- `together_open_gripper()`
- `left_move_to_pose()`
- `right_move_to_pose()`

### 数据导出

它提供：

- `_take_picture()`
- `save_traj_data()`
- `merge_pkl_to_hdf5_video()`
- `remove_data_cache()`

### 任务管理

它提供：

- `set_instruction()`
- `get_instruction()`
- `close_env()`
- `play_once()`
- `check_success()`

## 5. 单个任务文件怎么理解

以 `envs/open_laptop.py` 为例，任务文件通常只负责 4 件事：

1. `setup_demo()`

   - 调用 `super()._init_task_env_(...)`
   - 初始化通用场景
2. `load_actors()`

   - 创建这个任务的物体
   - 设置位置、姿态、随机化范围
3. `play_once()`

   - 定义一次任务演示过程
   - 通常包含抓取、移动、放置、微调
4. `check_success()`

   - 根据物体位置、姿态、夹爪状态等判断任务是否完成

## 6. 策略层与环境层的接口

以 RDT 为例，策略侧通常要求三个核心接口：

- `get_model(usr_args)`
- `eval(TASK_ENV, model, observation)`
- `reset_model(model)`

环境侧通常需要提供：

- `get_obs()`
- `take_action(action, action_type='qpos')`
- `set_instruction()`
- `check_success()`

### 常见观测格式

通常会包含：

- `observation.head_camera.rgb`
- `observation.right_camera.rgb`
- `observation.left_camera.rgb`
- `joint_action.vector`
- `endpose`
- `pointcloud`

如果你要接入现有策略，最关键的是保持观测结构一致。

## 7. 新测试环境应该怎么搭

如果你要新增一个测试环境，建议按下面的顺序做。

### 7.1 必须实现的任务接口

在 `envs/` 下新增一个任务文件，例如：

- `envs/my_new_task.py`

并定义同名类：

- `class my_new_task(Base_Task):`

至少实现：

- `setup_demo(self, **kwargs)`
- `load_actors(self)`
- `play_once(self)`
- `check_success(self)`

### 7.2 建议兼容的接口

为了兼容现有采集和评测链路，建议再保留：

- `get_obs(self)`
- `take_action(self, action, action_type='qpos')`
- `set_instruction(self, instruction=None)`
- `get_instruction(self)`
- `close_env(self, clear_cache=False)`

### 7.3 需要补的配置

通常还要补这些文件：

- `task_config/<your_task>.yml`
- `task_config/_embodiment_config.yml`
- `task_config/_camera_config.yml`
- `assets/embodiments/<name>/config.yml`
- 任务所需 mesh / urdf / usd / obj 资产

### 7.4 如果要接入现有数据采集

要让 `collect_data.py` 正常工作，任务类需要满足：

- 文件名和类名一致
- `setup_demo()` 可调用
- `play_once()` 可调用
- `check_success()` 可调用
- `get_obs()` 输出结构兼容

### 7.5 如果要接入现有策略评测

要让 `eval_policy.py` 正常工作，策略和环境要满足：

- 策略模块提供 `get_model / eval / reset_model`
- 环境提供统一观测与动作接口
- `check_success()` 能准确判定最终是否成功

## 8. 推荐的接入顺序

如果你要做一个新的测试环境，建议按这个顺序：

1. 先写任务类
2. 再写 task_config
3. 跑通 `collect_data.py`
4. 再接策略
5. 最后补描述生成和评测逻辑

## 9. 关键文件

建议重点看这些文件：

- `envs/_base_task.py`
- `envs/open_laptop.py`
- `envs/place_bread_basket.py`
- `script/collect_data.py`
- `script/eval_policy.py`
- `script/policy_model_server.py`
- `policy/RDT/deploy_policy.py`
- `task_config/demo_clean.yml`
- `task_config/demo_randomized.yml`
- `task_config/_embodiment_config.yml`
- `task_config/_camera_config.yml`

## 10. 结论

RoboTwin 的核心思想是：

- 用 `Base_Task` 统一环境骨架
- 用任务类定义具体物体和成功条件
- 用配置文件切换 embodiment、相机和随机化
- 用 `collect_data.py` 和 `eval_policy.py` 串起数据和评测
- 用 `policy/` 接外部策略模型

如果你要搭一个新的测试环境，最重要的就是：

1. 让新任务类符合 `Base_Task` 的接口约定
2. 让观测格式兼容现有策略
3. 让配置文件完整可读
4. 让 `check_success()` 足够稳定
