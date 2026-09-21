"""把一局 LunarLander 的关键帧拼成一张胶片图，方便一眼看清整条轨迹

跑法：.venv/bin/python lunarlander_strip.py
"""

from __future__ import annotations

from pathlib import Path

import gymnasium as gym
from PIL import Image, ImageDraw

OUT = Path(__file__).with_name("media") / "lunarlander_filmstrip.png"
COLS = 6
THUMB = (280, 187)


def main() -> None:
    with gym.make("LunarLander-v3", render_mode="rgb_array") as env:
        obs, _ = env.reset(seed=7)
        frames, rewards, done = [], [], False
        while not done and len(frames) < 400:
            frames.append(Image.fromarray(env.render()))
            obs, r, terminated, truncated, _ = env.step(env.action_space.sample())
            rewards.append(r)
            done = terminated or truncated

    # 均匀取 6 帧
    idx = [round(i * (len(frames) - 1) / (COLS - 1)) for i in range(COLS)]
    picks = [frames[i] for i in idx]

    width = THUMB[0] * COLS
    height = THUMB[1] + 26
    canvas = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)

    for col, (i, frame) in enumerate(zip(idx, picks)):
        x = col * THUMB[0]
        canvas.paste(frame.resize(THUMB), (x, 26))
        draw.text((x + 8, 8), f"step {i + 1}  累计 {sum(rewards[: i + 1]):.0f}", fill=(220, 220, 220))

    canvas.save(OUT)
    print(f"总步数 {len(frames)}  总分 {sum(rewards):.1f}")
    print(f"→ {OUT}  ({canvas.size[0]}x{canvas.size[1]})")


if __name__ == "__main__":
    main()
