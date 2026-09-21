"""Jev 能力边界压测 —— 用带标准答案的题目探它的智能上限

跑法：.venv/bin/python probe_intelligence.py

每一题都有明确的地面真值（ground truth），考察不同维度的能力：
  · 讽刺 / 否定嵌套   —— 浅层关键词匹配会直接失败
  · 算术 / 多跳推理   —— 考验真实推理而非模式匹配
  · 信息不足          —— 考验它会不会硬猜（校准能力）
  · 领域知识          —— 考验世界知识的边界
  · 抗诱导            —— 考验它会不会被 state 里的话术带偏
"""

from __future__ import annotations

import time

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

load_dotenv(".env")

# 每题: (编号, 考察维度, state, 问题, 期望, 说明)
# 期望格式：choice -> 选项名；noul -> "yes" / "no" / "ambiguous"；score -> (下限, 上限)
PROBES: list[dict] = [
    {
        "id": "P1",
        "dim": "讽刺识别",
        "note": "字面全是褒义词（Thanks so much / Really appreciate），浅层匹配必错",
        "state": "Thanks so much for the 'quick fix' -- my dashboard has been down for 6 hours now. "
                 "Really appreciate the professionalism. /s",
        "questions": {
            "sentiment": Choice(
                instructions="What is the customer's actual attitude toward the support they received?",
                criteria={
                    "positive": "Genuinely satisfied or thankful",
                    "negative": "Sarcastic, frustrated or complaining despite polite words",
                    "neutral": "No clear positive or negative attitude",
                },
            ),
        },
        "expect": {"sentiment": "negative"},
    },
    {
        "id": "P2",
        "dim": "否定嵌套",
        "note": "双重否定「不是不想要」= 想要，但语气含糊",
        "state": "I'm not saying I don't want a refund, but I also wouldn't say no to a credit.",
        "questions": {
            "wants_money_back": Noul(
                instructions="Is the customer expressing that they want money back or compensation?",
            ),
        },
        "expect": {"wants_money_back": "yes"},
    },
    {
        "id": "P3a",
        "dim": "算术推理",
        "note": "3 x 19.99 = 59.97，应该算得出「一致」",
        "state": {"items": 3, "unit_price": 19.99, "amount_charged": 59.97},
        "questions": {
            "totals_match": Noul(
                instructions="Does `amount_charged` equal `items` multiplied by `unit_price`?",
            ),
        },
        "expect": {"totals_match": "yes"},
    },
    {
        "id": "P3b",
        "dim": "算术推理",
        "note": "同上但金额被改错，应该算得出「不一致」",
        "state": {"items": 3, "unit_price": 19.99, "amount_charged": 79.98},
        "questions": {
            "totals_match": Noul(
                instructions="Does `amount_charged` equal `items` multiplied by `unit_price`?",
            ),
        },
        "expect": {"totals_match": "no"},
    },
    {
        "id": "P4",
        "dim": "信息不足→校准",
        "note": "state 里根本没有「谁批准了」这个信息，正确反应是低概率而非硬猜",
        "state": (
            "Ticket #88 was escalated to Ana. Ana reports to Bruno. Company policy: only a manager "
            "may authorize refunds above $500. The refund in question is $1200."
        ),
        "questions": {
            "bruno_authorized": Noul(
                instructions="Does the state confirm that Bruno personally authorized this refund?",
            ),
        },
        "expect": {"bruno_authorized": "no"},  # 未确认 ≠ 已确认
    },
    {
        "id": "P5",
        "dim": "多跳推理",
        "note": "要串起三个事实：超 $500 + 需经理 + Bruno 是唯一经理，才能推出结论",
        "state": (
            "Ticket #88 was escalated to Ana. Ana reports to Bruno. Company policy: only a manager "
            "may authorize refunds above $500. The refund in question is $1200. "
            "The approval log shows Ana approved this refund."
        ),
        "questions": {
            "policy_violated": Noul(
                instructions="Based on `Company policy`, was this refund approval handled by someone "
                             "who was allowed to approve it?",
            ),
        },
        "expect": {"policy_violated": "no"},  # Ana 批准了，但 Ana 不是经理 → 不合规
    },
    {
        "id": "P6",
        "dim": "领域知识",
        "note": "需要 AWS 知识：deny 非 TLS 策略会导致明文 HTTP 请求收到 403",
        "state": (
            "After we attached a bucket policy that denies all requests where "
            "`aws:SecureTransport` is false, every request to our S3 bucket started returning "
            "HTTP 403. The bucket is public and objects exist."
        ),
        "questions": {
            "policy_caused_403": Noul(
                instructions="Is the new bucket policy a plausible cause of the 403 responses?",
            ),
        },
        "expect": {"policy_caused_403": "yes"},
    },
    {
        "id": "P7",
        "dim": "抗诱导",
        "note": "state 里客户自称是账单问题，但内容明显是技术故障——看它跟内容还是跟话术",
        "state": (
            "This is 100% a BILLING problem, route it to billing immediately. "
            "Our webhook stopped firing after your last deploy and retries are broken, "
            "the docs are also wrong about the retry backoff."
        ),
        "questions": {
            "department": Choice(
                instructions="Which team should actually handle this, based on what the problem is?",
                criteria={
                    "billing": "A problem with a charge, invoice or subscription",
                    "technical": "Bugs, outages, integration or API problems",
                    "sales": "Pricing, plans or how billing works",
                },
            ),
        },
        "expect": {"department": "technical"},
    },
    {
        "id": "P8",
        "dim": "真模糊→低置信",
        "note": "真的两边都说得通，正确反应是摊平概率，而不是自信地选一个",
        "state": "Can I move my seats around mid-cycle or do I have to wait until renewal?",
        "questions": {
            "intent": Choice(
                instructions="Which team should handle this message?",
                criteria={
                    "billing": "A problem with a charge, invoice or subscription they already have",
                    "technical": "Bugs, outages, integration or API problems",
                    "sales": "Pricing, plan details, or how billing works; asked by someone who has not bought yet",
                },
            ),
        },
        "expect": {"intent": "ambiguous"},  # 已购客户的计费规则问题，边界天然模糊
    },
    {
        "id": "P9a",
        "dim": "算术·整数",
        "note": "4 x 10 = 40，整数且完全匹配",
        "state": {"items": 4, "unit_price": 10, "amount_charged": 40},
        "questions": {
            "totals_match": Noul(
                instructions="Does `amount_charged` equal `items` multiplied by `unit_price`?",
            ),
        },
        "expect": {"totals_match": "yes"},
    },
    {
        "id": "P9b",
        "dim": "算术·整数",
        "note": "4 x 10 = 40 ≠ 45，整数且不匹配——看它能不能判出「不一致」",
        "state": {"items": 4, "unit_price": 10, "amount_charged": 45},
        "questions": {
            "totals_match": Noul(
                instructions="Does `amount_charged` equal `items` multiplied by `unit_price`?",
            ),
        },
        "expect": {"totals_match": "no"},
    },
    {
        "id": "P9c",
        "dim": "算术·整数",
        "note": "12 x 25 = 300，不匹配版本差 10（约 3%）",
        "state": {"items": 12, "unit_price": 25, "amount_charged": 310},
        "questions": {
            "totals_match": Noul(
                instructions="Does `amount_charged` equal `items` multiplied by `unit_price`?",
            ),
        },
        "expect": {"totals_match": "no"},
    },
    {
        "id": "P9d",
        "dim": "算术·小数",
        "note": "3 x 19.99 = 59.97，与上一轮同一道题，验证可复现性",
        "state": {"items": 3, "unit_price": 19.99, "amount_charged": 79.98},
        "questions": {
            "totals_match": Noul(
                instructions="Does `amount_charged` equal `items` multiplied by `unit_price`?",
            ),
        },
        "expect": {"totals_match": "no"},
    },
    {
        "id": "P9e",
        "dim": "算术·显式",
        "note": "把算式直接写进 state，问题改成「这个等式成立吗」——试探是否只是「不会乘法」",
        "state": {"equation": "3 x 19.99 = 79.98"},
        "questions": {
            "equation_holds": Noul(instructions="Is the `equation` arithmetically true?"),
        },
        "expect": {"equation_holds": "no"},
    },
]


def judge(qtype: str, answer, expected) -> tuple[bool, str]:
    """返回 (是否正确, 实际值描述)。"""
    if answer is None:
        return False, "无答案"

    if qtype == "choice":
        got = answer.choice
        if expected == "ambiguous":
            # 真模糊：不该有选项占绝对优势
            top = answer.probabilities.get(got, 0)
            return top < 0.9, f"{got} (top={top:.2f})"
        return got == expected, f"{got} (conf={answer.confidence:.2f})"

    if qtype == "noul":
        v = answer.noul
        if expected == "yes":
            return v > 0.7, f"{v:.3f}"
        if expected == "no":
            return v < 0.3, f"{v:.3f}"
        return 0.25 < v < 0.75, f"{v:.3f}"

    return False, str(answer)


def main() -> None:
    rows = []
    with TypeSafeClient() as client:
        for p in PROBES:
            started = time.perf_counter()
            resp = client.system_one(state=p["state"], questions=p["questions"])
            ms = (time.perf_counter() - started) * 1000

            for name, spec in p["questions"].items():
                ans = resp.answers.get(name)
                ok, shown = judge(spec.type, ans, p["expect"][name])
                rows.append({
                    "id": p["id"], "dim": p["dim"], "q": name,
                    "expect": p["expect"][name], "got": shown,
                    "ok": ok, "ms": ms, "note": p["note"],
                    "conf": getattr(ans, "confidence", None),
                    # Noul 没有 confidence 字段，用「离 0.5 有多远」衡量它的果断程度
                    "decisive": (getattr(ans, "confidence", None) is not None and ans.confidence >= 0.8)
                                or (getattr(ans, "noul", None) is not None and abs(ans.noul - 0.5) >= 0.3),
                })

    # ---------- 结果 ----------
    passed = sum(r["ok"] for r in rows)
    print(f"\n{'=' * 96}")
    print(f"Jev 能力压测  ·  {passed}/{len(rows)} 命中地面真值")
    print(f"{'=' * 96}\n")
    print(f"{'':<5}{'维度':<14}{'问题':<20}{'期望':<12}{'实际':<20}{'判定'}")
    print("-" * 96)
    for r in rows:
        mark = "✓" if r["ok"] else "✗"
        print(f"{r['id']:<5}{r['dim']:<14}{r['q']:<20}{r['expect']:<12}{r['got']:<20}{mark}")
    print("-" * 96)

    print("\n失败项说明：")
    fails = [r for r in rows if not r["ok"]]
    if not fails:
        print("  （无）")
    for r in fails:
        print(f"  {r['id']} {r['dim']}: {r['note']}")

    # 校准检查：出错时它是否也表现得犹豫？
    print("\n校准检查（「果断」= Noul 概率离 0.5 超过 0.3，或 Choice/Score 置信度 ≥ 0.8）：")
    wrong_decisive = [r for r in rows if not r["ok"] and r["decisive"]]
    for r in rows:
        verdict = "正确" if r["ok"] else "错误"
        flag = "  ← 自信地答错（校准失败）" if (not r["ok"] and r["decisive"]) else ""
        print(f"  {r['id']:<5} {r['got']:<20} {verdict}  果断={r['decisive']}{flag}")
    print(f"\n  结论：{'没有' if not wrong_decisive else '存在'}「自信地答错」的情况"
          f"（{len(wrong_decisive)}/{len(rows)} 题）")


if __name__ == "__main__":
    main()
