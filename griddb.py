import argparse
import json
import logging
import sys
from argparse import Namespace, RawDescriptionHelpFormatter as RawFormatter
from datetime import datetime
from typing import Dict, List
from urllib.parse import quote
import os
from pathlib import Path
import re

import requests

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


def _create_directory(game_id: str, title=None) -> str:
    '''Create directory tree for game id and optional title'''
    if title is None:
        directory = f'images/{game_id}/heroes/'
    else:
        # Sanitize title, replace everything but letter. numbers or - _ with _
        title = re.sub(r'[^\w\-_]+', '_', title)
        directory = f'images/{title}-{game_id}/heroes/'
    dir = Path(directory)
    if not dir.exists():
        os.makedirs(dir)
    return directory


def _get_data_by_id(game_id: int) -> Dict:
    ''' Get game data by id '''
    path = Endpoints.by_id.format(game_id=game_id)
    LOG.debug(f'Retrieve by ID: {path}')
    return _api_get(path, headers=AUTH).json()


def _print_data(data: Dict):
    '''Pretty print json response data'''
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


def _get_images_by_id(game_id: int, endpoint: str, params: Dict) -> Dict:
    '''GET json response of artwork from specified endpoint and parameters'''
    path = endpoint.format(game_id=game_id)
    LOG.debug(f'Images by id: {path}')
    return _api_get(path, headers=AUTH, params=params).json()


def _auto_search(query: List[str], game_id=None) -> List[Dict]:
    '''
    Use API auto search to find game data
    param: query list of strings to form query
    return: list of result dictionaries
    '''
    if game_id is not None:
        data = _get_data_by_id(game_id)
    else:
        if len(query) == 0:
            raise ScriptError('Please specify a search query or id')
        query = ' '.join(query)
        print(f'Searching steamDB for \"{query}\"...')

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
    results = _auto_search(args.query, args.game_id)
    # Print the first 4 results
    for game in results[:3]:
        _print_data(game)


def action_hero(args: Namespace):
    '''
    Download Steam background "hero" artwork for games

        {PROG_NAME} hero --nsfw=false --count 3 The Witcher 3
        {PROG_NAME} hero -i 2254 -t --types=static
    '''
    title = None
    if args.game_id is None:
        # Only use the first result
        game = _auto_search(args.query)[0]
        print('Found Game')
        _print_data(game)
        game_id = game['id']
        title = game['name']
    else:
        game_id = args.game_id

    payload = {'nsfw': args.nsfw, 'types': args.types}

    images = _get_images_by_id(game_id, Endpoints.hero, params=payload)

    if len(images['data']) <= 0:
        print(f'No images found for {game_id}: {title}')
        return
    directory = _create_directory(game_id, title)
    print(
        f'Found {len(images["data"])} images, downloading {args.count if args.count else "all"}')

    type = 'thumb' if args.thumb else 'url'
    for image in images['data'][:args.count]:
        image_url = image[type]
        file_name = directory + '{game_id}-{score}-{id}-{nsfw}{ext}'.format(
            ext=Path(image_url).suffix,
            game_id=game_id,
            **image)

        r = requests.get(image['thumb'])
        with open(file_name, 'wb') as img_f:
            img_f.write(r.content)
            print(file_name)


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

    subparsers = parser.add_subparsers(help='Action to perform', required=True)

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        'query',
        nargs='*',
        default=None,
        help='Search query. Ignored if -i is present'
    )
    parent_parser.add_argument(
        '-i', help='SteamGridDB ID to search for', dest='game_id', type=int)

    # Search action
    parser_search = subparsers.add_parser('search',
                                          help='Search for games info based on string query',
                                          parents=[parent_parser],
                                          description=action_search.__doc__.format(
                                              PROG_NAME=progname),
                                          formatter_class=RawFormatter)
    parser_search.set_defaults(func=action_search)

    parent_image_parser = argparse.ArgumentParser(add_help=False)
    parent_image_parser.add_argument(
        '--thumb', '-t',
        action='store_true',
        help='Download low res thumbnails only'
    )
    parent_image_parser.add_argument(
        '--nsfw',
        choices=['false', 'true', 'any'],
        default='false',
        help='True to only include nsfw, (default: %(default)s)'
    )
    parent_image_parser.add_argument(
        '--types',
        choices=['static', 'animated'],
        default='static,animated',
        help='Filter static or animated artwork (default: both)'
    )
    parent_image_parser.add_argument(
        '--count', '-n',
        type=int,
        help='Number of images to download (default: all)'
    )
    parser_hero = subparsers.add_parser('hero',
                                        help='Search for large banner background images',
                                        parents=[parent_parser,
                                                 parent_image_parser],
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
        return args.func(args)
    else:
        return interactive()


if __name__ == '__main__':
    try:
        main()
    except ScriptError as e:
        print(f'Error: {e}')
        sys.exit(1)
