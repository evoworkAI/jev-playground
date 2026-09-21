"""LunarLander-v3 上手：环境长什么样 + 随机策略跑一遍

跑法：
    .venv/bin/python lunarlander_demo.py           # 随机策略统计 + 录一段 GIF
    .venv/bin/python lunarlander_demo.py --watch   # 开真实窗口看（需要桌面环境）

不需要任何 AI —— 先用纯随机动作把环境跑通，看基线分是多少。
"""

from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

import gymnasium as gym
import numpy as np
from PIL import Image

OUT = Path(__file__).with_name("media")
GIF = OUT / "lunarlander_random.gif"
PNG = OUT / "lunarlander_frame.png"

# LunarLander 的 8 个观测值，顺序是固定的
OBS_NAMES = [
    ("x", "水平位置", "0 在正中间，± 是偏离"),
    ("y", "垂直高度", "0 = 地面，越大越高"),
    ("vx", "水平速度", "正 = 往右飞"),
    ("vy", "垂直速度", "正 = 往上，负 = 往下掉"),
    ("theta", "机身倾角", "弧度，0 = 正立"),
    ("omega", "角速度", "正 = 逆时针转"),
    ("leg_l", "左腿触地", "0 / 1"),
    ("leg_r", "右腿触地", "0 / 1"),
]

# 只有 4 个动作，这就是 Jev 的 Choice 里那 4 个 criteria
ACTIONS = {
    0: "什么都不做",
    1: "左侧推进器",
    2: "主引擎（向上推）",
    3: "右侧推进器",
}


def line(title: str) -> None:
    print(f"\n{'=' * 84}\n{title}\n{'=' * 84}")


def describe_env() -> None:
    with gym.make("LunarLander-v3", render_mode="rgb_array") as env:
        line("环境说明")
        print(f"  环境 ID        : {env.spec.id}")
        print(f"  观测空间       : {env.observation_space}")
        print(f"  动作空间       : {env.action_space}  ← 4 个离散动作，天然就是一个 Choice")
        print(f"  单局最长步数   : {env.spec.max_episode_steps}")
        print(f"  解决标准        : 连续 100 局平均分 >= {env.spec.reward_threshold}")

        line("观测值逐项含义（这一局的第 1 帧）")
        obs, _ = env.reset(seed=0)
        for (key, name, note), v in zip(OBS_NAMES, obs):
            print(f"  {key:<7} {name:<8} = {v:>8.4f}   {note}")

        line("动作含义")
        for a, name in ACTIONS.items():
            print(f"  {a} → {name}")


def run_random(episodes: int = 50, seed: int = 42) -> list[float]:
    line(f"随机策略跑 {episodes} 局（这是必须知道的地板线）")
    rewards: list[float] = []
    with gym.make("LunarLander-v3") as env:
        for ep in range(episodes):
            obs, _ = env.reset(seed=seed + ep)
            total, steps, done = 0.0, 0, False
            while not done:
                action = env.action_space.sample()   # 纯随机，没有任何智能
                obs, reward, terminated, truncated, _ = env.step(action)
                total += reward
                steps += 1
                done = terminated or truncated
            rewards.append(total)
            if ep < 5:
                print(f"  第 {ep + 1:>2} 局: 总分 {total:>8.1f}   步数 {steps:>4}")

    crashed = sum(1 for r in rewards if r < -50)
    landed = sum(1 for r in rewards if r >= 100)
    print(f"\n  平均分        : {statistics.mean(rewards):.1f}")
    print(f"  中位数        : {statistics.median(rewards):.1f}")
    print(f"  最好 / 最差   : {max(rewards):.1f} / {min(rewards):.1f}")
    print(f"  坠毁(< -50)   : {crashed}/{episodes}")
    print(f"  成功着陆(>=100): {landed}/{episodes}")
    print("\n  → 这个数字就是基线。任何 AI 想宣称「会玩」，先得明显超过它。")
    return rewards


def record_gif(seed: int = 7) -> None:
    line("录一段随机策略的画面")
    OUT.mkdir(exist_ok=True)
    with gym.make("LunarLander-v3", render_mode="rgb_array") as env:
        obs, _ = env.reset(seed=seed)
        frames: list[Image.Image] = []
        total, done = 0.0, False
        while not done and len(frames) < 400:
            frames.append(Image.fromarray(env.render()))
            obs, reward, terminated, truncated, _ = env.step(env.action_space.sample())
            total += reward
            done = terminated or truncated

        # 每 2 帧取 1，缩小一半，控制 GIF 体积
        small = [f.resize((300, 200)) for f in frames[::2]]
        small[0].save(GIF, save_all=True, append_images=small[1:], duration=60, loop=0)
        frames[0].save(PNG)

        print(f"  这局得分 {total:.1f}，共 {len(frames)} 帧")
        print(f"  GIF → {GIF}")
        print(f"  单帧 → {PNG}")


def watch(episodes: int = 3, slow: float = 0.0) -> None:
    """开真实窗口，人肉看它怎么乱飞。

    slow: 每步额外等待的秒数。随机策略一局只飞 2~3 秒，想看清楚（或者想录屏）
          就加上 --slow 0.05 之类的慢放。
    """
    line("打开窗口实时观看（关掉窗口即可退出）")
    with gym.make("LunarLander-v3", render_mode="human") as env:
        for ep in range(episodes):
            obs, _ = env.reset(seed=ep)
            total, steps, done = 0.0, 0, False
            while not done:
                obs, reward, terminated, truncated, _ = env.step(env.action_space.sample())
                total += reward
                steps += 1
                done = terminated or truncated
                if slow:
                    time.sleep(slow)
            print(f"  第 {ep + 1} 局: 总分 {total:.1f}   步数 {steps}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true", help="开窗口实时看")
    parser.add_argument("--slow", type=float, default=0.0, help="每步额外等待秒数，用于慢放/录屏")
    parser.add_argument("--episodes", type=int, default=50)
    args = parser.parse_args()

    describe_env()
    if args.watch:
        watch(episodes=args.episodes if args.episodes != 50 else 3, slow=args.slow)
        return
    run_random(args.episodes)
    record_gif()

    line("小结")
    print("""  1. LunarLander 是真物理引擎（Box2D）驱动的，不是贴图动画 —— 有惯性、有碰撞、有燃料代价。
  2. 动作只有 4 个，观测只有 8 个数字。把 8 个数字写成一句话、把 4 个动作做成 Choice，
     就是一个现成的 Jev 决策任务（而且「腿有没有触地」这类状态是给模型的强提示）。
  3. 奖励是稠密的：离着陆坪越近、速度越慢，分越高；坠毁直接 -100。所以「打得好不好」
     可以逐帧画成曲线，这比看它飞更有说服力。
  4. 随机策略的地板线是负一两百分。没有记忆的决策模型会明显好于随机，但依然很难连成
     一条完整的降落轨迹 —— 因为「减速到什么时候、什么时候换另一侧推进器」需要多步规划。""")


if __name__ == "__main__":
    main()
