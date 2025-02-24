# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

import math
from dataclasses import MISSING

import isaaclab.sim as sim_utils
from isaaclab.assets import AssetBaseCfg
from isaaclab.envs import ManagerBasedRLEnvCfg
from isaaclab.managers import CurriculumTermCfg as CurrTerm
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.terrains import TerrainImporterCfg
from isaaclab.utils import configclass
from isaaclab.sensors import ContactSensorCfg, RayCasterCfg, patterns
from isaaclab.utils.noise import AdditiveUniformNoiseCfg as Unoise

import isaaclab_tasks.manager_based.moonshot.navigation.mdp as mdp

from isaaclab.utils.assets import ISAAC_NUCLEUS_DIR, ISAACLAB_NUCLEUS_DIR
##
# Pre-defined configs
##
from isaaclab_tasks.manager_based.moonshot.descriptions.config.moonbot_cfgs import VEHICLE_CFG  
from isaaclab_tasks.manager_based.moonshot.navigation.terrain.rough import ROUGH_TERRAINS_CFG

@configclass
class MySceneCfg(InteractiveSceneCfg):
    """Configuration for the terrain scene with an Moonbot Vehicle robot."""

    # terrain (flat plane)
    terrain = TerrainImporterCfg(
        prim_path="/World/ground",
        terrain_type="plane",
        collision_group=-1,
        physics_material=sim_utils.RigidBodyMaterialCfg(
            friction_combine_mode="average",
            restitution_combine_mode="average",
            static_friction=1.0,
            dynamic_friction=1.0,
            restitution=0.0,
        ),
        debug_vis=False,
    )
    # terrain (rough)
    # terrain = TerrainImporterCfg(
    #     prim_path="/World/ground",
    #     terrain_type="generator",
    #     terrain_generator=ROUGH_TERRAINS_CFG,
    #     max_init_terrain_level=5,
    #     collision_group=-1,
    #     physics_material=sim_utils.RigidBodyMaterialCfg(
    #         friction_combine_mode="multiply",
    #         restitution_combine_mode="multiply",
    #         static_friction=1.0,
    #         dynamic_friction=1.0,
    #     ),
    #     visual_material=sim_utils.MdlFileCfg(
    #         mdl_path=f"{ISAACLAB_NUCLEUS_DIR}/Materials/TilesMarbleSpiderWhiteBrickBondHoned/TilesMarbleSpiderWhiteBrickBondHoned.mdl",
    #         project_uvw=True,
    #         texture_scale=(0.25, 0.25),
    #     ),
    #     debug_vis=False,
    # )
    # robot
    robot = VEHICLE_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot") # type: ignore

    # sensors

    # height_scanner = RayCasterCfg(
    #     prim_path="{ENV_REGEX_NS}/Robot/base_link",
    #     offset=RayCasterCfg.OffsetCfg(pos=(0.0, 0.0, 20.0)),
    #     attach_yaw_only=True,
    #     pattern_cfg=patterns.GridPatternCfg(resolution=0.1, size=[1.6, 1.0]),
    #     debug_vis=True,
    #     mesh_prim_paths=["/World/ground"],
    # )
    contact_forces = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Robot/.*", history_length=3, track_air_time=False)

    # lights
    light = AssetBaseCfg(
        prim_path="/World/light",
        spawn=sim_utils.DistantLightCfg(color=(0.75, 0.75, 0.75), intensity=3000.0),
    )


##
# MDP settings
##

@configclass
class CommandsCfg:
    """Command terms for the MDP."""

    pose_command = mdp.UniformPose2dCommandCfg(
        asset_name="robot",
        simple_heading=False,
        resampling_time_range=(10.0,10.0),
        debug_vis=True,
        ranges=mdp.UniformPose2dCommandCfg.Ranges(pos_x=(3.0, 3.0), pos_y=(0, 0), heading=(0, 0)),
    )

@configclass
class ActionsCfg:
    """Action specifications for the MDP."""

    joint_vel_action = mdp.JointVelocityActionCfg(asset_name="robot", joint_names=["wheel11_left_joint",
                                                                                   "wheel11_right_joint",
                                                                                   "wheel12_left_joint",
                                                                                   "wheel12_right_joint"], scale=1.0)
    joint_pos_action = mdp.JointPositionActionCfg(asset_name="robot", joint_names=["leg1.*"], scale = 0.5, use_default_offset=True)

@configclass
class ObservationsCfg:
    """Observation specifications for the MDP."""

    @configclass
    class PolicyCfg(ObsGroup):
        """Observations for the policy."""

        body_lin_vel = ObsTerm(func=mdp.body_lin_vel,
                               params = {"body_name": "leg1link4"})
        body_ang_vel = ObsTerm(func=mdp.body_ang_vel,
                               params = {"body_name": "leg1link4"})
        body_height = ObsTerm(func=mdp.body_pos_z,
                               params = {"body_name": "leg1link4"})
        joint_pos = ObsTerm(func=mdp.joint_pos_rel, 
                            # noise=Unoise(n_min=-0.01, n_max=0.01)
                            )
        joint_vel = ObsTerm(func=mdp.joint_vel_rel, 
                            # noise=Unoise(n_min=-0.05, n_max=0.05)
                            )
        # height_scan = ObsTerm(
        #     func=mdp.height_scan,
        #     params={"sensor_cfg": SceneEntityCfg("height_scanner")},
        #     clip=(-1.0, 1.0),
        # )


        actions = ObsTerm(func=mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = False
            self.concatenate_terms = True

    # observation groups
    policy: PolicyCfg = PolicyCfg()


@configclass
class EventCfg:
    """Configuration for events."""

    reset_base = EventTerm(
        func=mdp.reset_root_state_uniform,
        mode="reset",
        params={"pose_range": {"yaw": (0, 0)}, "velocity_range": {}},
    )

    reset_robot_joints = EventTerm(
        func=mdp.reset_joints_by_offset_vehicle,
        mode="reset",
        params={
            "position_range": (-0.0, 0.0),
            "velocity_range": (-0.0, 0.0),
        },
    )


@configclass
class RewardsCfg:
    """Reward terms for the MDP."""

    position_tracking = RewTerm(
        func=mdp.position_command_error_tanh,
        weight=1.0, 
        params={"std": 0.20, "command_name": "pose_command"},
    )
    position_tracking_fine_grained = RewTerm(
        func=mdp.position_command_error_tanh,
        weight=0.5,
        params={"std": 0.02, "command_name": "pose_command"},
    )
    orientation_tracking = RewTerm(
        func=mdp.heading_command_error_abs,
        weight=-0.1,
        params={"command_name": "pose_command"},
    )
    # (4) Reward for wheels having contact with ground 
    # desired_contacts_left = RewTerm(
    #     func=mdp.undesired_contacts,
    #     weight=0.25,
    #     params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_left"), "threshold": 0.05},
    # )
    # desired_contacts_right = RewTerm(
    #     func=mdp.undesired_contacts,
    #     weight=0.25,
    #     params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_right"), "threshold": 0.05},
    # )

    # -- penalties
    termination_penalty = RewTerm(func=mdp.is_terminated, weight=-1.0e3)
    lin_vel_z_l2 = RewTerm(func=mdp.lin_vel_z_body_l2, weight=-1.0, params = {"body_name": "leg1link2"})
    dof_acc_l2 = RewTerm(func=mdp.joint_acc_l2, weight=-1e-4)
    action_rate_l2 = RewTerm(func=mdp.action_rate_l2, weight=-1.0e-2)
    # Penalty for not being in vehicle configuration 
    joint_deviation_l1 = RewTerm(func=mdp.joint_deviation_vehicle_l1, weight = -3.0)
    # Penalty for wheel velocities being different
    # wheel_vel_deviation_front = RewTerm(func=mdp.wheel_vel_deviation_front, weight = -5e-6)
    # wheel_vel_deviation_rear = RewTerm(func=mdp.wheel_vel_deviation_rear, weight = -5e-6)

    # Penalty for arm links to collide with anything
    # undesired_contacts = RewTerm(
    #     func=mdp.undesired_contacts,
    #     weight=-100.0,
    #     params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names="leg1link.*"), "threshold": 0.01},
    # )

@configclass
class TerminationsCfg:
    """Termination terms for the MDP."""

    # (1) Terminate if the episode length is exceeded
    time_out = DoneTerm(func=mdp.time_out, time_out=True)

    # (2) Terminate if any of the vehicle arm links collide with something
    base_contact = DoneTerm(
        func=mdp.illegal_contact,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names="leg1link.*"), "threshold": 0.01},
    )

@configclass
class CurriculumCfg:
    """Curriculum terms for the MDP."""

    # terrain_levels = CurrTerm(func=mdp.terrain_levels_vel)
    action_rate = CurrTerm(
        func=mdp.modify_reward_weight, params={"term_name": "energy", "weight": -0.01, "num_steps": 1000}
    )

    # joint_vel = CurrTerm(
    #     func=mdp.modify_reward_weight, params={"term_name": "joint_deviation", "weight": -0.5, "num_steps": 1000}
    # )

@configclass
class VehicleEnvCfg(ManagerBasedRLEnvCfg):
    """Configuration for Moonshot Vehicle environment."""

    # Scene settings
    scene: MySceneCfg = MySceneCfg(num_envs=4096, env_spacing=2.5)
    # Basic settings
    observations: ObservationsCfg = ObservationsCfg()
    actions: ActionsCfg = ActionsCfg()
    commands: CommandsCfg = CommandsCfg()
    # MDP settings
    rewards: RewardsCfg = RewardsCfg()
    terminations: TerminationsCfg = TerminationsCfg()
    events: EventCfg = EventCfg()
    # curriculum: CurriculumCfg = CurriculumCfg()

    def __post_init__(self):
        """Post initialization."""
        # general settings
        self.decimation = 4
        self.episode_length_s = 20.0
        # simulation settings
        self.viewer.eye = (3.5, 3.5, 3.5)
        self.sim.dt = 0.005
        self.sim.render_interval = self.decimation
        self.sim.disable_contact_processing = True
        self.sim.physics_material = self.scene.terrain.physics_material

        # update sensor update periods
        # we tick all the sensors based on the smallest update period (physics update period)
        # if self.scene.height_scanner is not None:
        #     self.scene.height_scanner.update_period = self.decimation * self.sim.dt
        if self.scene.contact_forces is not None:
            self.scene.contact_forces.update_period = self.sim.dt
