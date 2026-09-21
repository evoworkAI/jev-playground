"""手动玩 LunarLander —— 带开始 / 重玩按钮

跑法：
    .venv/bin/python play_lunarlander.py

玩法：
    把飞船稳稳放在两面旗子中间的着陆坪上。
    两个绿色小灯都亮 = 两条腿都站稳 = 安全着陆 +100；
    机身碰到月面 = 坠毁 -100。

键盘：
    ←  或  A     左侧推进器
    →  或  D     右侧推进器
    ↑  或  空格  主引擎（往上推）
    松手             不点火
    R                重玩
    H                让 Gymnasium 自带的手写控制器替你把飞船落下来（对比用）
    Esc              退出

鼠标：也能按住画面下方的按钮，按住不放就持续点火。
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np
import pygame
from gymnasium.envs.box2d.lunar_lander import heuristic

# ---------------------------------------------------------------- 布局常量
GAME_W, GAME_H = 600, 400        # 跟 Gymnasium 渲染输出一致
HUD_H = 78                       # 顶部状态栏
CTRL_H = 98                      # 底部按钮区
WIN_W = GAME_W
WIN_H = HUD_H + GAME_H + CTRL_H
GAME_Y = HUD_H
FPS = 50                         # LunarLander 的物理步频就是 50

# ---------------------------------------------------------------- 配色
BG = (18, 18, 20)
PANEL = (30, 30, 34)
PANEL_HI = (46, 46, 52)
TEXT = (232, 232, 236)
MUTED = (140, 140, 150)
ACCENT = (86, 156, 214)
GOOD = (106, 190, 120)
BAD = (214, 106, 106)
BORDER = (58, 58, 64)


def load_font(size: int, bold: bool = False) -> pygame.font.Font:
    """找个能显示中文的系统字体，找不到就退回默认字体。"""
    for name in (
        "PingFang SC", "Heiti SC", "Hiragino Sans GB",
        "Songti SC", "STHeiti", "Arial Unicode MS",
    ):
        path = pygame.font.match_font(name, bold=bold)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.SysFont(None, size)


class Button:
    def __init__(self, rect: pygame.Rect, label: str, hint: str = "") -> None:
        self.rect = rect
        self.label = label
        self.hint = hint
        self.held = False
        self.enabled = True

    def draw(self, surf: pygame.Surface, font: pygame.font.Font,
             hint_font: pygame.font.Font) -> None:
        active = self.held
        pygame.draw.rect(surf, PANEL_HI if active else PANEL, self.rect, border_radius=8)
        pygame.draw.rect(surf, ACCENT if active else BORDER, self.rect, width=1, border_radius=8)

        label = font.render(self.label, True, TEXT if self.enabled else MUTED)
        if self.hint:
            hint = hint_font.render(self.hint, True, MUTED)
            total = label.get_height() + hint.get_height() + 1
            top = self.rect.centery - total // 2
            surf.blit(label, (self.rect.centerx - label.get_width() // 2, top))
            surf.blit(hint, (self.rect.centerx - hint.get_width() // 2, top + label.get_height() + 1))
        else:
            surf.blit(label, (self.rect.centerx - label.get_width() // 2,
                              self.rect.centery - label.get_height() // 2))

    def hit(self, pos) -> bool:
        return self.enabled and self.rect.collidepoint(pos)


def make_buttons() -> dict[str, Button]:
    y = GAME_Y + GAME_H + 19
    h = 60
    return {
        "left":   Button(pygame.Rect(12, y, 128, h), "左推进", "← / A"),
        "main":   Button(pygame.Rect(150, y, 128, h), "主引擎", "↑ / 空格"),
        "right":  Button(pygame.Rect(288, y, 128, h), "右推进", "→ / D"),
        "auto":   Button(pygame.Rect(426, y, 84, h), "AI 演示", "H"),
        "replay": Button(pygame.Rect(520, y, 68, h), "重玩", "R"),
    }


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("LunarLander · 手动玩")
    clock = pygame.time.Clock()

    f_big = load_font(30, bold=True)
    f_mid = load_font(17, bold=True)
    f_small = load_font(14)
    f_tiny = load_font(11)

    env = gym.make("LunarLander-v3", render_mode="rgb_array")
    buttons = make_buttons()

    # 开始界面上的「开始」按钮
    start_rect = pygame.Rect(0, 0, 190, 56)
    start_rect.center = (WIN_W // 2, GAME_Y + GAME_H // 2 + 66)

    state = "ready"          # ready | playing | ended | auto
    obs = None
    frame = None
    score = 0.0
    steps = 0
    best: float | None = None
    history: list[tuple[float, int]] = []
    end_note = ""
    action = 0
    resume_auto_at: int | None = None

    def reset() -> None:
        nonlocal obs, frame, score, steps, state, action
        obs, _ = env.reset()
        frame = env.render()
        score, steps, action = 0.0, 0, 0
        state = "playing"

    def start_auto() -> None:
        nonlocal state, end_note, resume_auto_at
        reset()
        state = "auto"
        end_note = ""
        resume_auto_at = None

    def finish(note: str) -> None:
        nonlocal state, end_note, best, resume_auto_at
        end_note = note
        history.append((score, steps))
        if best is None or score > best:
            best = score
        if state == "auto":
            resume_auto_at = pygame.time.get_ticks() + 1400   # 自动演示循环播放
        state = "ended"

    reset()
    state = "ready"          # 首次进来先停在开始界面

    running = True
    while running:
        now = pygame.time.get_ticks()

        # ---------------------------------------------------- 事件
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    reset()
                elif event.key == pygame.K_h:
                    start_auto()
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and state in ("ready", "ended"):
                    reset()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == "ready":
                    if start_rect.collidepoint(event.pos):
                        reset()
                elif state == "playing":
                    if buttons["replay"].hit(event.pos):
                        reset()
                    elif buttons["auto"].hit(event.pos):
                        start_auto()
                elif state == "ended":
                    if buttons["replay"].hit(event.pos):
                        reset()
                    elif buttons["auto"].hit(event.pos):
                        start_auto()

        # ---------------------------------------------------- 决定这一帧的动作
        if state == "playing":
            keys = pygame.key.get_pressed()
            left = keys[pygame.K_LEFT] or keys[pygame.K_a]
            right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
            thrust = keys[pygame.K_UP] or keys[pygame.K_w] or keys[pygame.K_SPACE]

            mouse_held = pygame.mouse.get_pressed()[0]
            mpos = pygame.mouse.get_pos()
            for name in ("left", "main", "right"):
                buttons[name].held = mouse_held and buttons[name].hit(mpos)

            left = left or buttons["left"].held
            right = right or buttons["right"].held
            thrust = thrust or buttons["main"].held

            if left and not right:
                action = 1
            elif right and not left:
                action = 3
            elif thrust:
                action = 2
            else:
                action = 0

        elif state == "auto":
            action = int(heuristic(env.unwrapped, obs))

        # ---------------------------------------------------- 推进一步物理
        if state in ("playing", "auto"):
            obs, reward, terminated, truncated, _ = env.step(action)
            frame = env.render()
            score += reward
            steps += 1
            if terminated or truncated:
                legs_down = obs[6] > 0.5 and obs[7] > 0.5
                if truncated:
                    note = "超时，还没落地"
                elif legs_down and score > 0:
                    note = "安全着陆 ✓"
                else:
                    note = "坠毁 ✗"
                finish(note)

        if resume_auto_at is not None and now >= resume_auto_at:
            start_auto()

        # ==================================================== 绘制
        screen.fill(BG)

        # --- 顶部状态栏
        pygame.draw.rect(screen, PANEL, pygame.Rect(0, 0, WIN_W, HUD_H))
        pygame.draw.line(screen, BORDER, (0, HUD_H - 1), (WIN_W, HUD_H - 1))

        screen.blit(f_small.render("本局得分", True, MUTED), (16, 10))
        score_color = GOOD if score > 0 else (BAD if score < 0 else TEXT)
        screen.blit(f_big.render(f"{score:+.1f}", True, score_color), (16, 32))

        screen.blit(f_small.render("步数", True, MUTED), (152, 10))
        screen.blit(f_big.render(str(steps), True, TEXT), (152, 32))

        screen.blit(f_small.render("最好成绩", True, MUTED), (228, 10))
        screen.blit(f_big.render("—" if best is None else f"{best:+.1f}", True, TEXT), (228, 32))

        if history:
            screen.blit(f_small.render("最近几局", True, MUTED), (370, 10))
            x = 370
            for sc, _ in history[-5:]:
                text = f"{sc:+.0f}"
                w = f_small.size(text)[0] + 16
                rect = pygame.Rect(x, 34, w, 24)
                pygame.draw.rect(screen, PANEL_HI, rect, border_radius=12)
                surf = f_small.render(text, True, GOOD if sc > 0 else BAD)
                screen.blit(surf, (rect.centerx - surf.get_width() // 2,
                                   rect.centery - surf.get_height() // 2))
                x += w + 6

        # --- 游戏画面
        if frame is not None:
            surface = pygame.surfarray.make_surface(np.transpose(frame, (1, 0, 2)))
            screen.blit(surface, (0, GAME_Y))

        # --- 结束横幅
        if state == "ended":
            overlay = pygame.Surface((GAME_W, GAME_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 130))
            screen.blit(overlay, (0, GAME_Y))

            good = score > 0 and "安全" in end_note
            banner = f_big.render(end_note, True, GOOD if good else BAD)
            detail = f_mid.render(f"本局 {score:+.1f} 分 · {steps} 步", True, TEXT)
            cta = f_small.render("空格 / R 再来一局 · H 看 AI 落地", True, MUTED)
            cx, cy = WIN_W // 2, GAME_Y + GAME_H // 2
            screen.blit(banner, (cx - banner.get_width() // 2, cy - 46))
            screen.blit(detail, (cx - detail.get_width() // 2, cy + 2))
            screen.blit(cta, (cx - cta.get_width() // 2, cy + 34))

        # --- 开始界面
        if state == "ready":
            overlay = pygame.Surface((GAME_W, GAME_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 175))
            screen.blit(overlay, (0, GAME_Y))

            cx = WIN_W // 2
            title = f_big.render("月球着陆器", True, TEXT)
            sub = f_small.render("把飞船稳稳放在两面旗子中间的着陆坪上", True, MUTED)
            hint1 = f_small.render("← →  左右侧推进器        ↑ / 空格  主引擎", True, TEXT)
            hint2 = f_small.render("两个绿色小灯都亮 = 两条腿都站稳 = 安全着陆", True, MUTED)

            hover = start_rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(screen, PANEL_HI if hover else PANEL, start_rect, border_radius=10)
            pygame.draw.rect(screen, ACCENT, start_rect, width=1, border_radius=10)
            btxt = f_mid.render("开始", True, TEXT)
            screen.blit(btxt, (start_rect.centerx - btxt.get_width() // 2,
                               start_rect.centery - btxt.get_height() // 2))

            screen.blit(title, (cx - title.get_width() // 2, GAME_Y + 64))
            screen.blit(sub, (cx - sub.get_width() // 2, GAME_Y + 108))
            screen.blit(hint1, (cx - hint1.get_width() // 2, GAME_Y + 152))
            screen.blit(hint2, (cx - hint2.get_width() // 2, GAME_Y + 176))

        # --- 底部按钮区
        pygame.draw.rect(screen, PANEL, pygame.Rect(0, GAME_Y + GAME_H, WIN_W, CTRL_H))
        pygame.draw.line(screen, BORDER, (0, GAME_Y + GAME_H), (WIN_W, GAME_Y + GAME_H))

        manual_ok = state in ("playing", "ended", "ready")
        for name in ("left", "main", "right"):
            buttons[name].enabled = manual_ok
        buttons["replay"].enabled = state != "ready"
        buttons["auto"].enabled = state != "auto"

        for name in ("left", "main", "right", "auto", "replay"):
            buttons[name].draw(screen, f_mid, f_tiny)

        if state == "auto":
            tag = f_small.render("自动演示中 · Gymnasium 自带的手写控制器", True, ACCENT)
            screen.blit(tag, (14, GAME_Y + GAME_H + CTRL_H - 19))

        pygame.display.flip()
        clock.tick(FPS)

    env.close()
    pygame.quit()


if __name__ == "__main__":
    main()
