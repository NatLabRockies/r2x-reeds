"""Build the public ReEDS API pages and member navigation from Python source."""

from __future__ import annotations

import ast
import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/r2x_reeds"
PAGES = ROOT / "docs/src/content/docs/reference/api"
NAVIGATION = ROOT / "docs/src/generated/api-sidebar.json"
FRAGMENTS = ROOT / "docs/public/api-fragments.json"


def public_names() -> list[str]:
    """Read root exports without importing the package or its dependencies."""
    module = ast.parse((SOURCE / "__init__.py").read_text())
    exports = next(
        node.value
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
    )
    return [name for name in ast.literal_eval(exports) if not name.startswith("_")]


def generate() -> None:
    """Generate pages for exports and registered transform functions/configs."""
    definitions: dict[str, tuple[Path, ast.ClassDef | ast.FunctionDef | ast.Assign]] = {}
    for path in sorted(SOURCE.rglob("*.py")):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                definitions[node.name] = (path, node)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        definitions[target.id] = (path, node)
    names = public_names()
    registration = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["entry-points"]
    for target in registration["r2x.transforms"].values():
        function = target.split(":")[1]
        names.append(function)
        node = definitions[function][1]
        assert isinstance(node, ast.FunctionDef)
        annotation = node.args.args[1].annotation
        assert annotation is not None
        names.append(ast.unparse(annotation))
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    base = f"https://github.com/NatLabRockies/r2x-reeds/blob/{revision}"
    PAGES.mkdir(parents=True, exist_ok=True)
    NAVIGATION.parent.mkdir(parents=True, exist_ok=True)
    expected_pages = {name.lower().replace("_", "-") + ".md" for name in names}
    for stale in PAGES.glob("*.md"):
        if stale.name not in expected_pages:
            stale.unlink()
    sidebar: list[dict[str, object]] = []
    fragments = {"module-r2x_reeds": "/r2x-reeds/reference/python-api/"}
    for name in sorted(set(names)):
        path, node = definitions[name]
        slug = name.lower().replace("_", "-")
        route = f"/reference/api/{slug}/"
        lines = [
            f"---\ntitle: {name}\neditUrl: false\n---\n",
            f"[Source]({base}/{path.relative_to(ROOT)}#L{node.lineno})\n",
        ]
        members: list[dict[str, str]] = [{"label": "Overview", "link": route}]
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            doc = ast.get_docstring(node)
            if doc:
                lines.append(doc.split("\n\n")[0] + "\n")
        module = ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)
        import_module = "r2x_reeds" if name in public_names() else module
        lines += [
            "## Import\n",
            f"```python doctest\n>>> from {import_module} import {name}\n>>> assert {name} is not None\n```\n",
        ]
        if isinstance(node, ast.ClassDef):
            base_links = []
            for parent in node.bases:
                label = ast.unparse(parent)
                parent_name = ast.unparse(parent.value) if isinstance(parent, ast.Subscript) else label
                if parent_name in names:
                    parent_slug = parent_name.lower().replace("_", "-")
                    base_links.append(f"[`{label}`](/r2x-reeds/reference/api/{parent_slug}/)")
                else:
                    base_links.append(f"`{label}`")
            bases = ", ".join(base_links)
            lines.append(f"Bases: {bases}. Inherited contracts remain defined by the base classes.\n")
            fields = [child for child in node.body if isinstance(child, ast.AnnAssign)]
            enum_values = [
                child
                for child in node.body
                if isinstance(child, ast.Assign)
                and any(
                    ast.unparse(parent) in {"Enum", "StrEnum", "IntEnum", "Flag", "IntFlag"}
                    for parent in node.bases
                )
                and all(
                    isinstance(target, ast.Name) and not target.id.startswith("_") for target in child.targets
                )
            ]
            if enum_values:
                lines.append("## Enum values\n")
            for value in enum_values:
                for target in value.targets:
                    value_name = ast.unparse(target)
                    lines += [f"### {value_name}\n", f"```text\n{ast.unparse(value)}\n```\n"]
                    members.append({"label": value_name, "link": route + "#" + value_name.lower()})
            methods = [
                child
                for child in node.body
                if isinstance(child, ast.FunctionDef) and not child.name.startswith("_")
            ]
            if fields:
                lines.append(
                    "## Declared fields\n\nThese fields are declared on this class. Required/default behavior is shown directly from source. Base-class fields also apply.\n"
                )
            for field in fields:
                field_name = ast.unparse(field.target)
                lines += [f"### {field_name}\n", f"```text\n{ast.unparse(field)}\n```\n"]
                members.append({"label": field_name, "link": route + "#" + field_name})
            if methods:
                lines.append("## Declared methods and properties\n")
            for method in methods:
                decorators = "".join(f"@{ast.unparse(item)}\n" for item in method.decorator_list)
                lines += [
                    f"### {method.name}\n",
                    f"[Source]({base}/{path.relative_to(ROOT)}#L{method.lineno})\n",
                    f"```text\n{decorators}{method.name}({ast.unparse(method.args)}) -> {ast.unparse(method.returns) if method.returns else 'unspecified'}\n```\n",
                ]
                if method_doc := ast.get_docstring(method):
                    lines.append(method_doc.split("\n\n")[0] + "\n")
                members.append({"label": method.name, "link": route + "#" + method.name})
        elif isinstance(node, ast.FunctionDef):
            lines += [
                "## Signature\n",
                f"```text\n{name}({ast.unparse(node.args)}) -> {ast.unparse(node.returns) if node.returns else 'unspecified'}\n```\n",
            ]
        else:
            lines += ["## Definition\n", f"```text\n{ast.unparse(node)}\n```\n"]
        lines.append(
            "Continue with the [Python API overview](/r2x-reeds/reference/python-api/) and [transform contracts](/r2x-reeds/reference/transforms/).\n"
        )
        prefixes = {"r2x_reeds", module}
        if module.startswith("r2x_reeds.models."):
            prefixes.add("r2x_reeds.models")
        for prefix in prefixes:
            fragments[f"{prefix}.{name}"] = "/r2x-reeds" + route
            for member in members[1:]:
                fragments[f"{prefix}.{name}.{member['label']}"] = "/r2x-reeds" + member["link"]
        (PAGES / f"{slug}.md").write_text("\n".join(lines))
        sidebar.append({"label": name, "collapsed": True, "items": members})
    for prefix in ("r2x_reeds", "r2x_reeds.parser"):
        fragments[f"{prefix}.ReEDSParser.run"] = "/r2x-reeds/reference/python-api/#parser-and-configuration"
    FRAGMENTS.write_text(json.dumps(fragments, indent=2) + "\n")
    NAVIGATION.write_text(json.dumps(sidebar, indent=2) + "\n")
    print(f"Generated {len(sidebar)} public API pages and their member navigation")


if __name__ == "__main__":
    generate()
