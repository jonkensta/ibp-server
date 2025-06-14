# About

This repository hosts the Inside Books Project database web interface.
This interface is implemented using Flask and SQLAlchemy and includes the following features:

- printing processing labels through the Dymo JS framework,
- querying inmate data from the TDCJ and FBOP websites,
- printing warnings and alerts for inmates,
- printing shipment and request metrics,
- logging in through Google your google account.

# Installation

Installing and running this software requires several steps.
First, you must clone this repository with submodules.
Then, the Python and HTML/CSS/JS dependencies must be installed.
Finally, you must configure the application and initialize the database.

## Meeting Dependencies

All of the Python dependencies must be installed as given in [the requirements file](requirements.txt).
It is recommended that these be installed in a virtual environment.

```bash
pip install -r requirements.txt
```

The above command requires that the python package manager `pip` is installed.

Next, from the root directory, install the static HTML/CSS/JS dependencies as follows:

```bash
cd ibp/static
npm install
```

The above command requires that the javascript package manager `npm` is installed.

## Configuration

Next, you will need to set the configuration for your [development](conf/dev.conf) or [production](conf/production.conf) configuration files.
To do this, set both the `secret_key` and `apikey` variables in the `[server]` section to distinct passwords that you keep secret.

## Initialization

Finally, you will need to initialize the database and create an authorized user.
This is done using Python as follows:

```python
import ibp
ibp.db.create_all()
```

# Development

After going through each of the installation steps,
you can run the server in development mode on your local machine by doing the following:

```bash
FLASK_ENV=development python -m ibp
```

By default, this will load the interface on [localhost port 8000](http://localhost:8000).

## Dev tools

Install optional development dependencies using `uv`:

```bash
uv pip install .[dev]
```

This provides the `format`, `lint`, and `typecheck` commands for running
Black, Pylint, and Mypy against the `ibp` package:

```bash
format       # run Black
lint         # run Pylint
typecheck    # run Mypy
```
