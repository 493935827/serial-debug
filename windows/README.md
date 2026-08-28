# Shared Serial Console

这是一个适合 Windows 的简单串口工具。后台桥接进程独占物理 COM 口，再把数据转发到本机 TCP 端口。这样你打开的终端和自动化命令可以同时访问同一个串口，不需要反复关闭、重开串口软件。

## 第一次使用

1. 双击 `serial_console.cmd`。
2. 选择 `5` 查看当前串口号。
3. 选择 `6`，把 `serial_config.psd1` 中的 `Port` 和 `Baud` 改成开发板的实际参数并保存。
4. 选择 `1` 启动桥接。
5. 选择 `2` 打开交互终端。终端中按 `Ctrl+C` 只退出终端，不会停止后台桥接。
6. 回到菜单选择 `4`，才会真正关闭串口并释放 COM 口。

菜单本身可以随时关闭；只要没有选择 `4`，后台桥接仍会继续运行。再次双击脚本即可查看状态、打开终端或停止它。

## 配置说明

配置文件是 `serial_config.psd1`：

- `Port`：串口号，例如 `COM10`。
- `Baud`：波特率，例如 `57600` 或 `115200`。
- `LineEnding`：按 Enter 时发送的换行符。嵌入式 Shell 常用 `cr`；若命令不执行，可尝试 `crlf` 或 `lf`。
- `CharDelay`：逐字节发送间隔。较慢的 Shell 可以保留默认 `0.005`，高速可靠链路可设为 `0`。
- `TcpPort`：共享桥接的本机 TCP 端口，默认 `8888`。

默认监听 `127.0.0.1`，只有本机可以连接。工具不会主动切换 DTR/RTS，因此不会故意触发复位或 Boot 模式。

## 命令行用法

除了双击菜单，也可以在 PowerShell 中执行：

```powershell
.\serial_console.ps1 -Action Start
.\serial_console.ps1 -Action Status
.\serial_console.ps1 -Action Connect
.\serial_console.ps1 -Action Send -Command "help"
.\serial_console.ps1 -Action Stop
```

## 日志和故障排查

- 串口接收到的原始数据保存在 `logs` 目录。
- 桥接启动诊断保存在 `.runtime` 目录。
- 如果提示找不到 `serial` 模块，执行：

```powershell
python -m pip install -r requirements.txt
```

- 如果提示 COM 口被占用，请先关闭其他直接打开该串口的软件。
- 拔插 USB 串口后，桥接会每秒尝试重连；终端也会自动重连。
- 如果某条会修改设备状态的命令发送中途断线，不要立即盲目重发，先从终端或日志确认设备状态。

## 硬件安全

连接前确认 USB-UART 与芯片 IO 电平兼容（常见是 3.3 V，但不要凭经验假设），并确认波特率、数据位、校验位和停止位。当前工具使用 pyserial 的默认 `8-N-1`、无流控配置。擦除、烧写、复位和进入 Bootloader 等动作仍需要你明确确认后再执行。

