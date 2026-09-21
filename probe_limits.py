"""实测 Jev 的 state 长度上限

官方文档没给出具体数字，本脚本用二分法探出真实边界，并测中英文的 token 换算差异。

跑法：.venv/bin/python probe_limits.py
"""

from __future__ import annotations

import json

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient, TypeSafeError

load_dotenv(".env")

Q_ONE = {"q": Noul(instructions="Is this text fine?")}


def attempt(client: TypeSafeClient, state, questions=None) -> tuple[bool, int | None, str]:
    """返回 (是否成功, input_tokens, 错误信息)。"""
    try:
        r = client.system_one(state=state, questions=questions or Q_ONE)
        return True, r.usage.input_tokens, ""
    except TypeSafeError as exc:
        return False, None, f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, None, f"{type(exc).__name__}: {exc}"


def repeat_to(words: str, target_chars: int) -> str:
    """把一段种子文本重复拼到接近目标字符数。"""
    if not words:
        return ""
    seed = (words + " ")
    return (seed * (target_chars // len(seed) + 1))[:target_chars]


def measure_ratio(client: TypeSafeClient, seed: str, chars: int) -> float:
    """测得「每字符多少 token」。"""
    text = repeat_to(seed, chars)
    ok, tokens, err = attempt(client, text)
    if not ok:
        print(f"    测量失败：{err[:100]}")
        return 0.0
    return tokens / len(text)


def binary_search_max(client: TypeSafeClient, seed: str, hi_start: int, label: str) -> int:
    """二分找最大可用字符数。"""
    lo, hi = 0, hi_start
    # 先扩展上界直到失败
    while True:
        ok, tokens, err = attempt(client, repeat_to(seed, hi))
        if not ok:
            print(f"  上界确认：{hi:,} 字符失败 → {err[:120]}")
            break
        print(f"  {hi:,} 字符成功（{tokens:,} tok）")
        lo = hi
        hi *= 2
        if hi > 4_000_000:
            print("  上界扩展超限，停止")
            return lo

    # 二分收敛（精确到 ~2000 字符）
    while hi - lo > 2000:
        mid = (lo + hi) // 2
        ok, tokens, _ = attempt(client, repeat_to(seed, mid))
        if ok:
            lo = mid
        else:
            hi = mid
    print(f"  → {label} 最大字符数 ≈ {lo:,}（失败点在 {hi:,} 附近）")
    return lo


def main() -> None:
    with TypeSafeClient() as client:

        print("=" * 88)
        print("1 · 中英文 token 换算（同样字符数，token 数差多少）")
        print("=" * 88)
        en_seed = "The customer reported a duplicate charge on order A-104 and asked for a refund."
        zh_seed = "客户反馈订单重复扣款，要求退款，并强调已经等待了三天仍未得到处理。"
        for label, seed in [("英文", en_seed), ("中文", zh_seed)]:
            ratio = measure_ratio(client, seed, 4000)
            print(f"  {label}: {ratio:.3f} token/字符  → 1000 字符约 {ratio * 1000:.0f} tok")

        # ---------- 中文更长的样本，ratio 更稳 ----------
        print("\n  用更长样本复测：")
        for label, seed in [("英文", en_seed), ("中文", zh_seed)]:
            ratio = measure_ratio(client, seed, 20000)
            print(f"    {label}: {ratio:.3f} token/字符  → 1000 字符约 {ratio * 1000:.0f} tok")

        print("\n" + "=" * 88)
        print("2 · 单条 state 的真实上限（只有一个 Noul 问题）")
        print("=" * 88)

        print("\n  【英文】")
        en_max = binary_search_max(client, en_seed, 20_000, "英文 state")

        print("\n  【中文】")
        zh_max = binary_search_max(client, zh_seed, 20_000, "中文 state")

        print("\n" + "=" * 88)
        print("3 · 多问题时的上限（state + 所有问题共享额度）")
        print("=" * 88)
        # 构造一个很长的 instructions，看总预算怎么算
        long_instr = "原文见下。请判断这段文字所描述的情形是否属实。" + "补充说明。" * 2000
        many = {
            "q1": Noul(instructions="Is this fine?"),
            "q2": Noul(instructions=long_instr),
        }
        ok, tokens, err = attempt(client, repeat_to(en_seed, 1000), many)
        print(f"  state=1000 字符 + 1 个超长问题 → {'成功' if ok else '失败'}")
        if ok:
            print(f"    input_tokens = {tokens:,}（说明超长的 instructions 也计入同一预算）")
        else:
            print(f"    {err[:160]}")

        print("\n" + "=" * 88)
        print("4 · 文档给出的结构上限（实测验证）")
        print("=" * 88)

        # Score 等级数
        for n in (1, 2, 10, 11):
            levels = [f"等级 {i} 的描述" for i in range(n)]
            ok, _, err = attempt(
                client, "test", {"s": Score(instructions="Pick a level", criteria=levels)}
            )
            status = "✓ 接受" if ok else f"✗ {err[:70]}"
            print(f"  Score 等级数={n:<3} {status}")

        # Choice 选项数
        for n in (1, 2, 255, 256):
            opts = {f"opt_{i}": None for i in range(n)}
            ok, _, err = attempt(
                client, "test", {"c": Choice(instructions="Pick one", criteria=opts)}
            )
            status = "✓ 接受" if ok else f"✗ {err[:70]}"
            print(f"  Choice 选项数={n:<4} {status}")

        # 问题个数
        for n in (1, 10, 50, 100):
            qs = {f"q{i}": Noul(instructions="Is this fine?") for i in range(n)}
            ok, tokens, err = attempt(client, "test text", qs)
            status = f"✓ 接受（{tokens} tok）" if ok else f"✗ {err[:70]}"
            print(f"  问题个数={n:<4} {status}")

        print("\n" + "=" * 88)
        print("汇总")
        print("=" * 88)
        print(f"  英文 state 上限 ≈ {en_max:,} 字符")
        print(f"  中文 state 上限 ≈ {zh_max:,} 字符")


if __name__ == "__main__":
    main()
