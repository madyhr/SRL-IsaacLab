# Copyright (c) 2022-2025, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

import math

import isaaclab.sim as sim_utils
from isaaclab.utils import configclass
from isaaclab.assets import AssetBaseCfg
from isaaclab_tasks.manager_based.moonshot.locomotion.velocity.velocity_env_cfg import LocomotionVelocityRoughEnvCfg
from isaaclab.terrains import TerrainImporterCfg
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import EventTermCfg as EventTerm

import isaaclab_tasks.manager_based.moonshot.locomotion.velocity.mdp as mdp
import isaaclab_tasks.manager_based.moonshot.utils as moonshot_utils
ISAAC_LAB_PATH = moonshot_utils.find_isaaclab_path().replace("\\","/") 

##
# Pre-defined configs
##
from isaaclab_tasks.manager_based.moonshot.descriptions.config.moonbot_cfgs import DRAGON_ARTICULATED_CFG  # isort: skip


##
# Robot Base Link Name (desired base)
##
BASE_NAME: str = "leg4link4"
WHEEL_ONLY_MODE: bool = False

@configclass
class HeroDragonRoughEnvCfg(LocomotionVelocityRoughEnvCfg):
    def __post_init__(self):
        # post init of parent
        super().__post_init__()

        self.scene.robot = DRAGON_ARTICULATED_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")
        # scale down the terrains because the robot is small
        self.scene.terrain.terrain_generator.sub_terrains["random_rough"].noise_range=(0.001, 0.03) 
        self.scene.terrain.terrain_generator.sub_terrains["random_rough"].noise_step=0.01

        # commands
        self.commands.body_velocity.body_name = BASE_NAME
        self.commands.body_velocity = mdp.UniformVelocityCommandCfg(
            asset_name="robot",
            resampling_time_range=(5, 15),
            rel_standing_envs=0.02,
            rel_heading_envs=1.0,
            heading_command=False,
            heading_control_stiffness=0.5,
            debug_vis=True,
            ranges=mdp.UniformVelocityCommandCfg.Ranges(
                lin_vel_x=(-0.12, 0.12), 
                ang_vel_z=(-math.pi/12, math.pi/12), 
                lin_vel_y=(-0.0, 0.0),
                heading=(-math.pi, math.pi)
            ),
        )

        # observations
        self.observations.policy.body_lin_vel.params["body_name"] = BASE_NAME
        self.observations.policy.body_ang_vel.params["body_name"] = BASE_NAME
        
        # actions
        self.actions.joint_vel_action.joint_names = [
            "wheel12_left_joint",
            "wheel12_right_joint",
            "wheel14_left_joint",
            "wheel14_right_joint"
        ]
        self.actions.joint_pos_action.joint_names = [
            "leg4joint.*"
        ]

        # event
        self.events.push_robot = None
        self.events.add_base_mass = None
        self.events.reset_robot_joints.params["steering_joints"] = ("leg4joint1","leg4joint7")
        self.events.reset_base.params = {
            "pose_range": {"x": (-0.0, 0.0), "y": (-0.0, 0.0), "yaw": (-math.pi, math.pi)},
            "velocity_range": {
                "x": (0.0, 0.0),
                "y": (0.0, 0.0),
                "z": (0.0, 0.0),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (0.0, 0.0),
            },
        }

        # rewards
        self.rewards.track_lin_vel_xy_exp = RewTerm(
            func=mdp.track_lin_vel_xy_exp, 
            weight=1.0, 
            params= {
                "command_name": "body_velocity",
                "std": math.sqrt(0.01)
            }
        )
        self.rewards.track_ang_vel_z_exp = RewTerm(
            func=mdp.track_ang_vel_z_exp, 
            weight=1.0, 
            params= {
                "command_name": "body_velocity",
                "std": math.sqrt(0.01)
            }
        )
        self.rewards.dof_torques_l2.func = mdp.joint_torques_dragon_l2
        self.rewards.dof_torques_l2.weight = -1.0e-4
        self.rewards.dof_acc_l2.weight = -2.5e-7
        self.rewards.upright_wheel_bodies = None

        # terminations
        self.terminations.base_contact.params["sensor_cfg"].body_names = "leg4link.*"

        # curriculum
        self.curriculum.terrain_levels = None
        # self.curriculum.terrain_levels.params["body_name"] = BASE_NAME

        # wheel only mode toggle in case of no position controlled leg joints
        if WHEEL_ONLY_MODE:
            self.actions.joint_pos_action = None
            self.events.reset_robot_joints = None
            self.rewards.dof_torques_l2 = None

@configclass
class HeroDragonRoughEnvCfg_PLAY(HeroDragonRoughEnvCfg):
    def __post_init__(self):
        # post init of parent
        super().__post_init__()

        # make a smaller scene for play
        # self.scene.num_envs = 50
        self.scene.env_spacing = 2.5
        # spawn the robot randomly in the grid (instead of their terrain levels)
        self.scene.terrain.max_init_terrain_level = None
        # reduce the number of terrains to save memory
        if self.scene.terrain.terrain_generator is not None:
            self.scene.terrain.terrain_generator.num_rows = 5
            self.scene.terrain.terrain_generator.num_cols = 5
            self.scene.terrain.terrain_generator.curriculum = False

        self.commands.body_velocity.ranges.lin_vel_x = (0.1, 0.1)
        self.commands.body_velocity.ranges.lin_vel_y = (0.0, 0.0)
        self.commands.body_velocity.ranges.ang_vel_z = (0.0, 0.0)
        # disable randomization for play
        self.observations.policy.enable_corruption = False
        # remove random pushing event, torques and random position of joint1,7 (steering)
        self.events.base_external_force_torque = None
        self.events.push_robot = None
        self.events.reset_robot_joints.params["position_range"] = (-0.0,0.0)

@configclass
class HeroDragonMoonEnvCfg_PLAY(HeroDragonRoughEnvCfg):
    def __post_init__(self):
        # post init of parent
        super().__post_init__()
        self.episode_length_s = 20.0
        self.sim.gravity = (0,0,-1.62)
        self.scene.light = AssetBaseCfg(
            prim_path="/World/light",
            spawn=sim_utils.DistantLightCfg(color=(0.75, 0.75, 0.75), intensity=15000.0),
            init_state=AssetBaseCfg.InitialStateCfg(rot = (0.52133, 0.47771, 0.47771, 0.52133))
        )

        self.scene.terrain = TerrainImporterCfg(
            prim_path="/World/ground",
            terrain_type="usd",
            usd_path = ISAAC_LAB_PATH + "/source/isaaclab_tasks/isaaclab_tasks/manager_based/moonshot/descriptions/usd/terrain/petavius_crater.usd",
            collision_group=-1,
            debug_vis=False,
        )

        self.commands.body_velocity.ranges.lin_vel_x = (0.12, 0.12)
        self.commands.body_velocity.ranges.lin_vel_y = (0.0, 0.0)
        self.commands.body_velocity.ranges.ang_vel_z = (0.0, 0.0)

        self.viewer.resolution = (1920,1080)

        # self.viewer.eye = (8.0, 8.0, 4.5) # basic view
        # self.viewer.eye = (0.0, 0.0, 27.0) # bird eye view

        # make viewer follow robot
        self.viewer.origin_type = "asset_body"
        self.viewer.asset_name = "robot"
        self.viewer.body_name = BASE_NAME

        # self.viewer.eye = (0.0, 0.0, 4.0) # for top down view 
        self.viewer.eye = (3.0, 3.0, 2.0) # for sideways view 

        # make a smaller scene for play
        self.scene.num_envs = 4
        self.scene.env_spacing = 6.5
        
        self.curriculum.terrain_levels = None

        # disable randomization for play
        self.observations.policy.enable_corruption = False
        # remove random pushing event
        self.events.base_external_force_torque = None
        self.events.push_robot = None