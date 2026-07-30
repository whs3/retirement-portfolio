"""Entry point for the retirement portfolio tracker.

Run with:
    python app.py
    flask --app app run --debug

The application logic lives in the ``portfolio`` package; this module only
creates the app instance so existing scripts and systemd units keep working.
"""

import os

from portfolio import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=os.getenv("FLASK_ENV") == "development")
