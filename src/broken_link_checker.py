#!/usr/bin/env python3
"""Check links in Markdown and HTML docs.

Usage:
    python3 src/broken_link_checker.py docs/
    python3 src/broken_link_checker.py README.md docs/guide.md
    python3 src/broken_link_checker.py --local-only docs/
    python3 src/broken_link_checker.py --format json docs/

For every link it reports one of OK, BROKEN, or SKIPPED, and it
distinguishes the two broken kinds: a page that does not exist
(page) versus a page that exists but has no such anchor (anchor).
A link is never reported OK unless the check for it actually ran.

Python standard library only. Nothing is uploaded anywhere; remote
checks are plain HEAD/GET requests to the linked URL itself.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")
HTML_LINK_RE = re.compile(
    r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE
)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
SKIP_SCHEMES = {"mailto", "tel", "data", "javascript"}
CHECKABLE_SUFFIXES = {".md", ".markdown", ".html", ".htm"}


def slugify(text):
    """GitHub-style heading anchor: lowercase, punctuation stripped."""
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^a-z0-9 _-]", "", text)
    return re.sub(r"\s+", "-", text).strip("-")


def strip_code(text):
    """Remove fenced code blocks and inline code spans before scanning."""
    out = []
    in_fence = False
    fence = ""
    for line in text.splitlines():
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence = False
            # Keep the line count identical so reported line numbers match
            # the original document.
            out.append("")
            continue
        if in_fence:
            out.append("")
        else:
            out.append(re.sub(r"`[^`]*`", "", line))
    return "\n".join(out)


def extract_links(text, is_html=False):
    """Return [(line_number, target)] in document order."""
    found = []
    if is_html:
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in HTML_LINK_RE.finditer(line):
                found.append((lineno, match.group(1)))
        return found
    clean = strip_code(text)
    for lineno, line in enumerate(clean.splitlines(), 1):
        for match in LINK_RE.finditer(line):
            found.append((lineno, match.group(2)))
        for match in AUTOLINK_RE.finditer(line):
            found.append((lineno, match.group(1)))
    return found


def headings_of_markdown(text):
    anchors = set()
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            anchors.add(slugify(match.group(1)))
    return anchors


def anchors_of_html(text):
    ids = set(re.findall(r"""id\s*=\s*["']([^"']+)["']""", text, re.IGNORECASE))
    ids |= set(re.findall(r"""name\s*=\s*["']([^"']+)["']""", text, re.IGNORECASE))
    return ids


def fetch(url, timeout, method="HEAD"):
    request = urllib.request.Request(url, method=method)
    request.add_header("User-Agent", "broken-link-checker-cli/1.0")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


def check_remote(url, fragment, timeout):
    try:
        status, _ = fetch(url, timeout, "HEAD")
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403, 404, 405, 410, 501):
            # Some servers refuse HEAD; a GET is the real verdict.
            try:
                status, body = fetch(url, timeout, "GET")
            except urllib.error.HTTPError as err:
                return "BROKEN", "page", f"HTTP {err.code}"
            except Exception as err:  # network failure, not a page verdict
                return "BROKEN", "page", str(err)
        else:
            return "BROKEN", "page", f"HTTP {exc.code}"
    except Exception as err:
        return "BROKEN", "page", str(err)
    if status >= 400:
        return "BROKEN", "page", f"HTTP {status}"
    if not fragment:
        return "OK", "", ""
    try:
        _, body = fetch(url, timeout, "GET")
    except Exception as err:
        return "BROKEN", "page", str(err)
    text = body.decode("utf-8", "ignore")
    if fragment in anchors_of_html(text):
        return "OK", "", ""
    return "BROKEN", "anchor", f"no id or name '{fragment}' on page"


def check_local(source_file, target, fragment, timeout):
    base = source_file.parent
    path = (base / urllib.parse.unquote(target)).resolve()
    if not path.exists():
        return "BROKEN", "page", "file does not exist"
    if not fragment:
        return "OK", "", ""
    if path.suffix.lower() not in CHECKABLE_SUFFIXES:
        return "SKIPPED", "", "anchor cannot be checked in this file type"
    text = path.read_text(encoding="utf-8", errors="ignore")
    anchors = (
        headings_of_markdown(text)
        if path.suffix.lower() in (".md", ".markdown")
        else anchors_of_html(text)
    )
    if fragment in anchors:
        return "OK", "", ""
    return "BROKEN", "anchor", f"no heading or id '{fragment}' in file"


def check_link(source_file, target, timeout, local_only=False):
    """Return (status, kind, detail) for one link target."""
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme in SKIP_SCHEMES:
        return "SKIPPED", "", f"{parsed.scheme} link, not checked"
    if not parsed.scheme and not parsed.path and parsed.fragment:
        # Same-page anchor: check it against the source file itself.
        return check_local(source_file, source_file.name, parsed.fragment, timeout)
    if parsed.scheme in ("http", "https"):
        if local_only:
            return "SKIPPED", "", "remote check skipped with --local-only"
        url = urllib.parse.urlunparse(parsed._replace(fragment=""))
        return check_remote(url, parsed.fragment, timeout)
    if parsed.scheme:
        return "SKIPPED", "", f"unsupported scheme '{parsed.scheme}'"
    return check_local(source_file, parsed.path, parsed.fragment, timeout)


def collect_files(paths):
    files = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(
                sorted(
                    p
                    for p in path.rglob("*")
                    if p.is_file()
                    and p.suffix.lower() in CHECKABLE_SUFFIXES
                )
            )
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"no such file or directory: {raw}")
    return files


def check_files(files, timeout=10, local_only=False, exclude=()):
    results = []
    for source in files:
        text = source.read_text(encoding="utf-8", errors="ignore")
        is_html = source.suffix.lower() in (".html", ".htm")
        for lineno, target in extract_links(text, is_html=is_html):
            if any(re.search(pattern, target) for pattern in exclude):
                results.append(
                    {
                        "file": str(source),
                        "line": lineno,
                        "url": target,
                        "status": "SKIPPED",
                        "kind": "",
                        "detail": "excluded",
                    }
                )
                continue
            status, kind, detail = check_link(
                source, target, timeout, local_only=local_only
            )
            results.append(
                {
                    "file": str(source),
                    "line": lineno,
                    "url": target,
                    "status": status,
                    "kind": kind,
                    "detail": detail,
                }
            )
    return results


def summarize(results):
    counts = {"OK": 0, "BROKEN": 0, "SKIPPED": 0}
    for item in results:
        counts[item["status"]] += 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check links in Markdown and HTML docs."
    )
    parser.add_argument("paths", nargs="+", help="files or directories to check")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument(
        "--local-only", action="store_true", help="skip http(s) links"
    )
    parser.add_argument(
        "--exclude", action="append", default=[], help="regex: skip matching URLs"
    )
    args = parser.parse_args(argv)
    try:
        files = collect_files(args.paths)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    results = check_files(
        files,
        timeout=args.timeout,
        local_only=args.local_only,
        exclude=args.exclude,
    )
    counts = summarize(results)
    if args.format == "json":
        print(json.dumps({"counts": counts, "results": results}, indent=2))
    else:
        for item in results:
            line = f"{item['file']}:{item['line']}: {item['url']} -> {item['status']}"
            if item["kind"]:
                line += f" ({item['kind']})"
            if item["detail"]:
                line += f" ({item['detail']})"
            print(line)
        print(
            f"{counts['OK']} ok, {counts['BROKEN']} broken, "
            f"{counts['SKIPPED']} skipped"
        )
    return 1 if counts["BROKEN"] else 0


if __name__ == "__main__":
    sys.exit(main())
