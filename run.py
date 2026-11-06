"""
Start the SmartDent web app on this computer.

    .venv\\Scripts\\python run.py           (Windows)
    .venv/bin/python run.py                (Mac / Linux)
    add --open to also open it in the web browser (start.bat / start.sh do this)

Then open http://localhost:5000 in a browser. If port 5000 is already in use
(on a Mac, AirPlay Receiver often takes it), the next free port is used and printed.
"""
import os
import socket
import sys
import threading
import webbrowser

from app import create_app
from app.inference import get_model

HOST = "127.0.0.1"     # this computer only; never reachable from the network

app = create_app()


def free_port(first, tries=10):
    """The first port from `first` onwards that nothing else is listening on."""
    for port in range(first, first + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((HOST, port)) != 0:
                return port
    raise SystemExit(f"Ports {first}-{first + tries - 1} are all in use. Close another program and try again.")


if __name__ == "__main__":
    # Load the AI model in the background now, so the first upload doesn't wait for it.
    if app.config["MODEL_PATH"].exists():
        threading.Thread(target=get_model, args=(app.config["MODEL_PATH"],), daemon=True).start()
    port = free_port(int(os.environ.get("PORT", "5000")))
    url = f"http://localhost:{port}"
    print(f"\n  SmartDent is running at {url}\n  Keep this window open while you use it. Close it to stop SmartDent.\n")
    if "--open" in sys.argv[1:]:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    # debug=False: the debug console must never be reachable, even on a local network.
    app.run(host=HOST, port=port, debug=False)
