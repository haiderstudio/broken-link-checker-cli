# broken-link-checker-cli

Check links in Markdown and HTML docs against real pages — and tell page failures apart from anchor failures.

[![CI](https://github.com/hai02487/broken-link-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/hai02487/broken-link-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`broken-link-checker` scans `.md`, `.markdown`, and `.html` files for links and checks each one for real:

- Local links: the target file must exist. If the link has an anchor, the target Markdown heading (GitHub-style slug) or HTML `id`/`name` must exist too.
- Remote links: the URL must answer (HEAD, falling back to GET where a server refuses HEAD). If the link has an anchor, the fetched page must carry that `id` or `name`.
- Every result is one of three statuses, with the broken kind named: `BROKEN (page)` for a missing page, `BROKEN (anchor)` for a page that exists without that anchor. A link is never reported OK unless its check actually ran.
- Links inside fenced code blocks and inline code spans are ignored, so code samples never produce false failures.
- Exit code 0 means no broken links, 1 means at least one broken link, 2 means a usage error such as a missing path.

## What it does NOT do

- It does not guess. If an anchor cannot be checked (for example, an anchor on a PDF), the link is reported `SKIPPED` with the reason, never OK.
- It does not check `mailto:`, `tel:`, or other non-web schemes — those are reported `SKIPPED`, not broken.
- It does not follow JavaScript-rendered pages, log in to sites, or rewrite any file. It only reads and reports.
- It does not send your docs anywhere. Remote checks are plain requests to the linked URL itself; everything else runs locally.

## Who it is for

Anyone who maintains docs, a README collection, or a static site and wants a broken link caught before a reader finds it — in CI, or as a one-off check before publishing.

## Install

Python standard library only — no packages to download. Clone the repo and run it in place:

```sh
git clone https://github.com/hai02487/broken-link-checker-cli.git
cd broken-link-checker-cli
```

## Usage

Check a directory (scanned recursively) or individual files:

```sh
python3 src/broken_link_checker.py docs/
python3 src/broken_link_checker.py README.md docs/guide.md
```

Real output from the bundled examples (one link is deliberately broken):

```text
examples/sample-docs.md:3: other-page.md -> OK
examples/sample-docs.md:5: #sample-docs -> OK
examples/sample-docs.md:8: missing-page.md -> BROKEN (page) (file does not exist)
2 ok, 1 broken, 0 skipped
```

Useful flags:

```sh
# Skip remote checks entirely (local files only)
python3 src/broken_link_checker.py --local-only docs/

# Machine-readable output
python3 src/broken_link_checker.py --format json docs/

# Skip URLs matching a pattern (repeatable)
python3 src/broken_link_checker.py --exclude 'example\.com' docs/
```

## Examples

Check only local links in a docs folder, so the run works offline:

```sh
python3 src/broken_link_checker.py --local-only docs/
```

Check one file and get JSON for a CI step:

```sh
python3 src/broken_link_checker.py --format json README.md
```

Run the bundled example (expect 2 ok, 1 broken, exit code 1):

```sh
sh examples/run-example.sh
```

## How it is tested

```sh
python3 tests/test_broken_link_checker.py
```

The tests use only the standard library's `unittest`. Remote checks are exercised against a real HTTP server started by the tests on localhost — never against the public internet — covering a good page, a 404 page, a good anchor, and a missing anchor, plus local files, same-page anchors, skipped schemes, CLI exit codes, and JSON counts.

## Contributing

Small, focused improvements are welcome. Open an issue first for anything larger than a typo, keep the standard-library-only rule, and run the tests before opening a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE). This is original work, built fresh for this repo.
