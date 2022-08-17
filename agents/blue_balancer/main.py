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

import argparse
import asyncio
import logging
import traceback
import time
from os import path
from typing import Any, Dict

import aiorate
import gin
import yaml
from agents.blue_balancer.whole_body_controller import WholeBodyController
from mpacklog.python import AsyncLogger
from utils.realtime import configure_cpu
from vulp.spine import SpineInterface


def parse_command_line_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-c",
        "--config",
        metavar="config",
        help="Agent configuration to apply",
        default="default",
        type=str,
        required=False,
        choices=["default", "bullet", "pi3hat"],
    )
    return parser.parse_args()


async def run(
    spine: SpineInterface,
    config: Dict[str, Any],
    logger: AsyncLogger,
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
    debug: Dict[str, Any] = {}
    dt = 1.0 / frequency
    rate = aiorate.Rate(frequency, "controller")
    spine.start(config)
    observation = spine.get_observation()  # pre-reset observation
    while True:
        observation = spine.get_observation()
        action = whole_body_controller.cycle(observation, dt)
        action_time = time.time()
        spine.set_action(action)
        debug["rate"] = {
            "measured_period": rate.measured_period,
            "slack": rate.slack,
        }
        await logger.put(
            {
                "action": action,
                "debug": debug,
                "observation": observation,
                "time": action_time,
            }
        )
        await rate.sleep()


async def main(spine, config: Dict[str, Any], logger: AsyncLogger):
    await asyncio.gather(
        run(spine, config, logger),
        logger.write(),
        return_exceptions=False,  # make sure exceptions are raised
    )


if __name__ == "__main__":
    args = parse_command_line_arguments()
    agent_dir = path.dirname(__file__)

    # Gin configuration
    gin.parse_config_file(f"{agent_dir}/kinematics.gin")
    gin.parse_config_file(f"{agent_dir}/wheel_balancer.gin")
    gin.parse_config_file(f"{agent_dir}/whole_body_controller.gin")
    if args.config == "default":
        logging.warning('No configuration specified, assuming "bullet"')
        args.config = "bullet"
    if args.config == "pi3hat":
        gin.parse_config_file(f"{agent_dir}/pi3hat.gin")
    elif args.config == "bullet":
        gin.parse_config_file(f"{agent_dir}/bullet.gin")

    # Spine configuration
    with open(f"{agent_dir}/spine.yaml", "r") as fh:
        config = yaml.safe_load(fh)
    if args.config == "pi3hat":
        configure_cpu(cpu=3)

    logger = AsyncLogger("/dev/shm/brain.mpack")
    spine = SpineInterface()
    try:
        asyncio.run(main(spine, config, logger))
    except KeyboardInterrupt:
        logging.info("Caught a keyboard interrupt")
    except Exception:
        logging.error("Controller raised an exception")
        print("")
        traceback.print_exc()
        print("")

    logging.info("Stopping the spine")
    try:
        spine.stop()
    except Exception:
        logging.error("Error while stopping the spine!")
        print("")
        traceback.print_exc()
        print("")
