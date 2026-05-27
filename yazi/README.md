# Yazi 配置文件

Yazi 是一个用 Rust 编写的终端文件管理器，速度极快且功能丰富。

## 参考网站

- [Yazi 官方网站](https://yazi-rs.github.io/)
- [Yazi GitHub 仓库](https://github.com/sxyazi/yazi)
- [Yazi 官方文档](https://yazi-rs.github.io/docs/overview)
- [Yazi 配置文档](https://yazi-rs.github.io/docs/configuration/overview)
- [Yazi 插件列表](https://yazi-rs.github.io/docs/plugins/overview)
- [Yazi 主题/Flavors](https://yazi-rs.github.io/docs/flavors/overview)

## 目录结构

```
~/.config/yazi/
├── yazi.toml      # 主配置文件
├── keymap.toml    # 快捷键配置
├── theme.toml     # 主题配置
├── init.lua       # Lua 初始化脚本
└── package.toml   # 插件依赖管理
```

---

## 安装教程

### macOS

```bash
# 安装 Yazi 及所有可选依赖（推荐）
brew install yazi ffmpeg sevenzip jq poppler fd ripgrep fzf zoxide resvg imagemagick font-symbols-only-nerd-font

# 安装 starship（用于 starship 插件）
brew install starship

# 安装 eza（用于 eza-preview 插件）
brew install eza
```

配置 Starship，在 `~/.zshrc` 或 `~/.bashrc` 中添加：

```bash
eval "$(starship init zsh)"  # for zsh
# 或
eval "$(starship init bash)" # for bash
```

---

### Arch Linux

```bash
# 安装 Yazi 及所有可选依赖（推荐）
sudo pacman -S yazi ffmpeg 7zip jq poppler fd ripgrep fzf zoxide resvg imagemagick

# 安装 starship
sudo pacman -S starship

# 安装 eza
sudo pacman -S eza

# 安装 Nerd Font 字体（任选一个）
sudo pacman -S ttf-jetbrains-mono-nerd
# 或者
yay -S ttf-hack-nerd
```

配置 Starship，在 `~/.zshrc` 或 `~/.bashrc` 中添加：

```bash
eval "$(starship init zsh)"  # for zsh
# 或
eval "$(starship init bash)" # for bash
```

> 如需最新 Git 版本，可从 AUR 安装：`yay -S yazi-git`

---

### EndeavourOS

EndeavourOS 基于 Arch Linux，安装方式与 Arch 相同：

```bash
# 安装 Yazi 及所有可选依赖（推荐）
sudo pacman -S yazi ffmpeg 7zip jq poppler fd ripgrep fzf zoxide resvg imagemagick

# 安装 starship
sudo pacman -S starship

# 安装 eza
sudo pacman -S eza

# 安装 Nerd Font 字体（任选一个）
sudo pacman -S ttf-jetbrains-mono-nerd
# 或者
yay -S ttf-hack-nerd
```

配置 Starship，在 `~/.zshrc` 或 `~/.bashrc` 中添加：

```bash
eval "$(starship init zsh)"  # for zsh
# 或
eval "$(starship init bash)" # for bash
```

---

### Ubuntu / Debian

> 注意：Ubuntu/Debian 官方仓库中没有 Yazi，需要手动安装。

#### 1. 安装 Yazi

```bash
# 方法一：下载官方预编译二进制文件（推荐）
# 访问 https://github.com/sxyazi/yazi/releases 下载最新版本
# 解压后将 yazi 和 ya 移动到 /usr/local/bin/

# 方法二：使用 Cargo 从源码构建
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
cargo install --force yazi-build
```

#### 2. 安装可选依赖

```bash
# 安装大部分可选依赖
sudo apt install ffmpeg 7zip jq poppler-utils fd-find ripgrep fzf zoxide imagemagick

# 安装 resvg（需要通过 Cargo）
cargo install resvg

# 安装 starship
curl -sS https://starship.rs/install.sh | sh

# 安装 eza
sudo apt install eza
# 如果 apt 没有收录，可以从源安装：
# sudo apt install golang-go
# go install github.com/eza-community/eza@latest
```

#### 3. 安装 Nerd Font 字体

```bash
# 手动安装
mkdir -p ~/.local/share/fonts
cd ~/.local/share/fonts
# 从 https://www.nerdfonts.com/ 下载字体，解压到此目录
fc-cache -fv
```

配置 Starship，在 `~/.zshrc` 或 `~/.bashrc` 中添加：

```bash
eval "$(starship init zsh)"  # for zsh
# 或
eval "$(starship init bash)" # for bash
```

---

## 使用配置文件

### 1. 创建配置目录

```bash
mkdir -p ~/.config/yazi
```

### 2. 复制配置文件

将本仓库中的配置文件复制到 Yazi 配置目录：

```bash
# 克隆仓库或下载配置文件后
cp yazi.toml keymap.toml theme.toml init.lua package.toml ~/.config/yazi/
```

### 3. 安装插件

配置文件中使用了以下插件，使用 Yazi 包管理器安装：

```bash
# 智能进入（目录则进入，文件则打开）
ya pkg add yazi-rs/plugins:smart-enter

# Git 状态显示
ya pkg add yazi-rs/plugins:git

# Starship 提示符
ya pkg add Rolv-Apneseth/starship

# 书签管理
ya pkg add h-hg/yamb

# 状态栏美化
ya pkg add llanosrocas/yaziline

# 目录预览增强
ya pkg add ahkohd/eza-preview
```

或者直接使用 package.toml 自动安装：

```bash
# 复制 package.toml 后，Yazi 会自动安装依赖
# 或者手动运行
ya pkg install
```

### 4. 添加 Shell 包装函数（可选但推荐）

为了实现退出 Yazi 时自动 cd 到当前目录的功能，需要在 shell 配置文件中添加包装函数。

**对于 Zsh (~/.zshrc)：**

```bash
# Yazi wrapper function - cd on exit
# 退出时自动 cd 到 yazi 当前目录
function yazi_tmp() {
	local tmp="/tmp/yazi-cwd.$$"
	command yazi --cwd-file="$tmp" "$@"
	if [[ -f "$tmp" ]]; then
		local cwd
		cwd=$(<"$tmp")
		rm -f "$tmp"
		if [[ -n "$cwd" ]] && [[ "$cwd" != "$PWD" ]]; then
			builtin cd -- "$cwd"
		fi
	fi
}
alias y='yazi_tmp'
alias yazi='yazi_tmp'
```

**对于 Bash (~/.bashrc)：**

```bash
# Yazi wrapper function - cd on exit
# 退出时自动 cd 到 yazi 当前目录
function yazi_tmp() {
	local tmp="/tmp/yazi-cwd.$$"
	command yazi --cwd-file="$tmp" "$@"
	if [[ -f "$tmp" ]]; then
		local cwd
		cwd=$(<"$tmp")
		rm -f "$tmp"
		if [[ -n "$cwd" ]] && [[ "$cwd" != "$PWD" ]]; then
			cd -- "$cwd"
		fi
	fi
}
alias y='yazi_tmp'
alias yazi='yazi_tmp'
```

然后重新加载配置：

```bash
source ~/.zshrc   # for zsh
# 或
source ~/.bashrc  # for bash
```

---

## 快捷键说明

### 基本操作

| 快捷键 | 功能 |
|--------|------|
| `j` / `k` | 上下移动（不循环） |
| `h` | 返回上级目录 |
| `l` | 进入目录或打开文件（智能进入） |
| `y` | 复制文件 |
| `x` | 剪切文件 |
| `p` | 粘贴文件 |
| `d` | 删除到回收站 |
| `D` | 永久删除 |
| `r` | 重命名 |
| `a` | 创建文件/目录 |
| `q` | 退出并 cd 到当前目录 |
| `Q` / `S` | 退出并 cd 到当前目录 |
| `gl` | 在当前目录打开 lazygit |

### 导航

| 快捷键 | 功能 |
|--------|------|
| `gd` | 跳转到桌面 (~/Desktop) |
| `gs` | 跳转到 Study (~/Desktop/Study) |
| `gb` | 跳转到 Github (~/Desktop/Github) |
| `gh` | 跳转到主目录 (~) |
| `gc` | 跳转到 ~/.config |
| `H` / `L` | 后退 / 前进历史 |

### 选择

| 快捷键 | 功能 |
|--------|------|
| `Space` | 切换选中状态 |
| `V` | 全选当前目录文件 |
| `Ctrl+a` | 全选 |
| `Ctrl+r` | 反选 |

### 书签 (yamb 插件)

| 快捷键 | 功能 |
|--------|------|
| `ba` | 添加书签 |
| `bg` | 按键跳转书签 |
| `bd` | 删除书签 |
| `br` | 重命名书签 |

### 目录预览 (eza-preview 插件)

| 快捷键 | 功能 |
|--------|------|
| `et` | 切换树形/列表模式 |
| `e-` | 增加树的深度层级 |
| `e_` | 减少树的深度层级 |
| `e.` | 显示/隐藏隐藏文件 |

### 搜索和过滤

| 快捷键 | 功能 |
|--------|------|
| `s` | 使用 fd 搜索文件名 |
| `Alt+s` | 使用 ripgrep 搜索内容 |
| `f` | 过滤文件 |
| `/` | 查找下一个 |
| `?` | 查找上一个 |
| `z` | 使用 fzf 跳转 |
| `Z` | 使用 zoxide 跳转 |

### 标签页

| 快捷键 | 功能 |
|--------|------|
| `t` | 新建标签页 |
| `1-9` | 切换到第 n 个标签页 |
| `[` / `]` | 切换到上/下一个标签页 |

---

## 依赖列表

| 依赖 | 用途 |
|------|------|
| `yazi` | 文件管理器本体 |
| `ffmpeg` | 视频缩略图 |
| `sevenzip` / `7zip` | 压缩包提取和预览 |
| `jq` | JSON 预览 |
| `poppler` | PDF 预览 |
| `fd` | 文件搜索 |
| `ripgrep` | 文件内容搜索 |
| `fzf` | 快速文件子树导航 (>= 0.53.0) |
| `zoxide` | 历史目录导航 (需要 fzf) |
| `resvg` | SVG 预览 |
| `imagemagick` | Font、HEIC、JPEG XL 预览 (>= 7.1.1) |
| `eza` | 目录预览增强 (eza-preview 插件) |
| `starship` | 终端提示符 (starship 插件) |
| `nerd-fonts` | 图标显示 (推荐) |

---

## 故障排除

### 图标显示异常

确保终端使用的字体是 Nerd Font 兼容的。可以安装：
- JetBrains Mono Nerd Font
- Hack Nerd Font
- FiraCode Nerd Font

### 插件不生效

1. 确保插件已正确安装：`ya pkg list`
2. 重新安装插件：`ya pkg install`
3. 检查 init.lua 是否正确引用了插件

### 退出后没有 cd 到目录

1. 确保使用 `y` 或 `yazi` 别名启动（不是直接运行 yazi 命令）
2. 检查 shell 配置文件中是否正确添加了包装函数
3. 重新加载 shell 配置：`source ~/.zshrc`

### eza-preview 不工作

确保已安装 eza：
```bash
eza --version
```

---

## 许可证

本配置文件仅供个人使用和学习参考。
