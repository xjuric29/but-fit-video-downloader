import argparse
from bs4 import BeautifulSoup
import os
import re
import requests
import unidecode
import urllib3


class Downloader:
    """Simple class for download videos from FIT BUT courses."""
    # Requests header.
    HEADERS = {
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 '
                      'Safari/537.36'
    }
    # FIT BUT authentication page.
    LOGIN_PAGE_URL = 'https://cas.fit.vutbr.cz/'
    # Video server base url.
    VIDEO_BASE_URL = 'https://video1.fit.vutbr.cz/av/'
    # Mapping between program argument and needed regex for determine the type of the video.
    VIDEO_TYPE_MAP = {
        'board': re.compile(r'^(?:přednáška|demonstrační cvičení) - plátno,.*'),
        'full_view': re.compile(r'^(?:přednáška|demonstrační cvičení),.*'),
        'both': re.compile(r'^(?:přednáška|demonstrační cvičení).*')
    }

    def __init__(self):
        """Init function.

        Define important instance arguments.
        """
        # WIS username like 'xlogin00'.
        self._user = ''
        # WIS password.
        self._password = ''
        # URL of video list for course in specific semester.
        # Example: self._video_url = 'https://video1.fit.vutbr.cz/av/records-categ.php?id=1315'
        self._video_url = ''
        # Which type of video should be downloaded.
        # Example: self._video_type = 'board'
        self._video_type = ''
        # Path where should be downloaded videos stored.
        self._video_dir_path = ''
        # Create session with shared cookies.
        self._session = requests.Session()
        # If the option "--one-video-per-day" is chosen, this set is used to store days, from which is video downloaded.
        self._unique_days = set()

        # Disable warnings about missing certificates.
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _parse_args(self):
        """Parse program arguments.

        Parse arguments like username, password, etc.
        """
        parser = argparse.ArgumentParser(description='Download videos from FIT BUT courses.')
        parser.add_argument('-u', '--user', required=True, help='WIS username like "xlogin00"')
        parser.add_argument('-p', '--password', required=True, help='WIS password')
        parser.add_argument('-l', '--video-url', required=True, help='URL of video list for course in specific '
                                                                     'semester')
        parser.add_argument('-d', '--video-dir', required=True, help='path to the dir where should be videos stored')
        parser.add_argument('-t', '--video-type', default='board', choices=['board', 'full_view', 'both'],
                            help='which type of video should be downloaded. videos are captured in two version, first '
                                 'with full view to a teacher and bad shot of board and second only with view to a '
                                 'board')
        parser.add_argument('-x', '--one-video-per-day', action='store_true', help='course can be run more than once '
                                                                                   'per day with same content. with '
                                                                                   'this option you can skip it')
        arguments = parser.parse_args()

        # Store parse arguments.
        self._user = arguments.user
        self._password = arguments.password
        self._video_url = arguments.video_url
        self._video_dir_path = arguments.video_dir
        self._video_type = arguments.video_type
        self._one_video_per_day = arguments.one_video_per_day

    def _download_video(self, url, file_path):
        """Download video file. https://stackoverflow.com/questions/16694907/download-large-file-in-python-with-requests

        The video is stored in the path specified by program argument and the name which is from a server.

        :param url: URL of the downloaded file.
        :param file_path: Full path to the video file.
        """
        # NOTE the stream=True parameter below
        with self._session.get(url, headers=self.HEADERS, verify=False, stream=True) as file_query:
            # When the "Content-Disposition" in in the response header, file will be downloaded. There are also some
            # limits as cannot be downloaded same video at the same time more then twice or daily limit to all video
            # downloads.
            # Example:
            # file_query.headers = {
            #   'Date': 'Sat, 20 Jun 2020 01:02:00 GMT',
            #   'Server': 'Apache/1.3.41 Ben-SSL/1.59 (Unix)',
            #   'Last-Modified': 'Tue, 04 Oct 2016 09:05:24 GMT',
            #   'Expires': 'Sat, 20 Jun 2020 01:02:01 GMT',
            #   'Cache-Control': 'max_age=0', 'Pragma': 'global',
            #   'Content-Disposition': 'attachment; filename="IEL_2016-09-29.mp4"',
            #   'Content-Length': '635271310',
            #   'Keep-Alive': 'timeout=30, max=98',
            #   'Connection': 'Keep-Alive',
            #   'Content-Type': 'video/mp4'}
            if 'Content-Disposition' not in file_query.headers:
                print('Dosažen limit stahování záznamů.')
                return
            # Stole the file extension from original name of the video.
            # Example:
            # file_query.headers['Content-Disposition'] = 'attachment; filename="IEL_2016-09-29.mp4"'
            # file_path = '/home/user/Documents/iel/iel_29-9-2016_08:00-09:55_prednaska' ->
            # file_name = '/home/user/Documents/iel/iel_29-9-2016_08:00-09:55_prednaska.mp4'
            file_path = file_path + '.' + file_query.headers['Content-Disposition'].split('"')[1].split('.')[1]

            # If the file exists, skip downloading.
            if os.path.exists(file_path):
                print('Soubor s videem existuje, přeskakuji.')
                return

            file_query.raise_for_status()
            with open(file_path, 'wb') as big_file:
                for chunk in file_query.iter_content(chunk_size=8192):
                    # If you have chunk encoded response uncomment if
                    # and set chunk_size parameter to None.
                    # if chunk:
                    big_file.write(chunk)

    def _download(self):
        """Core of the downloader.

        Parse HTML pages and download videos from collected addresses.
        """
        # Get cookie 'cosign' with some session hash which is saved after visiting cas.fit.vutbr.cz.
        self._session.get(self.LOGIN_PAGE_URL, headers=self.HEADERS)

        # Log in to the video1.fit.vutbr.cz via cas.fit.vutbr.cz.
        login_query = self._session.post(self.LOGIN_PAGE_URL, headers=self.HEADERS, data={
            'login': self._user,
            'password': self._password,
            'doLogin': 'Log In',
            'required': None,
            'ref': None,
            'service': None
        })
        # In all cases page returns status code 200. There is used parsing of HTML content for identifying login and
        # other errors. When page return HTML code with element H1 and its content which is specified below, login was
        # successful.
        if BeautifulSoup(login_query.text, 'lxml').find_all('h1')[0].text != 'Aplikace autentizované CAS FIT VUT':
            raise ValueError('Authentication failure.')

        # Display private content of specific course and semester.
        video_query = self._session.get(self._video_url, headers=self.HEADERS, verify=False)
        parsed_list_page = BeautifulSoup(video_query.text, 'lxml')

        # Iterate over video items in the list from the pages.
        for item in parsed_list_page.find_all('li', style=True):
            # If video record is in needed type. For more information look at the 'video-type' program argument
            # definition or on the self.VIDEO_TYPE_MAP defined at the top of this class.
            if re.search(self.VIDEO_TYPE_MAP[self._video_type], item.div.text):
                # Example: video_detail_url = 'https://video1.fit.vutbr.cz/av/records.php?id=40841&categ_id=1315'
                video_detail_url = self.VIDEO_BASE_URL + item.a['href']
                # Get content of page with detail of specific record. There is link to specific faculty video server
                # where is the record stored.
                video_detail_query = self._session.get(video_detail_url, headers=self.HEADERS, verify=False)
                # Parsed HTML content of the video page.
                parsed_video_page = BeautifulSoup(video_detail_query.text, 'lxml')
                # URL of the needed file.
                # Example: https://video3.fit.vutbr.cz/av/record-download.php?id=40841
                video_url = parsed_video_page.find('a', class_='button')['href']
                # Scraped video metadata for video name construction.
                # Example: video_info = {
                #   'course': 'IEL Elektronika pro informační technologie',
                #   'date': '8. 12. 2016, 13:00 - 14:55'
                #   'type': 'přednáška, 29. 9. 2016'
                # }
                raw_video_info = {
                    'course': parsed_video_page.h3.text,
                    'date': parsed_video_page.find('td', text=re.compile(r'Záznam vytvořen')).next_sibling.text,
                    'type': item.div.text
                }
                # Example: modified_video_info = {
                #   'course': 'iel',
                #   'date': '2016-9-29',
                #   'time_range': '08:00-09:55',
                #   'type': 'demonstracni_cviceni-platno'
                # }
                modified_video_info = {
                    'course': raw_video_info['course'][0:3].lower(),
                    'date': '-'.join(raw_video_info['date'].split(', ')[0].replace('.', '').split(' ')[::-1]),
                    'time_range': raw_video_info['date'].split(', ')[1].replace(' ', ''),
                    'type': '-'.join([unidecode.unidecode(piece.replace(' ', '_')) for piece in
                                      raw_video_info['type'].split(',')[0].split(' - ')])
                }
                # Example: video_name = 'iel_29-9-2016_08:00-09:55_prednaska'
                video_name = '{}_{}_{}_{}'.format(modified_video_info['course'], modified_video_info['date'],
                                                  modified_video_info['time_range'], modified_video_info['type'])

                # If "--one-video-per-day" program argument is used.
                if self._one_video_per_day and modified_video_info['date'] in self._unique_days:
                    print('Přeskakuji video z {} {}.\n'.format(modified_video_info['date'],
                                                               modified_video_info['time_range']))
                    continue

                print('Stahuji video z {} {} varianta {}.'.format(modified_video_info['date'],
                                                                  modified_video_info['time_range'],
                                                                  modified_video_info['type']))
                print('{}'.format(video_url))

                # Store date.
                self._unique_days.add(modified_video_info['date'])
                # Download the video.
                self._download_video(video_url, os.path.join(self._video_dir_path, video_name))

                # Separate video logs.
                print()

        return 0

    def run(self):
        """Main public method.

        :return: Unix-like return code. If all is ok, return 0, in case of big error return 1.
        """
        # Parse program arguments.
        self._parse_args()

        # Run downloading.
        try:
            self._download()
        except ValueError:
            return 1

        return 0


if __name__ == "__main__":
    # Run downloader.
    exit(Downloader().run())
