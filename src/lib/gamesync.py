#!/usr/bin/env python3

import os
import logging
import argparse
import json
import sys
import fnmatch
import shutil
from datetime import date

'''
This script is used to stage directories specified in ~/.local/lib/gamesync/gamesync-settings.json to
~/.local/lib/gamesync/saves in order for syncthing to properly synchronize them

IMPORTANT NOTE: This script does not check if syncthing is currently synchronizing! 

This script is not meant to be used directly, instead the bash script gamesync will invoke this python script
when appropriate.
'''

LOCAL_GAMESYNC_ERR_NO_DOWNLOAD_UPLOAD_SPECIFIED = 20
LOCAL_GAMESYNC_ERR_NO_STEAM_APP_ID_AND_OR_ALIAS_NAME = 21
LOCAL_GAMESYNC_ERR_NO_GAME_DEFINITION = 22

debug = os.getenv('GAMESYNC_DEBUG', None)
log_file = None
logger = logging.getLogger('')

gamesync_log_level = os.getenv('GAMESYNC_LOG_LEVEL', None)

if gamesync_log_level == "NOTSET":
    log_level = logging.NOTSET
elif gamesync_log_level == "DEBUG":
    log_level = logging.DEBUG
elif gamesync_log_level == "INFO":
    log_level = logging.INFO
elif gamesync_log_level == "WARN":
    log_level = logging.WARN
elif gamesync_log_level == "ERROR":
    log_level = logging.ERROR
elif gamesync_log_level == "FATAL":
    log_level = logging.FATAL
else:
    log_level = logging.INFO

log_format = '%(asctime)s | %(levelname)s | gamesync.py | %(message)s'

logging.basicConfig(
    format=log_format,
    level=log_level,
    datefmt='%Y-%m-%d %H:%M:%S')

if debug == 'true':
    current_date = date.today()
    log_file = os.path.expanduser("~") + f'/.local/share/gamesync/logs/log.{current_date.strftime("%Y-%m-%d")}.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(file_handler)


def synchronize_directories(
        source_dir,
        dest_dir,
        include_patterns,
        exclude_patterns,
        remove_dest_conflicts):
    if os.path.exists(source_dir):
        logger.info(f'checking for files to sync in {source_dir} to {dest_dir}')
        for root, dirs, files in os.walk(source_dir):
            for directory in dirs:
                synchronize_directories(
                    os.path.join(source_dir, directory),
                    os.path.join(dest_dir, directory),
                    include_patterns,
                    exclude_patterns,
                    remove_dest_conflicts)

            for filename in files:
                source_path = os.path.join(root, filename)
                relative_path = os.path.relpath(source_path, source_dir)
                dest_path = os.path.join(dest_dir, relative_path)

                if should_skip(filename, include_patterns, exclude_patterns):
                    continue

                is_conflict_file = fnmatch.fnmatch(filename, '*.sync-conflict*')
                if is_conflict_file:
                    logger.warning(f'Found conflict file {source_path}, skipping!')
                    continue

                if not os.path.exists(dest_path) or os.path.getmtime(source_path) > os.path.getmtime(dest_path):
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)  # Create missing directories
                    shutil.copy2(source_path, dest_path)
                    logger.info(f"Copied {source_path} to {dest_path}")
                else:
                    logger.debug(f'file {dest_path} already up to date')
        logger.info(f'checking for files to delete from {dest_dir} not present in {source_dir}')
        for dest_root, dest_dirs, dest_files in os.walk(dest_dir):
            for filename in dest_files:
                if should_skip(filename, include_patterns, exclude_patterns):
                    continue

                file_to_delete = os.path.join(dest_root, filename)
                relative_path = os.path.relpath(file_to_delete, dest_dir)
                path_to_check = os.path.join(source_dir, relative_path)
                if not os.path.exists(path_to_check):
                    try:
                        logger.warning(f'{file_to_delete} marked for deletion')
                        os.remove(file_to_delete)
                        logger.info(f'deleted {file_to_delete} successfully')
                    except OSError as error:
                        logger.error(error)
                        logger.error(f'Could not remove {file_to_delete}')
    else:
        logger.info(f'{source_dir} does not exist, this may be first time sync')


def should_skip(filename, include_patterns, exclude_patterns):
    if include_patterns:
        logger.debug(f'Testing if {filename} is in include_patterns: {include_patterns}')
        matched_include = any(fnmatch.fnmatch(filename, pattern) for pattern in include_patterns)
        if not matched_include:
            return True

    if exclude_patterns:
        logger.debug(f'Testing if {filename} is in exclude_patterns: {include_patterns}')
        matched_exclude = any(fnmatch.fnmatch(filename, pattern) for pattern in exclude_patterns)
        if matched_exclude:
            return True

    return False


def synchronize_saves(game, gamesync_folder_name, download, remove_dest_conflicts):
    gamesync_directory = os.path.expanduser(f'~/.local/share/gamesync/saves/{gamesync_folder_name}')
    save_locations = game['saveLocations']
    for saveLocation in save_locations:
        save_location_name = saveLocation['name']
        source_directory = os.path.expanduser(saveLocation['sourceDirectory'])
        include = None if 'include' not in saveLocation else saveLocation['include']
        exclude = None if 'exclude' not in saveLocation else saveLocation['exclude']

        logger.debug(f'Save location name {save_location_name}')
        logger.debug(f'Source directory {source_directory}')
        logger.debug(f'Include {include}')
        logger.debug(f'Exclude {exclude}')

        first_time_sync = False
        gamesync_save_path = os.path.join(gamesync_directory, save_location_name)
        if not os.path.exists(gamesync_save_path):
            os.makedirs(gamesync_save_path)
            first_time_sync = True

        if download:
            if first_time_sync:
                logger.info(f'First time synchronization, nothing to download!')
            source = gamesync_save_path
            destination = source_directory
        else:
            source = source_directory
            destination = gamesync_save_path

        logger.info(f'Synchronizing from {source} to {destination}')
        synchronize_directories(source, destination, include, exclude, remove_dest_conflicts)


def load_game_definition(game_settings, steam_app_id, alias):
    if steam_app_id != "0":
        game = next((game for game in game_settings['games'] if f"{game['steamAppId']}" == steam_app_id), None)
        logger.debug(game)
        name = game['directoryName'] if game is not None and 'directoryName' in game else steam_app_id
        logger.debug(name)
    else:
        game = next((game for game in game_settings['games'] if ('alias' in game) and
                     game['alias'] == alias), None)
        logger.debug(game)
        name = game['directoryName'] if game is not None and 'directoryName' in game else alias
        logger.debug(name)
    return game, name


def main():
    parser = argparse.ArgumentParser(description="Synchronize game files for steam or non-steam game")
    parser.add_argument(
        "--steamAppId",
        required=True,
        help="The SteamAppId")
    parser.add_argument(
        "--alias",
        required=True,
        help="Required if the SteamAppId is 0")
    parser.add_argument(
        "--download",
        action="store_true",
        required=False,
        help="Used to download game saves")
    parser.add_argument(
        "--upload",
        action="store_true",
        required=False,
        help="Used to upload game saves")
    parser.add_argument(
        "--removeDestConflicts",
        action="store_true",
        required=False,
        help="remove conflict files in the destination directory")

    args = parser.parse_args()

    steam_app_id = args.steamAppId
    alias = args.alias
    download = args.download
    upload = args.upload
    remove_dest_conflicts = args.removeDestConflicts

    if (download is True and upload is True) or (download is False and upload is False):
        logger.error("Must either specify download or upload, but not both")
        sys.exit(LOCAL_GAMESYNC_ERR_NO_DOWNLOAD_UPLOAD_SPECIFIED)

    if steam_app_id == "0" and alias is None:
        logger.error("Must specify executableName if steamAppId is 0")
        sys.exit(LOCAL_GAMESYNC_ERR_NO_STEAM_APP_ID_AND_OR_ALIAS_NAME)

    logger.info(f'SteamAppId: {steam_app_id}')
    if alias is not None:
        logger.info(f'Alias: {alias}')

    gamesync_filepath = os.path.expanduser('~/.local/share/gamesync/gamesync-settings.json')
    logger.info(f'Synchronizing saves using entries in {gamesync_filepath}')

    with open(gamesync_filepath, 'r') as file:
        file_contents = file.read()
        game_settings = json.loads(file_contents)
        game, name = load_game_definition(game_settings, steam_app_id, alias)

        # if game is None, we need to check in .default-settings.json in case there is a default implementation
        if game is None:
            gamesync_default_filepath = os.path.expanduser('~/.local/share/gamesync/.default-settings.json')
            logger.info(f'Game not found in {gamesync_filepath}, searching in {gamesync_default_filepath}...')
            with open(gamesync_default_filepath, 'r') as default_file:
                default_file_contents = default_file.read()
                default_game_settings = json.loads(default_file_contents)
                game, name = load_game_definition(default_game_settings, steam_app_id, alias)

        # if a game is still None, then it's not defined anywhere
        if game is None:
            err_msg = f'Game with steam id {steam_app_id}'
            if steam_app_id == "0" and alias is not None:
                err_msg += f' and alias name {alias}'
            err_msg += f' was not found in {gamesync_filepath}'
            logger.error(err_msg)
            sys.exit(LOCAL_GAMESYNC_ERR_NO_GAME_DEFINITION)
        synchronize_saves(game, name, download, remove_dest_conflicts)


if __name__ == "__main__":
    main()
