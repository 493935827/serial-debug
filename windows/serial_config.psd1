@{
    # 默认配置。自动检测或手动编辑后，会创建优先级更高的 serial_config.local.psd1。
    # 串口号示例：COM10。
    Port       = "COM10"
    Baud       = 57600

    # 共享串口桥使用的本机 TCP 地址。除非明确需要局域网访问，否则保持 127.0.0.1。
    Host       = "127.0.0.1"
    TcpPort    = 8888

    # 常见嵌入式 Shell 按 Enter 时使用 CR；也可设置为 lf 或 crlf。
    LineEnding = "cr"
    Encoding   = "utf-8"
    CharDelay  = 0.005      # 每个发送字节之间的延迟，单位为秒
    Python     = "python"
}
