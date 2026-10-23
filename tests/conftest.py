"""The unit tests never touch the network: any outbound socket connection fails the test that tried it."""
import socket

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(self, *a, **k):
        raise AssertionError('a unit test tried to open a network connection: %r' % (a,))
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
