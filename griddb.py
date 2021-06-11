"""
Library and command line tool to grab artwork
from Steamgriddb.com using their api
"""
# Standard Library imports
import argparse
import json
import logging
import sys
from argparse import Namespace, RawDescriptionHelpFormatter as RawFormatter
from datetime import datetime
from typing import Dict, List, Literal
from urllib.parse import quote
import os
from pathlib import Path
import re
import textwrap
from enum import Enum, auto

# Third party imports
import requests

# Local application imports
import config

LOG = logging.getLogger(__name__)

KEY = config.api_key
AUTH = {'Authorization': f'Bearer {KEY}'}


class ScriptError(Exception):
    ''' General exception class for this script '''


class Artwork(Enum):
    GRID = 'grids'
    HERO = 'hereos'
    LOGO = 'logos'
    ICON = 'icons'


class Endpoint:
    ''' API endpoints, use .format() to specify arguments '''
    _top = 'https://www.steamgriddb.com/api/v2/'

    @staticmethod
    def artwork_path(game_id: int, type: Artwork):
        return Endpoint._top + f'{type.value}/game/{game_id}'

    @staticmethod
    def search_path(query: str):
        return Endpoint._top + f'search/autocomplete/{query}'

    @staticmethod
    def search_path_id(game_id: int):
        return Endpoint._top + f'games/id/{game_id}'


def _requests_get(url: str, **kwargs) -> requests.Response:
    '''Requests GET wrapper'''
    r = requests.get(url, **kwargs)
    if r.status_code != 200:
        if r.status_code == 401:
            msg = f'Unauthorized API request: HTTP Error {r.status_code}\n' + \
                'Did you generate an API key from your account?\n' + \
                'https://www.steamgriddb.com/profile/preferences'
        elif r.status_code == 404:
            msg = f'Requested page was not found: HTTP Error {r.status_code}\n' + \
                f'{r.url}'
        else:
            msg = f'HTTP Error: {r.status_code}'
        LOG.debug(msg)
        raise ScriptError(msg)
    return r


def _create_directory(game_id: str, type: Artwork, title=None) -> str:
    '''Create directory tree for game id and optional title'''
    if title is None:
        directory = f'images/{game_id}/{type.value}/'
    else:
        # Sanitize title, replace everything but letter. numbers or - _ with _
        title = re.sub(r'[^\w\-_]+', '_', title)
        directory = f'images/{title}-{game_id}/{type.value}/'
    dir = Path(directory)
    if not dir.exists():
        os.makedirs(dir)
    return directory


def _get_data_by_id(game_id: int) -> Dict:
    ''' Get game data by id '''
    path = Endpoint.search_path_id(game_id)
    LOG.debug(f'Retrieve by ID: {path}')
    return _requests_get(path, headers=AUTH).json()


def _print_data(data: Dict):
    '''Pretty print json response data'''
    date = '.'
    if 'release_date' in data:
        date = datetime.utcfromtimestamp(
            int(data['release_date'])).strftime('%m-%Y')

    data['release_date'] = date
    data['types'] = ', '.join(data['types'])

    # Escape newlines and format text
    s = '''\
    Title: {name}
    Released: {release_date}
    ID: {id}
    Stores: {types}
    Verified: {verified}\
    '''.format(**data)
    print(s)


def _get_json_images(game_id: int, type: Artwork, filters: Dict) -> Dict:
    '''GET json response of artwork from specified endpoint and parameters'''
    path = Endpoint.artwork_path(game_id, type)
    LOG.debug(f'Images by id: {path}')
    return _requests_get(path, headers=AUTH, params=filters).json()


def _auto_search(query: List[str], game_id=None) -> List[Dict]:
    '''
    Use API auto search to find game data
    query: list of strings to form query
    return: list of result dictionaries
    '''
    if game_id is not None:
        data = _get_data_by_id(game_id)
    else:
        if not query:
            raise ScriptError('Please specify a search query or id')
        query = ' '.join(query)
        print(f'Searching steamDB for \"{query}\"...')

        query_escaped = quote(query)
        path = Endpoint.search_path(query_escaped)
        LOG.debug(f'Auto Search: {path}')
        data = _requests_get(path, headers=AUTH).json()

    # Must return a list, even if one element
    if data['success']:
        return data['data'] if type(data['data']) is list else [data['data']]


def _download_images(
        artwork: Artwork,
        query: List[str] = None,
        game_id: int = None,
        thumb: bool = False,
        nsfw: Literal['true', 'false', 'any'] = 'false',
        types: Literal['any', 'animated', 'static'] = 'any',
        count: int = 5, **kwargs):

    if type(query) is str:
        query = query.split()

    title = None
    if game_id is None:
        # Only use the first result
        game = _auto_search(query)[0]
        print('Found Game')
        _print_data(game)
        game_id = game['id']
        title = game['name']
    else:
        game_id = game_id

    # Ensure valid filters
    if types not in ('static', 'animated', 'any'):
        raise ScriptError(f'Unsupported style filter: {types}' +
                          '(supported values \"static\", \"animated\", \"any\".')
    if types == 'any':
        types = None

    if nsfw not in ('true', 'false', 'any'):
        raise ScriptError(f'Unsupported nsfw filter: {nsfw}' +
                          '(supported values \"true\", \"false\", \"any\".')
    if nsfw == 'any':
        nsfw = None

    # requests params payload will not be sent if values are none
    payload = {'nsfw': nsfw, 'types': types}

    images = _get_json_images(game_id, artwork, filters=payload)

    if len(images['data']) <= 0:
        print(f'No artwork found for {game_id}: {title}')
        return

    print(
        f'Found {len(images["data"])} images, downloading {count if count else "all"}')

    directory = _create_directory(game_id, artwork, title)

    link = 'thumb' if thumb else 'url'
    for image in images['data'][:count]:
        image_url = image[link]
        file_name = directory + '{game_id}-{score}-{id}-{nsfw}{ext}'.format(
            ext=Path(image_url).suffix,
            game_id=game_id,
            **image)

        r = _requests_get(image['thumb'])
        with open(file_name, 'wb') as img_f:
            img_f.write(r.content)
            print(file_name)


def action_search(args: Namespace):
    '''
    Search the database for games
        e.g.
        {PROG_NAME} search Doom Eternal
        {PROG_NAME} search -i 5209479
    '''
    results = _auto_search(args.query, args.game_id)
    # Print the first 4 results
    print(f'Showing {args.count} of {len(results)} results')
    for i, game in enumerate(results[:args.count]):
        print(f'{i+1}:')
        _print_data(game)


def action_hero(args: Namespace):
    '''
    Download Steam background "hero" artwork for games
        e.g.
        {PROG_NAME} hero --nsfw=false -c3 The Witcher 3
        {PROG_NAME} hero -i 2254 -t --types=static
    '''
    _download_images(Artwork.HERO, **vars(args))


def action_grid(args: Namespace):
    '''
    Download Steam grid artwork for games
        e.g.
        {PROG_NAME} grid --count 3 Ori
        {PROG_NAME} grid -i 34744 -t --types=static
    '''
    _download_images(Artwork.GRID, **vars(args))


def action_icon(args: Namespace):
    '''
    Download icons for games
        e.g.
        {PROG_NAME} icon --count 3 Terraria
        {PROG_NAME} icon -i 38365 --types=static
    '''
    _download_images(Artwork.ICON, **vars(args))


def action_logo(args: Namespace):
    '''
    Download logos for games
        e.g.
        {PROG_NAME} logo --count 3 Bioshock
        {PROG_NAME} logo -i 24166 --types=static
    '''
    _download_images(Artwork.LOGO, **vars(args))


def interactive():
    pass


def _parse_args(argv: List[str]) -> Namespace:
    ''' Setup extensive argument parsing '''

    # Seperate program and rest of args
    progname, *argv = argv

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Global options
    parser.add_argument(
        '--debug',
        '-d',
        action='store_true',
        help='Print debug info'
    )

    subparsers = parser.add_subparsers(help='Action to perform', required=True)

    # Common options for all actions
    common_parser_1 = argparse.ArgumentParser(add_help=False)
    common_parser_1.add_argument(
        'query',
        nargs='*',
        default=None,
        help='Search query. Ignored if -i is present'
    )
    common_parser_1.add_argument(
        '-i', help='SteamGridDB ID to search for', dest='game_id', type=int)

    common_parser_1.add_argument(
        '--count', '-c',
        type=int,
        default=3,
        help='Number of results to display (default: %(default)s)'
    )

    # Search action
    parser_search = subparsers.add_parser('search',
                                          help='Search for games info based on string query',
                                          parents=[common_parser_1],
                                          description=action_search.__doc__.format(
                                              PROG_NAME=progname),
                                          formatter_class=RawFormatter)
    parser_search.set_defaults(func=action_search)

    # Common options for artwork download actions
    common_parser_2 = argparse.ArgumentParser(add_help=False)
    common_parser_2.add_argument(
        '--thumb', '-t',
        action='store_true',
        help='Download low res thumbnails only'
    )
    common_parser_2.add_argument(
        '--nsfw',
        choices=['false', 'true', 'any'],
        default='false',
        help='True to only include nsfw, (default: %(default)s)'
    )
    common_parser_2.add_argument(
        '--types',
        choices=['static', 'animated', 'any'],
        default='any',
        help='Filter static or animated artwork (default: both)'
    )

    # Artwork actions
    parser_hero = subparsers.add_parser('hero',
                                        help='Search for large banner background artwork',
                                        parents=[common_parser_1,
                                                 common_parser_2],
                                        description=action_hero.__doc__.format(
                                            PROG_NAME=progname),
                                        formatter_class=RawFormatter)
    parser_hero.set_defaults(func=action_hero)
    parser_grid = subparsers.add_parser('grid',
                                        help='Search for grid artwork',
                                        parents=[common_parser_1,
                                                 common_parser_2],
                                        description=action_grid.__doc__.format(
                                            PROG_NAME=progname),
                                        formatter_class=RawFormatter)
    parser_grid.set_defaults(func=action_grid)
    parser_icon = subparsers.add_parser('icon',
                                        help='Search for icons',
                                        parents=[common_parser_1,
                                                 common_parser_2],
                                        description=action_icon.__doc__.format(
                                            PROG_NAME=progname),
                                        formatter_class=RawFormatter)
    parser_icon.set_defaults(func=action_icon)
    parser_logo = subparsers.add_parser('logo',
                                        help='Search for logos',
                                        parents=[common_parser_1,
                                                 common_parser_2],
                                        description=action_logo.__doc__.format(
                                            PROG_NAME=progname),
                                        formatter_class=RawFormatter)
    parser_logo.set_defaults(func=action_logo)

    if len(argv) == 0:
        parser.print_help()
        parser.exit()
    return parser.parse_args(argv)


def main():
    '''Entrypoint'''

    args = _parse_args(sys.argv)

    # Setup debugging
    if args.debug:
        fmt = '%(levelname)s - %(name)s - ln %(lineno)s - %(message)s'
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=fmt)

    if hasattr(args, 'func'):
        return args.func(args)
    else:
        return interactive()


if __name__ == '__main__':
    try:
        main()
    except ScriptError as e:
        print(f'Error: {e}')
        sys.exit(1)
else:
    print(f'{__name__} is intended to be run directly from the command line',
          'try',
          f'\t$python {__name__}.py --help',
          'for more info',
          sep='\n')
    raise ImportWarning
