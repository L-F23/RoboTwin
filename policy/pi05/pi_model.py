#!/home/lin/software/miniconda3/envs/aloha/bin/python
# -- coding: UTF-8
"""
#!/usr/bin/python3
"""
import json
import sys
import jax
import numpy as np
from openpi.models import model as _model
from openpi.policies import aloha_policy
from openpi.policies import policy_config as _policy_config
from openpi.shared import download
from openpi.training import config as _config
from openpi.training import data_loader as _data_loader

import cv2
from PIL import Image

from openpi.models import model as _model
from openpi.policies import policy_config as _policy_config
from openpi.shared import download
from openpi.training import config as _config
from openpi.training import data_loader as _data_loader
import os

class PI0:

    def __init__(
        self,
        train_config_name,
        model_name,
        checkpoint_id,
        pi0_step,
        temporal_ensemble=False,
        temporal_ensemble_decay=0.5,
    ):
        self.train_config_name = train_config_name
        self.model_name = model_name
        self.checkpoint_id = checkpoint_id

        specified_path = f"policy/pi05/checkpoints/{self.train_config_name}/{self.model_name}/{self.checkpoint_id}/assets/"
        entries = os.listdir(specified_path)
        assets_id = entries[0]

        config = _config.get_config(self.train_config_name)
        self.policy = _policy_config.create_trained_policy(
            config,
            f"policy/pi05/checkpoints/{self.train_config_name}/{self.model_name}/{self.checkpoint_id}",
            robotwin_repo_id=assets_id,
            )
        print("loading model success!")
        self.img_size = (224, 224)
        self.observation_window = None
        self.pi0_step = pi0_step
        self.temporal_ensemble = temporal_ensemble
        self.temporal_ensemble_decay = temporal_ensemble_decay
        self._action_plans = []
        self._control_step = 0

    # set img_size
    def set_img_size(self, img_size):
        self.img_size = img_size

    # set language randomly
    def set_language(self, instruction):
        self.instruction = instruction
        print(f"successfully set instruction:{instruction}")

    # Update the observation window buffer
    def update_observation_window(self, img_arr, state):
        img_front, img_right, img_left, puppet_arm = (
            img_arr[0],
            img_arr[1],
            img_arr[2],
            state,
        )
        img_front = np.transpose(img_front, (2, 0, 1))
        img_right = np.transpose(img_right, (2, 0, 1))
        img_left = np.transpose(img_left, (2, 0, 1))

        self.observation_window = {
            "state": state,
            "images": {
                "cam_high": img_front,
                "cam_left_wrist": img_left,
                "cam_right_wrist": img_right,
            },
            "prompt": self.instruction,
        }

    def get_action(self):
        assert self.observation_window is not None, "update observation_window first!"
        return self.policy.infer(self.observation_window)["actions"]

    def get_action_chunk(self):
        """Predict a chunk and optionally blend overlapping action plans."""
        new_actions = np.asarray(self.get_action())
        chunk_size = min(self.pi0_step, len(new_actions))
        if chunk_size <= 0:
            raise ValueError(f"pi0_step must be positive, got {self.pi0_step}")

        if not self.temporal_ensemble:
            self._control_step += chunk_size
            return new_actions[:chunk_size]

        start_step = self._control_step
        self._action_plans = [
            (plan_start, plan)
            for plan_start, plan in self._action_plans
            if plan_start + len(plan) > start_step
        ]
        self._action_plans.append((start_step, new_actions))

        blended_actions = []
        arm_indices = np.array([*range(6), *range(7, 13)])
        gripper_indices = np.array([6, 13])

        for offset in range(chunk_size):
            absolute_step = start_step + offset
            candidates = []
            for plan_start, plan in reversed(self._action_plans):
                plan_index = absolute_step - plan_start
                if 0 <= plan_index < len(plan):
                    candidates.append(plan[plan_index])

            candidate_array = np.asarray(candidates)
            ages = np.arange(len(candidate_array), dtype=np.float64)
            weights = np.exp(-self.temporal_ensemble_decay * ages)
            weights /= weights.sum()

            action = candidate_array[0].copy()
            action[arm_indices] = np.sum(
                candidate_array[:, arm_indices] * weights[:, None], axis=0
            )
            # Gripper transitions are discrete, so use the latest plan directly.
            action[gripper_indices] = candidate_array[0, gripper_indices]
            blended_actions.append(action)

        self._control_step += chunk_size
        return np.asarray(blended_actions)

    def reset_obsrvationwindows(self):
        self.instruction = None
        self.observation_window = None
        self._action_plans = []
        self._control_step = 0
        print("successfully unset obs and language intruction")
