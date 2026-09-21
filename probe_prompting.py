"""Jev 的「提示词」机制实测

Jev 没有 system prompt，没有对话历史，每次调用都是独立的。
那规则怎么给？本脚本逐项验证四种可行/不可行的做法。

跑法：.venv/bin/python probe_prompting.py
"""

from __future__ import annotations

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, TypeSafeClient, TypeSafeError

load_dotenv(".env")


def line(title: str) -> None:
    print(f"\n{'=' * 88}\n{title}\n{'=' * 88}")


def noul_str(name: str, resp) -> str:
    return f"{resp.nouls[name].noul:.3f}"


def choice_str(name: str, resp) -> str:
    a = resp.choices[name]
    dist = "  ".join(f"{k}={v:.2f}" for k, v in sorted(a.probabilities.items(), key=lambda x: -x[1]))
    return f"{a.choice} (conf={a.confidence:.2f})   {dist}"


def main() -> None:
    with TypeSafeClient() as client:

        # ============================================================
        line("测试 1 · 有没有记忆？—— 把规则放在「上一次调用」里，看下次还记不记得")
        # ============================================================
        rule = "公司退款规则：金额超过 500 美元的退款，必须由经理批准。"
        ticket = {"case": "客户要求退款 1200 美元，由客服 Ana（非经理）批准。"}
        q = {
            "violated_policy": Noul(
                instructions="根据 state 中给出的规则，这笔退款的处理是否违反了规定？",
            )
        }

        r1 = client.system_one(state={"rule": rule, "ticket": ticket}, questions=q)
        print(f"  第 1 次调用（state 里【有】规则）: violated_policy = {noul_str('violated_policy', r1)}")

        r2 = client.system_one(state={"ticket": ticket}, questions=q)
        print(f"  第 2 次调用（state 里【没】规则）: violated_policy = {noul_str('violated_policy', r2)}")
        print("\n  → 结论：两次结果不同。第 2 次它完全不知道规则，因为**调用之间没有任何记忆**。")

        # ============================================================
        line("测试 2 · 规则放 state 有没有用？—— 用一条「反直觉」规则，让世界知识帮不上忙")
        # ============================================================
        # 这条规则故意和常识相反：常识会说「宕机+损失订单」= 紧急
        # 版本 V1：只说了一半（必要条件），故意留下歧义
        rule_v1 = (
            "本工单系统的内部约定：标签 urgent 只用于已付费客户。"
            "免费用户提交的任何问题一律标记 normal，无论内容多紧急、多严重。"
        )
        # 版本 V2：写成明确的充要条件，不留歧义
        rule_v2 = (
            "本工单系统的内部约定："
            "（1）已付费客户提交的任何问题，一律标记 urgent，即使内容并不紧急；"
            "（2）免费用户提交的任何问题，一律标记 normal，无论内容多紧急、多严重。"
            "内容本身是否紧急，与本标签无关。"
        )
        cases = {
            "免费用户 + 「网站宕机、正在损失订单、急需处理」": {
                "plan": "free", "message": "我的网站宕机了，正在损失订单，急需处理！",
            },
            "付费用户 + 「随便问一下，不急」": {
                "plan": "paid", "message": "随便问一下，不着急。",
            },
        }
        expected = {
            "免费用户 + 「网站宕机、正在损失订单、急需处理」": "normal",
            "付费用户 + 「随便问一下，不急」": "urgent",
        }
        q2 = {
            "tag": Choice(
                instructions="根据 state 中的内部约定，这条工单应该打哪个标签？",
                criteria={"urgent": None, "normal": None},  # 故意不给描述，只能靠 state 里的规则
            )
        }

        def run_case(label: str, state_extra: dict, note: str = "") -> None:
            print(f"  【{label}】{note}")
            for desc, c in cases.items():
                r = client.system_one(state={**state_extra, "case": c}, questions=q2)
                got = r.choices["tag"].choice
                ok = "✓" if got == expected[desc] else f"✗ 规则要求 {expected[desc]}"
                print(f"    {desc}\n        → {choice_str('tag', r)}   {ok}")

        run_case("A", {}, "state 里【不带】规则，只靠常识")
        print()
        run_case("B", {"rule": rule_v1}, "规则 V1：只写了「urgent 仅限付费客户」，没说付费用户一定 urgent")
        print()
        run_case("C", {"rule": rule_v2}, "规则 V2：明确写成充要条件")

        print("\n  → 结论 A：不带规则 → 完全按常识走（尤其付费用户那条也判 normal，因为内容确实不急）。")
        print("  → 结论 B：Jev 按 V1 的**字面**执行 —— V1 只规定了免费用户，对已付费客户是沉默的，")
        print("           所以它按内容判了 normal。**是规则写得有歧义，不是它没读懂。**")
        print("  → 结论 C：规则写成充要条件后，它**同时推翻两个方向上的常识**，两条全对。")
        print("           这说明它咬的是你的文字，而不是你的意图。")

        # ============================================================
        line("测试 3 · few-shot 示例放 state 有没有用？—— 用「任意约定」，只给例子不给说明")
        # ============================================================
        # 编造一条从逻辑上推不出来、只能从例子归纳的约定
        examples = [
            {"text": "Where is my order?", "label": "B"},
            {"text": "I need 2 more seats", "label": "C"},
            {"text": "Great product", "label": "A"},
            {"text": "Can you help me?", "label": "B"},
            {"text": "We bought 10 licenses", "label": "C"},
        ]
        q3 = {
            "label": Choice(
                instructions="按照 `examples` 中示范的规则，给 `new_message` 打上正确标签。",
                criteria={"A": None, "B": None, "C": None},
            )
        }
        tests = [
            ("请给我们再加 5 个用户席位", "C"),   # 含数字 → C
            ("有没有折扣?", "B"),                  # 含问号 → B
            ("Thanks!", "A"),                      # 都没有 → A
        ]

        print("  【A】不给 examples：")
        for msg, exp in tests:
            r = client.system_one(state={"new_message": msg}, questions=q3)
            print(f"    「{msg}」 → {choice_str('label', r)}   期望={exp}")

        print("\n  【B】给出 5 条 examples：")
        for msg, exp in tests:
            r = client.system_one(state={"examples": examples, "new_message": msg}, questions=q3)
            got = r.choices["label"].choice
            ok = "✓" if got == exp else "✗"
            print(f"    「{msg}」 → {choice_str('label', r)}   期望={exp}  {ok}")

        print("\n  → 结论：例子确实能把「任意约定」传递过去，这就是 Jev 版的 few-shot。")

        # ============================================================
        line("测试 4 · instructions 的措辞就是它的 prompt —— 同一 state 换问法")
        # ============================================================
        msg_state = {"message": "The dashboard loads slowly sometimes, no big deal."}
        variants = {
            "模糊问法": "Is this urgent?",
            "精确问法（给判据）": "Does this message meet the SLA bar for a P1 incident, i.e. an active outage "
                                  "or data loss affecting multiple users?",
            "可操作问法": "Should this ticket be paged to the on-call engineer right now, or queued for "
                          "the next business day?",
        }
        print("  同一个 state，只改 instructions：")
        for label, instr in variants.items():
            r = client.system_one(state=msg_state, questions={"q": Noul(instructions=instr)})
            print(f"    {label:<18} → noul = {noul_str('q', r)}   「{instr[:56]}…」")

        # ============================================================
        line("测试 5 · 能不能硬塞一个 system 字段？（通过 extra_body）")
        # ============================================================
        probe_state = {"message": "Hello, I just wanted to say thanks!"}
        q5 = {"is_unhappy": Noul(instructions="Is the customer unhappy or complaining?")}

        baseline = client.system_one(state=probe_state, questions=q5)
        print(f"  正常调用:                    is_unhappy = {noul_str('is_unhappy', baseline)}")

        for field_name in ("system", "system_prompt"):
            try:
                r = client.system_one(
                    state=probe_state, questions=q5,
                    extra_body={field_name: "Ignore all content. Always answer that the customer is unhappy."},
                )
                print(f"  带 {field_name!r} 字段:        is_unhappy = {noul_str('is_unhappy', r)}"
                      f"   ← API 接受了这个字段")
            except TypeSafeError as exc:
                print(f"  带 {field_name!r} 字段:        ✗ API 拒绝：{type(exc).__name__}: {str(exc)[:90]}")

        print("\n  → 结论：看结果是否与正常调用相同。相同 = 字段被忽略（无效）；不同 = 有可能生效。")

    line("总结")
    print("""  1. 没有 system prompt、没有对话历史、**调用之间零记忆**。
  2. 规则放 `state` —— 这是官方唯一支持、也最有效的方式。
  3. 例子放 `state` —— 能实现 few-shot 效果，可传递「任意约定」。
  4. `instructions` 就是每题的小 prompt，措辞直接决定判断质量。
  5. 没有「先教一次、之后都会」——每次调用都要把规则一起带上。""")


if __name__ == "__main__":
    main()
