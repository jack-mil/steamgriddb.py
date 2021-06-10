import argparse
import json
import logging
import sys
from argparse import Namespace, RawDescriptionHelpFormatter as RawFormatter
from datetime import datetime
from typing import Dict, List
from urllib.parse import quote

import requests
from requests.api import request
from requests.models import Response

import config

LOG = logging.getLogger(__name__)

KEY = config.api_key
AUTH = {'Authorization': f'Bearer {KEY}'}

class ScriptError(Exception):
    ''' General exception class for this script '''


class Endpoints:
    top = 'https://www.steamgriddb.com/api/v2/'

    search = top + 'search/autocomplete/{query}'
    by_id = top + 'games/id/{game_id}'
    hero = top + 'heroes/game/{game_id}'
    grid = top + 'grids/game/{game_id}'
    logos = top + 'logos/game/{game_id}'
    icons = top + 'icons/game/{game_id}'


def _api_get(url: str, **kwargs) -> requests.Response:
    '''Requests GET wrapper'''
    r = requests.get(url, **kwargs)
    if r.status_code != requests.codes.ok:
        msg = f'Bad Request: HTTP Error {r.status_code}'
        LOG.debug(msg)
        raise ScriptError(msg)
    return r


def _print_data(data: Dict):
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


def _get_data_by_id(game_id: int) -> Dict:
    ''' Get game data by id '''
    path = Endpoints.by_id.format(game_id=game_id)
    LOG.debug(f'Retrieve by ID: {path}')
    return _api_get(path, headers=AUTH).json()


def _get_images_by_id(game_id: int, endpoint: str) -> Dict:
    '''General GET images json from any image endpoint'''
    path = endpoint.format(game_id=game_id)
    LOG.debug(f'Images by id: {path}')
    return _api_get(path, headers=AUTH).json()


def _auto_search(query: str, game_id=None) -> List[Dict]:
    '''
    Use API auto search to find game data
    param: url unescaped search query
    return: list of result dictionaries
    '''
    if game_id is not None:
        data = _get_data_by_id(game_id)
    else:
        query_escaped = quote(query)
        path = Endpoints.search.format(query=query_escaped)
        LOG.debug(f'Auto Search: {path}')
        data = _api_get(path, headers=AUTH).json()

    # Must return a list, even if one element
    if data['success']:
        return data['data'] if type(data['data']) is list else [data['data']]


def action_search(args: Namespace):
    '''
    Search the database for games

        {PROG_NAME} search Doom Eternal
        {PROG_NAME} search -i 5209479
    '''
    query = ' '.join(args.query)
    print(f'Searching steamDB for \"{query}\"...')

    results = _auto_search(query, args.game_id)
    # Print the first 4 results
    for game in results[:3]:
        _print_data(game)


def action_hero(args: Namespace):
    '''
    Download the first hero image for game id

        {PROG_NAME} hero Half Life 2
        {PROG_NAME} hero -i 2254
    '''
    if args.game_id is not None:
        game_id = args.game_id
    else:
        query = ' '.join(args.query)
        games = _auto_search(query)
        print('Found Game')
        _print_data(games[0])
        game_id = games[0]['id']

    images = _get_images_by_id(game_id, Endpoints.hero)
    images['data']
    for image in images['data']:
        print(f'{image["id"]}: {image["thumb"]}')

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
        '-d',
        action='store_true',
        help='Print debug info'
    )

    subparsers = parser.add_subparsers(help='Action to perform')

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        '-i', help='SteamGridDB ID to search for', dest='game_id', type=int)

    parent_parser.add_argument(
        'query',
        nargs='*',
        default=None,
        help='Search query. Ignored if -i is present'
    )

    # Search action
    parser_search = subparsers.add_parser('search',
                                          help='Search for games info based on string query',
                                          parents=[parent_parser],
                                          description=action_search.__doc__.format(
                                              PROG_NAME=progname),
                                          formatter_class=RawFormatter)
    parser_search.set_defaults(func=action_search)

    parser_hero = subparsers.add_parser('hero',
                                        help='Search for large banner background images',
                                        parents=[parent_parser],
                                        description=action_hero.__doc__.format(
                                            PROG_NAME=progname),
                                        formatter_class=RawFormatter)
    parser_hero.set_defaults(func=action_hero)

    # Parse args
    args = parser.parse_args()

    if args.debug:
        fmt = '%(levelname)s - %(name)s - ln %(lineno)s - %(message)s'
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
