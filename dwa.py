import yaml
import math
import numpy as np


class Params:
    def __init__(self, config):
        for param, value in config.items():
            setattr(self, param, value)  # sett all config parameters as attributes


def get_params():
    # convert config yaml to dictionairy
    with open('config.yaml') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        p = Params(config)
    return p


class Robot:
    def __init__(self, start_pos, params):
        # initialize robot state
        self.x = start_pos[0]
        self.y = start_pos[1]
        self.theta = self.v = self.omega = 0
        self.p = params

    def update_state(self, v, omega):
        self.v = v
        self.omega = omega
        self.theta += self.omega * self.p.dt
        self.x += self.v * math.cos(self.theta) * self.p.dt
        self.y += self.v * math.sin(self.theta) * self.p.dt


class RobotPath:
    def __init__(self, bot, v, omega):
        self.v = v
        self.omega = omega
        self.obstacle = False
        self.optimal = False
        self.dist = 1000

        if self.omega == 0:
            self.type = 'straight'
            self.xA = bot.x
            self.yA = bot.y
            self.x = bot.x + self.v * math.cos(bot.theta)
            self.y = bot.y + self.v * math.sin(bot.theta)
        else:
            self.r = self.v / self.omega
            self.type = 'curved'
            if self.omega > 0:
                self.angle = bot.theta + math.pi / 2
                self.x = bot.x + self.r * math.cos(self.angle)
                self.y = bot.y + self.r * math.sin(self.angle)
                self.start = -90
                self.end = 0
            else:
                self.angle = bot.theta + math.pi / 2
                self.x = bot.x + self.r * math.cos(self.angle)
                self.y = bot.y + self.r * math.sin(self.angle)
                self.start = 180
                self.end = 270
            self.angle = math.degrees(bot.theta)


class Obstacle:
    def __init__(self, x, y, r):
        self.x = x
        self.y = y
        self.r = r


def dynamic_window(bot):
    # (Angular) velocities are limited either by hardware speed or acceleration limits.
    min_v = max(bot.p.min_v, bot.v - bot.p.max_a * bot.p.dt)
    max_v = min(bot.p.max_v, bot.v + bot.p.max_a * bot.p.dt)
    min_omega = max(-bot.p.max_omega, bot.omega - bot.p.max_alpha * bot.p.dt)
    max_omega = min(bot.p.max_omega, bot.omega + bot.p.max_alpha * bot.p.dt)

    return [min_v, max_v, min_omega, max_omega]


def admissible_paths(bot, window, obstacles):
    [min_v, max_v, min_omega, max_omega] = window
    paths = []
    for v in np.arange(min_v, max_v, bot.p.v_step):
        for omega in np.arange(min_omega, max_omega, bot.p.omega_step):
            path = RobotPath(bot, v, omega)
            collision, distance, obstacle_on_path = check_collision(bot, path, obstacles)
            if obstacle_on_path:
                path.obstacle = True
            path.dist = distance
            paths.append(path)
    return paths


def find_optimum(bot, paths, goal_pos, p):
    G = 0.0
    optimum = RobotPath(bot, 0, 0)
    goal_x = goal_pos[0]
    goal_y = goal_pos[1]
    for path in paths:
        goal_angle = np.arctan2(goal_y - bot.y, goal_x - bot.x)
        heading = 180 - (math.degrees(bot.theta - goal_angle) % 360)
        clearance = path.dist
        vel = path.v

        factors = np.array([heading, clearance, vel])
        norm_factors = normalize(factors)
        norm_factors = norm_factors.reshape(3, 1)
        gains = np.array([p.gain_alpha, p.gain_beta, p.gain_gamma])
        G_temp = np.matmul(gains, norm_factors)
        if G_temp > G:
            optimum = path
            G = G_temp
    optimum.optimal = True
    return optimum

def normalize(factors):
    min_factor = min(factors)
    max_factor = max(factors)
    if max_factor - min_factor == 0:
        norm_factors = np.zeros(len(factors))
    else:
        norm_factors = (factors - min_factor) / (max_factor - min_factor)
    return norm_factors


def check_collision(bot, path, obstacles):
    min_dist = 1000
    obstacle_on_path = False
    if path.type == "curved":
        for obstacle in obstacles:
            c_obs = [obstacle.x, obstacle.y, obstacle.r]
            c_path = [path.x, path.y, abs(path.r) - bot.p.r_bot, abs(path.r) + bot.p.r_bot]
            if check_circle_collision(c_obs, c_path):
                obstacle_on_path = True
                gamma_bot = np.arctan2(bot.y - path.y, bot.x - path.x)
                gamma = np.arctan2(obstacle.y - path.y, obstacle.x - path.x)
                dist = abs(gamma_bot - gamma) * abs(path.r)
                if dist < min_dist:
                    min_dist = dist
    else:
        for obstacle in obstacles:
            gamma = np.arctan2(obstacle.y - bot.y, obstacle.x - bot.x)
            dist = np.sqrt((obstacle.x - bot.x) ** 2 + (obstacle.y - bot.y) ** 2)
            delta_gamma = np.arcsin(obstacle.r / dist)
            if bot.theta - delta_gamma < gamma < bot.theta + delta_gamma:
                obstacle_on_path = True
                if dist < min_dist:
                    min_dist = dist

    max_v = np.sqrt(2 * min_dist * bot.p.max_a)
    max_omega = np.sqrt(2 * min_dist * bot.p.max_alpha)
    collision = (path.v >= max_v or (abs(path.omega) >= max_omega))
    return collision, min_dist, obstacle_on_path


def check_circle_collision(c_obs, c_path):
    [x_obs, y_obs, r_obs] = c_obs
    [x, y, r_in, r_out] = c_path
    dist = math.sqrt((x_obs - x) ** 2 + (y_obs - y) ** 2)  # distance center to center
    if (r_out + r_obs) >= dist > (r_in - r_obs):
        return True
    return False
