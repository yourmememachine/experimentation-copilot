"""P-value rendering in the results panel (app/static/app.js).

The verdict line must render identically wherever it appears: "p < 0.001"
below the display floor and "p = 0.032" otherwise — never "p = < 0.001".
The shipped JS is exercised directly: fmtP/pPhrase are extracted from
app.js and run under node, and the source is checked so no second,
divergent p-value construction can creep back in.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parent.parent / "app" / "static" / "app.js"


def _extract_fn(source, name):
    match = re.search(rf"function {name}\([^)]*\) \{{.*?\n\}}", source, re.DOTALL)
    assert match, f"{name} not found in app.js"
    return match.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_p_phrase_rendering_is_canonical():
    source = APP_JS.read_text()
    driver = (
        _extract_fn(source, "fmtP")
        + "\n"
        + _extract_fn(source, "pPhrase")
        + """
const cases = [
  [0.0004, "p < 0.001"],
  [0.0009, "p < 0.001"],
  [0.001, "p = 0.001"],
  [0.032, "p = 0.032"],
  [0.5, "p = 0.500"],
  [null, null],
  [undefined, null],
];
let bad = 0;
for (const [input, want] of cases) {
  const got = pPhrase(input);
  if (got !== want) { console.error(`pPhrase(${input}) = ${got}, want ${want}`); bad++; }
}
process.exit(bad ? 1 : 0);
"""
    )
    result = subprocess.run(
        ["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_no_divergent_p_value_construction_in_app_js():
    source = APP_JS.read_text()
    # The only place a "p = ..."/"p < ..." phrase may be built is pPhrase.
    body = _extract_fn(source, "renderResults")
    assert "pPhrase(d.p_value)" in body
    assert "fmtP(d.p_value);" not in body.replace("pPhrase(d.p_value)", "")
    assert body.count("p = ${") == 0 and body.count("p ${") == 0
