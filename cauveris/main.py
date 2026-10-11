"""
Main entry point for Cauveris backend.
"""

import argparse
import logging
import sys
import uvicorn
from cauveris.logging_config import setup_structured_logging, get_logger

logger = get_logger(__name__)


def setup_logging(debug: bool = False):
    """Setup structured JSON logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    setup_structured_logging(level=level, json_output=True)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Cauveris - Autonomous Reality Debugger")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Serve command (default)
    serve_parser = subparsers.add_parser("serve", help="Start the Cauveris API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind the server to")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind the server to")
    serve_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    # Export patch command
    export_parser = subparsers.add_parser(
        "export-patch", help="Export verified patch for direct import into infected space"
    )
    export_parser.add_argument(
        "--incident-id", required=True, help="Incident ID (must exist in evidence store)"
    )
    export_parser.add_argument(
        "--output-dir", default="./exported_patch", help="Output directory to save patch files"
    )

    # Apply patch command
    apply_parser = subparsers.add_parser(
        "apply-patch", help="Apply patch directly to infected space"
    )
    apply_parser.add_argument("patch_path", help="Path to apply_patch.py or fix.patch")
    apply_parser.add_argument(
        "--target", default=".", help="Target directory of the infected space"
    )
    apply_parser.add_argument(
        "--check", action="store_true", help="Verify patch applies cleanly without writing"
    )
    apply_parser.add_argument(
        "--rollback", action="store_true", help="Rollback applied patch using backup"
    )

    # Handle no command (default to serve)
    args = parser.parse_args()

    # If no command provided, default to serve
    if args.command is None:
        args.command = "serve"

        # Create a namespace with serve defaults
        class ServeArgs:
            def __init__(self):
                self.command = "serve"
                self.host = "0.0.0.0"
                self.port = 8000
                self.debug = False

        args = ServeArgs()
    elif args.command == "serve":
        pass  # Already have the right args
    elif args.command == "export-patch":
        from pathlib import Path
        import asyncio
        from cauveris.patch.generator import PatchGenerator
        from cauveris.simulation.runner import SimulationRunner
        from cauveris.sandbox.controller import SandboxController
        from cauveris.hypothesis.generator import HypothesisGenerator
        from cauveris.timeline.builder import TimelineBuilder
        from cauveris.ingestion.controller import IngestionController
        from cauveris.config import get_settings

        async def run_export():
            # Load real incident from evidence store
            settings = get_settings()
            evidence_path = Path(settings.evidence_store_path) / args.incident_id
            if not evidence_path.exists():
                # Also check common incident folder patterns
                for pattern in [
                    f"./incident-{args.incident_id}",
                    f"./incident-{args.incident_id.lower()}",
                ]:
                    p = Path(pattern)
                    if p.exists():
                        evidence_path = p
                        break

            if not evidence_path.exists():
                print(
                    f"Error: Incident {args.incident_id} not found in evidence store",
                    file=sys.stderr,
                )
                sys.exit(1)

            ingestion = IngestionController()
            try:
                incident = await ingestion.load_incident_from_store(args.incident_id, evidence_path)
            except Exception as e:
                print(f"Error: Failed to load incident from evidence store: {e}", file=sys.stderr)
                sys.exit(1)

            incident = await IngestionController().process(incident)
            incident = await TimelineBuilder().build(incident)
            hypotheses = await HypothesisGenerator().generate(incident)
            sandbox = SandboxController()
            experiments = await sandbox.plan_experiments(hypotheses)
            sim_experiments = await SimulationRunner().run_simulations(experiments)
            patches = await PatchGenerator().generate(sim_experiments)
            verified = [p for p in patches if "h1" in p.candidate_id or p.score > 0.8]
            target_patch = verified[0] if verified else patches[0]
            out_dir = Path(args.output_dir)
            results = PatchGenerator().export_patch(target_patch, out_dir)
            print(f"Exported patch for {target_patch.candidate_id} to {out_dir.resolve()}:")
            for k, p in results.items():
                print(f"  - {k}: {p}")

        asyncio.run(run_export())
        return
    elif args.command == "apply-patch":
        from pathlib import Path

        patch_file = Path(args.patch_path).resolve()
        if not patch_file.exists():
            print(f"Error: Patch file '{patch_file}' not found.", file=sys.stderr)
            sys.exit(1)
        scope: dict = {}
        with open(patch_file, "r", encoding="utf-8") as f:
            code = f.read()
        exec(code, scope)
        if args.rollback:
            fn = scope.get("rollback")
            if callable(fn):
                ok = fn(target_dir=args.target)
                sys.exit(0 if ok else 1)
        elif args.check:
            fn = scope.get("check")
            if callable(fn):
                ok = fn(target_dir=args.target)
                sys.exit(0 if ok else 1)
        else:
            fn = scope.get("apply")
            if callable(fn):
                ok = fn(target_dir=args.target)
                sys.exit(0 if ok else 1)
        return

    setup_logging()
    logger.info("Starting Cauveris backend")

    if args.debug:
        logger.setLevel(logging.DEBUG)

    # No golden incident auto-loading in production
    # Incidents are loaded from evidence store on demand via API

    uvicorn.run(
        "cauveris.api.main:app",
        host=args.host,
        port=args.port,
        reload=getattr(args, "debug", False),
        log_level="info",
    )


if __name__ == "__main__":
    main()
