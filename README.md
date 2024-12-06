# Odoo Test Loop

[![PyPI - Version](https://img.shields.io/pypi/v/odoo_test_loop.svg)](https://pypi.org/project/odoo_test_loop)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/odoo_test_loop.svg)](https://pypi.org/project/odoo_test_loop)

-----

Test your Odoo Module in a Test Loop. 
There is almost no overhead, as `Odoo Test Loop` uses the standard Odoo unittest test suites.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [License](#license)

## Features

-  Watch-Mode to automatically rerun tests on file changes
-  Failfast to stop testing on the first error
-  Full control of Odoo Log Level
-  Autoreload of the tested Module on code changes

## Installation

```console
pip install odoo-test-loop
```

## Usage

```console
 Usage: odoo_test_loop [OPTIONS] MODULE_NAME MODULE_PATH                                                          
                                                                                                                  
╭─ Arguments ────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    module_name      TEXT  Name of the module to test [default: None] [required]                                  │
│ *    module_path      TEXT  Path to the module to test [default: None] [required]                                  │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --failfast          --no-failfast             Stop test loop at the first failed test [default: no-failfast]       │
│ --watch             --no-watch                Rerun tests on file changes [default: no-watch]                      │
│ --failed-only       --no-failed-only          Run only failed tests after first loop [default: failed-only]        │
│ --odoo-config                           TEXT  Path to odoo config file [default: ./config/odoo.conf]               │
│ --odoo-database                         TEXT  Odoo Database name                                                   │
│ --odoo-log-level                        TEXT  Log Level for Odoo [default: warn]                                   │
│ --help                                        Show this message and exit.                                          │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## License

`odoo-test-loop` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
