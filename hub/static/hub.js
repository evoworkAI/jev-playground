/* ==========================================================================
   Jev 演示合集 · 前端
   ========================================================================== */
"use strict";

/* ---------------- 小工具 ---------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** 建元素：el("div", {class:"x"}, "文字" | 子节点…)
 *
 * value / checked / selected 这三个必须走「属性」而不是 setAttribute ——
 * 比如动态建出来的 <option> 事后补個 selected 属性，浏览器不会真的选中它。 */
const PROPS = new Set(["value", "checked", "selected"]);
function el(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (PROPS.has(k)) node[k] = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2).toLowerCase(), v);
    else node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

/** 极简 Markdown：只认 **粗体** */
function md(text) {
  const frag = document.createDocumentFragment();
  String(text ?? "").split(/\*\*(.+?)\*\*/g).forEach((part, i) => {
    frag.append(i % 2 ? el("b", { text: part }) : document.createTextNode(part));
  });
  return frag;
}

const num = (v, d = 3) => (v == null ? "—" : Number(v).toFixed(d));

/* ---------------- 网络 ---------------- */
async function post(path, body) {
  let res;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  } catch {
    throw new Error("连不上本地服务，请确认 python3 hub/server.py 还在运行");
  }
  let data;
  try {
    data = await res.json();
  } catch {
    throw new Error(`服务返回了非 JSON 响应（HTTP ${res.status}）`);
  }
  return data;
}

/* ==========================================================================
   左侧链接栏 + 内容区切换
   链接表就是唯一的「导航配置」—— 加一个演示只需要在这里加一行 + 加一个 section
   ========================================================================== */
const RAIL = [
  { id: "home", icon: "🏠", text: "总览", title: "这是什么" },
  { id: "pacman", icon: "👾", text: "吃豆人 AI 决策", badge: "对局", live: true },
  { id: "moderation", icon: "🛡️", text: "内容审核" },
  { id: "resume", icon: "📄", text: "简历筛选" },
  { id: "blank", icon: "🧪", text: "空白模板" },
];

let activeTab = null;
const frames = {};   // tabId -> iframe

function renderRail() {
  const rail = $("#rail");
  const meta = $("#railMeta");   // 保留它（在 HTML 里已存在），链接插到它前面
  const links = RAIL.map((t) =>
    el("button", {
      class: "rail-link", "data-tab": t.id,
      title: t.title || t.text,
      onclick: () => activate(t.id),
    },
      el("span", { class: "rl-ico", text: t.icon }),
      el("span", { class: "rl-text", text: t.text }),
      t.badge ? el("span", { class: `rl-badge${t.live ? " live" : ""}`, text: t.badge }) : null
    ));
  rail.replaceChildren(el("div", { class: "rail-title", text: "演示列表" }), ...links, meta);
}

function activate(id) {
  if (activeTab === id) return;
  const prev = RAIL.find((t) => t.id === activeTab);

  // 离开吃豆人时让它暂停：iframe 里的 RAF 和 AI 决策不会因为看不见就停下
  if (prev && prev.id === "pacman" && frames.pacman && frames.pacman.contentWindow) {
    try {
      frames.pacman.contentWindow.postMessage({ type: "hub:pause" }, "*");
    } catch { /* 静默跳过，不影响切 tab */ }
  }

  activeTab = id;
  $$(".rail-link").forEach((b) => b.classList.toggle("active", b.dataset.tab === id));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.dataset.tab === id));

  if (id === "pacman") {
    mountPacman();
    resumePacman();   // 离开时让它停了，回来得叫醒（详见 resumePacman 注释）
  }
  location.hash = id;
}

/** 吃豆人用 iframe 装进来，而且是第一次点开这个 tab 才创建 —— 否则一进页面就开始跑 */
function mountPacman() {
  const wrap = $('.frame-wrap[data-frame="pacman"]');
  if (!wrap || frames.pacman) return;
  // embed=1：让吃豆人页藏掉自己的页头页脚，只留中间那块内容
  const iframe = el("iframe", { src: "/pacman/?embed=1", title: "吃豆人 AI 决策实测" });
  wrap.replaceChildren(iframe);
  frames.pacman = iframe;
}

/* 把吃豆人叫醒。
   离开这个 tab 时我们会发 hub:pause，它那边会把渲染循环整个停掉（不只是暂停，
   否则 iframe 里的 RAF 会一直空转烧 CPU）。所以切回来必须把这一下补上，
   不然看到的是一张冻住的画面 —— 霓虹字不闪、嘴巴也不动。 */
function resumePacman() {
  const f = frames.pacman;
  if (!f || !f.contentWindow) return;   // 首次挂载时 iframe 还没加载完，本来也没被暂停
  try {
    f.contentWindow.postMessage({ type: "hub:resume" }, "*");
  } catch { /* 静默跳过，不影响切 tab */ }
}

/* ==========================================================================
   示例数据（对应 playground 里的 ② 内容审核 / ③ 简历筛选 / ⑤ 空白模板）
   ========================================================================== */
const PRESETS = {
  moderation: {
    title: "内容审核",
    hint: "中文场景 · 一次调用并行回答 3 个问题",
    state_mode: "text",
    state_text:
      "这条评论：\n\n\"楼主你这方案我劝你别做了，纯属浪费时间。我之前用过同款，三天就崩了，" +
      "售后还死不认账，客服态度差到离谱。顺便说下我这边有更好的替代品，需要的私信我，" +
      "价格好商量，比你这个靠谱一百倍。\"",
    rule_pack_mode: "text",
    rule_pack_text: "",
    questions: [
      {
        name: "是否含广告引流",
        type: "noul",
        instructions: "评论中是否包含向站外或私信引流、推销自己产品或服务的意图？",
        noulTrue: "出现「私信我」「加我」「有替代品」「价格好商量」等引流或推销表述",
        noulFalse: "只是在表达对内容的评价，没有推销任何东西",
      },
      {
        name: "内容分类",
        type: "choice",
        instructions: "这条评论最主要属于哪一类？",
        choiceRows: [
          ["正常批评", "针对内容本身的负面评价，就事论事"],
          ["人身攻击", "针对作者本人的侮辱、贬低或不尊重"],
          ["广告引流", "推销产品、引导私信或站外联系"],
          ["不实信息", "陈述了可核实为假的事实性说法"],
          ["其他", "上述都不符合，或无法判断"],
        ],
      },
      {
        name: "违规程度",
        type: "score",
        instructions: "这条评论的违规严重程度如何？",
        scoreRows: [
          "语气不好但只针对内容，没有可执行的问题",
          "有明显不适表述，但未构成明确违规，边界情况需人工判",
          "构成明确违规，按社区规则应当处置",
        ],
      },
    ],
  },

  resume: {
    title: "简历筛选",
    hint: "复合打分 · 把模糊判断拆成原子维度",
    state_mode: "text",
    state_text:
      "候选人在职 6 年，主力语言 Python（做过数据管道、内部平台，负责过服务的性能优化与架构拆分）。" +
      "带过 4 人小组约两年，做过招聘和绩效。分布式系统方面设计过订单与库存两个核心服务的架构，" +
      "没做过跨地域多活。日常写 Go 做网关侧改造。",
    rule_pack_mode: "text",
    rule_pack_text: "",
    questions: [
      {
        name: "python_depth",
        type: "score",
        instructions: "简历体现的 Python 深度如何？",
        scoreRows: [
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
        scoreRows: ["没有", "非正式指导他人", "带过小团队", "有直接下属", "同时管理多个团队"],
      },
      {
        name: "system_design",
        type: "score",
        instructions: "分布式系统设计经验如何？",
        scoreRows: [
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
        noulTrue: "明确缺少跨地域、多活、海量流量这类经历的描述",
        noulFalse: "有相关经历，或者缺口并不明显",
      },
    ],
  },

  blank: {
    title: "空白模板",
    hint: "从零开始 · 填内容 → 写问题 → 定义选项",
    state_mode: "text",
    state_text: "",
    rule_pack_mode: "text",
    rule_pack_text: "",
    questions: [
      {
        name: "你的问题名",
        type: "noul",
        instructions: "用一句完整的话写出要判断什么，措辞越具体越准。",
        noulTrue: "",
        noulFalse: "",
      },
    ],
  },
};

/* ==========================================================================
   工作台：一个组件，三个 tab 各实例化一份
   ========================================================================== */
class Workbench {
  constructor(root, presetKey) {
    this.root = root;
    this.presetKey = presetKey;
    this.busy = false;
    this.lastPayloads = null;
    this.state = null;          // 内部模型，提交时再转成接口要的形状
    this.load(this.presetKey, { render: false });
    this.render();
  }

  /** 把预设深拷一份成内部模型（预设本身不被动，所以「恢复示例」永远能回到原样） */
  load(key, { render = true } = {}) {
    const p = JSON.parse(JSON.stringify(PRESETS[key]));
    this.preset = p;
    this.state = {
      title: p.title,
      hint: p.hint,
      stateMode: p.state_mode,
      stateText: p.state_text,
      ruleOn: false,
      ruleMode: p.rule_pack_mode,
      ruleText: p.rule_pack_text,
      questions: p.questions,
    };
    if (render) this.render();
    this.clearResults();
  }

  /* ---------------- 渲染 ---------------- */
  render() {
    const s = this.state;
    this.root.replaceChildren(
      /* 顶栏：标题 + 运行按钮，position: sticky 钉在内容区顶端。
         原来这排按钮在编辑区的最下方，配置一多就得滚下去才能点运行 ——
         录屏时很难看，操作也别扭。钉住之后滚动编辑区它一直可见。 */
      el("div", { class: "wb-bar" },
        el("div", { class: "wb-bar-main" },
          el("h2", { text: s.title }),
          el("div", { class: "wb-hint", text: s.hint })),
        el("div", { class: "actions" },
          el("button", { class: "primary", id: this.id("run"), text: "▶ 运行", onclick: () => this.run() }),
          el("button", { class: "ghost", id: this.id("peek"), text: "查看实际请求", onclick: () => this.peek() }),
          el("button", { class: "link", text: "恢复示例", onclick: () => this.load(this.presetKey) }))),
      el("div", { class: "wb-grid" },
        el("div", { class: "wb-col" },
          this.renderStateBlock(),
          this.renderRuleBlock()),
        el("div", { class: "wb-col" },
          el("div", { class: "wb-head" },
            el("h2", { text: "结果" }),
            el("div", { class: "wb-hint", id: this.id("meta"), text: "还没跑" })),
          el("div", { class: "results", id: this.id("results") },
            el("p", { class: "placeholder" }, md(
              "点「运行」。\n\nJev 不会返回一段话让你去解析，它直接给类型化的值：\n" +
              "**Choice** 选中项 + 全部选项概率 + 置信度\n" +
              "**Score** 分数（可落在两档之间）+ 每档概率 + 等级说明\n" +
              "**Noul** 「是」的概率（0~1）")))),
      ),
    );
    // 问题编辑器放在 state 块下面（顺序更符合操作直觉）
    $("#" + this.id("stateBlock"), this.root).after(this.renderQuestionsBlock());
    // input/textarea 的 .value 不算 DOM 变更，MutationObserver 接不住，
    // 只能在这里主动补扫一遍。render() 是唯一写表单值的地方，一处就够。
    if (window.ZH) ZH.refresh(this.root);
  }

  id(suffix) {
    return `wb-${this.presetKey}-${suffix}`;
  }

  renderStateBlock() {
    const s = this.state;
    const ta = el("textarea", {
      id: this.id("state"), rows: 9, spellcheck: "false", value: s.stateText,
      oninput: (e) => { s.stateText = e.target.value; },
    });
    return el("div", { class: "block", id: this.id("stateBlock") },
      el("div", { class: "block-label" }, "state ", el("em", { text: "要被判断的内容，每次调用都整份发给它" })),
      ta);
  }

  renderQuestionsBlock() {
    const s = this.state;
    const list = el("div", { id: this.id("qlist") },
      ...s.questions.map((q, i) => this.renderQuestion(q, i)));
    return el("div", { class: "block" },
      el("div", { class: "block-label" },
        `questions `, el("em", { text: `一次调用全部并行回答 · 当前 ${s.questions.length} 个` })),
      list,
      el("button", {
        class: "q-add", text: "+ 加一个问题",
        onclick: () => {
          s.questions.push(this.blankQuestion());
          this.render();
        },
      }));
  }

  blankQuestion() {
    return { name: `问题${this.state.questions.length + 1}`, type: "noul", instructions: "", noulTrue: "", noulFalse: "" };
  }

  renderQuestion(q, i) {
    const s = this.state;

    // 加/删选项、换类型只重画这个问题的 criteria 区，不整块重建 ——
    // 否则正在编辑的 instructins 会丢焦点、光标跳回开头。
    const body = el("div", {});
    const repaint = () => body.replaceChildren(...this.renderCriteria(q, repaint));

    const head = el("div", { class: "q-edit-top" },
      el("input", {
        class: "q-name", value: q.name, spellcheck: "false",
        title: "问题名只用于你自己取结果，不会发给模型",
        oninput: (e) => { q.name = e.target.value; },
      }),
      el("select", {
        onchange: (e) => {
          q.type = e.target.value;
          // 换类型时补上该类型需要的字段，别让渲染拿到 undefined
          if (q.type === "choice" && !q.choiceRows) q.choiceRows = [["选项A", ""], ["选项B", ""]];
          if (q.type === "score" && !q.scoreRows) q.scoreRows = ["等级 0 的描述", "等级 1 的描述"];
          if (q.type === "noul" && q.noulTrue == null) { q.noulTrue = ""; q.noulFalse = ""; }
          repaint();
        },
      },
        ...[["choice", "Choice 选一个"], ["score", "Score 打分"], ["noul", "Noul 是/否"]]
          .map(([v, t]) => el("option", { value: v, text: t, selected: q.type === v })),
      ),
      el("button", {
        class: "icon-btn", text: "×", title: "删掉这个问题",
        // 删问题会改变整个列表，这里重建一次是可接受的
        onclick: () => { s.questions.splice(i, 1); this.render(); },
      })
    );

    repaint();

    return el("div", { class: "q-edit" },
      head,
      el("textarea", {
        class: "q-instr", rows: 2, spellcheck: "false", value: q.instructions || "",
        placeholder: "instructions：这就是它的小 prompt，措辞直接决定判断质量",
        oninput: (e) => { q.instructions = e.target.value; },
      }),
      body);
  }

  renderCriteria(q, repaint) {
    if (q.type === "choice") {
      const rows = q.choiceRows || (q.choiceRows = [["", ""], ["", ""]]);
      return [
        ...rows.map((row, ri) => el("div", { class: "q-line" },
          el("input", {
            class: "q-key", value: row[0], placeholder: "选项名", spellcheck: "false",
            oninput: (e) => { row[0] = e.target.value; },
          }),
          el("input", {
            value: row[1], placeholder: "什么情况算这个选项（可留空）", spellcheck: "false",
            oninput: (e) => { row[1] = e.target.value; },
          }),
          el("button", {
            class: "icon-btn", text: "×", title: "删掉这个选项",
            onclick: () => { rows.splice(ri, 1); repaint(); },
          })
        )),
        el("button", {
          class: "q-add", text: "+ 加一个选项",
          onclick: () => { rows.push(["", ""]); repaint(); },
        }),
        el("div", { class: "tip", text: "至少 2 个、最多 255 个选项。选项名要短，说明要写清「什么情况算它」。" }),
      ];
    }

    if (q.type === "score") {
      const rows = q.scoreRows || (q.scoreRows = ["", ""]);
      return [
        ...rows.map((lv, ri) => el("div", { class: "q-line" },
          el("input", {
            class: "q-key", value: String(ri), readOnly: true, title: "位置就是分数，不可改",
          }),
          el("input", {
            value: lv, placeholder: "这一档描述的是什么情况", spellcheck: "false",
            oninput: (e) => { rows[ri] = e.target.value; },
          }),
          el("button", {
            class: "icon-btn", text: "×", title: "删掉这一档",
            onclick: () => { rows.splice(ri, 1); repaint(); },
          })
        )),
        el("button", {
          class: "q-add", text: "+ 加一档",
          onclick: () => { rows.push(""); repaint(); },
        }),
        el("div", { class: "tip", text: "2 ~ 10 档，从 0 开始编号。每档要描述「什么情况」，而不是「多少程度」—— 写成形容词会明显掉准。" }),
      ];
    }

    return [
      el("div", { class: "q-line" },
        el("input", { class: "q-key", value: "true", readOnly: true }),
        el("input", {
          value: q.noulTrue || "", placeholder: "什么情况算「是」（可留空）", spellcheck: "false",
          oninput: (e) => { q.noulTrue = e.target.value; },
        })),
      el("div", { class: "q-line" },
        el("input", { class: "q-key", value: "false", readOnly: true }),
        el("input", {
          value: q.noulFalse || "", placeholder: "什么情况算「否」（可留空）", spellcheck: "false",
          oninput: (e) => { q.noulFalse = e.target.value; },
        })),
      el("div", { class: "tip", text: "两个都留空也能用，但把边界写出来（尤其「什么不算」）通常能明显提升准确率。" }),
    ];
  }

  renderRuleBlock() {
    const s = this.state;
    const body = el("div", { class: `rule-body${s.ruleOn ? "" : " hidden"}` },
      el("div", { class: "seg" },
        ...[["json", "JSON"], ["text", "纯文本"]].map(([v, t]) =>
          el("button", {
            class: s.ruleMode === v ? "active" : "", text: t,
            onclick: () => { s.ruleMode = v; this.render(); },
          }))),
      el("textarea", {
        rows: 4, spellcheck: "false", value: s.ruleText, style: "margin-top:8px",
        oninput: (e) => { s.ruleText = e.target.value; },
      }),
      el("div", { class: "tip" }, md(
        "Jev 没有 system 字段（硬塞会返回 400），也没有跨调用的记忆 —— 所以规则必须每次随 state 一起带上。\n" +
        "写规则时务必把条件写完整：只写「urgent 仅限付费用户」，等于没规定付费用户该怎么办。")));

    return el("div", { class: "block" },
      el("div", { class: "rule-box" },
        el("label", { class: "rule-toggle" },
          el("input", {
            type: "checkbox", checked: s.ruleOn,
            onchange: (e) => { s.ruleOn = e.target.checked; this.render(); },
          }),
          el("span", {}, "常驻规则 ", el("em", { text: "· 每次随 state 一起发送，相当于 system prompt" }))),
        body));
  }

  clearResults() {
    const box = $("#" + this.id("results"), this.root);
    const meta = $("#" + this.id("meta"), this.root);
    if (meta) meta.textContent = "还没跑";
    if (box) {
      box.replaceChildren(el("p", { class: "placeholder" }, md(
        "点「运行」。\n\nJev 不会返回一段话让你去解析，它直接给类型化的值：\n" +
        "**Choice** 选中项 + 全部选项概率 + 置信度\n" +
        "**Score** 分数（可落在两档之间）+ 每档概率 + 等级说明\n" +
        "**Noul** 「是」的概率（0~1）")));
    }
  }

  /* ---------------- 提交 ---------------- */
  /** 内部模型 → 接口要的形状。顺手在这里做校验，错误信息直接给到用户。 */
  buildPayload() {
    const s = this.state;
    if (!s.stateText.trim()) throw new Error("state 不能为空 —— 至少放点要被判断的内容");

    const questions = s.questions.map((q, i) => {
      const label = q.name || `第 ${i + 1} 个问题`;
      if (!q.name || !q.name.trim()) throw new Error(`第 ${i + 1} 个问题缺少名字`);
      const base = { name: q.name.trim(), type: q.type, instructions: (q.instructions || "").trim() };

      if (q.type === "choice") {
        const criteria = {};
        (q.choiceRows || []).forEach(([k, v]) => {
          const key = (k || "").trim();
          if (key) criteria[key] = (v || "").trim() || null;
        });
        if (Object.keys(criteria).length < 2) throw new Error(`Choice「${label}」至少需要 2 个选项`);
        return { ...base, criteria };
      }

      if (q.type === "score") {
        const levels = (q.scoreRows || []).map((v) => (v || "").trim()).filter(Boolean);
        if (levels.length < 2) throw new Error(`Score「${label}」至少需要 2 个等级`);
        return { ...base, criteria: levels };
      }

      const criteria = {};
      if ((q.noulTrue || "").trim()) criteria.true = q.noulTrue.trim();
      if ((q.noulFalse || "").trim()) criteria.false = q.noulFalse.trim();
      return { ...base, criteria };
    });

    return {
      state_mode: s.stateMode,
      state_text: s.stateText,
      questions,
      use_rule_pack: s.ruleOn,
      rule_pack_mode: s.ruleMode,
      rule_pack_text: s.ruleOn ? s.ruleText : "",
    };
  }

  async run() {
    if (this.busy) return;
    let payload;
    try {
      payload = this.buildPayload();
    } catch (err) {
      this.banner("err", err.message);
      return;
    }

    this.busy = true;
    const btn = $("#" + this.id("run"), this.root);
    if (btn) { btn.disabled = true; btn.textContent = "运行中…"; }
    this.hideBanner();
    $("#" + this.id("meta"), this.root).textContent = "调用中…";
    $("#" + this.id("results"), this.root).replaceChildren(
      el("p", { class: "placeholder", text: "Jev 正在并行回答所有问题…" }));

    let data;
    try {
      data = await post("hub/api/evaluate", payload);
    } catch (err) {
      data = { ok: false, error: err.message };
    }

    this.busy = false;
    if (btn) { btn.disabled = false; btn.textContent = "▶ 运行"; }

    if (!data.ok) {
      $("#" + this.id("meta"), this.root).textContent = "调用失败";
      $("#" + this.id("results"), this.root).replaceChildren(
        el("p", { class: "placeholder", text: "✗ " + (data.error || "调用失败") }));
      return;
    }

    this.lastPayloads = { request: payload, response: data };
    this.renderResults(data);
    if (data.rule_conflicts && data.rule_conflicts.length) {
      this.banner("err", `⚠ 常驻规则与 state 存在同名键，已被 state 的值覆盖：${data.rule_conflicts.join("、")}`);
    }
  }

  renderResults(data) {
    const s = this.state;
    $("#" + this.id("meta"), this.root).replaceChildren(
      el("span", { class: "hl", text: data.model || "—" }),
      el("span", { text: ` · ${data.elapsed_ms} ms · 输入 ${data.usage?.input_tokens ?? "?"} tok` }),
      el("span", { text: ` · ${s.questions.length} 个问题 / 1 次请求` }),
      el("span", { text: s.ruleOn ? " · 已带常驻规则" : " · 未带常驻规则" }),
    );

    const answers = data.answers || {};
    $("#" + this.id("results"), this.root).replaceChildren(
      ...s.questions.map((q) => this.answerCard(q, answers[q.name.trim()])));
  }

  answerCard(q, ans) {
    if (!ans) {
      return el("div", { class: "ans-card" },
        el("div", { class: "ans-head" }, el("span", { class: "ans-name", text: q.name })),
        el("div", { class: "legend-note", text: "（没有答案）" }));
    }

    const typeTag = el("span", { class: "ans-type", text: ans.type });

    if (ans.type === "choice") {
      return el("div", { class: "ans-card" },
        el("div", { class: "ans-head" },
          el("span", { class: "ans-name", text: q.name }), typeTag,
          el("span", { class: "ans-value", text: ans.choice }),
          el("span", { class: "ans-conf", text: `confidence ${num(ans.confidence, 2)}` })),
        bars(ans.probabilities, ans.choice));
    }

    if (ans.type === "score") {
      const legend = Object.entries(ans.legend || {});
      const desc = Object.fromEntries(legend.map(([k, v]) => [String(k), v]));
      // 档位说明已经写进每行了，卡片底部那行「等级说明：0=… 1=…」纯属重复，去掉。
      // （原来它同时承担「档位号是什么意思」的职责，现在这个职责归行内标签。）
      //
      // 档位以 legend 为准补齐：模型偶尔只回部分档位的概率，缺的那些补 0，
      // 这样每一档都有一行，不会因为没出现在返回里就整档消失。
      const probs = { ...(ans.probabilities || {}) };
      legend.forEach(([k]) => { if (!(String(k) in probs)) probs[String(k)] = 0; });

      // 高亮「概率最高的那一档」，而不是四舍五入后的分数档 ——
      // 分数落在两档之间时，四舍五入指向的那档未必是概率最高的
      const top = Object.entries(probs).sort((a, b) => b[1] - a[1])[0]?.[0];
      return el("div", { class: "ans-card" },
        el("div", { class: "ans-head" },
          el("span", { class: "ans-name", text: q.name }), typeTag,
          el("span", { class: "ans-value score", text: ans.score.toFixed(2) }),
          el("span", { class: "ans-conf", text: `confidence ${num(ans.confidence, 2)} · ${legend.length} 级` })),
        bars(probs, top, desc));
    }

    return el("div", { class: "ans-card" },
      el("div", { class: "ans-head" },
        el("span", { class: "ans-name", text: q.name }), typeTag,
        el("span", { class: "ans-value noul", text: num(ans.noul) }),
        el("span", { class: "ans-conf", text: "『是』的概率" })),
      el("div", { class: "legend-note", text: "Noul 没有单独的 confidence 字段 —— 这个概率本身就是把握程度。" }));
  }

  /* ---------------- 查看实际请求 / 提示条 ---------------- */
  peek() {
    const existing = $("#" + this.id("peek"), this.root);
    if (existing) { existing.remove(); return; }
    if (!this.lastPayloads) {
      this.banner("err", "还没运行过，没有可看的请求。");
      return;
    }
    const { response } = this.lastPayloads;
    const box = el("pre", { class: "peek", id: this.id("peek") });
    box.textContent = [
      "=== 实际发出去的 state（常驻规则已合并）===",
      JSON.stringify(response.sent_state, null, 2),
      "",
      "=== 问题定义 ===",
      JSON.stringify(this.buildPayload().questions, null, 2),
    ].join("\n");
    $("#" + this.id("meta"), this.root).after(box);
  }

  banner(kind, text) {
    this.hideBanner();
    const box = el("div", { class: `banner ${kind}`, id: this.id("banner"), text });
    const anchor = $(".wb-col", this.root);
    anchor.insertBefore(box, anchor.firstChild);
  }

  hideBanner() {
    const b = $("#" + this.id("banner"), this.root);
    if (b) b.remove();
  }
}

/** 概率分布条：最高的那条高亮。
 *
 * labels 传了就是「带说明的档位」（Score 用）：左侧不再只写 0/1/2，
 * 而是「档位号 + 这档描述」，省得来回对照卡片底部那行等级说明。
 * 不传就是「选项名」（Choice 用），选项名本身可读，照旧。
 *
 * 条形动画由 CSS 的 bar-grow 关键帧负责（transform: scaleX 0→1），
 * 这里只负责把最终宽度写死 —— 动画没跑起来时条形也是正确长度。 */
function bars(probs, topKey, labels) {
  const rows = Object.entries(probs || {}).sort((a, b) => b[1] - a[1]);
  return el("div", { class: `bars${labels ? " labeled" : ""}` },
    ...rows.map(([k, v]) => {
      const desc = labels ? String(labels[String(k)] || "") : "";
      const fill = el("div", { class: "bar-fill" });
      // 先写 0 再写目标值，让 CSS 过渡真的有个起点（同一帧内改两次不会触发过渡，
      // 但配合 animation 的 backwards 填充，条形仍然从 0 长出来）
      fill.style.width = `${Math.max(0, Math.min(1, v)) * 100}%`;
      return el("div", { class: `bar-row${k === topKey ? " top" : ""}` },
        el("span", { class: "bar-key", title: desc ? `${k} · ${desc}` : k },
          labels ? el("b", { class: "bar-lv", text: k }) : null,
          el("span", { class: "bar-desc", text: desc || k })),
        el("div", { class: "bar-track" }, fill),
        el("span", { class: "bar-val", text: num(v, 2) })
      );
    }));
}

/* ==========================================================================
   链接栏底部的环境信息（原来单独占一行，现在塞进链接栏，省下一行高度）
   ========================================================================== */
async function renderMeta() {
  const box = $("#railMeta");
  try {
    const res = await fetch("hub/api/meta");
    const m = await res.json();
    box.replaceChildren(
      el("div", {}, "模型 ", el("b", { text: m.model })),
      el("div", {}, el("b", { text: String(m.base).replace(/^https?:\/\//, "") })),
      el("div", { class: m.hasKey ? "" : "bad" },
        m.hasKey ? ["key ", el("b", { text: m.keyHint })] : "key 未配置"),
    );
  } catch {
    box.replaceChildren(el("div", { class: "bad", text: "连不上本地服务" }));
  }
}

/* ==========================================================================
   --chrome-h 自测
   ========================================================================== */
/* --chrome-h 是「画布之外占掉多少高度」的总预留，容器高度和画布边长都由它反推：
       container = 100vh - header块 - footer块
       board     = 100vh - chrome-h

   这个值随字号变 —— 页头会跟着字长高。写死在样式表里的话，每次调字号都得手动
   回头量一遍，忘了就顶出一根页面滚动条（已经踩过两次）。所以改成直接量：
   页头页脚的真实高度 + 容器那圈固定开销，量到多少写多少，字号怎么变都不会错。

   顺带把页面滚动条也彻底消掉：与其留固定余量去赌，不如按实测值算，
   容器高度会刚好等于剩余空间。 */
function syncChromeHeight() {
  const header = $("header");
  const footer = $("footer");
  if (!header || !footer) return;

  const rootStyle = getComputedStyle(document.documentElement);
  const num = (name, fallback) => {
    const v = parseFloat(rootStyle.getPropertyValue(name));
    return Number.isFinite(v) ? v : fallback;
  };
  // 元素自身高度 + 它占掉的那侧外边距
  const block = (node, marginSide) =>
    node.getBoundingClientRect().height +
    (parseFloat(getComputedStyle(node)[marginSide]) || 0);

  // 容器内部那圈固定开销：画布与按钮的间距 + 按钮行 + 上下内边距 + 上下描边 + 亚像素余量。
  // --top-gap 也算进来 —— 它是 body 的顶端留白，同样是从一屏高度里扣掉的。
  const rest =
    num("--top-gap", 0) +
    num("--pac-col-gap", 12) +
    num("--pac-actions-h", 40) +
    2 * num("--pad", 14) +
    2 +
    6;

  const total = block(header, "marginBottom") + block(footer, "marginTop") + rest;
  document.documentElement.style.setProperty("--chrome-h", `${Math.ceil(total)}px`);
}

/* ==========================================================================
   启动
   ========================================================================== */
function boot() {
  renderRail();
  renderMeta();

  // 三个工作台各实例化一份
  $$(".wb").forEach((root) => new Workbench(root, root.dataset.preset));

  $$("[data-goto]").forEach((card) =>
    card.addEventListener("click", () => activate(card.dataset.goto)));

  // 先量一次，再在窗口变化时重量（宽度变了页头文字可能换行，高度就变了）
  syncChromeHeight();
  window.addEventListener("resize", syncChromeHeight);
  // 字体晚于首屏到位时高度还会跳一次，补量一次
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(syncChromeHeight);
  }

  // 支持 hash 直达，方便录屏时切镜头
  const want = (location.hash || "").replace("#", "");
  activate(RAIL.some((t) => t.id === want) ? want : "home");
}

document.addEventListener("DOMContentLoaded", boot);
