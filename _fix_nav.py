"""Apply the single-panel navigation fix (Issue 2) across controllers.

The stacking bug: each loadX() only hid #skill-tree + its own view, so other
open panels stayed visible underneath. Fix: replace the per-controller
hide/show lines with a single window.ensureSinglePanelVisible('<view-id>')
call (defined in dashboard.js) which hides ALL panels first, then shows the
target - so navigating replaces the view instead of stacking.
"""
from pathlib import Path

BASE = Path("core/static/core/js")

# (file, view_id) - the two-line hide/show block is identical in all of these.
LOAD_FILES = [
    ("recovery.js", "recovery-view"),
    ("boss.js", "boss-view"),
    ("nutrition.js", "nutrition-view"),
    ("hydration.js", "hydration-view"),
    ("endurance.js", "endurance-view"),
    ("strength.js", "strength-view"),
]

OLD_LOAD = (
    "        if (tree) tree.classList.add('hidden');\n"
    "        view.classList.remove('hidden');\n"
)


def repl_load(content, view_id):
    new_block = (
        "        // Single-panel navigation: hide ALL panels, then show only this panel.\n"
        "        window.ensureSinglePanelVisible('" + view_id + "');\n"
    )
    return content.replace(OLD_LOAD, new_block), OLD_LOAD in content


reports = []
for fname, view_id in LOAD_FILES:
    p = BASE / fname
    content = p.read_text(encoding="utf-8")
    new_content, changed = repl_load(content, view_id)
    if changed:
        p.write_text(new_content, encoding="utf-8")
    reports.append((fname, "load", changed))

# leagues.js: backToLeaguesPlan + loadLeagues + remove local hideOtherPanels.
lp = BASE / "leagues.js"
content = lp.read_text(encoding="utf-8")

old_back = (
    "    window.backToLeaguesPlan = function () {\n"
    "        var view = document.getElementById('leagues-view');\n"
    "        if (view) view.classList.add('hidden');\n"
    "        var tree = document.getElementById('skill-tree');\n"
    "        if (tree) tree.classList.remove('hidden');\n"
    "    };\n"
)
new_back = (
    "    window.backToLeaguesPlan = function () {\n"
    "        var view = document.getElementById('leagues-view');\n"
    "        if (view) view.classList.add('hidden');\n"
    "        // Single-panel navigation: hide ALL panels, then show only the skill tree.\n"
    "        window.ensureSinglePanelVisible('skill-tree');\n"
    "    };\n"
)
changed_back = old_back in content
content = content.replace(old_back, new_back)

old_load = (
    "        hideOtherPanels();\n"
    "        view.classList.remove('hidden');\n"
)
new_load = (
    "        // Single-panel navigation: hide ALL panels, then show only leagues.\n"
    "        window.ensureSinglePanelVisible('leagues-view');\n"
)
changed_load = old_load in content
content = content.replace(old_load, new_load)

# Remove the now-unused local hideOtherPanels() (dashboard.js provides the global).
lines = content.splitlines(keepends=True)
out = []
skip = False
for i, ln in enumerate(lines):
    if "function hideOtherPanels() {" in ln:
        skip = True
        continue
    if skip:
        # stop skipping at the closing "}" at the prior indent of the function body.
        stripped = ln.strip()
        if stripped.startswith("}"):
            skip = False
            # also drop a following blank line
            continue
        continue
    out.append(ln)
removed_hide = len(out) < len(lines)
content = "".join(out)
lp.write_text(content, encoding="utf-8")
reports.append(("leagues.js", "back", changed_back))
reports.append(("leagues.js", "load", changed_load))
reports.append(("leagues.js", "hideOtherPanels removed", removed_hide))

# badges.js: backToBadgesPlan + loadBadges.
bp = BASE / "badges.js"
content = bp.read_text(encoding="utf-8")

old_back = (
    "    window.backToBadgesPlan = function () {\n"
    "        var view = document.getElementById('badges-view');\n"
    "        if (view) view.classList.add('hidden');\n"
    "        var tree = document.getElementById('skill-tree');\n"
    "        if (tree) tree.classList.remove('hidden');\n"
    "        var hint = document.getElementById('loading-hint');\n"
    "        if (hint) hint.classList.add('hidden');\n"
    "    };\n"
)
new_back = (
    "    window.backToBadgesPlan = function () {\n"
    "        var view = document.getElementById('badges-view');\n"
    "        if (view) view.classList.add('hidden');\n"
    "        var hint = document.getElementById('loading-hint');\n"
    "        if (hint) hint.classList.add('hidden');\n"
    "        // Single-panel navigation: hide ALL panels, then show only the skill tree.\n"
    "        window.ensureSinglePanelVisible('skill-tree');\n"
    "    };\n"
)
changed_back = old_back in content
content = content.replace(old_back, new_back)
_, changed_load = repl_load(content, "badges-view")
content = content if changed_load else repl_load(content, "badges-view")[0]
bp.write_text(content, encoding="utf-8")
reports.append(("badges.js", "back", changed_back))
reports.append(("badges.js", "load", changed_load))

for r in reports:
    print(f"{r[0]:16} {r[1]:22} {'OK' if r[2] else 'MISS'}")
