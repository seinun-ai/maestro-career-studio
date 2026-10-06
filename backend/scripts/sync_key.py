"""Make, show or locate the sync key: `python -m scripts.sync_key create|show|path`.

Run it from backend/ (native installs: with the same environment the backend runs under, so
it names the same file), or in Docker: `docker compose exec backend python -m scripts.sync_key
create`. Only `show` ever prints the key.
"""

import argparse
import sys

from app.services.sync import status

_SHOW_HELP = (
    "Print the key. This is for your own terminal: copy it into your password vault once, "
    "never into a chat, a ticket or a shell history."
)


def _create() -> int:
    try:
        path = status.create_key()
    except FileExistsError:
        print(f"A sync key already exists at {status.key_path()}; "
              "delete it yourself first if you mean to replace it.", file=sys.stderr)
        return 1
    except OSError:
        print(f"Cannot write the sync key at {status.key_path()}; check that folder's permissions.",
              file=sys.stderr)
        return 1
    print(path)
    return 0


def _show() -> int:
    key = status.read_key()
    if key is None:
        print(f"No sync key at {status.key_path()}; run `create` first.", file=sys.stderr)
        return 1
    print(key)
    return 0


def _path() -> int:
    print(status.key_path())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.sync_key", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="Write a new key (refuses to overwrite) and print only its path.")
    commands.add_parser("show", help=_SHOW_HELP, description=_SHOW_HELP)
    commands.add_parser("path", help="Print where the key lives, whether or not it exists yet.")
    command = parser.parse_args(argv).command
    return {"create": _create, "show": _show, "path": _path}[command]()


if __name__ == "__main__":
    raise SystemExit(main())
