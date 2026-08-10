"""Out-of-process, bounded, network-isolated Typst compilation plus the shared
comment/string-aware Typst source scanner.

Kept import-light (stdlib + a lazy ``import typst``) so a spawned child
re-imports only this leaf module, never the heavier render stack. Two hardening
concerns live here because the in-process ``typst.compile()`` has neither:

* No wall-clock cap. A pathological template (deep layout, huge loop) pins a
  worker forever; the pdflatex branch bounds its subprocess at 60s. We run the
  compile in a terminable ``spawn`` subprocess with a join-timeout and kill it.
* ``@preview/*`` imports resolve over the NETWORK, downloading and executing
  third-party (LLM / user authored) code at render time. We FAIL CLOSED by
  rejecting any package import in the source before compiling. Empty
  ``package_path`` / ``package_cache_path`` do NOT prevent the fetch in typst
  0.15.0 (verified: the cache dir is populated from the network), so an empty
  dir is only defense in depth, never the gate.
"""

from __future__ import annotations

import multiprocessing
import re
import tempfile
from pathlib import Path

# Matches the pdflatex subprocess wall-clock cap (compile_pdf timeout=60).
TYPST_COMPILE_TIMEOUT_S: float = 60.0


def strip_typst_comments(source: str) -> str:
    """Remove Typst comments while preserving string literals verbatim.

    A small hand scanner, not a regex: it never treats ``//`` or ``/*`` inside a
    ``"double-quoted string"`` as a comment, and it counts nesting so
    ``/* /* */ */`` is fully removed. String contents (including any ``//`` such
    as an ``https://`` URL, or a ``/*``) are kept, so a token that legitimately
    appears inside a string still reads as live template code. Shared by the
    package-import gate below and by the capability scans (extras / fmt keys) so
    a token in a comment is never miscredited and a ``//`` inside a string never
    hard-rejects a working template.
    """
    out: list[str] = []
    i, n = 0, len(source)
    in_string = False
    block_depth = 0
    while i < n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(nxt)  # escape: copy the escaped char verbatim
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if block_depth > 0:
            if c == "/" and nxt == "*":
                block_depth += 1
                i += 2
            elif c == "*" and nxt == "/":
                block_depth -= 1
                i += 2
            else:
                i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
        elif c == "/" and nxt == "/":
            while i < n and source[i] != "\n":
                i += 1  # drop to end of line; the newline itself is kept
        elif c == "/" and nxt == "*":
            block_depth += 1
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


# A package import is ``import``/``include`` of an ``@namespace/name`` string
# literal (``@preview/...``, ``@local/...``). Plain file imports (``"header.typ"``)
# are NOT packages and stay allowed; they are confined to the per-render staging
# root (see pdf_render._compile_typst_file).
_PACKAGE_IMPORT_RE = re.compile(r'\b(?:import|include)\s+"\s*@')


def source_imports_package(source: str) -> bool:
    """True if the comment-stripped source imports a Typst package (``@...``)."""
    return bool(_PACKAGE_IMPORT_RE.search(strip_typst_comments(source)))


def _worker(conn, kwargs) -> None:
    try:
        import typst

        typst.compile(**kwargs)
        conn.send(("ok", ""))
    except BaseException as exc:  # noqa: BLE001 -- ship the diagnostic back
        # TypstError.diagnostic carries the full LOCATED rendering
        # ("error: <msg>\n  ..- file:line:col ..."); str(exc) is only the bare
        # message. Prefer the located form so callers surface file:line:col.
        diag = getattr(exc, "diagnostic", None) or str(exc)
        conn.send(("err", str(diag)[-4000:]))
    finally:
        conn.close()


def run_typst_compile(
    *,
    input: str,
    output: str,
    root: str,
    font_paths: list[str],
    sys_inputs: dict[str, str],
    package_dir: str,
    timeout: float | None = None,
) -> None:
    """Compile ``input`` -> ``output`` out of process with a wall-clock bound.

    Raises ``RuntimeError("typst failed\\n...")`` on any failure, matching the
    pdflatex branch's error contract; the message carries typst's located
    diagnostic (file:line:col) when available, or a timeout notice."""
    if timeout is None:
        timeout = TYPST_COMPILE_TIMEOUT_S
    kwargs = {
        "input": input,
        "output": output,
        "root": root,
        "font_paths": font_paths,
        # ONLY the fonts we ship. typst scans the machine's system fonts by
        # default and merges them with font_paths, so the same resume could
        # render with different glyphs on different machines — which is the one
        # thing a tool whose selling point is reproducible output must not do.
        #
        # Not theoretical: CI installs texlive-fonts-extra, which puts a second
        # XCharter on the box, and the emphasis role resolved to a different
        # face there than it does on a laptop without it. The vendored set in
        # app/assets/fonts/xcharter carries the four faces the templates need
        # (Roman, Bold, Italic, BoldItalic) and deliberately NOT the Slanted
        # obliques — see that directory's README: two faces claiming the same
        # family and italic bit let filesystem order decide the letterforms.
        #
        # Consequence worth knowing: a USER template naming a font we do not
        # vendor now fails loudly instead of silently substituting. That is the
        # better failure — silent substitution is how a resume goes out in a
        # typeface its author never saw. To support more families, vendor them
        # and extend settings.typst_font_paths.
        "ignore_system_fonts": True,
        "sys_inputs": sys_inputs,
        # Defense in depth only (the package gate already rejected @-imports):
        # point package resolution at an empty dir so nothing local resolves.
        "package_path": package_dir,
        "package_cache_path": package_dir,
    }
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe()
    proc = ctx.Process(target=_worker, args=(child_conn, kwargs), daemon=True)
    proc.start()
    child_conn.close()  # only the child writes; the parent reads
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        raise RuntimeError(
            "typst failed\n"
            f"compile exceeded the {timeout:g}s time limit and was terminated"
        )
    status, payload = "err", "compiler exited without a result"
    if parent_conn.poll():
        status, payload = parent_conn.recv()
    if status != "ok":
        raise RuntimeError(f"typst failed\n{payload}")


def compile_typst(
    *,
    source: str,
    input_name: str,
    output: Path,
    font_paths: list[str],
    sys_inputs: dict[str, str],
    timeout: float | None = None,
) -> None:
    """Fail-closed, root-scoped, bounded compile of ``source`` to ``output``.

    Stages ``source`` alone in a fresh temp dir used as the typst ``root`` so a
    template's ``read()`` / file ``import`` cannot reach sibling renders' sources
    (base resumes share one ``tex/`` dir); rejects package imports up front; and
    runs the compile out of process with a wall-clock cap. ``output`` may live
    outside ``root`` (writes are not root-confined)."""
    if source_imports_package(source):
        raise RuntimeError(
            "typst failed\nremote package imports (@preview/...) are not allowed"
        )
    with tempfile.TemporaryDirectory() as staging:
        staging_dir = Path(staging)
        staged = staging_dir / input_name
        staged.write_text(source, encoding="utf-8")
        pkg_dir = staging_dir / "_no_packages"
        pkg_dir.mkdir()
        run_typst_compile(
            input=str(staged),
            output=str(output),
            root=str(staging_dir),
            font_paths=font_paths,
            sys_inputs=sys_inputs,
            package_dir=str(pkg_dir),
            timeout=timeout,
        )
