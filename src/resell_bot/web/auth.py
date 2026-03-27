"""Simple session-based authentication for the dashboard.

Credentials are set via environment variables:
  DASHBOARD_USER=guillaume
  DASHBOARD_PASS=your_password

All routes except /login require a valid session cookie.
"""

import os
import secrets

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

# Generate a random secret key at startup (sessions invalidated on restart — fine)
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))

# Credentials from .env
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "")


def setup_auth(app) -> None:
    """Add session middleware and auth routes to the FastAPI app."""
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=86400 * 30)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Skip auth if no password configured (local dev)
        if not DASHBOARD_PASS:
            return await call_next(request)

        # Allow login page and static assets
        if request.url.path in ("/login", "/favicon.ico"):
            return await call_next(request)

        # Check session
        if not request.session.get("authenticated"):
            if request.url.path == "/login":
                return await call_next(request)
            return RedirectResponse("/login", status_code=302)

        return await call_next(request)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, error: str | None = None):
        # Already logged in
        if request.session.get("authenticated"):
            return RedirectResponse("/", status_code=302)
        error_html = ""
        if error:
            error_html = '<p style="color: var(--red); margin-bottom: 1rem;">Identifiants incorrects</p>'
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>resell-bot — Connexion</title>
            <style>
                :root {{
                    --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
                    --text: #e1e4ed; --muted: #8b8fa3; --accent: #6c63ff;
                    --green: #22c55e; --red: #ef4444;
                }}
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    background: var(--bg); color: var(--text);
                    display: flex; align-items: center; justify-content: center;
                    min-height: 100vh;
                }}
                .login-card {{
                    background: var(--surface); border: 1px solid var(--border);
                    border-radius: 12px; padding: 2rem; width: 360px;
                }}
                .login-card h1 {{ font-size: 1.4rem; margin-bottom: 0.5rem; }}
                .login-card h1 span {{ color: var(--accent); }}
                .login-card p {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 1.5rem; }}
                .form-group {{ margin-bottom: 1rem; }}
                .form-group label {{ display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 0.3rem; }}
                .form-input {{
                    width: 100%; padding: 0.6rem 0.75rem; border-radius: 6px;
                    border: 1px solid var(--border); background: var(--bg);
                    color: var(--text); font-size: 0.9rem;
                }}
                .form-input:focus {{ outline: none; border-color: var(--accent); }}
                .btn {{
                    width: 100%; padding: 0.65rem; border-radius: 6px; border: none;
                    background: var(--accent); color: white; font-size: 0.95rem;
                    cursor: pointer; font-weight: 600;
                }}
                .btn:hover {{ opacity: 0.9; }}
            </style>
        </head>
        <body>
            <div class="login-card">
                <h1><span>resell</span>-bot</h1>
                <p>Connexion au dashboard</p>
                {error_html}
                <form method="post" action="/login">
                    <div class="form-group">
                        <label>Utilisateur</label>
                        <input type="text" name="username" class="form-input" required autofocus>
                    </div>
                    <div class="form-group">
                        <label>Mot de passe</label>
                        <input type="password" name="password" class="form-input" required>
                    </div>
                    <button type="submit" class="btn">Se connecter</button>
                </form>
            </div>
        </body>
        </html>
        """)

    @app.post("/login")
    async def login_submit(request: Request):
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        if username == DASHBOARD_USER and password == DASHBOARD_PASS:
            request.session["authenticated"] = True
            request.session["user"] = username
            return RedirectResponse("/", status_code=302)
        return RedirectResponse("/login?error=1", status_code=302)

    @app.get("/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=302)
