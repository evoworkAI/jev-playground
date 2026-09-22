# Release 发布说明

## 下载即用（不用装 Python）

按系统点对应链接，下载后解压，双击里面的程序：

| 你的电脑 | 直接下载 | 解压后双击 |
|---|---|---|
| Mac | [Jev-Playground-Mac.zip](https://github.com/evoworkAI/jev-playground/releases/latest/download/Jev-Playground-Mac.zip) | `Jev游乐场.app` |
| Windows | [Jev-Playground-Windows.zip](https://github.com/evoworkAI/jev-playground/releases/latest/download/Jev-Playground-Windows.zip) | `Jev游乐场.exe` |

浏览器会自动打开 http://127.0.0.1:8800/ 。吃豆人选手工模式即可开玩。

Mac 首次若提示「无法打开」：右键 `Jev游乐场.app` → **打开** → 再点「打开」。

### 其他下载

| 文件 | 适合谁 | 需要 Python |
|---|---|---|
| 上面两个 zip | 想直接玩的人 | 不需要 |
| Source code (zip) | 开发者 / 想改代码的人 | 需要 3.10+ |

### v1.0.0 包含

- 🎮 **吃豆人 AI 决策**：手工 / Jev / LLM 三种模式，赛博霓虹迷宫
- 🛡️ **内容审核**、📄 **简历筛选**、🧪 **空白模板** 三个 Jev 工作台
- 🌐 **简繁切换**（默认繁体）
- 📦 **独立程序版**：Mac `.app` / Windows `.exe`，解压双击即用
- 📝 源码版启动脚本：`start-mac.command` / `start-windows.bat`

### 维护者：如何打 Release 包

Mac 的 `.app` 只能在 Mac 上打包，Windows 的 `.exe` 只能在 Windows 上打包。两边都可以交给 Actions 里的 **Build release binaries**。

```bash
python3 packaging/build.py
python3 packaging/zip_release.py
gh release upload v1.0.0 Jev-Playground-Mac.zip Jev-Playground-Windows.zip --clobber --notes-file RELEASE.md
```

---

## 视频简介模板（可直接复制）

```
🎮 Jev 模型游乐场 · 开源下载
GitHub：https://github.com/evoworkAI/jev-playground

Mac 直接下载：
https://github.com/evoworkAI/jev-playground/releases/latest/download/Jev-Playground-Mac.zip

Windows 直接下载：
https://github.com/evoworkAI/jev-playground/releases/latest/download/Jev-Playground-Windows.zip

解压双击即用，不用装 Python。
吃豆人 AI 决策 + 内容审核 + 简历筛选 Demo

频道：@j-AI99 · 静电的AI研习社
```
