# About
This repository hosts the Inside Books Project database web interface.
This interface is implemented using Flask and SQLAlchemy and includes the following features:
  - printing processing labels through the Dymo JS framework,
  - querying inmate data from the TDCJ and FBOP websites,
  - printing warnings and alerts for inmates,
  - printing shipment and request metrics.

# Installation
Installing and running this software requires several steps.
First, the Python and HTML/CSS/JS dependencies must be installed.


## Meeting Dependencies
All of the Python dependencies must be installed as given in `requirements.txt`.
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
Coming soon ...

## Initialization
Coming soon ...

# Deployment
Coming soon ...
