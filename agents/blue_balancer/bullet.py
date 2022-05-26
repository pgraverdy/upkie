#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2022 Stéphane Caron
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import logging
import os
import time
import traceback
from os import path
from typing import Any, Dict

import aiorate
import gin
import yaml
from agents.blue_balancer.whole_body_controller import WholeBodyController
from rules_python.python.runfiles import runfiles
from vulp.spine import SpineInterface


class ExampleAdvice(Exception):

    """
    Exception raised when this example is called with unexpected parameters.
    """


async def run(
    spine: SpineInterface,
    config: Dict[str, Any],
    frequency: float = 200.0,
) -> None:
    """
    Read observations and send actions to the spine.

    Args:
        spine: Interface to the spine.
        config: Configuration dictionary.
        frequency: Control frequency in Hz.
    """
    whole_body_controller = WholeBodyController(config)
    dt = 1.0 / frequency
    rate = aiorate.Rate(frequency, "controller")
    spine.start(config)
    observation = spine.get_observation()  # pre-reset observation
    while True:
        observation = spine.get_observation()
        action = whole_body_controller.cycle(observation, dt)
        spine.set_action(action)
        await rate.sleep()


if __name__ == "__main__":
    agent_dir = path.dirname(__file__)
    deez_runfiles = runfiles.Create()
    spine_path = os.path.join(
        agent_dir,
        deez_runfiles.Rlocation("upkie_locomotion/spines/bullet"),
    )

    if "-opt" not in spine_path or "-fastbuild" in spine_path:
        raise ExampleAdvice(
            "This example is meant to be called by ``bazel run -c opt`` "
            "so that the simulator performs well, but it seems the "
            'compilation mode is "fastbuild"? Go to the code and comment out '
            "this check if you know what you are doing :)"
        )

    # Gin configuration
    gin.parse_config_file(f"{agent_dir}/bullet.gin")
    gin.parse_config_file(f"{agent_dir}/kinematics.gin")
    gin.parse_config_file(f"{agent_dir}/wheel_balancer.gin")
    gin.parse_config_file(f"{agent_dir}/whole_body_controller.gin")

    # Spine configuration
    with open(f"{agent_dir}/spine.yaml", "r") as fh:
        config = yaml.safe_load(fh)

    pid = os.fork()
    if pid == 0:  # child process: spine
        spine_argv = ["--spine-frequency", "1000.0", "--show"]
        os.execvp(spine_path, ["bullet"] + spine_argv)
    else:
        time.sleep(1.0)  # wait for Bullet to start
        spine = SpineInterface()
        try:
            asyncio.run(run(spine, config))
        except KeyboardInterrupt:
            logging.info("Caught a keyboard interrupt")
        except Exception:
            logging.error("Controller raised an exception")
            print("")
            traceback.print_exc()
            print("")
        finally:
            spine.stop()
