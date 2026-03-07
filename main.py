"""
ViolaWatch — Launch Script
Run this file to start either the Desktop GUI or Web Server
"""
import sys

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        print("Starting web server...")
        from server import app
        import config as cfg
        app.run(host=cfg.SERVER_HOST, port=cfg.SERVER_PORT, debug=False, threaded=True)
    else:
        print("Starting desktop GUI...")
        try:
            from gui.app import ViolaWatchApp
            app = ViolaWatchApp()
            app.run()
        except ImportError as e:
            print(f"GUI dependencies missing: {e}")
            print("Install: pip install customtkinter Pillow")
            print("Or run web mode: python main.py --web")

if __name__ == "__main__":
    main()
