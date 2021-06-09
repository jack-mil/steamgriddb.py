import argparse
import json
import logging
import sys
import textwrap
from argparse import RawDescriptionHelpFormatter as RawFormatter
from datetime import datetime
from typing import Dict
from urllib.parse import quote

import requests
from requests.models import Response

import config

LOG = logging.getLogger(__name__)

KEY = config.api_key
API = config.api_endpoint

AUTH = {'Authorization': f'Bearer {KEY}'}


class ScriptError(Exception):
    ''' General exception class for this script '''


def _format_data(data: Dict):

    date = '.'
    if 'release_date' in data:
        date = datetime.utcfromtimestamp(
            int(data['release_date'])).strftime('%m-%Y')

    data['release_date'] = date
    data['types'] = ', '.join(data['types'])

    s = '''
        Title: {name}
        Released: {release_date}
        ID: {id}
        Stores: {types}
        Verified: {verified}
    '''.format(**data)
    print(s)


def action_search(args):
    '''
    Search the database for games

        {PROG_NAME} search "Doom Eternal"
    '''
    query = ' '.join(args.query)
    print(f'Searching steamDB for \"{query}\"...')
    query_escaped = quote(query)
    path = API + f'/search/autocomplete/{query_escaped}'

    LOG.debug(f'Using URL: {path}')

    r = requests.get(path, headers=AUTH)

    if r.status_code != requests.codes.ok:
        msg = f'Bad Request: HTTP Error {r.status_code}'
        LOG.debug(msg)
        raise ScriptError(msg)

    data = r.json()
    if data['success'] and len(data['data']):
        for game in data['data'][:3]:
            _format_data(game)
    else:
        print(f'No results found for {query}')
    with open('result.json', 'w+') as f:
        f.write(r.text)


def action_hero(args):
    '''
    Download the first hero image for game id

        {PROG_NAME} hero <id>
    '''
    print(f'Downloading hero for title {args.id}')


def interactive():
    pass


def main():
    '''Entrypoint'''
    progname = sys.argv[0]
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Global options
    parser.add_argument(
        '--debug',
        '-v',
        action='store_true',
        help='Print debug info'
    )

    subparsers = parser.add_subparsers()

    # Search action
    parser_search = subparsers.add_parser('search',
                                          description=action_search.__doc__.format(
                                              PROG_NAME=progname),
                                          formatter_class=RawFormatter)
    parser_search.set_defaults(func=action_search)
    parser_search.add_argument(
        'query',
        nargs='+',
        help='Search query (can have spaces)'
    )

    parser_hero = subparsers.add_parser('hero',
                                        description=action_hero.__doc__.format(
                                            PROG_NAME=progname),
                                        formatter_class=RawFormatter)
    parser_hero.set_defaults(func=action_hero)
    parser_hero.add_argument(
        'id',
        help='SteamDB ID of title to search for'
    )

    # Parse args
    args = parser.parse_args()

    if args.debug:
        fmt = 'ln %(lineno)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=fmt)

    if hasattr(args, 'func'):
        try:
            return args.func(args)
        except ScriptError as e:
            print(e)
    else:
        return interactive()


if __name__ == '__main__':
    try:
        main()
    except ScriptError as e:
        print(f'Error: {e}')
        sys.exit(1)
