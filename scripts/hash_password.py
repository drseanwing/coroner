#!/usr/bin/env python
"""
Password Hashing Utility

Generate bcrypt password hashes for the admin dashboard.

Usage:
    python scripts/hash_password.py [password] [--raw]

If no password is provided, you'll be prompted to enter one.

Options:
    --raw    Output raw bcrypt hash without docker-compose escaping.
             By default, $ characters are escaped as $$ for docker-compose
             compatibility in .env files.

Example:
    python scripts/hash_password.py mypassword
    # Output: $$2b$$12$$...  (docker-compose compatible)

    python scripts/hash_password.py mypassword --raw
    # Output: $2b$12$...  (raw bcrypt hash)
"""

import sys
import bcrypt


def main():
    """Generate a bcrypt hash for a password."""
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    raw_mode = "--raw" in sys.argv

    if args:
        password = args[0]
    else:
        password = input("Password: ")

    if not password:
        print("Error: Password cannot be empty", file=sys.stderr)
        sys.exit(1)

    # Generate bcrypt hash
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    hash_str = hashed.decode("utf-8")

    if raw_mode:
        # Output raw bcrypt hash
        print(hash_str)
    else:
        # Escape $ as $$ for docker-compose compatibility
        escaped_hash = hash_str.replace("$", "$$")
        print(escaped_hash)


if __name__ == "__main__":
    main()
