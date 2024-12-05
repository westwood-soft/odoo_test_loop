import importlib
import logging
import odoo
import os
import sys
import threading
import time
import typer

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    MofNCompleteColumn,
    Progress,
    TextColumn,
    BarColumn,
    SpinnerColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from typing_extensions import Annotated
from unittest import TestCase, TestResult
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

console = Console()
rerun_requested = False
rerun_requested_lock = threading.Lock()
reload_odoo_module = False
to_repeat = []


class TestFileChangeHandler(FileSystemEventHandler):
    def __init__(self, rerun_tests, command, delay=5):
        self.rerun_tests = rerun_tests
        self.command = command
        self.delay = delay
        self.last_event_time = 0

    def on_modified(self, event):
        global reload_odoo_module
        if event.src_path.endswith(".py"):
            console.print(f"File changed: {event.src_path}.")
            filename_with_ext = os.path.basename(event.src_path)
            filename, _ = os.path.splitext(filename_with_ext)
            if not filename.startswith("test_"):
                reload_odoo_module = True
            modules = [name for name in sys.modules if name.endswith("." + filename)]
            for module in modules:
                console.print(f"Reloading module {module}.")
                importlib.reload(sys.modules[module])
            current_time = time.time()
            if current_time - self.last_event_time <= self.delay:
                return
            global rerun_requested
            global rerun_requested_lock
            with rerun_requested_lock:
                rerun_requested = True

            self.last_event_time = current_time
        elif event.src_path.endswith(".xml"):
            console.print(f"File changed: {event.src_path}.")
            reload_odoo_module = True


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
    odoo_log_level: Annotated[str, typer.Option()] = "warn",
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    if odoo_database == "":
        odoo_database = f"test_{module_name}"

    options = [f"--config={odoo_config}"]
    for param_name, param_value in ctx.params.items():
        if param_name.startswith("odoo_"):
            options.append(f"--{param_name[5:].replace('_', '-')}={param_value}")

    odoo.tools.config.parse_config(options)

    logging.disable(logging.CRITICAL)
    from odoo.tests import loader
    from odoo.tests.tag_selector import TagsSelector
    from odoo.tests.suite import OdooSuite

    logging.disable(logging.NOTSET)

    class ProgressOdooSuite(OdooSuite):
        def run(self, result, debug=False):
            global rerun_requested
            with rerun_requested_lock:
                rerun_requested = False
            with Progress(
                TextColumn(":person_standing:"),
                BarColumn(),
                TextColumn(":person_running:"),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                auto_refresh=False,
            ) as progress:
                task = progress.add_task("Testing", total=self.countTestCases())
                for test in self:
                    with rerun_requested_lock:
                        if rerun_requested:
                            break
                    assert isinstance(test, (TestCase))
                    progress.console.print(
                        f"[yellow]{test._testMethodName}[/yellow] from [yellow]{test.test_class}[/yellow]"
                    )
                    self._tearDownPreviousClass(test, result)
                    self._handleClassSetUp(test, result)
                    result._previousTestClass = test.__class__

                    if not test.__class__._classSetupFailed:
                        test(result)
                    progress.update(task, advance=1)
                    progress.refresh()
                    if failfast and not result.wasSuccessful():
                        break

            self._tearDownPreviousClass(None, result)
            return result

    def make_suite(module_names, position="at_install", include_tests=[]):
        """Creates a test suite for all the tests in the specified modules,
        filtered by the provided ``position`` and the current test tags

        :param list[str] module_names: modules to load tests from
        :param str position: "at_install" or "post_install"
        :param list[str] include_tests: specific tests to include
        """

        config_tags = TagsSelector(module_name)
        position_tag = TagsSelector(position)
        tests = (
            t
            for module_name in module_names
            for m in loader.get_test_modules(module_name)
            for t in loader.get_module_test_cases(m)
            if position_tag.check(t) and config_tags.check(t)
        )
        if include_tests:
            tests = [t for t in tests if t.id() in include_tests]
        return ProgressOdooSuite(sorted(tests, key=lambda t: t.test_sequence))

    odoo.service.server.start(preload=[], stop=True)

    def run_tests(command):
        global to_repeat
        global reload_odoo_module

        from odoo.modules import module

        if reload_odoo_module:
            console.print()
            with Progress(
                TextColumn(f"Reinstall module {module_name}."), SpinnerColumn()
            ) as progress:
                progress.add_task("Reinstall")
                with odoo.modules.registry.Registry(odoo_database).cursor() as cr:
                    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
                    up_module = env["ir.module.module"].search(
                        [("name", "=", module_name)]
                    )
                    up_module.button_immediate_upgrade()
            reload_odoo_module = False

        module.current_test = True
        threading.current_thread().testing = True

        results = TestResult()
        if command == "f" and to_repeat:
            suite_failed = make_suite(
                [module_name], include_tests=[test.id() for test in to_repeat]
            )
            suite_failed(results)
            if not results.errors and not results.failures:
                suite = make_suite([module_name])
                results = TestResult()
                suite(results)
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

        if results.wasSuccessful():
            console.print(
                Panel.fit(
                    "[bold green]All tests passed![/bold green]",
                    title="Success :rocket:",
                )
            )
        else:
            console.print(
                Panel.fit(
                    f"[bold red]{len(results.errors)} Errors.[/bold red]\n[bold red]{len(results.failures)} Failures.[/bold red]",
                    title="Failures :person_facepalming:",
                )
            )

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
                global rerun_requested
                if rerun_requested:
                    time.sleep(1)
                    run_tests(command)
            except KeyboardInterrupt:
                break
        observer.join()
    else:
        run_tests(command)


def main():
    typer.run(cli)


if __name__ == "__main__":
    typer.run(cli)
