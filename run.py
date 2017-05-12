#!/usr/bin/env python

import ibp


def main():
    debug = ibp.config.getboolean('server', 'debug')
    host = ibp.config.get('server', 'interface')
    port = ibp.config.getint('server', 'port')
    ibp.app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    main()
