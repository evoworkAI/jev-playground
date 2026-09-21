"use strict";

/* ============================================================
   工具
   ============================================================ */
const $ = (sel) => document.querySelector(sel);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === null || v === undefined) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "value") node.value = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2).toLowerCase(), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined) node.append(c);
  return node;
}

const pct = (x) => `${(x * 100).toFixed(x < 0.1 && x > 0 ? 1 : 0)}%`;
/** 把 0~1 的比例映射成「避开通栏两端 8px」的 left/width，与 CSS 里的 padding 对齐。 */
const at = (frac) => `calc(8px + (100% - 16px) * ${Math.max(0, Math.min(1, frac))})`;
const span = (frac) => `calc((100% - 16px) * ${Math.max(0, Math.min(1, frac))})`;
/** 置信度条自身没有内边距，用 3px（指针半宽）补偿，让指针在 0 和 1 两端也不会被裁掉。 */
const confPos = (frac) => `calc(3px + (100% - 6px) * ${Math.max(0, Math.min(1, frac))})`;
/** JSON 里 dict[int, float] 的键会变成字符串，统一取数字键并排序。 */
const numKeys = (obj) => Object.keys(obj || {}).map(Number).sort((a, b) => a - b);
const confClass = (c) => (c < 0.5 ? "lo" : c < 0.8 ? "mid" : "hi");

/* ============================================================
   示例
   ============================================================ */
const PRESETS = [
  {
    label: "① 客服工单路由（英文，最经典的用法）",
    state_mode: "json",
    state_text: JSON.stringify(
      {
        customer: { name: "林然", plan: "pro", tenure_months: 14 },
        message:
          "I've been charged twice for order A-104. This is the second time this week and I'm losing sales. Please refund the duplicate charge ASAP.",
        order: {
          id: "A-104",
          charges: [
            { amount_usd: 49, status: "captured" },
            { amount_usd: 49, status: "captured" },
          ],
        },
        refund_policy: "Duplicate charges are refunded in full.",
      },
      null,
      2
    ),
    questions: [
      {
        name: "department",
        type: "choice",
        instructions: "Which team should handle `message`, given the rest of the state?",
        criteria: {
          billing: "A problem with a charge, invoice or subscription they ALREADY have",
          technical: "Bugs, outages, integration or API problems",
          sales: "Pricing, plan details, or how billing works, asked by someone who has NOT bought yet",
          other: "Nothing above fits",
        },
      },
      {
        name: "frustration",
        type: "score",
        instructions: "How frustrated does the customer appear in `message`?",
        criteria: [
          "Calm, only stating facts",
          "Frustrated but polite and civil",
          "Angry, strong language or an explicit complaint",
        ],
      },
      {
        name: "refund_requested",
        type: "noul",
        instructions: "Is the customer explicitly asking for a refund or a credit?",
        criteria: {
          true: "They ask for money back, a refund, or a credit",
          false: "They only report a problem or ask for help",
        },
      },
      {
        name: "policy_supports",
        type: "noul",
        instructions: "Does `refund_policy` cover the situation described in `message`?",
        criteria: {},
      },
      {
        name: "is_urgent",
        type: "noul",
        instructions: "Does `message` convey urgency or time-sensitivity?",
        criteria: {},
      },
    ],
  },
  {
    label: "② 内容审核（中文，测中文表现）",
    state_mode: "text",
    state_text:
      "这条评论：\n\n\"楼主你这方案我劝你别做了，纯属浪费时间。我之前用过同款，三天就崩了，售后还死不认账，客服态度差到离谱。顺便说下我这边有更好的替代品，需要的私信我，价格好商量，比你这个靠谱一百倍。\"",
    questions: [
      {
        name: "是否含广告引流",
        type: "noul",
        instructions: "评论中是否包含向站外或私信引流、推销自己产品或服务的意图？",
        criteria: {
          true: "出现「私信我」「加我」「有替代品」「价格好商量」等引流或推销表述",
          false: "只是在表达对内容的评价，没有推销任何东西",
        },
      },
      {
        name: "内容分类",
        type: "choice",
        instructions: "这条评论最主要属于哪一类？",
        criteria: {
          正常批评: "针对内容本身的负面评价，就事论事",
          人身攻击: "针对作者本人的侮辱、贬低或不尊重",
          广告引流: "推销产品、引导私信或站外联系",
          不实信息: "陈述了可核实为假的事实性说法",
          其他: "上述都不符合，或无法判断",
        },
      },
      {
        name: "违规程度",
        type: "score",
        instructions: "这条评论的违规严重程度如何？",
        criteria: [
          "语气不好但只针对内容，没有可执行的问题",
          "有明显不适表述，但未构成明确违规，边界情况需人工判",
          "构成明确违规，按社区规则应当处置",
        ],
      },
    ],
  },
  {
    label: "③ 简历筛选（复合打分：把模糊判断拆成原子维度）",
    state_mode: "text",
    state_text:
      "候选人在职 6 年，主力语言 Python（做过数据管道、内部平台，负责过服务的性能优化与架构拆分）。带过 4 人小组约两年，做过招聘和绩效。分布式系统方面设计过订单与库存两个核心服务的架构，没做过跨地域多活。日常写 Go 做网关侧改造。",
    questions: [
      {
        name: "python_depth",
        type: "score",
        instructions: "简历体现的 Python 深度如何？",
        criteria: [
          "未提及",
          "提到过，但没有细节",
          "在项目中使用过",
          "主力语言",
          "深度专精：架构设计、性能调优层面",
        ],
      },
      {
        name: "team_leadership",
        type: "score",
        instructions: "带团队的经历如何？",
        criteria: ["没有", "非正式指导他人", "带过小团队", "有直接下属", "同时管理多个团队"],
      },
      {
        name: "system_design",
        type: "score",
        instructions: "分布式系统设计经验如何？",
        criteria: [
          "未提及",
          "参与过讨论",
          "设计过组件",
          "负责过一个系统的整体架构",
          "跨领域大规模架构设计",
        ],
      },
      {
        name: "has_scale_gap",
        type: "noul",
        instructions: "简历中是否存在明显的规模化经验缺口（例如从未涉及跨地域、多活、海量流量）？",
        criteria: {},
      },
    ],
  },
  {
    label: "④ 规则对照实验（演示「常驻规则」怎么起作用）",
    state_mode: "json",
    state_text: JSON.stringify(
      { ticket: { plan: "free", message: "我的网站宕机了，正在损失订单，急需处理！" } },
      null,
      2
    ),
    rule_pack_mode: "json",
    rule_pack_text: JSON.stringify(
      {
        internal_conventions: [
          "（1）已付费客户提交的任何问题，一律标记 urgent，即使内容并不紧急；",
          "（2）免费用户提交的任何问题，一律标记 normal，无论内容多紧急、多严重。",
          "内容本身是否紧急，与本标签无关。",
        ],
      },
      null,
      2
    ),
    questions: [
      {
        name: "tag",
        type: "choice",
        // criteria 故意留空：标签含义完全由常驻规则定义，这样才能看清规则的作用
        instructions: "根据 state 中的 internal_conventions，这条工单应该打哪个标签？",
        criteria: { urgent: "", normal: "" },
      },
      {
        name: "content_is_urgent",
        type: "noul",
        instructions: "抛开内部约定，单看 `ticket.message` 的内容本身，这件事紧急吗？",
        criteria: {},
      },
    ],
  },
  {
    label: "⑤ 空白模板（从零开始填）",
    state_mode: "text",
    state_text: "",
    rule_pack_mode: "text",
    rule_pack_text: "",
    questions: [{ name: "你的问题名", type: "noul", instructions: "", criteria: {} }],
  },
];

/* ============================================================
   状态
   ============================================================ */
let questions = [];
let stateMode = "text";
let threshold = 0.5;
// lastData 同时承载「单次运行」和「对照实验」两种结果，拖阈值时按 kind 重新渲染
let lastData = null;
let rulePack = { enabled: true, mode: "json" };

/** 统一成前端编辑用的结构：choice → [{key,desc}]，score → [str]，noul → {true,false} */
function normalize(q) {
  const base = { name: q.name, type: q.type, instructions: q.instructions || "" };
  if (q.type === "choice") {
    const c = q.criteria || {};
    base.criteria = Object.entries(c).map(([key, desc]) => ({ key, desc: desc || "" }));
  } else if (q.type === "score") {
    base.criteria = [...(q.criteria || [])];
  } else {
    const c = q.criteria || {};
    base.criteria = { true: c.true || "", false: c.false || "" };
  }
  return base;
}

/** 前端结构 → 后端 payload */
function toPayload() {
  return questions.map((q) => {
    if (q.type === "choice") {
      const obj = {};
      for (const r of q.criteria) {
        const k = r.key.trim();
        if (k) obj[k] = r.desc.trim() || null;
      }
      return { name: q.name.trim(), type: "choice", instructions: q.instructions, criteria: obj };
    }
    if (q.type === "score") {
      return {
        name: q.name.trim(),
        type: "score",
        instructions: q.instructions,
        criteria: q.criteria.map((s) => s.trim()).filter(Boolean),
      };
    }
    return {
      name: q.name.trim(),
      type: "noul",
      instructions: q.instructions,
      criteria: { true: q.criteria.true.trim(), false: q.criteria.false.trim() },
    };
  });
}

/* ============================================================
   问题卡片
   ============================================================ */
function criteriaEditor(q, rerender) {
  const box = el("div", { class: "criteria" });

  if (q.type === "choice") {
    q.criteria.forEach((row, i) => {
      box.append(
        el(
          "div",
          { class: "crow" },
          el("input", {
            class: "ckey",
            value: row.key,
            spellcheck: "false",
            placeholder: "选项值",
            oninput: (e) => (q.criteria[i].key = e.target.value),
          }),
          el("input", {
            class: "cdesc",
            value: row.desc,
            placeholder: "描述什么情况属于这个选项（边界模糊时务必写清）",
            oninput: (e) => (q.criteria[i].desc = e.target.value),
          }),
          el("button", {
            class: "icon-btn",
            text: "✕",
            title: "删除选项",
            onclick: () => {
              q.criteria.splice(i, 1);
              rerender();
            },
          })
        )
      );
    });
    box.append(
      el("button", {
        class: "add-row",
        text: "+ 添加选项",
        onclick: () => {
          q.criteria.push({ key: "", desc: "" });
          rerender();
        },
      })
    );
  }

  if (q.type === "score") {
    q.criteria.forEach((text, i) => {
      box.append(
        el(
          "div",
          { class: "crow" },
          el("span", { class: "clevel", text: String(i) }),
          el("input", {
            class: "cdesc",
            value: text,
            placeholder: "描述「什么情况」落在这个等级，不要写「中等程度」",
            oninput: (e) => (q.criteria[i] = e.target.value),
          }),
          el("button", {
            class: "icon-btn",
            text: "✕",
            title: "删除等级",
            onclick: () => {
              q.criteria.splice(i, 1);
              rerender();
            },
          })
        )
      );
    });
    box.append(
      el("button", {
        class: "add-row",
        text: "+ 添加等级（从 0 开始，由低到高，最多 10 级）",
        onclick: () => {
          q.criteria.push("");
          rerender();
        },
      })
    );
  }

  if (q.type === "noul") {
    for (const [side, label] of [
      ["true", "「是」的含义"],
      ["false", "「否」的含义"],
    ]) {
      box.append(
        el(
          "div",
          { class: "crow noul-crow" },
          el("span", { class: "ckey", text: side === "true" ? "true =" : "false =" }),
          el("input", {
            class: "cdesc",
            value: q.criteria[side],
            placeholder: `${label}（可选，边界微妙时很有用）`,
            oninput: (e) => (q.criteria[side] = e.target.value),
          })
        )
      );
    }
  }

  return box;
}

/** 切换问题类型时给一套干净的最小模板，避免把示例里无关的选项带进来。 */
function blankCriteria(type) {
  if (type === "choice") return { "选项1": "", "选项2": "" };
  if (type === "score") return ["等级 0 的描述", "等级 1 的描述"];
  return { true: "", false: "" };
}

function questionCard(q, index) {
  const rerender = renderQuestions;

  const nameInput = el("input", {
    class: "qname",
    value: q.name,
    spellcheck: "false",
    placeholder: "问题名（只给你自己取结果用，不会发给模型）",
    oninput: (e) => (q.name = e.target.value),
  });

  const typeSel = el(
    "select",
    {
      class: "qtype",
      onchange: (e) => {
        const t = e.target.value;
        Object.assign(
          q,
          normalize({ name: q.name, type: t, instructions: q.instructions, criteria: blankCriteria(t) })
        );
        rerender();
      },
    },
    el("option", { value: "choice", text: "Choice 选择" }),
    el("option", { value: "score", text: "Score 打分" }),
    el("option", { value: "noul", text: "Noul 是/否" })
  );
  typeSel.value = q.type;

  const instr = el("textarea", {
    class: "qinstr",
    rows: 2,
    spellcheck: "false",
    placeholder: "用一句完整的问句说清要判断什么。可用 `字段名` 指向 state 里的具体字段。",
    oninput: (e) => (q.instructions = e.target.value),
  });
  instr.value = q.instructions;

  return el(
    "div",
    { class: "qcard", "data-type": q.type },
    el(
      "div",
      { class: "qcard-head" },
      nameInput,
      typeSel,
      el("button", {
        class: "icon-btn",
        text: "✕",
        title: "删除这个问题",
        onclick: () => {
          questions.splice(index, 1);
          rerender();
        },
      })
    ),
    instr,
    criteriaEditor(q, rerender)
  );
}

function renderQuestions() {
  $("#questions").replaceChildren(...questions.map(questionCard));
  zhSync($("#questions"));   // 卡片里的 select/textarea 值是直接赋的，得补扫
}

/* ============================================================
   结果可视化
   ============================================================ */
function confidenceMeter(conf) {
  return el(
    "div",
    { class: "conf" },
    el("div", { class: "conf-label", text: "置信度" }),
    el(
      "div",
      { class: "conf-track" },
      el("div", { class: "conf-mask", style: `width:${(conf * 100).toFixed(1)}%` }),
      el("div", { class: "conf-marker", style: `left:${confPos(conf)}` })
    ),
    el("div", {
      class: `conf-val ${confClass(conf)}`,
      text: conf.toFixed(2),
      title: conf < 0.5 ? "低于阈值：建议转人工" : "高于阈值",
    })
  );
}

function bars(entries, winner, wide = false) {
  return el(
    "div",
    { class: `bars${wide ? " wide" : ""}` },
    entries.map(([label, value]) =>
      el(
        "div",
        { class: `bar${winner === label ? " win" : ""}` },
        el("div", { class: "bar-label", text: label, title: label }),
        el("div", { class: "bar-track" }, el("div", { class: "bar-fill", style: `width:${(value * 100).toFixed(1)}%` })),
        el("div", { class: "bar-val", text: pct(value) })
      )
    )
  );
}

function resultCard(q, ans) {
  if (!ans) {
    return el(
      "div",
      { class: "rcard" },
      el("div", { class: "rcard-head" }, el("span", { class: "rname", text: q.name })),
      el("div", { class: "note err", text: "这次响应里没有这个问题的答案。" })
    );
  }

  const head = el(
    "div",
    { class: "rcard-head" },
    el("span", { class: "rname", text: q.name }),
    el("span", { class: `tag ${ans.type}`, text: ans.type.toUpperCase() }),
    el("span", { class: "spacer" })
  );
  const body = [];

  /* ---------- Choice ---------- */
  if (ans.type === "choice") {
    const low = ans.confidence < threshold;
    if (low) head.append(el("span", { class: "tag warn", text: "低于阈值 → 建议转人工" }));
    body.push(
      el(
        "div",
        { class: "picked" },
        el("span", { class: "pv", text: ans.choice }),
        el("span", { class: "pl", text: `最高概率选项 · ${pct(ans.probabilities[ans.choice] ?? 0)}` })
      ),
      bars(Object.entries(ans.probabilities), ans.choice),
      confidenceMeter(ans.confidence)
    );
    if (!("other" in ans.probabilities) && !("none_of_the_above" in ans.probabilities)) {
      body.push(
        el("div", {
          class: "note",
          text: "提示：选项里没有 other / none_of_the_above 这类兜底项。模型必须从你给的选项里选一个，缺兜底项时它会把「都不像」强行塞进最接近的那个。",
        })
      );
    }
  }

  /* ---------- Score ---------- */
  if (ans.type === "score") {
    const levels = numKeys(ans.probabilities);
    const legend = ans.legend || {};
    const max = Math.max(...levels, 1);
    const frac = ans.score / max;
    const low = ans.confidence < threshold;
    if (low) head.append(el("span", { class: "tag warn", text: "置信度偏低：等级描述可能不够可分" }));

    body.push(
      el(
        "div",
        { class: "scale" },
        el("div", { class: "scale-track" }),
        el("div", { class: "scale-fill", style: `width:${span(frac)}` }),
        levels.map((lv) => el("div", { class: "scale-tick", style: `left:${at(lv / max)}` }, el("span", { text: String(lv) }))),
        el("div", { class: "scale-marker", style: `left:${at(frac)}`, "data-score": ans.score.toFixed(2) })
      ),
      bars(levels.map((lv) => [`${lv} · ${legend[lv] ?? ""}`, ans.probabilities[lv]]), null, true),
      confidenceMeter(ans.confidence)
    );
    body.push(
      el("div", {
        class: "note",
        text: `分数 ${ans.score.toFixed(2)} 是各等级概率的加权平均，可以落在两档之间。一定要连着看分布：同样的分数，可能是「全压在第 1 档」，也可能是「第 0 档和第 2 档各一半」，这是完全不同的两种情况。`,
      })
    );
  }

  /* ---------- Noul ---------- */
  if (ans.type === "noul") {
    const v = ans.noul;
    const ambiguous = v >= 0.35 && v <= 0.65;
    if (ambiguous) head.append(el("span", { class: "tag warn", text: "模型在犹豫（≈0.5）" }));

    body.push(
      el(
        "div",
        { class: "picked" },
        el("span", { class: "pv", text: v.toFixed(3) }),
        el("span", { class: "pl", text: "「是」的概率" })
      ),
      el(
        "div",
        { class: "gauge" },
        el("div", { class: "gauge-track" }),
        el("div", { class: "gauge-good", style: `width:${span(v)}` }),
        el("div", { class: "gauge-marker", style: `left:${at(v)}` }),
        el("div", { class: "gauge-ends" }, el("span", { text: "0 否" }), el("span", { text: "1 是" }))
      )
    );
    if (ambiguous) {
      body.push(
        el("div", {
          class: "note",
          text: "Noul ≈ 0.5 不表示「中等」，它表示模型没法从你给的 state 里判出来。想衡量程度请改用 Score，或者把问题问得更具体（例如加上可核实的判据）。",
        })
      );
    }
    body.push(
      el("div", {
        class: "note",
        text: "Noul 没有单独的 confidence 字段——这个概率本身就是它全部的信念。",
      })
    );
  }

  const card = el("div", { class: "rcard" }, head, body);
  if (ans.type !== "noul" && ans.confidence < threshold) card.classList.add("low");
  return card;
}

function legendBlock() {
  return el(
    "div",
    { class: "legend" },
    el("h3", { text: "三种原语速查" }),
    el("div", { class: "legend-row" }, el("b", { text: "Choice" }), el("span", { text: "无序选项里选一个 → 选中值 + 各选项概率 + 置信度。最多 255 个选项。" })),
    el("div", { class: "legend-row s" }, el("b", { text: "Score" }), el("span", { text: "有序等级谱上的位置 → 分数（可落在两档之间）+ 各档概率 + 等级说明。2~10 级。" })),
    el("div", { class: "legend-row n" }, el("b", { text: "Noul" }), el("span", { text: "是/否 → 「是」的概率。没有单独的置信度字段。" })),
    el("div", { class: "legend-row" }, el("b", { text: "置信度" }), el("span", { text: "只由概率分布的集中程度决定。它是模型对自己判断的把握，不是正确率保证。" }))
  );
}

/* ============================================================
   网络
   ============================================================ */
function banner(text, kind = "") {
  const b = $("#banner");
  b.className = `banner ${kind}`.trim();
  b.textContent = text;
}

function hideBanner() {
  $("#banner").className = "banner hidden";
}

async function callApi(url, options) {
  let res;
  try {
    res = await fetch(url, options);
  } catch (err) {
    throw new Error("连不上本地服务。请确认 playground/server.py 还在运行。");
  }
  let data;
  try {
    data = await res.json();
  } catch (err) {
    throw new Error(`服务返回了非 JSON 响应（HTTP ${res.status}）`);
  }
  if (!data.ok) throw new Error(data.error || `请求失败（HTTP ${res.status}）`);
  return data;
}

async function checkModels() {
  try {
    const data = await callApi("api/models");
    const names = data.models.map((m) => m.name).join(" / ");
    $("#model-badge").className = "badge ok";
    $("#model-badge").textContent = `可用模型：${names}`;
    banner(`✓ key 有效。账号可用：${data.models.map((m) => `${m.name}（${String(m.release_date).slice(0, 10)}）`).join("、")}`, "ok");
  } catch (err) {
    $("#model-badge").className = "badge";
    $("#model-badge").textContent = "模型：未连接";
    banner(`✗ ${err.message}`, "err");
  }
}

/** 组装请求体。useRulePack=false 时故意不带规则，用于对照实验。 */
function buildBody(useRulePack) {
  return JSON.stringify({
    state_mode: stateMode,
    state_text: $("#state-text").value,
    questions: toPayload(),
    use_rule_pack: useRulePack,
    rule_pack_mode: rulePack.mode,
    rule_pack_text: $("#rp-text").value,
  });
}

async function evaluate(useRulePack) {
  return callApi("api/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: buildBody(useRulePack),
  });
}

async function run() {
  const btn = $("#btn-run");
  const cmp = $("#btn-compare");
  btn.disabled = cmp.disabled = true;
  btn.textContent = "运行中…";
  hideBanner();
  try {
    renderResults(await evaluate(rulePack.enabled));
  } catch (err) {
    banner(`✗ ${err.message}`, "err");
  } finally {
    btn.disabled = cmp.disabled = false;
    btn.innerHTML = "▶ 运行 <kbd>⌘/Ctrl + Enter</kbd>";
  }
}

/** 对照实验：同一份 state 和问题跑两次，唯一变量是「带不带常驻规则」。 */
async function runCompare() {
  const btn = $("#btn-run");
  const cmp = $("#btn-compare");
  btn.disabled = cmp.disabled = true;
  cmp.textContent = "跑两次…";
  hideBanner();
  try {
    const [off, on] = await Promise.all([evaluate(false), evaluate(true)]);
    renderCompare(off, on);
  } catch (err) {
    banner(`✗ ${err.message}`, "err");
  } finally {
    btn.disabled = cmp.disabled = false;
    cmp.textContent = "⇄ 对照实验";
  }
}

function warnConflicts(data) {
  const conflicts = data.rule_conflicts || [];
  if (conflicts.length) {
    banner(`⚠ 常驻规则与 state 存在同名键，已被 state 的值覆盖：${conflicts.join("、")}`, "err");
  }
}

function renderResults(data) {
  lastData = { kind: "single", data };
  const usedRules = rulePack.enabled && $("#rp-text").value.trim();
  $("#meta").replaceChildren(
    el("span", { class: "hl", text: `模型 ${data.model}` }),
    el("span", { text: `${data.elapsed_ms} ms` }),
    el("span", { text: `输入 ${data.usage?.input_tokens ?? "?"} tok` }),
    el("span", { text: `${questions.length} 个问题 / 1 次请求` }),
    el("span", { text: usedRules ? "已带常驻规则" : "未带常驻规则" })
  );
  $("#results").replaceChildren(
    ...questions.map((q) => resultCard(q, data.answers[q.name])),
    legendBlock()
  );
  warnConflicts(data);
}

/* ---------- 对照实验 ---------- */

/** 把答案压成短字符串，便于并排比较。 */
function answerSummary(ans) {
  if (!ans) return "（无答案）";
  if (ans.type === "choice") return `${ans.choice} · ${ans.confidence.toFixed(2)}`;
  if (ans.type === "score") return `${ans.score.toFixed(2)} · ${ans.confidence.toFixed(2)}`;
  return ans.noul.toFixed(3);
}

/** 两次答案是否算「实质不同」——阈值放宽，避免采样噪声被当成差异。 */
function isDiff(a, b) {
  if (!a || !b) return true;
  if (a.type === "choice") return a.choice !== b.choice;
  if (a.type === "score") return Math.abs(a.score - b.score) > 0.3;
  return Math.abs(a.noul - b.noul) > 0.1;
}

function renderCompare(off, on) {
  lastData = { kind: "compare", off, on };

  const rows = questions.map((q) => {
    const a = off.answers[q.name];
    const b = on.answers[q.name];
    const diff = isDiff(a, b);
    return el(
      "div",
      { class: `cmp-row${diff ? " diff" : ""}` },
      el("div", { class: "cmp-q" }, el("b", { text: q.name }), el("em", { text: q.type })),
      el("div", { class: "cmp-v", text: answerSummary(a) }),
      el("div", { class: "cmp-v", text: answerSummary(b) }),
      el("div", { class: "cmp-flag", text: diff ? "变了" : "不变" })
    );
  });

  const diffs = questions.filter((q) => isDiff(off.answers[q.name], on.answers[q.name])).length;
  $("#meta").replaceChildren(
    el("span", { class: "hl", text: "对照实验" }),
    el("span", { text: `不带规则 ${off.elapsed_ms} ms · 带规则 ${on.elapsed_ms} ms` }),
    el("span", { text: `输入 ${off.usage?.input_tokens ?? "?"} + ${on.usage?.input_tokens ?? "?"} tok` }),
    el("span", { text: `${diffs}/${questions.length} 个问题的结果发生变化` })
  );
  $("#results").replaceChildren(
    el(
      "div",
      { class: "cmp" },
      el(
        "div",
        { class: "cmp-head" },
        el("div", { class: "cmp-q", text: "问题" }),
        el("div", { class: "cmp-v", text: "不带常驻规则" }),
        el("div", { class: "cmp-v", text: "带常驻规则" }),
        el("div", { class: "cmp-flag", text: "差异" })
      ),
      rows
    ),
    el("div", {
      class: "note",
      text: "读法：结果被规则改变的问题，说明它确实在读你的规则；而「本该受影响却没变」的，通常是规则写法有歧义。"
        + "注意区分两类问题——受规则支配的（如 label 分配）应该变，客观事实判断（如内容本身是否紧急）不应该变。",
    }),
    legendBlock()
  );
  warnConflicts(on);
}

/** 显示「实际发出去的 state」和问题定义，用于确认规则合并是否正确。 */
function togglePeek() {
  const existing = $("#peek-box");
  if (existing) {
    existing.remove();
    return;
  }
  const data = lastData ? (lastData.kind === "single" ? lastData.data : lastData.on) : null;
  const box = el("pre", { class: "peek", id: "peek-box" });
  box.textContent = [
    "=== 实际发出去的 state（常驻规则已合并）===",
    data ? JSON.stringify(data.sent_state, null, 2) : "（还没运行过）",
    "",
    "=== 问题定义 ===",
    JSON.stringify(toPayload(), null, 2),
  ].join("\n");
  $("#meta").after(box);
}

/* ============================================================
   简繁同步
   ============================================================ */
/** input/textarea 的 .value 赋值不算 DOM 变更，zh.js 的 MutationObserver
 *  看不见，所以每次程序写完表单值都得主动喊一声让它重扫。
 *  漏掉的话症状很怪：页面显示着繁體，但发出去的是简体（payload 是从
 *  内部状态拼的，不是读 DOM）。 */
function zhSync(root) {
  if (window.ZH) ZH.refresh(root || document);
}

/* ============================================================
   初始化
   ============================================================ */
function loadPreset(index) {
  const p = PRESETS[index];
  setStateMode(p.state_mode);
  $("#state-text").value = p.state_text;
  setRulePack(p.rule_pack_mode || "json", p.rule_pack_text || "");
  questions = p.questions.map(normalize);
  renderQuestions();
  // 必须排在 run() 前面：run() 的 state / 常驻规则是直接从 DOM 读的
  // （questions 却读内部状态）。晚一步同步的话，首屏那次自动运行会把
  // 简体发出去，而界面上已经是繁體了。
  zhSync();
  // 空白模板没有 state，自动运行只会弹报错，改成给一句引导
  if (p.state_text.trim()) {
    run();
  } else {
    showPlaceholder("空白模板：左边填要判断的内容 → 写问题 → 定义选项 → 点「运行」或「对照实验」。");
  }
}

function setStateMode(mode) {
  stateMode = mode;
  for (const btn of $("#state-mode").children) {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  }
}

function setRulePack(mode, text) {
  rulePack.mode = mode;
  $("#rp-text").value = text;
  for (const btn of $("#rp-mode").children) {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  }
}

function showPlaceholder(text) {
  lastData = null;
  $("#meta").replaceChildren();
  $("#results").replaceChildren(el("p", { class: "placeholder", text }));
}

/** 清空全部输入，回到从零开始。 */
function resetAll() {
  setStateMode("text");
  $("#state-text").value = "";
  setRulePack("json", "");
  $("#rp-enabled").checked = true;
  rulePack.enabled = true;
  questions = [normalize({ name: "你的问题名", type: "noul", instructions: "", criteria: {} })];
  renderQuestions();
  const blank = PRESETS.findIndex((p) => p.label.includes("空白模板"));
  if (blank >= 0) $("#preset-select").value = String(blank);
  showPlaceholder("已清空。填入 state → 写问题 → 定义选项 → 点「运行」或「对照实验」。");
  zhSync();
}

function init() {
  const sel = $("#preset-select");
  PRESETS.forEach((p, i) => sel.append(el("option", { value: String(i), text: p.label })));
  sel.addEventListener("change", () => loadPreset(Number(sel.value)));

  for (const btn of $("#state-mode").children) {
    btn.addEventListener("click", () => setStateMode(btn.dataset.mode));
  }

  for (const btn of $("#rp-mode").children) {
    btn.addEventListener("click", () => setRulePack(btn.dataset.mode, $("#rp-text").value));
  }

  $("#rp-enabled").addEventListener("change", (e) => {
    rulePack.enabled = e.target.checked;
    $(".rulepack").classList.toggle("disabled", !rulePack.enabled);
  });

  $("#btn-add-q").addEventListener("click", () => {
    const existing = new Set(questions.map((q) => q.name.trim()));
    let n = questions.length + 1;
    while (existing.has(`question_${n}`)) n += 1;
    questions.push(
      normalize({
        name: `question_${n}`,
        type: "noul",
        instructions: "",
        criteria: {},
      })
    );
    renderQuestions();
  });

  $("#btn-run").addEventListener("click", run);
  $("#btn-compare").addEventListener("click", runCompare);
  $("#btn-peek").addEventListener("click", togglePeek);
  $("#btn-reset").addEventListener("click", resetAll);
  $("#btn-models").addEventListener("click", checkModels);

  const slider = $("#threshold");
  slider.addEventListener("input", () => {
    threshold = Number(slider.value);
    $("#threshold-val").textContent = threshold.toFixed(2);
    // 阈值是纯本地规则，改它不需要重新调模型——直接按新阈值重新判定已有结果
    if (lastData?.kind === "single") renderResults(lastData.data);
    else if (lastData?.kind === "compare") renderCompare(lastData.off, lastData.on);
  });

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      run();
    }
  });

  loadPreset(0);
  checkModels();
}

init();
