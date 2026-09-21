"""Jev 最小可用案例 —— 客服工单路由

Jev 不生成任何文字，它只回答你在调用前定义好的「带类型的判断」：

  Choice — 从一组无序选项里选一个   → .choice / .probabilities / .confidence
  Score  — 在一个有序等级谱上打分    → .score  / .probabilities / .legend / .confidence
  Noul   — 是 / 否                  → .noul （回答「是」的概率，0~1）

用法：
    .venv/bin/python ticket_router.py            # 跑三张示例工单
    .venv/bin/python ticket_router.py --check    # 只验证 key 能不能通

前置：把 API key 填进同目录的 .env（TYPESAFE_API_KEY）。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import (
    Choice,
    Noul,
    Score,
    TypeSafeAuthenticationError,
    TypeSafeClient,
    TypeSafeError,
)

load_dotenv(Path(__file__).with_name(".env"))

# 阈值是本案例自己定的业务规则，不是官方默认值。
# 原则：出错代价越高，要求的置信度越高。
REVIEW_FLOOR = 0.50           # 低于此置信度：判断不可信，转人工
AUTO_REFUND_CONFIDENCE = 0.85  # 触发自动退款（动钱）要求更高的置信度

# 所有问题都在一次调用里并行回答，加问题几乎不增加耗时，所以可以放心多问。
QUESTIONS = {
    "department": Choice(
        instructions="Which team should handle `message`, given the rest of the state?",
        # 描述里点明「谁在问 / 是否已经买过」，把容易混淆的边界钉死。
        # 实测：只把 billing 改成「已购买后的账单问题」、sales 改成「未购买者的定价/计费咨询」，
        # 同一张售前咨询工单就从 billing(0.83) 翻到 sales(1.00)。
        criteria={
            "billing": "A problem with a charge, invoice or subscription they ALREADY have",
            "technical": "Bugs, outages, integration or API problems",
            "sales": "Pricing, plan details, or how billing works, asked by someone who has NOT bought yet",
            "other": "Nothing above fits",
        },
    ),
    "frustration": Score(
        # Score 的每个等级要描述「什么情况」，而不是「多少程度」
        instructions="How frustrated does the customer appear in `message`?",
        criteria=[
            "Calm, only stating facts",
            "Frustrated but polite and civil",
            "Angry, strong language or an explicit complaint",
        ],
    ),
    "refund_requested": Noul(
        instructions="Is the customer explicitly asking for a refund or a credit?",
        criteria={
            "true": "They ask for money back, a refund, or a credit",
            "false": "They only report a problem or ask for help",
        },
    ),
    "policy_supports": Noul(
        instructions="Does `refund_policy` cover the situation described in `message`?",
    ),
    "is_urgent": Noul(
        instructions="Does `message` convey urgency or time-sensitivity?",
    ),
}

TICKETS = [
    {
        "id": "T-1001",
        "state": {
            "customer": {"name": "林然", "plan": "pro", "tenure_months": 14},
            "message": (
                "I've been charged twice for order A-104. This is the second time this week "
                "and I'm losing sales. Please refund the duplicate charge ASAP."
            ),
            "order": {
                "id": "A-104",
                "charges": [
                    {"amount_usd": 49, "status": "captured"},
                    {"amount_usd": 49, "status": "captured"},
                ],
            },
            "refund_policy": "Duplicate charges are refunded in full.",
        },
    },
    {
        "id": "T-1002",
        "state": {
            "customer": {"name": "Marco", "plan": "free", "tenure_months": 0},
            "message": (
                "Hi! Before we buy, can you explain how seats are billed when someone "
                "leaves the team mid-month?"
            ),
            "refund_policy": "Refunds are available within 14 days of purchase.",
        },
    },
    {
        "id": "T-1003",
        "state": {
            "customer": {"name": "Aisha", "plan": "team", "tenure_months": 3},
            "message": (
                "the webhook fires sometimes? not always. maybe retry logic broken. "
                "also why is the docs so out of date. anyway it's blocking our launch."
            ),
            "refund_policy": "Refunds are available within 14 days of purchase.",
        },
    },
]


def build_client() -> TypeSafeClient:
    if not os.getenv("TYPESAFE_API_KEY"):
        sys.exit("✗ 没读到 TYPESAFE_API_KEY，请先把 key 填进 .env")
    # 不传 model 时 SDK 用 TYPESAFE_DEFAULT_MODEL，默认 jev-latest。
    return TypeSafeClient()


def check_key(client: TypeSafeClient) -> None:
    """最小连通性测试：列出这个账号能用的模型。"""
    resp = client.models.list()
    print("✓ key 有效，账号可用的模型：")
    for m in resp.models:
        print(f"  - {m.name}  ({m.release_date})  {m.description}")


def show_answers(resp) -> None:
    """把结构化答案按类型打印出来。"""
    for name, ans in resp.answers.items():
        if ans.type == "choice":
            spread = "  ".join(f"{k}={v:.2f}" for k, v in ans.probabilities.items())
            print(f"    [Choice] {name:<17} → {ans.choice:<9} confidence={ans.confidence:.2f}")
            print(f"             分布: {spread}")
        elif ans.type == "score":
            spread = "  ".join(f"{k}={v:.2f}" for k, v in ans.probabilities.items())
            print(f"    [Score ] {name:<17} → {ans.score:.2f} (共 {len(ans.legend)} 级) confidence={ans.confidence:.2f}")
            print(f"             分布: {spread}")
        else:  # noul
            print(f"    [Noul  ] {name:<17} → {ans.noul:.3f}  (『是』的概率)")


def route(resp) -> list[str]:
    """业务规则留在你自己的代码里：模型只负责判断，代码决定动作。"""
    dept = resp.choices["department"]
    frustration = resp.scores["frustration"]
    refund = resp.nouls["refund_requested"]
    policy = resp.nouls["policy_supports"]
    urgent = resp.nouls["is_urgent"]

    # 置信度太低就别硬猜，交给人。宁可慢，不可错。
    if dept.confidence < REVIEW_FLOOR:
        return [f"× 分流置信度 {dept.confidence:.2f} < {REVIEW_FLOOR} → 转人工分流"]

    actions = [f"→ 路由到 {dept.choice} 队列"]

    if dept.choice == "billing" and refund.noul >= 0.7:
        if policy.noul >= 0.8 and dept.confidence >= AUTO_REFUND_CONFIDENCE:
            actions.append("→ 命中自动退款流程（政策覆盖 + 高置信度）")
        else:
            actions.append("→ 有退款诉求，但政策/置信度不足 → 人工核单")

    if urgent.noul >= 0.8:
        actions.append("→ 标记紧急")
    if frustration.score >= 1.5 and frustration.confidence >= 0.5:
        actions.append(f"→ 标记高情绪客户（frustration={frustration.score:.2f}）")

    return actions


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev 客服工单路由案例")
    parser.add_argument("--check", action="store_true", help="只验证 API key")
    args = parser.parse_args()

    with build_client() as client:
        try:
            if args.check:
                check_key(client)
                return

            for ticket in TICKETS:
                started = time.perf_counter()
                # 关键点：一次请求带上所有问题，模型并行回答（不是逐个追问）。
                resp = client.system_one(state=ticket["state"], questions=QUESTIONS)
                elapsed_ms = (time.perf_counter() - started) * 1000

                print(f"\n{'=' * 68}")
                print(f"工单 {ticket['id']}   （{elapsed_ms:.0f} ms，in={resp.usage.input_tokens} tok）")
                print(f"内容: {ticket['state']['message'][:90]}...")
                print(f"{'-' * 68}")
                print(f"  模型版本: {resp.model}")
                show_answers(resp)
                print(f"{'-' * 68}")
                for line in route(resp):
                    print(f"  {line}")

        except TypeSafeAuthenticationError:
            sys.exit("✗ 认证失败：TYPESAFE_API_KEY 不对或已失效")
        except TypeSafeError as exc:
            sys.exit(f"✗ 调用失败：{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
