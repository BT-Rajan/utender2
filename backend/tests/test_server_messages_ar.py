"""Every message the server sends a person exists in Arabic too. Collects
each fixed message raised as an HTTPException (and the quality gate's and
eligibility's own sentences) straight from the source, so a new message
without a translation fails here."""
import ast
import pathlib
import re

from fastapi.testclient import TestClient

from app.i18n_server import translate
from app.main import app

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
ARABIC = re.compile(r"[؀-ۿ]")


def _messages() -> set[str]:
    found = set()
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                for kw in node.keywords:
                    if name == "HTTPException" and kw.arg == "detail" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        found.add(kw.value.value)
                    if name == "EligibilityReason" and kw.arg == "message" and isinstance(kw.value, ast.Constant):
                        found.add(kw.value.value)
                # requirement_quality: err(code, section, message) / warn(...)
                if name in ("err", "warn") and len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
                    found.add(node.args[2].value)
    # Machine codes the interface acts on (not shown as text).
    return {m for m in found if " " in m}


def test_every_fixed_message_has_an_arabic_translation():
    messages = _messages()
    assert len(messages) > 100
    missing = sorted(m for m in messages if not ARABIC.search(translate(m, "ar")) or translate(m, "ar") == m)
    assert missing == [], missing


def test_messages_with_values_and_composites_translate():
    for text in [
        'Item 3 ("Gate") has a quantity but no unit.',
        "Duration must be between 1 and 3650 days.",
        'This requirement needs a valid "Electrical licence"; yours expired on 2026-01-01.',
        "This requirement is in Hawalli, which isn't among the governorates your profile says you serve.",
        'Your offer is missing a completion period, the "Programme" document.',
        "This requirement isn't ready to publish. Set an offer deadline in the future. Choose the governorate, so providers can judge travel and whether they cover the area.",
    ]:
        out = translate(text, "ar")
        assert ARABIC.search(out) and not re.search(r"[A-Za-z]{4,} [a-z]{4,}", out.replace("Gate", "").replace("Electrical licence", "").replace("Programme", "")), out


def test_the_api_answers_in_the_language_asked_for(db):
    c = TestClient(app)
    r = c.post("/auth/login", json={"email": "nobody@example.com", "password": "x"}, headers={"Accept-Language": "ar"})
    assert r.json()["detail"] == "البريد الإلكتروني أو كلمة المرور غير صحيحة."
    r = c.post("/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert r.json()["detail"] == "Invalid email or password."
    r = c.post("/auth/login", json={"email": 5}, headers={"Accept-Language": "ar"})  # validation error
    assert r.status_code == 422 and ARABIC.search(r.json()["detail"])
