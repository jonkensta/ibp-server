import urllib
import argparse
import itertools

from bs4 import BeautifulSoup


URL = 'https://www.tdcj.state.tx.us/death_row/dr_offenders_on_dr.html'


def process_last_name(last_name):
    return last_name.split(',', 1)[0]


def process_tdcj(tdcj):
    return '{:08d}'.format(int(tdcj))


def process_entry(entry):
    last_name = entry['Last Name']
    last_name = process_last_name(last_name)

    first_name = entry['First Name']

    if (',' in first_name) or (',' in last_name):
        msg = "Unexpected comma present in name"
        raise ValueError(msg)

    entry['Last Name'] = last_name
    entry['TDCJ Number'] = process_tdcj(entry['TDCJ Number'])

    return entry


def generate_entries():
    html = urllib.urlopen(URL).read()
    soup = BeautifulSoup(html, 'lxml')

    table = soup.find('table')
    rows = iter(table.findAll('tr'))
    keys = [key.text for key in next(rows).findAll('th')]

    for row in rows:
        values = [value.text for value in row.findAll('td')]
        entry = dict(zip(keys, values))
        yield entry


def main():
    desc = "Grab deathrow inmate information from TDCJ website."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('outfilename', help="Output CSV file")
    args = parser.parse_args()

    columns = ['Last Name', 'First Name', 'TDCJ Number']

    entries = generate_entries()
    entries = itertools.imap(process_entry, entries)

    with open(args.outfilename, 'w') as outfile:
        for entry in entries:
            line = ', '.join([entry[column] for column in columns]) + '\n'
            outfile.write(line)


if __name__ == '__main__':
    main()
