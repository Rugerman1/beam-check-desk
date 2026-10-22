"""Optional Claude-written narrative for the calc package.

The model only ever sees the computed numbers in `summary_dict` and is told
to quote them, never to compute anything.  If no API key is configured the
app falls back to a template narrative so it works fully offline.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

MODEL = "claude-sonnet-4-5"
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM = (
    "You are a structural engineer writing the narrative section of a steel beam "
    "calculation package. You are given a JSON summary of a beam check that was "
    "already computed by software. Write in plain, professional English for an "
    "engineer reviewing the calc. Rules: quote numbers exactly as given in the JSON "
    "and never compute, round differently, or invent values; do not restate every "
    "number, pick the ones that matter; name the governing check and the ratio; "
    "if any check fails or there are warnings, say what failed and suggest one or "
    "two concrete next steps (heavier section, add bracing, reduce span); keep it "
    "under 220 words, three short paragraphs, no headings, no bullet points, no "
    "em dashes. Units: kips, kip-ft, inches, ksi."
)


def api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or _settings_key()


def _settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "BeamCheckDesk", "settings.json")


def _settings_key() -> str | None:
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            return json.load(f).get("anthropic_api_key") or None
    except (OSError, ValueError):
        return None


def save_api_key(key: str) -> None:
    path = _settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"anthropic_api_key": key.strip()}, f)


def template_narrative(summary: dict) -> str:
    g = summary["governing_check"]
    r = summary["governing_ratio"]
    verdict = "passes" if summary["passes"] else "does not pass"
    support = {
        "simple": "simply supported",
        "cantilever_left": "a cantilever fixed at the left end",
        "cantilever_right": "a cantilever fixed at the right end",
    }[summary["support"]]
    text = (
        f"The {summary['shape']} (Fy = {summary['fy_ksi']:g} ksi) is {support} over "
        f"{summary['length_ft']:g} ft and was checked by {summary['method']} using "
        f"{summary['strength_combo']}. The maximum moment is {summary['mu_kipft']:g} kip-ft "
        f"at {summary['x_at_mu_ft']:g} ft and the maximum shear is {summary['vu_kips']:g} kips.\n\n"
        f"Flexural strength is governed by {summary['flexure_governed_by']} with "
        f"Mn = {summary['mn_kipft']:g} kip-ft (Mp = {summary['mp_kipft']:g} kip-ft, "
        f"Lp = {summary['lp_ft']:g} ft, Lr = {summary['lr_ft']:g} ft, Lb = {summary['lb_ft']:g} ft). "
        f"Nominal shear strength is {summary['vn_kips']:g} kips. Live load deflection is "
        f"{summary['live_deflection_in']:g} in and total load deflection is "
        f"{summary['total_deflection_in']:g} in.\n\n"
        f"The member {verdict}. The governing check is {g} at a demand to capacity ratio of {r:g}."
    )
    if summary["warnings"]:
        text += " Warnings: " + " ".join(summary["warnings"])
    return text


def write_narrative(summary: dict, timeout: float = 30.0) -> tuple[str, str]:
    """Return (narrative, source) where source is 'claude' or 'template'."""
    key = api_key()
    if not key:
        return template_narrative(summary), "template"
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 600,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": "Beam check summary:\n" + json.dumps(summary, indent=1)}],
    }).encode()
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        text = "".join(block.get("text", "") for block in data.get("content", []))
        if text.strip():
            return text.strip(), "claude"
    except (urllib.error.URLError, ValueError, KeyError, OSError):
        pass
    return template_narrative(summary), "template"
