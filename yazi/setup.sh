#!/bin/bash

# Yazi 配置文件安装脚本
# 使用方法: ./setup.sh

set -e

CONFIG_DIR="$HOME/.config/yazi"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Yazi 配置文件安装脚本 ==="
echo ""

# 检测操作系统
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ -f /etc/endeavouros-release ]]; then
        echo "endeavouros"
    elif [[ -f /etc/arch-release ]]; then
        echo "arch"
    elif [[ -f /etc/lsb-release ]] && grep -q "Ubuntu" /etc/lsb-release 2>/dev/null; then
        echo "ubuntu"
    elif [[ -f /etc/debian_version ]]; then
        echo "ubuntu"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)
echo "检测到操作系统: $OS"
echo ""

# 显示安装依赖的提示
show_install_deps() {
    echo "=========================================="
    echo "  请先安装 Yazi 及其依赖"
    echo "=========================================="
    echo ""

    case "$1" in
        macos)
            echo "macOS 安装命令："
            echo ""
            echo "  # 安装 Yazi 及所有可选依赖"
            echo "  brew install yazi ffmpeg sevenzip jq poppler fd ripgrep fzf zoxide resvg imagemagick font-symbols-only-nerd-font"
            echo ""
            echo "  # 安装 starship"
            echo "  brew install starship"
            echo ""
            echo "  # 安装 eza"
            echo "  brew install eza"
            ;;
        arch|endeavouros)
            echo "Arch Linux / EndeavourOS 安装命令："
            echo ""
            echo "  # 安装 Yazi 及所有可选依赖"
            echo "  sudo pacman -S yazi ffmpeg 7zip jq poppler fd ripgrep fzf zoxide resvg imagemagick"
            echo ""
            echo "  # 安装 starship 和 eza"
            echo "  sudo pacman -S starship eza"
            echo ""
            echo "  # 安装 Nerd Font 字体"
            echo "  sudo pacman -S ttf-jetbrains-mono-nerd"
            echo "  # 或者"
            echo "  yay -S ttf-hack-nerd"
            ;;
        ubuntu)
            echo "Ubuntu / Debian 安装命令："
            echo ""
            echo "  # Yazi 需要手动安装，下载预编译二进制文件："
            echo "  # https://github.com/sxyazi/yazi/releases"
            echo ""
            echo "  # 安装可选依赖"
            echo "  sudo apt install ffmpeg 7zip jq poppler-utils fd-find ripgrep fzf zoxide imagemagick"
            echo ""
            echo "  # 安装 resvg (通过 Cargo)"
            echo "  cargo install resvg"
            echo ""
            echo "  # 安装 starship"
            echo "  curl -sS https://starship.rs/install.sh | sh"
            echo ""
            echo "  # 安装 eza"
            echo "  sudo apt install eza"
            ;;
        *)
            echo "未知操作系统，请参考 README.md 手动安装依赖"
            ;;
    esac

    echo ""
}

# 检查 yazi 是否已安装
if ! command -v yazi &> /dev/null; then
    show_install_deps "$OS"
    read -p "是否已安装 Yazi？继续配置？(y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 创建配置目录
echo "[1/3] 创建配置目录..."
mkdir -p "$CONFIG_DIR"
echo "配置目录创建完成: $CONFIG_DIR"
echo ""

# 复制配置文件
echo "[2/3] 复制配置文件..."
cp "$SCRIPT_DIR/yazi.toml" "$CONFIG_DIR/"
cp "$SCRIPT_DIR/keymap.toml" "$CONFIG_DIR/"
cp "$SCRIPT_DIR/theme.toml" "$CONFIG_DIR/"
cp "$SCRIPT_DIR/init.lua" "$CONFIG_DIR/"
cp "$SCRIPT_DIR/package.toml" "$CONFIG_DIR/"
echo "配置文件复制完成"
echo ""

# 安装插件
echo "[3/3] 安装插件..."
ya pkg install
echo "插件安装完成"
echo ""

echo "=== 安装完成 ==="
echo ""
echo "=========================================="
echo "  Shell 配置（需要手动添加）"
echo "=========================================="
echo ""
echo "请在你的 shell 配置文件中添加以下代码："
echo ""
echo "  Zsh 用户 -> ~/.zshrc"
echo "  Bash 用户 -> ~/.bashrc"
echo ""
echo "--- 复制以下内容 ---"
echo ""
echo '# Yazi wrapper function - cd on exit'
echo '# q: 退出并回到原目录'
echo '# Q/S: 退出并 cd 到当前目录'
echo 'function yazi_tmp() {'
echo '	local tmp="/tmp/yazi-cwd.$$"'
echo '	command yazi --cwd-file="$tmp" "$@"'
echo '	if [[ -f "$tmp" ]]; then'
echo '		local cwd="$(cat "$tmp")"'
echo '		rm -f "$tmp"'
echo '		if [[ -n "$cwd" ]] && [[ "$cwd" != "$PWD" ]]; then'
echo '			builtin cd -- "$cwd"'
echo '		fi'
echo '	fi'
echo '}'
echo "alias yazi='yazi_tmp'"
echo "alias y='yazi_tmp'"
echo ""
echo "--- 结束 ---"
echo ""
echo "快捷键说明："
echo "  q     - 退出并回到原目录"
echo "  Q / S - 退出并 cd 到当前目录"
echo ""
echo "如果使用 starship 插件，还需添加："
echo ""
echo '  eval "$(starship init zsh)"  # for zsh'
echo '  # 或'
echo '  eval "$(starship init bash)" # for bash'
echo ""
echo "添加后运行以下命令使配置生效："
echo "  source ~/.zshrc    # Zsh 用户"
echo "  source ~/.bashrc   # Bash 用户"
echo ""
echo "然后使用 'yazi' 或 'y' 命令启动 Yazi"
