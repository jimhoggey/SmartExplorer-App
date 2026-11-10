"""The How it works guide is front-end only: these check it is wired into the page, so a
missing id can't stop the script (its diagram and steps are checked by hand in the app)."""
import re
from pathlib import Path

from test_app import client  # noqa: F401  (a fixture)

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_the_page_loads_the_guide_after_the_app(client):  # noqa: F811
    page = client.get("/").get_data(as_text=True)
    assert page.index("/static/app.js") < page.index("/static/how.js")
    assert client.get("/static/how.js").status_code == 200


def test_settings_opens_the_guide():
    page = (STATIC / "index.html").read_text("utf-8")
    assert page.index('id="settings"') < page.index('id="howOpen"') < page.index('<dialog id="how"')


def test_every_id_the_scripts_ask_for_is_on_the_page():
    ids = set(re.findall(r'\bid="(\w+)"', (STATIC / "index.html").read_text("utf-8")))
    app = (STATIC / "app.js").read_text("utf-8")
    listed = re.search(r"const els = \[(.*?)\]", app, re.S).group(1)
    wanted = set(re.findall(r'"(\w+)"', listed))
    for script in ("app.js", "how.js"):
        wanted |= set(re.findall(r'\$\("(\w+)"\)', (STATIC / script).read_text("utf-8")))
    assert len(wanted) > 50 and wanted <= ids, wanted - ids
