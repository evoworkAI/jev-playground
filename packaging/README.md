# 打包独立程序（粉丝不用装 Python）

## 你（维护者）怎么做

在 **Mac** 或 **Windows** 上各打包一次（不能交叉编译）：

```bash
python3 packaging/build.py
```

产出在 `dist/`：

| 系统 | 文件 |
|---|---|
| Mac | `dist/Jev游乐场.app` |
| Windows | `dist/Jev游乐场.exe` |

## 发给粉丝

把下面文件打成一个 zip，上传到 **GitHub Releases**：

```
Jev游乐场-Mac.zip
  ├── Jev游乐场.app
  └── 怎么启动.txt

Jev游乐场-Windows.zip
  ├── Jev游乐场.exe
  └── 怎么启动.txt
```

`.env` 不用打包——程序首次运行会在旁边自动生成。

## 体积参考

约 15–25 MB（含 Python 运行时 + 网页资源 + OpenCC 词表）。

## 注意

- Windows 的 `.exe` 必须在 Windows 机器上打包
- Mac 的 `.app` 必须在 Mac 上打包
- 若杀毒软件误报，在 Release 说明里写「开源可自查，PyInstaller 打包常见误报」
