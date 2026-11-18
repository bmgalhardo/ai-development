"""The read-only issue board."""

import click

from ..core.settings import Settings


@click.command()
@click.option("--host", help="bind address (default: OVERMIND_DASHBOARD_HOST, else this host only)")
@click.option("--port", type=int, help="port (default: OVERMIND_DASHBOARD_PORT, else 8765)")
def dashboard(host, port):
    """Serve the read-only issue board; it never starts or touches workers."""
    settings = Settings.load()
    try:
        import uvicorn

        from ..dashboard.app import create_app
    except ImportError:
        raise click.ClickException(
            "The dashboard needs Overmind's dashboard extra: install overmind[dashboard], "
            "or run it through tools/overmind.sh dashboard") from None
    uvicorn.run(create_app(settings.root), host=host or settings.dashboard_host,
                port=port or settings.dashboard_port)
