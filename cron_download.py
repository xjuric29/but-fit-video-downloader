import argparse
from download import Downloader
import os
import re
import schema as s
import sys
import yaml


class CronDownloader:
    """Automatize downloading large count of course records.

    Simply set configuration YAML file with URLs of videos, what you need and run this script one per day by cron. When
    the downloading limit is reached, downloader continuous next day.
    """
    def __init__(self):
        """Init of backup object.

        Here are defined instance attributes.
        """
        # Configuration file location.
        self._config_path = './config.yml'
        # Here will be stored loaded configuration from YAML.
        self._config = {}
        # Schema object for checking validating config structure. Look at https://github.com/keleshev/schema for
        # information how it use.
        self._config_schema = s.Schema({
            # WIS username like "xlogin00". Mandatory option.
            'user': str,
            # WIS password.
            'password': str,
            # Courses definition.
            'videos': [
                {
                    # URL of video list for course in specific semester. Mandatory option.
                    'url': str,
                    # Path to the dir where should be videos stored. Mandatory option.
                    'dir_path': s.And(str, os.path.isdir, error='Bad video directory.'),
                    # Which type of video should be downloaded.
                    'video_type': s.And(str, s.Regex(r'^board|full_view|both]$', re.IGNORECASE),
                                        error='Bad video type.'),
                    # Course can be run more than once per day with same content. With this option you can skip it.
                    s.Optional('one_video_per_day'): bool
                }
            ]
        })

    def _parse_args(self):
        """Parse program arguments.

        Parse argument config.
        """
        parser = argparse.ArgumentParser(description='Automatically download needed courses records.')
        parser.add_argument('-c', '--config-file', help='File with the YAML configuration.')

        arguments = parser.parse_args()

        # Store parse arguments.
        # If config file is inserted and is not blank.
        if hasattr(arguments, 'config_file') and arguments.config_file:
            self._config_path = arguments.config_file

    def _load_config(self):
        """Load configuration file.

        This method tries to load configuration in YAML, checks if the file is accessible and in correct syntax and
        saves it into attribute 'self._config'. Then run option control method.

        :return: 1 when some error occurs else 0
        """
        res = 0

        # Try to load YAML.
        try:
            with open(self._config_path, mode='r') as config:
                self._config = yaml.safe_load(config) or {}
        # Inaccessible or non exist file.
        except IOError:
            print('Config file does not exist or is not accessible.', file=sys.stderr)
            res = 1
        # Syntax error.
        except yaml.YAMLError as exc:
            print('Syntax error in config file.\n\n{}'.format(str(exc)), file=sys.stderr)
            res = 1

        # If there is no error, run option check.
        if res == 0:
            try:
                self._config_schema.validate(self._config)
            except s.SchemaError as exc:
                print('Error in config file:\n\n{}'.format(str(exc)), file=sys.stderr)
                res = 1

        return res

    def _download_videos(self):
        """Download videos from specified courses.

        Create instance of "Downloader" for every video URL.
        """
        # Iterate over the videos URLs specified in the configuration file.
        for video_data in self._config['videos']:
            # Check optional option and create its default value.
            if 'one_video_per_day' not in video_data:
                video_data['one_video_per_day'] = False

            # Run downloader.
            Downloader(user=self._config['user'], password=self._config['password'], video_url=video_data['url'],
                       video_dir_path=video_data['dir_path'], video_type=video_data['video_type'],
                       one_video_per_day=video_data['one_video_per_day']).run()

    def run(self):
        """The main method which is responsible for invoking all other program parts.

        :return: Unix like status code.
        """
        # Parse program arguments.
        self._parse_args()

        # Load and check configuration.
        if self._load_config():
            return 1

        # Run backup.
        self._download_videos()

        return 0


if __name__ == "__main__":
    # Run downloader.
    exit(CronDownloader().run())
