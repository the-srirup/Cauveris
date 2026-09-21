"""
Main entry point for Cauveris backend.
"""
import argparse
import logging
import sys
from cauveris.config import get_settings
import uvicorn

logger = logging.getLogger(__name__)


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("cauveris.log")
        ]
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Cauveris - Autonomous Reality Debugger")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Serve command (default)
    serve_parser = subparsers.add_parser("serve", help="Start the Cauveris API server")
    serve_parser.add_argument(
        "--host",
        default=get_settings().host,
        help="Host to bind the server to"
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=get_settings().port,
        help="Port to bind the server to"
    )
    serve_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )

    # Golden command
    golden_parser = subparsers.add_parser("golden", help="Load golden incident on startup")
    golden_parser.add_argument(
        "--host",
        default=get_settings().host,
        help="Host to bind the server to"
    )
    golden_parser.add_argument(
        "--port",
        type=int,
        default=get_settings().port,
        help="Port to bind the server to"
    )
    golden_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )

    # Handle no command (default to serve)
    args = parser.parse_args()

    # If no command provided, default to serve
    if args.command is None:
        args.command = "serve"
        # Create a namespace with serve defaults
        class ServeArgs:
            def __init__(self):
                self.host = get_settings().host
                self.port = get_settings().port
                self.debug = False
                self.golden = False
        args = ServeArgs()
    elif args.command == "serve":
        pass  # Already have the right args
    elif args.command == "golden":
        # For golden command, we'll load the incident and then serve
        pass

    setup_logging()
    logger.info("Starting Cauveris backend")

    if args.debug:
        logger.setLevel(logging.DEBUG)

    # If golden flag is set or command is golden, load the golden incident
    if getattr(args, 'golden', False) or args.command == "golden":
        logger.info("Loading golden incident on startup...")
        # Import here to avoid circular imports
        from cauveris.datasets.golden_incident import GoldenIncidentGenerator
        from cauveris.api.main import incidents
        generator = GoldenIncidentGenerator()
        incident = generator.generate()
        incidents[incident.id] = incident
        logger.info(f"Loaded golden incident {incident.id}")

    uvicorn.run(
        "cauveris.api.main:app",
        host=args.host,
        port=args.port,
        reload=getattr(args, 'debug', False),
        log_level="info"
    )


if __name__ == "__main__":
    main()
