import logging
import odoo
import threading
import time
import typer

from rich.console import Console
from rich.progress import (
    MofNCompleteColumn,
    Progress,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from typing_extensions import Annotated
from unittest import TestCase, TestResult
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

console = Console()
rerun_requested = False
rerun_requested_lock = threading.Lock()
to_repeat = []


class TestFileChangeHandler(FileSystemEventHandler):
    def __init__(self, rerun_tests, command):
        self.rerun_tests = rerun_tests
        self.command = command

    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            global rerun_requested
            with rerun_requested_lock:
                rerun_requested = True
            console.print(f"File changed: {event.src_path}.")
            console.print("Rerunning tests...")
            self.rerun_tests(self.command)


def _odoo_database_callback(ctx: typer.Context, value: str):
    if value == "":
        value = f"test_{ctx.params['module_name']}"
    return value


def cli(
    module_name: Annotated[str, typer.Argument()],
    module_path: Annotated[str, typer.Argument()],
    failfast: Annotated[bool, typer.Option()] = False,
    watch: Annotated[bool, typer.Option()] = False,
    failed_only: Annotated[bool, typer.Option()] = True,
    odoo_config: Annotated[str, typer.Option()] = "./config/odoo.conf",
    odoo_database: Annotated[str, typer.Option(callback=_odoo_database_callback)] = "",
    odoo_log_level: Annotated[str, typer.Option()] = "info",
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    if odoo_database == "":
        odoo_database = f"test_{module_name}"

    options = [f"--test-tags={module_name}", f"--config={odoo_config}"]
    for param_name, param_value in ctx.params.items():
        if param_name.startswith("odoo_"):
            options.append(f"--{param_name[5:].replace('_', '-')}={param_value}")

    logging.disable(logging.CRITICAL)
    odoo.tools.config.parse_config(options)

    odoo.service.server.start(preload=[], stop=True)

    from odoo.tests import loader
    from odoo.tests.tag_selector import TagsSelector
    from odoo.tests.suite import OdooSuite

    class ProgressOdooSuite(OdooSuite):
        def run(self, result, debug=False):
            global rerun_requested
            with rerun_requested_lock:
                rerun_requested = False
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
            ) as progress:
                task = progress.add_task("Test", total=self.countTestCases())
                for test in self:
                    with rerun_requested_lock:
                        if rerun_requested:
                            break
                    assert isinstance(test, (TestCase))
                    progress.console.print(f"Running {test}")
                    self._tearDownPreviousClass(test, result)
                    self._handleClassSetUp(test, result)
                    result._previousTestClass = test.__class__

                    if not test.__class__._classSetupFailed:
                        test(result)
                    progress.update(task, advance=1)

            self._tearDownPreviousClass(None, result)
            return result

    def make_suite(module_names, position="at_install"):
        """Creates a test suite for all the tests in the specified modules,
        filtered by the provided ``position`` and the current test tags

        :param list[str] module_names: modules to load tests from
        :param str position: "at_install" or "post_install"
        """

        config_tags = TagsSelector(odoo.tools.config["test_tags"])
        position_tag = TagsSelector(position)
        tests = (
            t
            for module_name in module_names
            for m in loader.get_test_modules(module_name)
            for t in loader.get_module_test_cases(m)
            if position_tag.check(t) and config_tags.check(t)
        )
        return ProgressOdooSuite(sorted(tests, key=lambda t: t.test_sequence))

    def run_tests(command):
        global to_repeat
        from odoo.modules import module

        module.current_test = True
        threading.current_thread().testing = True

        results = TestResult()
        if command == "f" and to_repeat:
            suite_failed = ProgressOdooSuite(to_repeat)
            suite_failed(results)
        else:
            suite = make_suite([module_name])
            suite(results)

        if len(results.errors) > 0:
            for error, traceback in results.errors:
                console.rule("[bold red]ERROR[/bold red]")
                console.print(f"[yellow]{error.id()}")
                console.print(traceback)
                console.rule()
        if len(results.failures) > 0:
            for failure, traceback in results.failures:
                console.rule("[bold red]FAILURE[/bold red]")
                console.print(f"[yellow]{failure.id()}")
                console.print(traceback)
                console.rule()
        error_tests = [error[0] for error in results.errors]
        failure_tests = [failure[0] for failure in results.failures]
        to_repeat = error_tests + failure_tests

        threading.current_thread().testing = False
        module.current_test = False

    command = "f" if failed_only else "a"
    if watch:
        event_handler = TestFileChangeHandler(run_tests, command)
        observer = Observer()
        observer.schedule(event_handler, path=module_path, recursive=True)
        observer.start()
        run_tests(command)
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break
        observer.join()
    else:
        run_tests(command)


def main():
    typer.run(cli)


if __name__ == "__main__":
    typer.run(cli)
