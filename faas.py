#!/usr/bin/env python3
import re
import os
import sys
import subprocess
from urllib.request import urlopen
from urllib.error import HTTPError
from argparse import ArgumentParser
from html.parser import HTMLParser
from collections import namedtuple
from distutils.version import LooseVersion
from configparser import ConfigParser


SYSTEMD_PATH = '/etc/systemd/system'


def main():
    vargs = init_args_parse()
    fc = FactorioCommands(vargs)
    if vargs.latest_version:
        fc.get_latest_version()
    elif vargs.update:
        fc.update_server()
    elif vargs.factorio_version:
        fc.get_local_version()
    elif vargs.create_service:
        fc.create_service()


def init_args_parse():
    parser = ArgumentParser(description='Commands to manage linux factorio server...')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-c', '--create-service', help='Configure Factorio as a systemd service (need root permissions)',
                       action='store_true')
    group.add_argument('-u', '--update', help='Update factorio if needed', action='store_true')
    group.add_argument('-f', '--factorio-version', help='Get the version of factorio installed on this server',
                       action='store_true')
    group.add_argument('-l', '--latest-version', help='Get the latest version of factorio', action='store_true')
    parser.add_argument('-x', '--experimental', help='Force using the experimental version', action='store_true')
    parser.add_argument('-v', '--verbose', help='Verbose', action='store_true')
    return parser.parse_args()


class FactorioCommands:
    def __init__(self, vargs):
        self.vargs = vargs
        self.config = ConfigParser()
        config_path = get_abs_path('./config.ini')
        if vargs.verbose:
            print('Reading config from "{0}"'.format(config_path))
        self.config.read(config_path)
        self.experimental = self.config.getboolean('DEFAULT', 'experimental', fallback=False) or self.vargs.experimental
        self.baseurl = self.config.get('WEBSITE', 'baseurl', fallback='https://www.factorio.com')
        self.service_name = self.config.get('SERVICE', 'service-name', fallback='factorio.service')
        self.save_path = get_abs_path(self.config.get('DEFAULT', 'save-path', fallback='../factorio/save/fsave.zip'))
        self.dir_path = None
        self.bin_path = None
        self.bin_exists = False
        self.settings_path = None
        self.latest_version_data = None

    def vprint(self, *args, **kwargs):
        if self.vargs.verbose:
            print(*args, **kwargs)

    def get_dir_path(self):
        if self.dir_path:
            return self.dir_path
        path = self.config.get('DEFAULT', 'factorio-path', fallback='/factorio')
        self.dir_path = get_abs_path(path)
        self.vprint('Factorio directory path:', self.dir_path)
        self.bin_path = os.path.join(self.dir_path, self.config.get('DEFAULT', 'bin-path', fallback='bin/x64/factorio'))
        self.vprint('Factorio binary path:', self.bin_path)
        return self.dir_path

    def check_dir_path(self, create_dir=True):
        path = self.get_dir_path()
        if os.path.exists(path):
            if os.path.isdir(path):
                if os.path.isfile(self.bin_path):
                    if not os.access(self.bin_path, os.X_OK):
                        self.vprint('Not allowed to execute binary, tying to chmod file')
                        os.chmod(self.bin_path, 0o755)
                    self.bin_exists = True
                else:
                    self.vprint(self.bin_path, 'is not a file')
            else:
                print('Path', path, 'already exists and is not a directory', file=sys.stderr)
                sys.exit(-1)
        elif create_dir:
            self.vprint('Directory does not exist')
            os.makedirs(path)
            self.vprint('Directory created:', path)
        return False

    def _get_latest_version(self):
        if self.experimental:
            page = self.config.get('WEBSITE', 'experimentalpage', fallback='/download-headless/experimental')
        else:
            page = self.config.get('WEBSITE', 'stablepage', fallback='/download-headless/stable')

        url = '{0}{1}'.format(self.baseurl, page)
        self.vprint('Downloading page:', url)
        parser = FactorioVersionPageParser()
        try:
            with urlopen(url) as fs:
                parser.feed(fs.read().decode())
        except HTTPError as httperr:
            print('Unable to open "{0}":'.format(url), file=sys.stderr)
            print('Code {0}: {1}'.format(httperr.code, httperr.msg), file=sys.stderr)
            sys.exit(-1)
        self.latest_version_data = parser.latest_version
        return parser

    def get_latest_version(self):
        ret = self._get_latest_version()
        if self.vargs.verbose:
            print(str(ret))
        else:
            print(ret.latest_version.number)

    def _get_local_version(self):
        self.check_dir_path()
        if not self.bin_exists:
            print('File', '"{0}"'.format(self.bin_path), 'does not exist or is not executable')
            sys.exit(-3)
        try:
            return str_to_version(subprocess.check_output([self.bin_path, '--version'], universal_newlines=True))
        except subprocess.CalledProcessError:
            self.vprint('Unable to find local version')
        return None

    def get_local_version(self):
        version = self._get_local_version()
        print('Version of', self.bin_path, ':', version.vstring)

    def update_server(self):
        self.check_dir_path()
        if self.is_download_needed():
            self.stop_server()
            self.download_extract_archive()
            self.start_server()
            print('Server updated successfully!')
        else:
            print('No update required')

    def is_download_needed(self):
        latest = self._get_latest_version().latest_version
        if not self.bin_exists:
            self.vprint('No binary found, update required')
            return True
        local_version = self._get_local_version()
        if local_version is None:
            return True
        self.vprint('Latest version:', latest.number.vstring)
        self.vprint('Local  version:', local_version.vstring)
        if latest.number > local_version:
            self.vprint('Updating required')
            return True
        self.vprint('Local version is up-to-date')
        return False

    def download_extract_archive(self):
        url = '{0}{1}'.format(self.baseurl, self.latest_version_data.path)
        self.vprint('Downloading file:', url)
        path = '/tmp/factorio_headless.tar.xz'
        with urlopen(url) as fs:
            with open(path, 'wb') as f:
                self.vprint('Creation of the archive at:', path)
                f.write(fs.read())
        tar = ['tar', '-xf', path, '-C', self.dir_path, '--strip-components=1']
        self.vprint("Extracting data to", self.dir_path)
        sub = subprocess.Popen(tar, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        stdout, stderr = sub.communicate()
        if sub.returncode == 0:
            self.vprint('Extraction succeeded')
            os.remove(path)
            self.vprint("Archive deleted")
        else:
            print('Error during archive extraction:', stderr, file=sys.stderr)
            sys.exit(-2)

    def stop_server(self):
        self.vprint('Stoping service...')
        if not self._service_file_exists():
            self.vprint('Service is not configured yet (unable to start it)')
            return
        command = ['sudo', '/bin/systemctl', 'stop', 'factorio.service']
        sub = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        _, _ = sub.communicate()

    def start_server(self):
        self.vprint('Starting service...')
        if not self._service_file_exists():
            self.vprint('Service is not configured yet (unable to start it)')
            return
        command = ['sudo', '/bin/systemctl', 'start', 'factorio.service']
        sub = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        _, _ = sub.communicate()

    def create_service(self):
        check_root_permission()
        self.vprint('You have root permissions')
        check_systemd_dir()
        self.check_dir_path(create_dir=False)
        if not self.bin_exists:
            print('Unable to find binary file at:', self.bin_path, file=sys.stderr)
            sys.exit(-8)
        if not os.path.isfile(self.save_path):
            print('Unable to find save file at:', self.save_path, file=sys.stderr)
            sys.exit(-15)
        self.stop_server()
        self._write_service()
        self._manage_service_permissions()
        self._reload_daemon_service()
        print('Service successfully created')
        self.start_server()

    def _manage_service_permissions(self):
        rules = ['ALL ALL=(ALL) NOPASSWD: /bin/systemctl start {0}'.format(self.service_name),
                 'ALL ALL=(ALL) NOPASSWD: /bin/systemctl status {0}'.format(self.service_name),
                 'ALL ALL=(ALL) NOPASSWD: /bin/systemctl stop {0}'.format(self.service_name)]
        rule_path = '/etc/sudoers.d/99_factorio'
        with open(rule_path, 'w') as f:
            self.vprint('Adding rules in sudoers to allow all users to use service at:', rule_path)
            f.write('\n'.join(rules))
            f.write('\n')
        self.vprint('Changing rule file permission')
        os.chmod(rule_path, 0o440)

    def _reload_daemon_service(self):
        sub = subprocess.Popen(['systemctl', 'daemon-reload'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        stdout, stderr = sub.communicate()
        if sub.returncode == 0:
            self.vprint('Systemctl daemon reloaded')
        else:
            self.vprint(stderr)
            print('Unable to restart systemctl daemon, continuing anyway ...', file=sys.stderr)
            print("Please consider running 'systemctl daemon-reload' to reload units", file=sys.stderr)

    def _service_file_exists(self):
        service = os.path.join(SYSTEMD_PATH, self.service_name)
        return os.path.isfile(service)

    def _write_service(self):
        path = os.path.join(SYSTEMD_PATH, self.service_name)
        user = self.config.get('DEFAULT', 'user', fallback='root')
        check_user_exists(user)
        settings_path = self.get_server_settings_path()
        settings_command = ''
        if settings_path:
            settings_command = ' --server-settings {0}'.format(settings_path)
        service = '''
[Unit]
Description=Factorio Server
After=network.target

[Service]
Type=simple
User={0}
WorkingDirectory={1}
ExecStart={2} --start-server {3}{4}
        '''.format(user, self.dir_path, self.bin_path, self.save_path, settings_command)
        with open(path, 'w') as f:
            self.vprint('Creating service file at:', path)
            f.write(service)

    def get_server_settings_path(self):
        if not self.config.getboolean('DEFAULT', 'custom-settings-path', fallback=False):
            self.vprint('No settings file specified')
            return None
        path = get_abs_path(self.config.get('DEFAULT', 'settings-path', fallback=''))
        if not os.path.isfile(path):
            print('Unable to find settings file at:', path, file=sys.stderr)
            sys.exit(-16)
        return path


def str_to_version(version):
    version = str(version or '').strip()
    res = re.search(r'\d+(\.\d+)+', version)
    if not res:
        return None
    return LooseVersion(res.group())


def get_abs_path(path):
    path = str(path or '').strip()
    if path.startswith('~'):
        path = os.path.expanduser(path)
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(os.path.dirname(__file__), path))


def check_root_permission(required=True):
    if os.getuid() == 0:
        return
    if not required:
        print("It seems you don't have root permissions, it could be problematic !")
        return
    print('Root permissions are required !', file=sys.stderr)
    sys.exit(13)


def check_systemd_dir():
    if not os.path.isdir(SYSTEMD_PATH):
        print("Your system seems not compatible with systemd. Impossible to create service", file=sys.stderr)
        sys.exit(14)


def check_user_exists(username):
    from pwd import getpwnam
    username = str(username or '')
    if username:
        try:
            _ = getpwnam(username)
            return
        except KeyError:
            pass
    print('User "{0}" does not exist'.format(username), file=sys.stderr)
    sys.exit(-10)


class FactorioVersionPageParser(HTMLParser):

    def __init__(self):
        self.Version = namedtuple('Version', 'number path')
        self.available_version = []
        self.current_version = None
        self._in_h3 = False
        super().__init__()

    def handle_starttag(self, tag, attrs):
        if tag == 'h3':
            self._in_h3 = True
        elif tag == 'a' and self.current_version is not None:
            self.get_download_link(attrs)

    def handle_endtag(self, tag):
        self._in_h3 = False

    def handle_data(self, data):
        if self._in_h3:
            self.parse_version(data)

    def parse_version(self, data):
        version = str_to_version(data)
        if version:
            self.current_version = version

    def get_download_link(self, attrs):
        for attr in attrs:
            if attr[0] == 'href':
                self.available_version.append(self.Version(number=self.current_version, path=attr[1]))
                self.available_version = sorted(self.available_version, key=lambda x: x.number, reverse=True)
                self.current_version = None
                break

    def error(self, message):
        pass

    def __str__(self):
        if not self.available_version:
            return 'No available version found :('
        ls = ['Latest version:',
              '{0} [{1}]'.format(self.available_version[0].number.vstring, self.available_version[0].path)]
        if len(self.available_version) > 1:
            ls.append('-- Other versions --')
            for v in self.available_version[1:]:
                ls.append('{0} [{1}]'.format(v.number.vstring, v.path))
        return '\n'.join(ls)

    @property
    def latest_version(self):
        if not self.available_version:
            return None
        return self.available_version[0]


if __name__ == "__main__":
    main()
