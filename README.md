# 中低频聚焦频谱播放器 — 使用指南

基于 Python 的桌面音乐播放器，支持实时频谱/波形可视化、麦克风模式、歌单管理与音乐库归档。

---

## 目录结构

```
midlow_spectrum_player/
├── main_midlow.py        # 主程序入口
├── playlist_store.py     # 歌单数据与音乐库
├── playlist_ui.py        # 歌单管理界面
├── window_chrome.py      # 窗口主题与 DPI 适配
├── requirements.txt      # Python 依赖列表
├── run.bat               # 一键运行（开发环境）
├── setup.bat             # 选择 Python 环境 + 安装依赖（首次必做）
├── setup.ps1             # setup.bat 调用的脚本
├── select_python.bat     # 仅切换 Python（不重装依赖，可选）
├── get_python.bat        # 内部：读取 .python_path
├── build_exe.bat         # 一键打包 exe
├── build_exe.py          # 打包脚本（Python 版）
├── playlists.json        # 歌单数据（运行后自动生成）
├── music_library/        # 歌曲库（导入后自动创建）
└── dist/                 # 打包输出目录（打包后生成）
    └── MidLowSpectrumPlayer/
        ├── MidLowSpectrumPlayer.exe
        └── _internal/    # 运行时依赖（不可删除）
```

---

## 一、从 GitHub 下载后首次使用

从 GitHub 下载代码后，请按顺序操作：

```
1. 安装 Python 3.10+（https://www.python.org/downloads/，勾选 Add Python to PATH）
2. 双击 setup.bat          ← 安装依赖（首次必做）
3. 双击 run.bat            ← 运行播放器
   或
   双击 build_exe.bat      ← 打包成 exe
```

### 默认用哪个 Python？

| 情况 | 使用的环境 |
|------|------------|
| 未手动选择 | **`py -3`**（Windows 默认 3.x），否则 PATH 里的 **`python`** |
| 运行过 **`setup.bat`** 并保存 | **`.python_path`** 里的路径（仅本机，不上传 GitHub） |

**`setup.bat`** 会先让你选/确认 Python，再自动 `pip install`。  
电脑上有多个 Python（如 Anaconda）时，在菜单里选编号即可。

只想换环境、不重装依赖：可运行 **`select_python.bat`**（内部调用同一套选择界面）。

选 **0** 恢复自动检测。

### 方式 1：双击 `run.bat`（推荐）

1. 进入 `midlow_spectrum_player` 文件夹
2. 先运行 **`setup.bat`**（首次必做，安装依赖）
3. 双击 **`run.bat`**
4. 播放器窗口会自动打开

> 若 Python 未加入 PATH，请先安装 Python 并勾选 “Add Python to PATH”，或运行 `setup.bat` 检查环境。

### 方式 2：命令行运行

```bat
cd midlow_spectrum_player
pip install -r requirements.txt
python main_midlow.py
```

### 首次运行前：安装依赖

若尚未安装依赖，在命令行执行：

```bat
pip install -r requirements.txt
```

依赖包括：`sounddevice`、`soundfile`、`numpy`、`scipy`、`mutagen`、`windnd`。

---

## 二、播放器使用说明

### 主界面操作

| 操作 | 效果 |
|------|------|
| **双击** 画布空白处 | 弹出文件选择框，选歌后开始播放 |
| **单击** 画布 | 播放 / 暂停 |
| **右键** 画布 | 打开歌单管理窗口 |
| **拖入** 音乐文件到画布 | 自动导入到专辑/歌手歌单，并复制到 `music_library/` |

支持的音频格式：`.mp3`、`.flac`、`.wav`、`.ogg`、`.m4a`、`.aac`、`.wma`、`.opus`

### 麦克风模式

- 程序启动后，若无音乐播放，会自动开启麦克风，显示实时频谱和波形
- 开始播放音乐时，麦克风自动关闭
- 音乐播放结束或暂停后，波形自然归零，再切换回麦克风

### 歌单管理（右键打开）

窗口分为四栏：

| 栏位 | 说明 |
|------|------|
| **专辑** | 按专辑自动分类，歌曲按碟号/曲目号排序 |
| **歌手** | 按歌手自动分类（合作歌曲会出现在每位歌手歌单中） |
| **自建歌单** | 用户手动创建的歌单 |
| **当前列表** | 显示当前选中歌单的曲目，可增删排序 |

**常用操作：**

| 操作 | 方法 |
|------|------|
| 新建歌单 | 双击「自建歌单」栏**空白处** |
| 播放歌单 | 双击歌单名称 |
| 播放单首 | 双击「当前列表」中的歌曲 |
| 删除歌单 | 将歌单行拖到窗口底部**回收站** |
| 删除歌曲 | 将歌曲拖到回收站（仅自建歌单/播放列表） |
| 调整顺序 | 在「当前列表」中上下拖动歌曲 |
| 跨歌单添加 | 将歌曲拖到其他歌单上 |
| 预览歌单 | 拖动歌曲悬停在某歌单上超过 0.5 秒，第四栏自动预览 |

**删除规则：**

- **专辑**：可整个删除（拖到回收站）；专辑内单首歌曲不可单独删除
- **歌手**：不可手动删除，随专辑变化自动更新
- **自建歌单 / 播放列表**：可删除歌单，也可删除单首歌曲

### 音乐库（`music_library/`）

- 每次导入歌曲时，程序会自动将文件**复制**到 `music_library/` 目录
- 歌单里保存的是库内路径，原文件移动或删除不影响播放
- 首次启用此功能后，重启程序会自动迁移已有歌曲到库中

---

## 三、打包成 exe（给其他电脑用）

### 使用 `build_exe.bat`（推荐）

1. 进入 `midlow_spectrum_player` 文件夹
2. 首次请先运行 **`setup.bat`**
3. 双击 **`build_exe.bat`**
4. 等待 1–3 分钟，出现「打包完成！」即可

脚本会自动：查找本机 Python → 安装依赖（如缺失）→ 安装 PyInstaller → 打包

> 若双击后窗口一闪而过，说明未安装 Python。请先安装 Python 并运行 `setup.bat`。

### 使用 Python 脚本打包

```bat
cd midlow_spectrum_player
python build_exe.py
```

### 打包输出

```
dist\MidLowSpectrumPlayer\
├── MidLowSpectrumPlayer.exe   ← 双击运行
├── _internal\                 ← 依赖库（必须保留，不可删）
├── music_library\             ← 歌曲库（运行后自动创建）
├── playlists.json             ← 歌单数据
└── 使用说明.txt
```

---

## 四、在其他电脑上运行

**不能只复制 `.exe` 文件**，必须复制整个文件夹：

1. 将 `dist\MidLowSpectrumPlayer` **整个文件夹**复制到 U 盘或目标电脑
2. 在目标电脑上双击 `MidLowSpectrumPlayer.exe` 即可运行
3. **无需安装 Python** 或任何其他软件

**建议一并带走的文件：**

| 文件/文件夹 | 说明 |
|-------------|------|
| `MidLowSpectrumPlayer.exe` | 主程序 |
| `_internal\` | 运行时依赖（必须） |
| `music_library\` | 歌曲库，带上则保留已导入的音乐 |
| `playlists.json` | 歌单数据，带上则保留歌单 |

---

## 五、数据文件说明

| 文件 | 作用 |
|------|------|
| `playlists.json` | 所有歌单、曲目、播放状态 |
| `playlists.bak` | 歌单备份（主文件损坏时自动恢复） |
| `music_library/` | 导入歌曲的本地副本 |
| `player_errors.log` | 错误日志（exe 模式下无控制台时查看） |

**注意：** 重装或迁移时，请保留 `playlists.json` 和 `music_library/`，否则歌单和歌曲会丢失。

---

## 六、常见问题

**Q：拖入歌曲没反应？**  
A：确认已安装 `windnd`（`pip install windnd`）。用 `run.bat` 运行时需使用已安装依赖的 Python 环境。

**Q：歌单重启后变空？**  
A：检查 exe 同目录下是否有 `playlists.json`。若损坏，可尝试将 `playlists.bak` 重命名为 `playlists.json` 恢复。

**Q：某首歌播放不了，显示 ⚠？**  
A：原文件路径已失效。播放时会尝试自动搜索；若找不到，会弹出对话框让你手动定位文件。

**Q：打包后 exe 无法运行？**  
A：确保复制的是整个 `MidLowSpectrumPlayer` 文件夹，包含 `_internal` 子目录。单独复制 exe 会报错。

**Q：如何修改 Python 路径？**  
A：编辑 `run.bat` 或 `build_exe.bat` 中的 `CONDA_PYTHON` / `PYTHON` 变量为你的 Python 可执行文件路径。

---

## 七、系统要求

- **操作系统**：Windows 10 / 11
- **开发运行**：Python 3.10+，见 `requirements.txt`
- **exe 运行**：无需 Python，Windows 10/11 即可

---

## 八、上传到 GitHub（首次使用）

本地代码已准备好 Git 仓库。按以下步骤上传到你的 GitHub 账号：

### 第 1 步：在 GitHub 网站创建空仓库

1. 登录 [https://github.com](https://github.com)
2. 点击右上角 **+** → **New repository**
3. 填写：
   - **Repository name**：例如 `midlow-spectrum-player`
   - **Public** 或 **Private** 任选
   - **不要**勾选 "Add a README file"（本地已有）
4. 点击 **Create repository**

### 第 2 步：关联远程仓库并推送

创建完成后，GitHub 会显示仓库地址。在命令行执行（把 `你的用户名` 和 `仓库名` 换成你的）：

```bat
cd "D:\python project\project\midlow_spectrum_player"

git remote add origin https://github.com/iammf-104/Spectrum-Player.git

git push -u origin main
```

### 第 3 步：登录验证

首次推送时，Windows 可能弹出浏览器让你登录 GitHub，或要求输入：

- **用户名**：你的 GitHub 用户名
- **密码**：不是登录密码，而是 **Personal Access Token（PAT）**

生成 Token 的方法（找不到 Developer settings 时用直接链接）：

**直接打开：** [https://github.com/settings/tokens/new](https://github.com/settings/tokens/new)

或手动找：

1. GitHub 右上角头像 → **Settings**
2. 左侧菜单**滑到最底部** → **Developer settings**（在 Emails 等选项下面）
3. **Personal access tokens** → **Tokens (classic)** → **Generate new token**
4. 勾选 **repo** 权限，生成后复制 token
5. 推送时：**用户名**填 `iammf-104`，**密码**粘贴 token（不是登录密码）

**更简单的方式：** 双击项目里的 **`push_to_github.bat`**，按提示操作即可。

### 已上传的内容

| 会上传 | 不会上传（已在 .gitignore 中排除） |
|--------|-----------------------------------|
| 源代码、README、run.bat、build_exe.bat | `music_library/`（你的私人音乐） |
| requirements.txt | `playlists.json`（你的歌单数据） |
| | `dist/`、`build/`（打包产物） |

### 以后更新代码

修改代码后，执行：

```bat
cd "D:\python project\project\midlow_spectrum_player"
git add .
git commit -m "描述你改了什么"
git push
```
