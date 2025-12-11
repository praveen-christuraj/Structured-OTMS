import sys
import os
import time
import tempfile
import threading
import socket
import streamlit.web.cli as stcli
try:
    import main_app  # ensure PyInstaller includes the app module
except Exception:
    main_app = None

def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except Exception:
        return False

def _launch_streamlit(port: int):
    # Create a temporary stub that imports the packaged main_app module
    fd, stub_path = tempfile.mkstemp(prefix="otms_entry_", suffix=".py")
    os.close(fd)
    with open(stub_path, "w", encoding="utf-8") as f:
        f.write("import main_app\nmain_app.main()\n")
    sys.argv = [
        "streamlit",
        "run",
        stub_path,
        "--server.headless",
        "true",
        "--server.address",
        "0.0.0.0",
        # Let Streamlit use default port (8501) in dev mode
    ]
    stcli.main()

def _start_ngrok_tunnel(port: int) -> str:
    try:
        from pyngrok import ngrok, conf
    except Exception:
        return ""

    auth_token = os.environ.get("NGROK_AUTHTOKEN") or os.environ.get("NGROK_AUTH_TOKEN")
    if not auth_token:
        print("Ngrok authtoken not set. Skipping external URL.")
        return ""
    conf.get_default().auth_token = auth_token

    region = os.environ.get("NGROK_REGION")  # e.g., "us", "eu", "in"
    kwargs = {"bind_tls": True}
    if region:
        kwargs["region"] = region

    try:
        tunnel = ngrok.connect(addr=port, **kwargs)
        public_url = getattr(tunnel, "public_url", "")
        if public_url:
            print(f"External URL: {public_url}")
        return public_url
    except Exception as e:
        print(f"Failed to start ngrok tunnel: {e}")
        return ""

def _wait_and_start_ngrok(port: int):
    for _ in range(180):
        if _is_port_open(port):
            break
        time.sleep(1)
    chosen_port = port
    if not _is_port_open(chosen_port):
        for p in range(port, port + 10):
            if _is_port_open(p):
                chosen_port = p
                break
    try:
        _start_ngrok_tunnel(chosen_port)
    except Exception as e:
        print(f"External URL setup failed: {e}")

def main():
    port = int(os.environ.get("OTMS_PORT", "8501"))

    # Print local/network hints early
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"Local URL: http://127.0.0.1:{port}")
        print(f"Network URL: http://{local_ip}:{port}")
    except Exception:
        pass

    # Start background thread to create external URL when server is up
    threading.Thread(target=_wait_and_start_ngrok, args=(port,), daemon=True).start()

    # Run Streamlit in main thread
    _launch_streamlit(port)

if __name__ == "__main__":
    main()
