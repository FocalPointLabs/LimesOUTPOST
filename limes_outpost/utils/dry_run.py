import os


def dry_run_enabled() -> bool:
    """Returns True if the system is running in dry run mode.

    Reads the DRY_RUN environment variable (set in .env).
    Defaults to True if the variable is not set — this is intentional.
    An unset DRY_RUN should never result in live API calls and unexpected costs.

    Usage in agents:
        from limes_outpost.utils.dry_run import dry_run_enabled

        if dry_run_enabled():
            return self.dry_run(...)
        return self.live_run(...)

    .env values:
        DRY_RUN=True   -> dry run (mock APIs, no cost)
        DRY_RUN=False  -> live (real API calls, real cost)
    """
    return os.getenv("DRY_RUN", "True").lower() != "false"