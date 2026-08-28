@{
    # Change this to the COM port shown by menu item 5, for example COM10.
    Port       = "COM10"
    Baud       = 57600

    # Local TCP endpoint used by the shared bridge. Keep Host on 127.0.0.1
    # unless you intentionally want other computers to reach the console.
    Host       = "127.0.0.1"
    TcpPort    = 8888

    # Common embedded shells expect CR when Enter is pressed.
    LineEnding = "cr"       # cr, lf, or crlf
    Encoding   = "utf-8"
    CharDelay  = 0.005      # seconds between transmitted bytes
    Python     = "python"
}
