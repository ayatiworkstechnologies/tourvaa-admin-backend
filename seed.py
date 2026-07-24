"""Compatibility seed entrypoint.

Run from the backend root:

    python seed.py
    python seed.py --production
"""

from scripts.reset_seed_admin_rbac import main


if __name__ == "__main__":
    main()
