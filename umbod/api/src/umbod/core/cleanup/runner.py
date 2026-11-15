import asyncio

from umbod.core.diagnostics import ApplicationFailure, NoFailureContext, report_application_failure
from umbod.core.signals import SignalPublisher

from .ports import CleanupJob


class CleanupRunner:
    def __init__(
        self, jobs: tuple[CleanupJob, ...], timeout_seconds: float,
        application_failures: SignalPublisher[ApplicationFailure],
    ) -> None:
        self._jobs = jobs
        self._timeout_seconds = timeout_seconds
        self._application_failures = application_failures

    async def run(self) -> bool:
        succeeded = True
        for job in self._jobs:
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    await job.run()
            except Exception as error:
                report_application_failure(
                    self._application_failures, job.failure_kind, error, NoFailureContext(),
                )
                succeeded = False
        return succeeded
