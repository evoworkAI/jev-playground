/* ==========================================================================
   简繁文字切换 —— 默认繁體，点一下切简体
   --------------------------------------------------------------------------
   源文件里的文案是简体，所以：
       繁體（默认）＝ 用 OpenCC 把每一段文字转一遍
       简体         ＝ 原样显示

   为什么必须用 OpenCC，而不是自己写一张字符映射表：
   简→繁是「一对多」的方向，同一个简化字在不同词里对应不同繁体字 ——
   里→裡/里、发→發/髮、只→隻/只、干→乾/幹、复→復/複、台→臺/台。
   实测只用单字符表（32KB）会把「里程」转成「裏程」、「头发」转成「頭發」、
   「干燥」转成「幹燥」、「复杂」转成「復雜」—— 全是会被中文观众一眼看出的错。
   所以这里带上了 OpenCC 的短语词表（opencc-cn2t.js，1MB）。
   本地服务加载，不走网络，换来的正确性比省下的大小值。

   为什么能做到「页面上任何文字都跟着切」：
   不是把转换塞进每个渲染函数，而是走查 DOM —— 给每个文本节点/属性记住
   原文（简体），只改它的显示值。于是：
     · 静态 HTML          —— 初次加载走查一遍
     · JS 动态生成的节点  —— MutationObserver 接住新增子树
     · 程序改写已有节点    —— characterData / attributes 变更也接得住
   唯一接不住的是 input/textarea 的 .value（它不算 DOM 变更），
   所以额外提供了 ZH.refresh()，由应用在写完表单值之后主动喊一声。

   跨上下文同步走 localStorage：浏览器会把 storage 事件派发给同源的其他
   浏览上下文 —— 包括同页的 iframe、以及另外开的标签页。所以门户页切一下，
   嵌在里面的吃豆人页和「完整调试台」标签页会自己跟上，不需要 postMessage。
   ========================================================================== */
"use strict";

(function (global) {
  const TC = "tc";
  const SC = "sc";
  const DEFAULT_MODE = TC;         // 默认繁體
  const STORE_KEY = "jev:script";

  /** 会被一起转换的属性。只挑了「给人看的文案」类属性；
      顺带避开 data-* 和 id/class，那些是给代码用的，动了会出事。 */
  const ATTRS = ["title", "placeholder", "aria-label", "alt"];

  /** 这些标签里的文字不转：脚本样式自不必说，canvas 的 fallback 文字
      也不会被渲染出来，转它纯属浪费。 */
  const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "CANVAS", "IFRAME", "OBJECT"]);

  /** 汉字范围（含扩展 A 和兼容区）。没汉字就直接返回，省掉词典查找 ——
      页面里一大半文本节点是数字和英文，这一步能省掉大部分开销。 */
  const HAN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;

  const SRC_REC = new WeakMap();   // 文本节点 -> { src, out }
  const ATTR_REC = new WeakMap();  // 元素 -> Map(属性名 -> { src, out })

  let mode = DEFAULT_MODE;
  let conv = null;
  let warned = false;
  const subs = [];                 // 模式变化订阅者

  /* ---------------------------------------------------------------------
     转换本身
     --------------------------------------------------------------------- */
  function doConvert(s) {
    if (mode === SC || !s || !HAN.test(s)) return s;
    if (!conv) {
      if (!global.OpenCC) {
        // 词表没加载上就别把整页搞崩：原样显示，只提示一次
        if (!warned) {
          warned = true;
          console.warn("[zh] 未找到 OpenCC：zh/opencc-cn2t.js 没加载成功，简繁切换停用");
        }
        return s;
      }
      // 建 Trie 大约 60ms，只做一次
      conv = global.OpenCC.Converter({ from: "cn", to: "tw" });
    }
    return conv(s);
  }

  /* ---------------------------------------------------------------------
     走查器
     --------------------------------------------------------------------- */

  /** 统一的「保住原文、只改显示」。
   *
   *  read()/write() 是这个节点读/写显示值的方式（文本节点和属性各一套）。
   *  rec 是它的记录：src = 原文，out = 我们上次写进去的显示值。
   *
   *  force=false（默认，处理 DOM 变更时用）：
   *      如果当前值 === 我们上次写的，说明是自己写触发的回调，直接跳过；
   *      否则说明是应用写进来的新内容，把它当成新原文。
   *  force=true（整页重扫 / 切换模式）：
   *      从记录里的原文重算 —— 这是「切回简体还能变回去」的关键，
   *      否则繁体转不回简体，因为原文已经被覆盖了。
   *
   *  新记录的 out 特意给 null：保证第一次一定走一遍转换。
   */
  function sync(rec, read, write, force) {
    const cur = read();
    if (!force && rec.out === cur) return;      // 自己写的，不动
    if (!force || rec.out !== cur) rec.src = cur;
    rec.out = doConvert(rec.src);
    if (cur !== rec.out) write(rec.out);
  }

  function nodeRec(node, initial) {
    let rec = SRC_REC.get(node);
    if (!rec) SRC_REC.set(node, (rec = { src: initial, out: null }));
    return rec;
  }

  /** 这个节点身上（或祖先里）有没有「不该动」的标签。
   *
   *  树走查会提前剪枝（遇到 script/style 就不往里走），但 MutationObserver 的
   *  characterData / attributes 分支是直接对目标节点动手的，childList 分支拿到的
   *  也可能是「已经挂在 script 里的文本节点」—— 都绕过了剪枝。
   *
   *  这不是理论风险：HTML 解析器构造内联 <script> 时是「先插元素、再挂文本节点」，
   *  于是解析器给出的 addedNodes 就是这个文本节点本身，它的 parentNode 已经是
   *  <script> 了。少这一道判断，整段内联脚本（包括里面的字符串常量和注释）会被
   *  当页面文案翻掉 —— 踩过一次。 */
  function insideSkipped(node) {
    for (let p = node.parentNode; p; p = p.parentNode) {
      if (p.nodeType === Node.ELEMENT_NODE && SKIP_TAGS.has(p.tagName.toUpperCase())) return true;
    }
    return false;
  }

  function applyText(node, force) {
    if (insideSkipped(node)) return;
    const rec = nodeRec(node, node.data);
    sync(rec, () => node.data, (v) => { node.data = v; }, force);
  }

  function applyAttr(node, name, force) {
    if (!node.hasAttribute(name) || insideSkipped(node)) return;
    let bag = ATTR_REC.get(node);
    if (!bag) ATTR_REC.set(node, (bag = new Map()));
    let rec = bag.get(name);
    if (!rec) bag.set(name, (rec = { src: node.getAttribute(name), out: null }));
    sync(
      rec,
      () => node.getAttribute(name),
      (v) => { node.setAttribute(name, v); },
      force
    );
  }

  /** input / textarea 的 .value 不是 DOM 变更，MutationObserver 看不见，
      只能靠这里主动扫（切模式时整页扫，或者应用写完值后调 ZH.refresh）。
      正在编辑的那个框跳过 —— 动它会把光标位置和撤销记录全打乱，
      代价比「切完这个框还是简体」大得多。 */
  function applyField(node, force) {
    if (node === document.activeElement) return;
    const rec = nodeRec(node, node.value);   // 和文本节点共用一套记录（一个节点只会是其中一种）
    sync(rec, () => node.value, (v) => {
      node.value = v;
      // 程序改 .value 不会触发 input。补一个合成事件，让应用自己的 oninput
      // 处理器把内部模型同步过去 —— 否则页面显示着繁體，提交给模型的
      // 却还是简体原文（工作台的 payload 是从内部模型拼的，不是读 DOM）。
      node.dispatchEvent(new Event("input", { bubbles: true }));
    }, force);
  }

  function walk(root, force) {
    const type = root.nodeType;
    if (type === Node.TEXT_NODE) {
      applyText(root, force);
      return;
    }
    if (type !== Node.ELEMENT_NODE && type !== Node.DOCUMENT_FRAGMENT_NODE && type !== Node.DOCUMENT_NODE) return;

    if (type === Node.ELEMENT_NODE) {
      const tag = root.tagName.toUpperCase();
      if (SKIP_TAGS.has(tag)) return;
      for (const name of ATTRS) applyAttr(root, name, force);
      if (tag === "INPUT" || tag === "TEXTAREA") applyField(root, force);
    }
    // 用 snapshot：转换过程中我们自己的写入不会再触发回调（回调是微任务，
    // 这轮同步走查早结束了），但理论上仍可能被应用改动 childNodes，
    // 边遍历边动 childNodes 会漏节点，所以先固化一份。
    for (const child of Array.from(root.childNodes)) walk(child, force);
  }

  /* ---------------------------------------------------------------------
     模式
     --------------------------------------------------------------------- */
  function normalize(m) {
    return m === SC ? SC : TC;
  }

  function persist(m) {
    try {
      localStorage.setItem(STORE_KEY, m);
    } catch {
      // 隐私模式下 localStorage 可能直接抛异常。存不上就算了，
      // 大不了刷新后回到默认繁體，不该因此中断切换。
    }
  }

  function setMode(next, opts) {
    const m = normalize(next);
    const changed = m !== mode;
    mode = m;

    document.documentElement.lang = m === TC ? "zh-Hant" : "zh-Hans";
    document.documentElement.dataset.zh = m;   // 按钮的选中态由 CSS 吃这个属性

    if (document.documentElement) walk(document.documentElement, true);
    if (changed) {
      persist(m);
      for (const fn of subs) {
        try { fn(m); } catch (e) { console.error("[zh] 订阅者抛错：", e); }
      }
    }
    return m;
  }

  function initMode() {
    let stored = null;
    try { stored = localStorage.getItem(STORE_KEY); } catch { /* 同上 */ }
    mode = normalize(stored || DEFAULT_MODE);
    document.documentElement.lang = mode === TC ? "zh-Hant" : "zh-Hans";
    document.documentElement.dataset.zh = mode;
  }

  /* ---------------------------------------------------------------------
     切换按钮
     --------------------------------------------------------------------- */
  function button(sizeClass) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "zh-switch" + (sizeClass ? " " + sizeClass : "");
    // 原标题写的是「简繁切换 / 簡繁切換」，可这半句简繁同形：繁体模式下
    // 两边一起被翻成「簡繁切換 / 簡繁切換」，悬停时看着像出了 bug。
    // 换成一句简繁不同形的话，两个模式下都读得通。
    btn.title = "切换繁体 / 简体";
    btn.setAttribute("aria-label", "簡繁切換");

    for (const [m, label] of [[TC, "繁體"], [SC, "简体"]]) {
      const seg = document.createElement("span");
      seg.dataset.zhSet = m;
      seg.textContent = label;
      seg.addEventListener("click", (e) => {
        e.stopPropagation();
        setMode(m);
      });
      btn.append(seg);
    }
    return btn;
  }

  /** 挂载点：页面上写 <span data-zh-slot></span>（要小号就写 ="sm"），
      按钮自动填进去。这样三个页面都不需要为它写一行 JS 接线。
      childElementCount 判断是为了幂等 —— 填过就不再填，否则
      「插入按钮 → 触发 observer → 又插入按钮」会转成死循环。 */
  function fillSlots(root) {
    const slots = root.matches?.("[data-zh-slot]")
      ? [root]
      : Array.from(root.querySelectorAll?.("[data-zh-slot]") || []);
    for (const slot of slots) {
      if (slot.childElementCount) continue;
      slot.replaceChildren(button(slot.getAttribute("data-zh-slot") || ""));
    }
  }

  /* ---------------------------------------------------------------------
     启动
     --------------------------------------------------------------------- */
  function start() {
    initMode();
    if (document.documentElement) {
      // 先把按钮插进去，再走查 —— 顺序反了按钮上的字就不会被转换
      fillSlots(document.documentElement);
      // 从 documentElement 走起，而不是 body：<title> 在 head 里，
      // 不带上它的话浏览器标签页上那行字永远停在简体。
      walk(document.documentElement, false);
    }

    new MutationObserver((records) => {
      for (const r of records) {
        if (r.type === "characterData") {
          applyText(r.target, false);
        } else if (r.type === "attributes") {
          applyAttr(r.target, r.attributeName, false);
        } else {
          for (const n of r.addedNodes) {
            fillSlots(n);
            walk(n, false);
          }
        }
      }
    }).observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRS,
    });

    // 正在编辑的那个输入框在上面是被跳过的（动它会毁掉光标和撤销记录）。
    // 但它不能就这么一直停在旧字形，所以在失焦时补转一次。
    document.addEventListener("focusout", (e) => {
      const t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) applyField(t, true);
    }, true);

    // 别的标签页 / 本页内的 iframe 改了模式 —— 浏览器会把 storage 事件
    // 派给同源的其他浏览上下文（不含改动的那个），正好用来保持全局一致。
    global.addEventListener("storage", (e) => {
      if (e.key === STORE_KEY && e.newValue && normalize(e.newValue) !== mode) {
        setMode(e.newValue, { silent: true });
      }
    });
  }

  global.ZH = {
    MODES: { TC, SC },
    get mode() { return mode; },
    /** convert：给画布这种「文字不进 DOM」的地方用（吃豆人的迷宫霓虹字、状态角标） */
    convert: doConvert,
    set: setMode,
    toggle: () => setMode(mode === TC ? SC : TC),
    button,
    /** refresh：重新扫一遍（默认整页）。给 input/textarea 的 .value 用 —— 
        MutationObserver 看不到 .value 的赋值。传 root 可以只扫一小块。 */
    refresh: (root, force = true) => walk(root || document.documentElement, force),
    /** onChange：模式变化回调。吃豆人靠它重建缓存的霓虹图层。不会立即触发，
        调用方自己读 ZH.mode 拿当前值。 */
    onChange: (fn) => { subs.push(fn); },
  };

  // 脚本放在 </body> 前面时，这会儿 body 已经解析完了 —— 直接同步转换，
  // 赶在浏览器第一次绘制之前把文字换掉，避免「先闪一下简体」。
  // 万一被放到 <head> 里（body 还不存在），才退回 DOMContentLoaded。
  if (document.body) {
    start();
  } else {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  }
})(window);
