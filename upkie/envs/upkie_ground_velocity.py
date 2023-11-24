#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2022 Stéphane Caron
# Copyright 2023 Inria
# SPDX-License-Identifier: Apache-2.0

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
from gymnasium import spaces
from numpy.typing import NDArray

from upkie.observers.base_pitch import (
    compute_base_angular_velocity_from_imu,
    compute_base_pitch_from_imu,
)
from upkie.utils.exceptions import UpkieException

from .upkie_base_env import UpkieBaseEnv


class UpkieGroundVelocity(UpkieBaseEnv):

    """!
    Environment where Upkie is used as a wheeled inverted pendulum.

    The environment id is ``UpkieGroundVelocity-v3``. Model assumptions are
    summarized in the <a
    href="https://scaron.info/robotics/wheeled-inverted-pendulum-model.html">following
    note</a>.

    @note For reinforcement learning with neural networks: the observation
    space and action space are not normalized.

    ### Action space

    The action corresponds to the ground velocity resulting from wheel
    velocities. The action vector is simply:

    <table>
        <tr>
            <td><strong>Index</strong></td>
            <td><strong>Description</strong></td>
            </tr>
        <tr>
            <td>``0``</td>
            <td>Ground velocity in [m] / [s].</td>
        </tr>
    </table>

    Note that, while this action is not normalized, [-1, 1] m/s is a reasonable
    range for ground velocities.

    ### Observation space

    Vectorized observations have the following structure:

    <table>
        <tr>
            <td><strong>Index</strong></td>
            <td><strong>Description</strong></td>
        </tr>
        <tr>
            <td>0</td>
            <td>Pitch angle of the base with respect to the world vertical, in
            radians. This angle is positive when the robot leans forward.</td>
        </tr>
        <tr>
            <td>1</td>
            <td>Position of the average wheel contact point, in meters.</td>
        </tr>
        <tr>
            <td>2</td>
            <td>Body angular velocity of the base frame along its lateral axis,
            in radians per seconds.</td>
        </tr>
        <tr>
            <td>3</td>
            <td>Velocity of the average wheel contact point, in meters per
            seconds.</td>
        </tr>
    </table>

    ### Attributes

    The environment class defines the following attributes:

    - ``fall_pitch``: Fall pitch angle, in radians.
    - ``version``: Environment version number.
    - ``wheel_radius``: Wheel radius in [m].

    """

    LEG_JOINTS = [
        f"{side}_{joint}"
        for side in ("left", "right")
        for joint in ("hip", "knee")
    ]

    @dataclass
    class RewardWeights:
        position: float = 1.0
        velocity: float = 1.0

    fall_pitch: float
    version: int = 3
    wheel_radius: float

    def __init__(
        self,
        max_ground_velocity: float = 1.0,
        reward_weights: Optional[RewardWeights] = None,
        wheel_radius: float = 0.06,
        **kwargs,
    ):
        """!
        Initialize environment.

        @param max_ground_velocity Maximum commanded ground velocity in m/s.
        @param reward_weights Coefficients before each reward term.
        @param wheel_radius Wheel radius in [m].
        @param kwargs Keyword arguments are forwarded to the parent class ctor.
        """
        super().__init__(**kwargs)

        if self.dt is None:
            raise UpkieException("This environment needs a loop frequency")

        weights: UpkieGroundVelocity.RewardWeights = (
            reward_weights
            if reward_weights is not None
            else UpkieGroundVelocity.RewardWeights()
        )

        MAX_BASE_PITCH: float = np.pi
        MAX_GROUND_POSITION: float = float("inf")
        MAX_BASE_ANGULAR_VELOCITY: float = 1000.0  # rad/s
        observation_limit = np.array(
            [
                MAX_BASE_PITCH,
                MAX_GROUND_POSITION,
                MAX_BASE_ANGULAR_VELOCITY,
                max_ground_velocity,
            ],
            dtype=np.float32,
        )

        # gymnasium.Env: observation_space
        self.observation_space = spaces.Box(
            -observation_limit,
            +observation_limit,
            shape=observation_limit.shape,
            dtype=observation_limit.dtype,
        )

        # gymnasium.Env: action_space
        action_limit = np.array([max_ground_velocity], dtype=np.float32)
        self.action_space = spaces.Box(
            -action_limit,
            +action_limit,
            shape=action_limit.shape,
            dtype=action_limit.dtype,
        )

        self.leg_positions = {}
        self.reward_weights = weights
        self.wheel_radius = wheel_radius

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> Tuple[NDArray[float], Dict]:
        """!
        Resets the environment and get an initial observation.

        @param seed Number used to initialize the environment’s internal random
            number generator.
        @param options Currently unused.
        @returns
            - ``observation``: Initial vectorized observation, i.e. an element
              of the environment's ``observation_space``.
            - ``info``: Dictionary with auxiliary diagnostic information. For
              Upkie this is the full observation dictionary sent by the spine.
        """
        return super().reset(seed=seed)

    def parse_first_observation(self, observation_dict: dict) -> None:
        """!
        Parse first observation after the spine interface is initialize.

        @param observation_dict First observation.
        """
        self.leg_positions = {
            joint: observation_dict["servo"][joint]["position"]
            for joint in self.LEG_JOINTS
        }

    def vectorize_observation(self, observation_dict: dict) -> NDArray[float]:
        """!
        Extract observation vector from a full observation dictionary.

        @param observation_dict Full observation dictionary from the spine.
        @returns Observation vector.
        """
        imu = observation_dict["imu"]
        pitch_base_in_world = compute_base_pitch_from_imu(imu["orientation"])
        angular_velocity_base_in_base = compute_base_angular_velocity_from_imu(
            observation_dict["imu"]["angular_velocity"]
        )
        ground_position = observation_dict["wheel_odometry"]["position"]
        ground_velocity = observation_dict["wheel_odometry"]["velocity"]

        obs = np.empty(4, dtype=np.float32)
        obs[0] = pitch_base_in_world
        obs[1] = ground_position
        obs[2] = angular_velocity_base_in_base[1]
        obs[3] = ground_velocity
        return obs

    def get_leg_servo_action(self) -> Dict[str, Dict[str, float]]:
        """!
        Get servo actions for each hip and knee joint.

        @returns Servo action dictionary.
        """
        return {
            joint: {
                "position": self.leg_positions[joint],
                "velocity": 0.0,
            }
            for joint in self.LEG_JOINTS
        }

    def dictionarize_action(self, action: NDArray[float]) -> dict:
        """!
        Convert action vector into a spine action dictionary.

        @param action Action vector.
        @returns Action dictionary.
        """
        ground_velocity = action[0]
        wheel_velocity = ground_velocity / self.wheel_radius
        servo_dict = self.get_leg_servo_action()
        servo_dict.update(
            {
                "left_wheel": {
                    "position": math.nan,
                    "velocity": +wheel_velocity,
                },
                "right_wheel": {
                    "position": math.nan,
                    "velocity": -wheel_velocity,
                },
            }
        )
        action_dict = {"servo": servo_dict}
        return action_dict

    def get_reward(
        self, observation: NDArray[float], action: NDArray[float]
    ) -> float:
        """!
        Get reward from observation and action.

        @param observation Observation vector.
        @param action Action vector.
        @returns Reward.
        """
        pitch = observation[0]
        ground_position = observation[1]
        angular_velocity = observation[2]
        ground_velocity = observation[3]

        tip_height = 0.58  # [m]
        tip_position = ground_position + tip_height * np.sin(pitch)
        tip_velocity = (
            ground_velocity + tip_height * angular_velocity * np.cos(pitch)
        )

        std_position = 0.05  # [m]
        position_reward = np.exp(-((tip_position / std_position) ** 2))
        velocity_penalty = -abs(tip_velocity)

        return (
            self.reward_weights.position * position_reward
            + self.reward_weights.velocity * velocity_penalty
        )
