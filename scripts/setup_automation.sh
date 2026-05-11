#!/bin/bash
# setup_automation.sh - 一键配置 WorkBuddy 定时触发 auto_monitor
#
# 用法:
#   bash setup_automation.sh                    # 交互式配置
#   bash setup_automation.sh --daemon 60       # 守护模式，60秒间隔
#   bash setup_automation.sh --once             # 单次定时任务
#   bash setup_automation.sh --uninstall        # 卸载自动化
#
# 注意: 此脚本需要与 auto_monitor.py 放在同一目录下

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_MONITOR="$SCRIPT_DIR/auto_monitor.py"
WORKDIR="$HOME/WorkBuddy/2026-05-11-task-17"
MEMORY_DIR="$WORKDIR/.workbuddy/memory"
SKILL_NAME="context-rotation"
AUTOMATION_NAME="context-auto-monitor"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err() { echo -e "${RED}[ERR]${NC} $1"; }

# 检查依赖
check_dependencies() {
    if [[ ! -f "$AUTO_MONITOR" ]]; then
        log_err "找不到 auto_monitor.py: $AUTO_MONITOR"
        exit 1
    fi

    if ! command -v python3 &> /dev/null; then
        log_err "需要 python3，请先安装"
        exit 1
    fi

    # 检查yaml模块
    if ! python3 -c "import yaml" 2>/dev/null; then
        log_warn "缺少 PyYAML 模块，尝试安装..."
        pip3 install pyyaml --quiet
    fi

    log_info "依赖检查通过"
}

# 读取当前自动化配置
get_automation_config() {
    python3 -c "
import json, sqlite3, os
db_path = os.path.expanduser('~/.workbuddy/workbuddy.db')
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT id, name, prompt FROM automations WHERE name LIKE \"%context%\" OR name LIKE \"%auto_monitor%\"')
    rows = cur.fetchall()
    for r in rows:
        print(f'id={r[0]} name={r[1]}')
    conn.close()
" 2>/dev/null || echo ""
}

# 创建守护进程启动脚本
create_daemon_script() {
    local interval=${1:-60}
    local daemon_script="$MEMORY_DIR/auto_monitor_daemon.sh"

    mkdir -p "$MEMORY_DIR"

    cat > "$daemon_script" << EOF
#!/bin/bash
# auto_monitor 守护进程启动脚本（由 setup_automation.sh 生成）
# 间隔: ${interval}秒

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "\$SCRIPT_DIR/../../../.."  # 回到工作区根目录

python3 ~/.workbuddy/skills/context-rotation/scripts/auto_monitor.py \
    --mode daemon \
    --interval ${interval} \
    >> ~/.workbuddy/logs/auto_monitor.log 2>&1
EOF

    chmod +x "$daemon_script"
    echo "$daemon_script"
}

# 创建单次定时任务脚本
create_once_script() {
    local once_script="$MEMORY_DIR/auto_monitor_once.sh"

    mkdir -p "$MEMORY_DIR"

    cat > "$once_script" << 'EOF'
#!/bin/bash
# auto_monitor 单次检查脚本（由 setup_automation.sh 生成）

python3 ~/.workbuddy/skills/context-rotation/scripts/auto_monitor.py --mode once
EOF

    chmod +x "$once_script"
    echo "$once_script"
}

# 交互式菜单
interactive_menu() {
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   context-rotation 自动化配置             ║"
    echo "╠══════════════════════════════════════════╣"
    echo "║  1. 守护进程模式 (后台持续监控)           ║"
    echo "║  2. 单次检查模式 (每天固定时间)           ║"
    echo "║  3. 查看当前配置                         ║"
    echo "║  4. 卸载自动化                           ║"
    echo "║  0. 退出                                 ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""

    read -p "请选择 [0-4]: " choice

    case $choice in
        1)
            read -p "检查间隔（秒，默认60）: " interval
            interval=${interval:-60}
            setup_daemon "$interval"
            ;;
        2)
            read -p "检查时间（HH:MM，默认09:00）: " check_time
            check_time=${check_time:-09:00}
            setup_cron "$check_time"
            ;;
        3)
            show_config
            ;;
        4)
            uninstall
            ;;
        0)
            echo "退出"
            exit 0
            ;;
        *)
            log_err "无效选择: $choice"
            ;;
    esac
}

# 设置守护进程
setup_daemon() {
    local interval=${1:-60}
    log_info "配置守护进程模式（间隔 ${interval}s）..."

    # 创建启动脚本
    daemon_script=$(create_daemon_script "$interval")
    log_info "守护脚本已创建: $daemon_script"

    # macOS: 使用 launchd
    if [[ "$(uname)" == "Darwin" ]]; then
        setup_launchd "$daemon_script"
    else
        # Linux: 使用 systemd 或 cron
        if command -v systemctl &> /dev/null; then
            setup_systemd "$daemon_script"
        else
            setup_cron_minutely
        fi
    fi

    log_info "守护进程配置完成"
    log_info "启动命令: $daemon_script"
}

# macOS launchd 配置
setup_launchd() {
    local daemon_script=$1
    local plist="$HOME/Library/LaunchAgents/com.workbuddy.context-rotation.plist"

    mkdir -p "$(dirname "$plist")"

    cat > "$plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.workbuddy.context-rotation</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$daemon_script</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.workbuddy/logs/auto_monitor.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.workbuddy/logs/auto_monitor.err</string>
</dict>
</plist>
EOF

    mkdir -p "$HOME/.workbuddy/logs"
    launchctl unload "$plist" 2>/dev/null || true
    launchctl load "$plist"
    log_info "launchd 已配置: $plist"
}

# systemd 配置
setup_systemd() {
    local daemon_script=$1
    local service_file="/etc/systemd/system/context-rotation-monitor.service"

    sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=WorkBuddy Context Rotation Monitor
After=network.target

[Service]
Type=simple
ExecStart=$daemon_script
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable context-rotation-monitor
    sudo systemctl start context-rotation-monitor
    log_info "systemd 已配置并启动"
}

# cron 定时配置
setup_cron() {
    local check_time=$1
    local once_script=$(create_once_script)

    # 读取当前 crontab
    local current_cron
    current_cron=$(crontab -l 2>/dev/null || echo "")

    # 移除旧的 context-rotation 相关配置
    current_cron=$(echo "$current_cron" | grep -v "context-rotation\|auto_monitor" || echo "")

    # 添加新的 crontab
    local cron_entry="0 9 * * * $once_script >> $HOME/.workbuddy/logs/auto_monitor_cron.log 2>&1"
    echo "$current_cron" > /tmp/current_cron.tab
    echo "$cron_entry" >> /tmp/current_cron.tab
    crontab /tmp/current_cron.tab
    rm /tmp/current_cron.tab

    log_info "cron 定时任务已配置: 每天 $check_time 执行"
}

# 简化版 cron（每5分钟检查）
setup_cron_minutely() {
    local once_script=$(create_once_script)

    local current_cron
    current_cron=$(crontab -l 2>/dev/null || echo "")
    current_cron=$(echo "$current_cron" | grep -v "context-rotation\|auto_monitor" || echo "")

    local cron_entry="*/5 * * * * $once_script >> $HOME/.workbuddy/logs/auto_monitor_cron.log 2>&1"
    echo "$current_cron" > /tmp/current_cron.tab
    echo "$cron_entry" >> /tmp/current_cron.tab
    crontab /tmp/current_cron.tab
    rm /tmp/current_cron.tab

    log_info "cron 已配置: 每5分钟检查一次"
}

# 显示当前配置
show_config() {
    echo ""
    echo "=== 当前 context-rotation 自动化配置 ==="
    echo ""

    # 检查守护进程
    if [[ "$(uname)" == "Darwin" ]]; then
        if launchctl list | grep -q "context-rotation"; then
            log_info "守护进程: 运行中 (launchd)"
        else
            log_warn "守护进程: 未运行"
        fi
    fi

    # 检查 cron
    local cron_line
    cron_line=$(crontab -l 2>/dev/null | grep "auto_monitor" | grep -v "^#" || echo "")
    if [[ -n "$cron_line" ]]; then
        log_info "定时任务: $cron_line"
    else
        log_warn "定时任务: 未配置"
    fi

    # 检查交接队列
    local queue_file="$MEMORY_DIR/handover/auto_handover_queue.json"
    if [[ -f "$queue_file" ]]; then
        local queue_count
        queue_count=$(python3 -c "import json; print(len(json.load(open('$queue_file'))))" 2>/dev/null || echo "0")
        log_info "待处理交接建议: $queue_count 条"
    fi

    echo ""
}

# 卸载自动化
uninstall() {
    log_warn "卸载 context-rotation 自动化..."

    # macOS launchd
    if [[ "$(uname)" == "Darwin" ]]; then
        launchctl unload "$HOME/Library/LaunchAgents/com.workbuddy.context-rotation.plist" 2>/dev/null || true
        rm -f "$HOME/Library/LaunchAgents/com.workbuddy.context-rotation.plist"
    fi

    # systemd
    if command -v systemctl &> /dev/null; then
        sudo systemctl stop context-rotation-monitor 2>/dev/null || true
        sudo systemctl disable context-rotation-monitor 2>/dev/null || true
        sudo rm -f /etc/systemd/system/context-rotation-monitor.service
    fi

    # cron
    local current_cron
    current_cron=$(crontab -l 2>/dev/null || echo "")
    current_cron=$(echo "$current_cron" | grep -v "context-rotation\|auto_monitor" || echo "")
    echo "$current_cron" > /tmp/current_cron.tab
    crontab /tmp/current_cron.tab 2>/dev/null || true
    rm -f /tmp/current_cron.tab

    log_info "卸载完成"
}

# 主入口
main() {
    check_dependencies

    # 解析命令行参数
    case "${1:-}" in
        --daemon)
            setup_daemon "${2:-60}"
            ;;
        --once)
            setup_cron "09:00"
            ;;
        --uninstall)
            uninstall
            ;;
        --show)
            show_config
            ;;
        "")
            interactive_menu
            ;;
        *)
            echo "用法: $0 [--daemon <间隔>] [--once] [--uninstall] [--show]"
            echo ""
            echo "示例:"
            echo "  $0                    # 交互式菜单"
            echo "  $0 --daemon 60        # 守护模式，60秒间隔"
            echo "  $0 --once             # 每天09:00检查"
            echo "  $0 --uninstall        # 卸载自动化"
            exit 1
            ;;
    esac
}

main "$@"
