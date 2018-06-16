#!/usr/bin/env python

import argparse

import ibp


def main():
    """Run the IBP development server."""

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default='8000')
    args = parser.parse_args()

    ibp.app.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
