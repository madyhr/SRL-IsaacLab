# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Sub-module containing command generators for the velocity-based locomotion task."""

from __future__ import annotations

import torch
from collections.abc import Sequence
from typing import TYPE_CHECKING

import omni.log

import isaaclab.utils.math as math_utils
from isaaclab.assets import Articulation
from isaaclab.managers import CommandTerm
from isaaclab.markers import VisualizationMarkers

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedEnv

    from .commands_cfg import UniformBodyVelocityCommandCfg


class UniformBodyVelocityCommand(CommandTerm):
    r"""Command generator that generates a velocity command in SE(2) from uniform distribution.

    The command comprises of a linear velocity in x and y direction and an angular velocity around
    the z-axis. It is given in the robot's base frame.

    If the :attr:`cfg.heading_command` flag is set to True, the angular velocity is computed from the heading
    error similar to doing a proportional control on the heading error. The target heading is sampled uniformly
    from the provided range. Otherwise, the angular velocity is sampled uniformly from the provided range.

    Mathematically, the angular velocity is computed as follows from the heading command:

    .. math::

        \omega_z = \frac{1}{2} \text{wrap_to_pi}(\theta_{\text{target}} - \theta_{\text{current}})

    """

    cfg: UniformBodyVelocityCommandCfg
    """The configuration of the command generator."""

    def __init__(self, cfg: UniformBodyVelocityCommandCfg, env: ManagerBasedEnv):
        """Initialize the command generator.

        Args:
            cfg: The configuration of the command generator.
            env: The environment.

        Raises:
            ValueError: If the heading command is active but the heading range is not provided.
        """
        # initialize the base class
        super().__init__(cfg, env)

        # check configuration
        if self.cfg.heading_command and self.cfg.ranges.heading is None:
            raise ValueError(
                "The velocity command has heading commands active (heading_command=True) but the `ranges.heading`"
                " parameter is set to None."
            )
        if self.cfg.ranges.heading and not self.cfg.heading_command:
            omni.log.warn(
                f"The velocity command has the 'ranges.heading' attribute set to '{self.cfg.ranges.heading}'"
                " but the heading command is not active. Consider setting the flag for the heading command to True."
            )

        # obtain the robot asset
        # -- robot
        self.robot: Articulation = env.scene[cfg.asset_name]
        
        # crete buffers to store the command
        # -- command: x vel, y vel, yaw vel, heading
        self.vel_command_b = torch.zeros(self.num_envs, 3, device=self.device)
        self.heading_target = torch.zeros(self.num_envs, device=self.device)
        self.is_heading_env = torch.zeros(self.num_envs, dtype=torch.bool, device=self.device)
        self.is_standing_env = torch.zeros_like(self.is_heading_env)
        self.body_link_idx = self.robot.find_bodies(cfg.body_name)[0][0]
        # -- metrics
        self.metrics["error_vel_xy"] = torch.zeros(self.num_envs, device=self.device)
        self.metrics["error_vel_yaw"] = torch.zeros(self.num_envs, device=self.device)

    def __str__(self) -> str:
        """Return a string representation of the command generator."""
        msg = "UniformVelocityCommand:\n"
        msg += f"\tCommand dimension: {tuple(self.command.shape[1:])}\n"
        msg += f"\tResampling time range: {self.cfg.resampling_time_range}\n"
        msg += f"\tHeading command: {self.cfg.heading_command}\n"
        if self.cfg.heading_command:
            msg += f"\tHeading probability: {self.cfg.rel_heading_envs}\n"
        msg += f"\tStanding probability: {self.cfg.rel_standing_envs}"
        return msg

    """
    Properties
    """

    @property
    def command(self) -> torch.Tensor:
        """The desired base velocity command in the base frame. Shape is (num_envs, 3)."""
        return self.vel_command_b

    """
    Implementation specific functions.
    """

    def _get_body_vel_d(self, body_vel_w):
        # calculates velocity of body in desired (d) frame (x = forwards, y = left, z = up)
        body_quat_w = self.robot.data.body_quat_w[:, self.body_link_idx, :]
        if self.cfg.body_name == "leg1link2":
            tf_d_matrix = torch.tensor([[-1,0,0],[0,0,1],[0,1,0]], device = self.device)
            tf_d_matrix_expanded = tf_d_matrix.unsqueeze(0).expand(self.num_envs, -1, -1)
            tf_d_quat = math_utils.quat_from_matrix(tf_d_matrix_expanded)
        elif self.cfg.body_name == "leg1link4":
            tf_d_matrix = torch.tensor([[0,0,-1],[-1,0,0],[0,1,0]], device = self.device)
            tf_d_matrix_expanded = tf_d_matrix.unsqueeze(0).expand(self.num_envs, -1, -1)
            tf_d_quat = math_utils.quat_from_matrix(tf_d_matrix_expanded)      
        else:
            raise ValueError(f"Unexpected link name: {self.cfg.body_name}")
        
        quat_w_d = math_utils.quat_mul(body_quat_w, tf_d_quat)
        
        body_vel_d = math_utils.quat_rotate_inverse(
            quat_w_d, body_vel_w
        )

        return body_vel_d

    def _get_body_quat_d(self):
        # calculates quat from world (w) to desired (d) frame
        body_quat_w = self.robot.data.body_quat_w[:, self.body_link_idx, :]
        
        if self.cfg.body_name == "leg1link2":
            tf_d_matrix = torch.tensor([[-1,0,0],[0,0,1],[0,1,0]], device = self.device)
            tf_d_matrix_expanded = tf_d_matrix.unsqueeze(0).expand(self.num_envs, -1, -1)
            tf_d_quat = math_utils.quat_from_matrix(tf_d_matrix_expanded)
        elif self.cfg.body_name == "leg1link4":
            tf_d_matrix = torch.tensor([[0,0,-1],[-1,0,0],[0,1,0]], device = self.device)
            tf_d_matrix_expanded = tf_d_matrix.unsqueeze(0).expand(self.num_envs, -1, -1)
            tf_d_quat = math_utils.quat_from_matrix(tf_d_matrix_expanded)
        else:
            raise ValueError(f"Unexpected link name: {self.cfg.body_name}")
        
        quat_w_d = math_utils.quat_mul(body_quat_w, tf_d_quat)

        return quat_w_d

    def _update_metrics(self):
        # time for which the command was executed
        max_command_time = self.cfg.resampling_time_range[1]
        max_command_step = max_command_time / self._env.step_dt
        # logs data
        body_lin_vel_d = self._get_body_vel_d(self.robot.data.body_lin_vel_w[:, self.body_link_idx, :])

        self.metrics["error_vel_xy"] += (
            torch.norm(self.vel_command_b[:, :2] - body_lin_vel_d[:, :2], dim=-1) / max_command_step
        )
        # self.metrics["error_vel_yaw"] += (
        #     torch.abs(self.vel_command_b[:, 2] - body_ang_vel_d[:, 2]) / max_command_step
        # )
        self.metrics["error_vel_yaw"] += (
            torch.abs(self.vel_command_b[:, 2] - self.robot.data.body_ang_vel_w[:, self.body_link_idx, 2]) / max_command_step
        )

    def _resample_command(self, env_ids: Sequence[int]):
        # sample velocity commands
        r = torch.empty(len(env_ids), device=self.device)
        # -- linear velocity - x direction
        self.vel_command_b[env_ids, 0] = r.uniform_(*self.cfg.ranges.lin_vel_x)
        # -- linear velocity - y direction
        self.vel_command_b[env_ids, 1] = r.uniform_(*self.cfg.ranges.lin_vel_y)
        # -- ang vel yaw - rotation around z
        self.vel_command_b[env_ids, 2] = r.uniform_(*self.cfg.ranges.ang_vel_z)

        # heading target
        if self.cfg.heading_command:
            self.heading_target[env_ids] = r.uniform_(*self.cfg.ranges.heading)
            # update heading envs
            self.is_heading_env[env_ids] = r.uniform_(0.0, 1.0) <= self.cfg.rel_heading_envs
        # update standing envs
        self.is_standing_env[env_ids] = r.uniform_(0.0, 1.0) <= self.cfg.rel_standing_envs

    def _update_command(self):
        """Post-processes the velocity command.

        This function sets velocity command to zero for standing environments and computes angular
        velocity from heading direction if the heading_command flag is set.
        """
        # Compute angular velocity from heading direction
        if self.cfg.heading_command:
            # resolve indices of heading envs
            env_ids = self.is_heading_env.nonzero(as_tuple=False).flatten()
            # compute angular velocity
            heading_error = math_utils.wrap_to_pi(self.heading_target[env_ids] - math_utils.euler_xyz_from_quat(self._get_body_quat_d())[2][env_ids])
            self.vel_command_b[env_ids, 2] = torch.clip(
                self.cfg.heading_control_stiffness * heading_error,
                min=self.cfg.ranges.ang_vel_z[0],
                max=self.cfg.ranges.ang_vel_z[1],
            )
        # Enforce standing (i.e., zero velocity command) for standing envs
        # TODO: check if conversion is needed
        standing_env_ids = self.is_standing_env.nonzero(as_tuple=False).flatten()
        self.vel_command_b[standing_env_ids, :] = 0.0

    def _set_debug_vis_impl(self, debug_vis: bool):
        # set visibility of markers
        # note: parent only deals with callbacks. not their visibility
        if debug_vis:
            # create markers if necessary for the first tome
            if not hasattr(self, "goal_vel_visualizer"):
                # -- goal
                self.goal_vel_visualizer = VisualizationMarkers(self.cfg.goal_vel_visualizer_cfg)
                # -- current
                self.current_vel_visualizer = VisualizationMarkers(self.cfg.current_vel_visualizer_cfg)
            # set their visibility to true
            self.goal_vel_visualizer.set_visibility(True)
            self.current_vel_visualizer.set_visibility(True)
        else:
            if hasattr(self, "goal_vel_visualizer"):
                self.goal_vel_visualizer.set_visibility(False)
                self.current_vel_visualizer.set_visibility(False)

    def _debug_vis_callback(self, event):
        # check if robot is initialized
        # note: this is needed in-case the robot is de-initialized. we can't access the data
        if not self.robot.is_initialized:
            return
        # get marker location
        # -- base state
        body_pos_w = self.robot.data.body_pos_w[:,self.body_link_idx,:].clone()
        body_pos_w[:, 2] += 0.5
        # -- resolve the scales and quaternions
        vel_des_arrow_scale, vel_des_arrow_quat = self._resolve_xy_velocity_to_arrow(self.command[:, :2])
        vel_arrow_scale, vel_arrow_quat = self._resolve_xy_velocity_to_arrow(self._get_body_vel_d(self.robot.data.body_lin_vel_w[:, self.body_link_idx, :])[:, :2])
        # display markers
        self.goal_vel_visualizer.visualize(body_pos_w, vel_des_arrow_quat, vel_des_arrow_scale)
        self.current_vel_visualizer.visualize(body_pos_w, vel_arrow_quat, vel_arrow_scale)

    """
    Internal helpers.
    """

    def _resolve_xy_velocity_to_arrow(self, xy_velocity: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Converts the XY base velocity command to arrow direction rotation."""
        # obtain default scale of the marker
        default_scale = self.goal_vel_visualizer.cfg.markers["arrow"].scale
        # arrow-scale
        arrow_scale = torch.tensor(default_scale, device=self.device).repeat(xy_velocity.shape[0], 1)
        arrow_scale[:, 0] *= torch.linalg.norm(xy_velocity, dim=1) * 3.0
        # arrow-direction
        heading_angle = torch.atan2(xy_velocity[:, 1], xy_velocity[:, 0])
        zeros = torch.zeros_like(heading_angle)
        arrow_quat = math_utils.quat_from_euler_xyz(zeros, zeros, heading_angle)
        # convert everything back from base to world frame
        body_quat_d = self._get_body_quat_d()
        # body_quat_w = self.robot.data.body_quat_w[:, self.body_link_idx, :]
        arrow_quat = math_utils.quat_mul(body_quat_d, arrow_quat)
        return arrow_scale, arrow_quat