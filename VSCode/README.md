# VSCode Configuration

Visual Studio Code configuration for macOS.

## Config Files

| File | Purpose |
|------|---------|
| `settings.json` | Editor settings (theme, Vim, LaTeX, etc.) |
| `keybindings.json` | Custom keyboard shortcuts |
| `vimrc-vscode` | Vim emulation settings |
| `hsnips/` | HyperSnips snippets (LaTeX, Markdown) |
| `extensions.txt` | List of installed extensions |

## Config Highlights

- **Theme**: Material Theme
- **Icon Theme**: vscode-icons-mac
- **Vim**: Enabled with custom vimrc
- **LaTeX**: LaTeX Workshop configured
- **Snippets**: HyperSnips for LaTeX/Markdown

## Installation

### 1. Install VSCode
```bash
brew install --cask visual-studio-code
```

### 2. Install Extensions
```bash
cat extensions.txt | xargs -L 1 code --install-extension
```

Or install manually:
```bash
# Appearance
code --install-extension zhuangtongfa.material-theme
code --install-extension vscode-icons-team.vscode-icons
code --install-extension wayou.vscode-icons-mac

# Vim
code --install-extension vscodevim.vim

# Git
code --install-extension mhutchie.git-graph
code --install-extension wakatime.vscode-wakatime

# Python
code --install-extension ms-python.python
code --install-extension ms-python.debugpy
code --install-extension ms-python.vscode-pylance
code --install-extension ms-python.vscode-python-envs

# Jupyter
code --install-extension ms-toolsai.jupyter
code --install-extension ms-toolsai.jupyter-keymap
code --install-extension ms-toolsai.jupyter-renderers

# C/C++
code --install-extension ms-vscode.cpptools
code --install-extension ms-vscode.cpptools-extension-pack
code --install-extension ms-vscode.cpptools-themes
code --install-extension ms-vscode.cmake-tools
code --install-extension twxs.cmake
code --install-extension danielpinto8zz6.c-cpp-compile-run
code --install-extension vadimcn.vscode-lldb

# LaTeX
code --install-extension james-yu.latex-workshop

# Markdown
code --install-extension shd101wyy.markdown-preview-enhanced
code --install-extension yzhang.markdown-all-in-one
code --install-extension yzane.markdown-pdf

# Web
code --install-extension esbenp.prettier-vscode
code --install-extension ritwickdey.liveserver
code --install-extension svelte.svelte-vscode
code --install-extension kamikillerto.vscode-colorize
code --install-extension dzhavat.css-flexbox-cheatsheet
code --install-extension qiuqiu-xt.css-flex

# Lua
code --install-extension sumneko.lua

# Docker
code --install-extension ms-azuretools.vscode-containers

# Utilities
code --install-extension formulahendry.code-runner
code --install-extension aaron-bond.better-comments
code --install-extension alefragnani.bookmarks
code --install-extension streetsidesoftware.code-spell-checker
code --install-extension christian-kohler.path-intellisense
code --install-extension ionutvmi.path-autocomplete
code --install-extension mechatroner.rainbow-csv
code --install-extension adpyke.codesnap
code --install-extension gerrnperl.outline-map
code --install-extension wayou.vscode-todo-highlight
code --install-extension natqe.reload
code --install-extension y-ysss.cisco-config-highlight

# AI
code --install-extension github.copilot-chat
code --install-extension amazonwebservices.codewhisperer-for-command-line-companion

# Testing
code --install-extension hbenl.vscode-test-explorer
code --install-extension ms-vscode.test-adapter-converter

# Chinese
code --install-extension ms-ceintl.vscode-language-pack-zh-hans
```

### 3. Setup Configuration

All config files go to the same directory: `~/Library/Application Support/Code/User/`

**Copy:**
```bash
# Target directory
VSCODE_USER="$HOME/Library/Application Support/Code/User"

# Copy settings and keybindings
cp settings.json "$VSCODE_USER/"
cp keybindings.json "$VSCODE_USER/"

# Copy hsnips folder
cp -r hsnips "$VSCODE_USER/"
```

**Or use symlink (recommended):**
```bash
# Target directory
VSCODE_USER="$HOME/Library/Application Support/Code/User"

# Symlink config files
ln -sf $(pwd)/settings.json "$VSCODE_USER/settings.json"
ln -sf $(pwd)/keybindings.json "$VSCODE_USER/keybindings.json"
ln -sf $(pwd)/hsnips "$VSCODE_USER/hsnips"
```

## Config Location

All files are in: `~/Library/Application Support/Code/User/`

```
~/Library/Application Support/Code/User/
├── settings.json
├── keybindings.json
└── hsnips/
    ├── latex.hsnips
    └── markdown.hsnips
```

## Update Extensions List

```bash
code --list-extensions > extensions.txt
```

## References

- [VSCode Documentation](https://code.visualstudio.com/docs)
- [Vim Extension](https://github.com/VSCodeVim/Vim)
- [LaTeX Workshop](https://github.com/James-Yu/LaTeX-Workshop)
