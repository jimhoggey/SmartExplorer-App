import json
import os
import sys
import threading
import webbrowser

from werkzeug.serving import make_server

from app import app
from version import APP_VERSION


def serve():
    srv = make_server("127.0.0.1", int(os.environ.get("SMART_EXPLORER_PORT", 0)), app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d" % srv.server_port


def dropped_paths(event):
    """Full paths of files and folders dropped on the window. A browser only
    sees file names; pywebview adds pywebviewFullPath on the native side."""
    files = (event.get("dataTransfer") or {}).get("files") or []
    return [f["pywebviewFullPath"] for f in files if isinstance(f, dict) and f.get("pywebviewFullPath")]


def listen_for_drops(window):
    from webview.dom import DOMEventHandler

    def on_drop(event):
        window.evaluate_js("window.onDropPaths && window.onDropPaths(%s)" % json.dumps(dropped_paths(event)))

    window.dom.document.events.drop += DOMEventHandler(on_drop, prevent_default=True, stop_propagation=True)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if "--watch" in args:
        import watch  # background renaming: no window, no web server
        return watch.main(now="--now" in args)  # --now: started from the window, so no start-up wait
    url = serve()
    if os.environ.get("SMART_EXPLORER_HEADLESS") == "1":
        print(url, flush=True)
        return threading.Event().wait()
    try:
        import webview
        # text_select=False (the default) injects user-select: none, which macOS WebKit
        # passes down to inputs: the key field and name boxes then ignore typing and paste.
        window = webview.create_window("Smart Explorer " + APP_VERSION, url, width=1200, height=820, min_size=(900, 640),
                                       background_color="#f4f5f8", text_select=True)
        webview.start(listen_for_drops, window)
    except Exception:
        webbrowser.open(url)
        threading.Event().wait()


if __name__ == "__main__":
    main()
