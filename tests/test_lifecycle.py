"""Actual official general hook, persistent settings and listener lifecycle.

These tests open temporary loopback ports only. They never install the plugin
into, or connect to, an operating BookOasis server.
"""
from contextlib import contextmanager
import socket
import time
from types import SimpleNamespace
import urllib.request


def wait_until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("Listener did not reach the expected state before the deadline")


def free_port():
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


def settings(bookcase, port, enabled=True):
    gateway = bookcase.provider.get_db_gateway("general")
    gateway.set_plugin_config("audiobook_opds", {"service_enabled": enabled,
                              "bind_host": "127.0.0.1", "port": port})
    return gateway


def get_catalog(bookcase, port):
    request = urllib.request.Request(f"http://127.0.0.1:{port}/opds", headers=bookcase.auth())
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        assert b"Allowed library" in response.read()


@contextmanager
def started(bookcase, plugin, monkeypatch):
    monkeypatch.setattr(plugin, "_SUPERVISOR", None)
    began = time.monotonic()
    bookcase.provider.start_background_service("general")
    elapsed = time.monotonic() - began
    supervisor = plugin._SUPERVISOR
    try:
        assert elapsed < 0.5, "Official startup hook must return without blocking"
        assert supervisor.thread.is_alive()
        yield supervisor
    finally:
        supervisor.stop()
        assert not supervisor.thread.is_alive()
        assert supervisor.server is None


def test_general_hook_starts_once_and_plugin_disable_closes_listener(bookcase, plugin, monkeypatch):
    port = free_port()
    gateway = settings(bookcase, port)
    gateway.set_setting("PLUGIN_ENABLED_audiobook_opds", "true")
    with started(bookcase, plugin, monkeypatch) as supervisor:
        wait_until(lambda: supervisor.server is not None)
        get_catalog(bookcase, port)
        bookcase.provider.start_background_service("general")
        assert plugin._SUPERVISOR is supervisor
        assert plugin._SUPERVISOR.thread is supervisor.thread
        gateway.set_setting("PLUGIN_ENABLED_audiobook_opds", "false")
        wait_until(lambda: supervisor.server is None)
        assert supervisor.thread.is_alive()


def test_changed_port_and_service_config_are_applied_by_poll(bookcase, plugin, monkeypatch):
    original_port = free_port()
    settings(bookcase, original_port)
    with started(bookcase, plugin, monkeypatch) as supervisor:
        wait_until(lambda: supervisor.server is not None)
        get_catalog(bookcase, original_port)
        replacement_port = free_port()
        settings(bookcase, replacement_port)
        wait_until(lambda: supervisor.server is not None and
                   supervisor.server.server_address[1] == replacement_port)
        get_catalog(bookcase, replacement_port)
        settings(bookcase, replacement_port, enabled=False)
        wait_until(lambda: supervisor.server is None)
        assert supervisor.thread.is_alive()


def test_occupied_port_is_retried_after_release(bookcase, plugin, monkeypatch):
    reservation = socket.socket()
    reservation.bind(("127.0.0.1", 0))
    reservation.listen()
    port = reservation.getsockname()[1]
    settings(bookcase, port)
    try:
        with started(bookcase, plugin, monkeypatch) as supervisor:
            wait_until(lambda: supervisor.last_problem is not None)
            assert supervisor.thread.is_alive()
            assert supervisor.server is None
            reservation.close()
            wait_until(lambda: supervisor.server is not None)
            get_catalog(bookcase, port)
            assert supervisor.last_problem is None
    finally:
        reservation.close()


def test_worker_start_failure_cleans_unstarted_listener_without_shutdown_deadlock(plugin, monkeypatch):
    gateway = SimpleNamespace(get_setting=lambda *args: None)
    provider = SimpleNamespace(get_plugin_config=lambda *args, **kwargs: {
        "service_enabled": True, "bind_host": "127.0.0.1", "port": 25931},
        get_db_gateway=lambda *args: gateway)
    supervisor = plugin._Supervisor(provider)
    state = {"closed": False, "error": None}

    class Server:
        def __init__(self, *args):
            pass

        def serve_forever(self):
            pass

        def shutdown(self):
            raise AssertionError("shutdown before serve_forever starts would deadlock")

        def server_close(self):
            state["closed"] = True

    class Worker:
        ident = None

        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("simulated thread creation failure")

        def is_alive(self):
            return False

        def join(self, **kwargs):
            raise AssertionError("An unstarted worker cannot be joined")

    def problem(error):
        state["error"] = error
        supervisor.stop_event.set()

    monkeypatch.setattr(plugin, "_LimitedServer", Server)
    monkeypatch.setattr(plugin.threading, "Thread", Worker)
    monkeypatch.setattr(supervisor, "problem", problem)
    supervisor.run()
    assert isinstance(state["error"], RuntimeError)
    assert state["closed"]
    assert supervisor.server is None
    assert supervisor.worker is None
