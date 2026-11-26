#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # The checkout CLI supports the family pilot. Hosted containers set their
    # settings explicitly, and requesting non-development mode selects them too.
    local = os.environ.get("GARDEN_LOCAL_PILOT") == "1" or os.environ.get("GARDEN_DEV", "1") == "1"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "garden.local_settings" if local else "garden.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
