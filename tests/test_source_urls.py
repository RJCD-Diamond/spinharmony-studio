"""Tests for :mod:`spinharmony_studio.source_urls`."""

from spinharmony_studio.source_urls import (
    SCATTY_DOWNLOAD_URL,
    SPINTERACT_DOWNLOAD_URL,
    SPINVERT_DOWNLOAD_URL,
)


def test_urls_are_icloud_share_links():
    for url in (SCATTY_DOWNLOAD_URL, SPINVERT_DOWNLOAD_URL, SPINTERACT_DOWNLOAD_URL):
        assert url.startswith("https://www.icloud.com/iclouddrive/")
