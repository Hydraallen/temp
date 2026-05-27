# Kitty Terminal Configuration

Kitty is a fast, feature-rich, GPU-based terminal emulator. This configuration provides a personalized setup with custom theme and settings.

## Config Files

| File | Purpose |
|------|---------|
| `kitty.conf` | Main configuration file |
| `current-theme.conf` | Color theme (Adwaita dark) |
| `termpdf.py/` | Terminal PDF viewer plugin |

## Config Highlights

- **Font**: HackNerdFont-Regular, size 18
- **Theme**: Adwaita dark
- **Ligatures**: Enabled
- **Features**: GPU rendering, Unicode support, true color

## Installation

### macOS
```bash
# Install Kitty via Homebrew
brew install --cask kitty

# Install recommended font
brew install --cask font-hack-nerd-font
```

### Ubuntu / Debian
```bash
# Install via apt (may be outdated)
sudo apt update && sudo apt install kitty

# Recommended: Install latest via script
curl -L https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin

# Create symlink for easy access
ln -sf ~/.local/kitty.app/bin/kitty ~/.local/bin/
```

### Arch / Manjaro
```bash
# Install via pacman
sudo pacman -S kitty

# Install recommended font
sudo pacman -S ttf-hack-nerd
```

## Setup Configuration

### Quick Setup (Copy)
```bash
# Create config directory
mkdir -p ~/.config/kitty

# Copy all config files
cp kitty.conf current-theme.conf ~/.config/kitty/

# Optional: Copy termpdf.py
cp -r termpdf.py ~/.config/kitty/
```

### Or use symlink (recommended for auto-sync)
```bash
# Create parent directory
mkdir -p ~/.config/kitty

# Symlink config files
ln -sf $(pwd)/kitty.conf ~/.config/kitty/kitty.conf
ln -sf $(pwd)/current-theme.conf ~/.config/kitty/current-theme.conf

# Optional: Symlink termpdf.py
ln -sf $(pwd)/termpdf.py ~/.config/kitty/termpdf.py
```

## Verify Installation

```bash
# Check kitty version
kitty --version

# List available fonts
kitty +list-fonts | grep -i hack

# Debug configuration
kitty --debug-config
```

## Useful Shortcuts

### Tabs
| Action | Linux | macOS |
|--------|-------|-------|
| New tab | `Ctrl+Shift+T` | `Cmd+T` |
| Close tab | `Ctrl+Shift+Q` | `Cmd+W` |
| Next tab | `Ctrl+Shift+→` | `Cmd+→` |
| Previous tab | `Ctrl+Shift+←` | `Cmd+←` |

### Windows
| Action | Linux | macOS |
|--------|-------|-------|
| New window | `Ctrl+Shift+Enter` | `Cmd+D` |
| Close window | `Ctrl+Shift+W` | `Shift+Cmd+D` |
| Resize window | `Ctrl+Shift+R` | `Cmd+R` |

### Other
| Action | Linux | macOS |
|--------|-------|-------|
| Copy | `Ctrl+Shift+C` | `Cmd+C` |
| Paste | `Ctrl+Shift+V` | `Cmd+V` |
| Zoom in | `Ctrl+Shift+=` | `Cmd++` |
| Zoom out | `Ctrl+Shift+-` | `Cmd+-` |
| Reset zoom | `Ctrl+Shift+Backspace` | `Cmd+0` |
| Fullscreen | `Ctrl+Shift+F11` | `Ctrl+Cmd+F` |
| Edit config | `Ctrl+Shift+F2` | `Cmd+,` |
| Reload config | `Ctrl+Shift+F5` | `Ctrl+Cmd+,` |

## Troubleshooting

### SSH issues
If you encounter problems with SSH, add to your `~/.zshrc` or `~/.bashrc`:
```bash
export TERM=xterm
```

### Font not found
Make sure Hack Nerd Font is installed:
```bash
# macOS
brew install --cask font-hack-nerd-font

# Arch
sudo pacman -S ttf-hack-nerd

# Ubuntu (manual install)
mkdir -p ~/.local/share/fonts
cd ~/.local/share/fonts
curl -fLo "Hack Regular Nerd Font Complete.ttf" https://github.com/ryanoasis/nerd-fonts/raw/master/patched-fonts/Hack/Regular/HackNerdFont-Regular.ttf
fc-cache -f
```

## Change Theme

To use a different theme:

```bash
# Download a theme (e.g., Tokyonight)
kitty +kitten themes Tokyonight

# Or manually replace current-theme.conf
# Browse themes: https://github.com/kovidgoyal/kitty-themes
```

## References

- [Kitty Documentation](https://sw.kovidgoyal.net/kitty/)
- [Kitty Quickstart](https://sw.kovidgoyal.net/kitty/quickstart/)
- [Kitty Themes](https://github.com/kovidgoyal/kitty-themes)
- [Nerd Fonts](https://www.nerdfonts.com/)
