from pathlib import Path

public = Path(__file__).resolve().parent.parent / "backend" / "public"
mapping = {
    "INDEX_HTML": "index.html",
    "APP_JS": "app.js",
    "STYLES_CSS": "styles.css",
}
lines = ["# Auto-generated frontend assets for Vercel deployment", ""]
for const, fname in mapping.items():
    content = (public / fname).read_text(encoding="utf-8")
    lines.append(f"{const} = {content!r}")
    lines.append("")
Path(__file__).resolve().parent.parent.joinpath("backend", "frontend_assets.py").write_text(
    "\n".join(lines), encoding="utf-8"
)
print("Generated backend/frontend_assets.py")
