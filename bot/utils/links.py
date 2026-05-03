from __future__ import annotations

from html import escape

_TONSCAN = "https://tonscan.org"


def address_url(address: str) -> str:
    """Raw TonScan URL for an address."""
    return f"{_TONSCAN}/address/{address}"


def tx_url(tx_hash: str) -> str:
    """Raw TonScan URL for a transaction."""
    return f"{_TONSCAN}/tx/{tx_hash}"


def address_link(address: str) -> str:
    """Full address shown as clickable TonScan link.

    Display text = full address (copyable).
    href         = tonscan.org/address/...
    """
    url = address_url(address)
    return f'<a href="{url}">{escape(address)}</a>'


def tx_link(tx_hash: str) -> str:
    """Full hash shown as clickable TonScan link.

    Display text = full hash (copyable).
    href         = tonscan.org/tx/...
    """
    url = tx_url(tx_hash)
    return f'<a href="{url}">{escape(tx_hash)}</a>'


def address_url_link(address: str) -> str:
    """The TonScan URL itself shown as clickable text (for alert messages).

    Display text = https://tonscan.org/address/...
    """
    url = address_url(address)
    return f'<a href="{url}">{url}</a>'


def tx_url_link(tx_hash: str) -> str:
    """The TonScan TX URL itself shown as clickable text.

    Display text = https://tonscan.org/tx/...
    """
    url = tx_url(tx_hash)
    return f'<a href="{url}">{url}</a>'
