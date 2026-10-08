"""HTTPS for the app and its updater.

Python checks servers against a list of trusted certificates taken from the
machine it was built on. A packaged Mac app does not find that list on a
volunteer's Mac, so every request would fail certificate checks. certifi's list
is added on top of whatever the system provides, wherever the app runs.
"""
import ssl
import urllib.request

import certifi

CONTEXT = ssl.create_default_context()
CONTEXT.load_verify_locations(certifi.where())


def urlopen(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout, context=CONTEXT)
