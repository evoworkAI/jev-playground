# Release 发布说明

## v1.0.0 — 首次公开发布

### 下载（粉丝用这个）

| 文件 | 适合谁 | 需要 Python |
|---|---|---|
| **Jev游乐场-Mac.zip** | Mac 用户 | ❌ 不需要 |
| **Jev游乐场-Windows.zip** | Windows 用户 | ❌ 不需要（需维护者在 Windows 上打包） |
| **Source code (zip)** | 开发者 / 想改代码的人 | ✅ 需要 3.10+ |

### v1.0.0 包含

- 🎮 **吃豆人 AI 决策**：手工 / Jev / LLM 三种模式，赛博霓虹迷宫
- 🛡️ **内容审核**、📄 **简历筛选**、🧪 **空白模板** 三个 Jev 工作台
- 🌐 **简繁切换**（默认繁体）
- 📦 **独立程序版**：Mac `.app` / Windows `.exe`，解压双击即用
- 📝 源码版启动脚本：`start-mac.command` / `start-windows.bat`

### 快速开始

1. 下载 **Jev游乐场-Mac.zip**（或 Windows 版）
2. 解压
3. 双击 `Jev游乐场.app`（Mac）或 `Jev游乐场.exe`（Windows）
4. 浏览器自动打开 → 吃豆人选手工模式即可开玩

### 维护者：如何打 Release 包

```bash
# 1. 打包（Mac 上出 .app，Windows 上出 .exe）
python3 packaging/build.py

# 2. 打 zip（Mac 示例）
cd dist
zip -r ../Jev游乐场-Mac.zip Jev游乐场.app ../怎么启动.txt ../.env.example

# 3. 上传到 GitHub Release
gh release create v1.0.0 \
  Jev游乐场-Mac.zip \
  --title "v1.0.0 · 小白也能马上掌握的 Jev 模型游乐场" \
  --notes-file ../RELEASE.md
```

Windows 版需在 Windows 机器上执行 `packaging/build.py` 后同样打 zip 上传。

---

## 视频简介模板（可直接复制）

```
🎮 Jev 模型游乐场 · 开源下载
GitHub：https://github.com/evoworkAI/jev-playground

Mac / Windows 解压双击即用，不用装 Python！
吃豆人 AI 决策 + 内容审核 + 简历筛选 Demo

频道：@j-AI99 · 静电的AI研习社
```
