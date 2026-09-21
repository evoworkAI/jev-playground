"""三条轨迹对比：随机乱飞 vs Gymnasium 自带的手写控制器

LunarLander 里其实藏着一个现成的参考答案 —— Gymnasium 自带一个手写的
PT（比例控制）控制器，两条腿稳稳落地，得分 +296。

跑法：.venv/bin/python lunarlander_compare.py
输出：media/lunarlander_compare.png
"""

from __future__ import annotations

from pathlib import Path

import gymnasium as gym
from gymnasium.envs.box2d.lunar_lander import heuristic
from PIL import Image, ImageDraw

OUT = Path(__file__).with_name("media") / "lunarlander_compare.png"
COLS = 6
THUMB = (280, 187)
LABEL_H = 26


def play(env, policy, seed: int) -> tuple[list[Image.Image], list[float]]:
    obs, _ = env.reset(seed=seed)
    frames, rewards, done = [], [], False
    while not done and len(frames) < 600:
        frames.append(Image.fromarray(env.render()))
        action = policy(env, obs) if callable(policy) else env.action_space.sample()
        obs, r, terminated, truncated, _ = env.step(action)
        rewards.append(r)
        done = terminated or truncated
    return frames, rewards


def row(frames: list[Image.Image], rewards: list[float], title: str) -> Image.Image:
    idx = [round(i * (len(frames) - 1) / (COLS - 1)) for i in range(COLS)]
    strip = Image.new("RGB", (THUMB[0] * COLS, THUMB[1] + LABEL_H), (18, 18, 18))
    draw = ImageDraw.Draw(strip)
    for col, i in enumerate(idx):
        x = col * THUMB[0]
        strip.paste(frames[i].resize(THUMB), (x, LABEL_H))
        draw.text((x + 8, 8), f"{title}  step {i + 1}  累计 {sum(rewards[: i + 1]):+.0f}", fill=(225, 225, 225))
    return strip


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    with gym.make("LunarLander-v3", render_mode="rgb_array") as env:
        r_frames, r_rew = play(env, None, seed=7)
        h_frames, h_rew = play(env, heuristic, seed=7)

    top = row(r_frames, r_rew, "随机策略 总分")
    bot = row(h_frames, h_rew, "手写控制器 总分")

    canvas = Image.new("RGB", (top.width, top.height + bot.height + 4), (18, 18, 18))
    canvas.paste(top, (0, 0))
    canvas.paste(bot, (0, top.height + 4))
    canvas.save(OUT)

    print(f"随机策略     : {sum(r_rew):+.1f} 分，{len(r_frames)} 步")
    print(f"手写控制器   : {sum(h_rew):+.1f} 分，{len(h_frames)} 步")
    print(f"→ {OUT}  ({canvas.size[0]}x{canvas.size[1]})")


if __name__ == "__main__":
    main()
