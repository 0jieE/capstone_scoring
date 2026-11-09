"""
Start the scoring server for LAN access.

Detects this machine's LAN IP, applies pending migrations, prints the URL
panelists should open, then runs `manage.py runserver 0.0.0.0:8000`.

    python run_lan.py            # port 8000
    python run_lan.py 8080       # another port
"""
import os
import socket
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = 8000


def lan_ips():
    """Best-effort list of this machine's IPv4 LAN addresses (no internet needed)."""
    ips = []
    # The OS picks the outgoing interface for a private address; UDP connect
    # sends no packets.
    for probe in ("10.255.255.255", "192.168.255.255", "172.31.255.255", "8.8.8.8"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 1))
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127.") and ip not in ips:
                    ips.append(ip)
        except OSError:
            pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith(("127.", "169.254.")) and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    os.chdir(BASE_DIR)
    manage = [sys.executable, str(BASE_DIR / "manage.py")]

    print("Preparing the database...")
    subprocess.run(manage + ["migrate", "--noinput", "-v", "0"], check=True)

    ips = lan_ips()
    line = "=" * 60
    print()
    print(line)
    print("  Capstone Defense Scoring System")
    if ips:
        print(f"  Panelists open: http://{ips[0]}:{port}")
        for ip in ips[1:]:
            print(f"             or: http://{ip}:{port}")
    else:
        print("  Could not detect a LAN IP. Run `ipconfig` and use the IPv4 address:")
        print(f"  Panelists open: http://<this-PC-IP>:{port}")
    print(f"  On this PC:     http://127.0.0.1:{port}")
    print("  Press Ctrl+C to stop the server.")
    print(line)
    print(flush=True)

    # --insecure serves static files even when CAPSTONE_DEBUG=0 (LAN only).
    try:
        subprocess.run(manage + ["runserver", f"0.0.0.0:{port}", "--insecure"], check=False)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
