#!/usr/bin/env python
"""
Password Hashing Utility

Generate bcrypt password hashes for the admin dashboard.

Usage:
    python scripts/hash_password.py [password]

If no password is provided, you'll be prompted to enter one.

Example:
    python scripts/hash_password.py mypassword
    # Output: $2b$12$...
"""

import sys
import bcrypt


def main():
    """Generate a bcrypt hash for a password."""
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = input("Password: ")

    if not password:
        print("Error: Password cannot be empty", file=sys.stderr)
        sys.exit(1)

    # Generate bcrypt hash
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    # Print the hash
    print(hashed.decode("utf-8"))


if __name__ == "__main__":
    main()
