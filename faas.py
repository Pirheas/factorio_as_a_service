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
SUDOER_PATH = '/etc/sudoers.d'


def main():
    vargs = init_args_parse()
    fc = FactorioCommands(vargs)
    if vargs.latest_version:
        fc.get_latest_version()
    elif vargs.update:
        fc.update_server()
    elif vargs.installed_version:
        fc.get_local_version()
    elif vargs.create_service:
        fc.create_service()


def init_args_parse():
    parser = ArgumentParser(description='Commands to manage linux factorio server...')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-c', '--create-service', help='Configure Factorio as a systemd service (need root permissions)',
                       action='store_true')
    group.add_argument('-u', '--update', help='Update factorio if needed', action='store_true')
    group.add_argument('-i', '--installed-version', help='Get the version of factorio installed on this server',
                       action='store_true')
    group.add_argument('-l', '--latest-version', help='Get the latest version of factorio', action='store_true')
    parser.add_argument('-x', '--experimental', help='Force using the experimental version', action='store_true')
    parser.add_argument('-v', '--verbose', help='Verbose', action='store_true')
    return parser.parse_args()


class ConfigData:
    def __init__(self, config, command_args):
        self.config = config
        self.command_args = command_args
        self._verbose = None
        self._baseurl = None
        self._experimental = None
        self._factorio_path = None
        self._experimental_url = None
        self._stable_url = None
        self._factorio_binary = None
        self._factorio_service = None
        self._factorio_service_path = None
        self._save_path = None
        self._user = None

    def vprint(self, *args, **kwargs):
        if self.verbose:
            print(*args, **kwargs)

    @property
    def verbose(self):
        if self._verbose is None:
            self._verbose = self.command_args.verbose
            self.vprint("** Verbose mode enabled **")
        return self._verbose

    @property
    def experimental(self):
        if self._experimental is None:
            self._experimental = self.config.getboolean('DEFAULT', 'experimental', fallback=False)
            self._experimental = self._experimental or self.command_args.experimental
            if self.experimental:
                self.vprint("Looking for Experimental version")
            else:
                self.vprint("Looking for stable version")
        return self._experimental

    @property
    def baseurl(self):
        if self._baseurl is None:
            self._baseurl = self.config.get('WEBSITE', 'baseurl', fallback='https://www.factorio.com')
        return self._baseurl

    @property
    def experimental_url(self):
        if self._experimental_url is None:
            page = self.config.get('WEBSITE', 'experimentalpage', fallback='/download-headless/experimental')
            self._experimental_url = '{0}{1}'.format(self.baseurl, page)
            self.vprint('Downloading page:', self._experimental_url)
        return self._experimental_url

    @property
    def stable_url(self):
        if self._stable_url is None:
            page = self.config.get('WEBSITE', 'stablepage', fallback='/download-headless/stable')
            self._stable_url = '{0}{1}'.format(self.baseurl, page)
            self.vprint('Downloading page:', self._stable_url)
        return self._stable_url

    @property
    def factorio_path(self):
        if self._factorio_path is None:
            path = self.config.get('DEFAULT', 'factorio-path', fallback='/factorio')
            self._factorio_path = get_abs_path(path)
        return self._factorio_path

    @property
    def factorio_binary(self):
        if self._factorio_binary is None:
            self._factorio_binary = os.path.join(self.factorio_path,
                                                 self.config.get('DEFAULT', 'bin-path', fallback='bin/x64/factorio'))
            self.vprint('Checking factorio binary at', self._factorio_binary)
        return self._factorio_binary

    @property
    def factorio_service(self):
        if self._factorio_service is None:
            self._factorio_service = self.config.get('SERVICE', 'service-name', fallback='factorio.service')
            self.vprint("Service name found:", self._factorio_service)
            if not str(self._factorio_service).endswith('.service'):
                print('Your service name must end with: ".service"', file=sys.stderr)
                sys.exit(-100)
        return self._factorio_service

    @property
    def factorio_service_path(self):
        return os.path.join(SYSTEMD_PATH, self.factorio_service)

    @property
    def factorio_service_rule_path(self):
        if self._factorio_service_path is None:
            filename = re.sub(r'\W', '_', self.factorio_service)
            filename = '99_{0}'.format(filename)
            self._factorio_service_path = os.path.join(SUDOER_PATH, filename)
            self.vprint("Writing permission at", self._factorio_service_path)
        return self._factorio_service_path

    @property
    def save_path(self):
        if self._save_path is None:
            self._save_path = get_abs_path(self.config.get('DEFAULT', 'save-path',
                                                           fallback='../factorio/save/fsave.zip'))
            self.vprint('Save path configured at', self._save_path)
        return self._save_path

    @property
    def user(self):
        if self._user is None:
            self._user = self.config.get('DEFAULT', 'user', fallback='root')
        return self._user


class FactorioCommands:
    def __init__(self, vargs):
        self.vargs = vargs
        config = ConfigParser()
        config_path = get_abs_path('./config.ini')
        if vargs.verbose:
            print('Reading config from "{0}"'.format(config_path))
        config.read(config_path)
        self.config = ConfigData(config, self.vargs)
        self.latest_version_data = None

    def vprint(self, *args, **kwargs):
        self.config.vprint(*args, **kwargs)

    def check_factorio_path(self, create_dir=True):
        path = self.config.factorio_path
        if os.path.exists(path):
            if os.path.isdir(path):
                return True
            else:
                self.vprint("{0} is not a directory".format(path))
                return False
        elif create_dir is True:
            try:
                os.makedirs(self.config.factorio_path)
                return True
            except:
                print('Unable to create directory', self.config.factorio_path, file=sys.stderr)
                sys.exit(-1)
        else:
            self.vprint('Directory "{0}" does not exist'.format(path))
        return False

    def check_factorio_bin_path(self):
        path = self.config.factorio_binary
        if not os.path.isfile(path):
            self.vprint("{0} does not exist or is not a file".format(path))
            return False
        if not os.access(path, os.X_OK):
            self.vprint("Current user does not have execution permission on file", path)
            return False
        return True

    def _get_latest_version(self):
        success = False
        parser = None
        if self.config.experimental:
            parser, success = self._download_and_parse_page(self.config.experimental_url)
        if not success:
            if self.config.experimental:
                self.vprint('Unable to find any experimental version, fallback to stable branch')
            parser, success = self._download_and_parse_page(self.config.stable_url)
        if not success:
            print("Unable to find any factorio version a their website !", file=sys.stderr)
            sys.exit(-5)
        self.latest_version_data = parser.latest_version
        return parser

    def _download_and_parse_page(self, url):
        parser = FactorioVersionPageParser()
        try:
            with urlopen(url) as fs:
                parser.feed(fs.read().decode())
            if parser.version_found:
                return parser, True
            else:
                self.vprint("No version found on this page !")
        except HTTPError as httperr:
            self.vprint('Unable to open "{0}":'.format(url))
            self.vprint('Code {0}: {1}'.format(httperr.code, httperr.msg))
        except Exception as err:
            self.vprint("Error:", str(err))
        return None, False

    def get_latest_version(self):
        ret = self._get_latest_version()
        if self.config.verbose:
            print(str(ret))
        else:
            print(ret.latest_version.number)

    def _get_local_version(self):

        if not self.check_factorio_path(False):
            print('Unable to find factorio directory at', self.config.factorio_path, file=sys.stderr)
            sys.exit(-10)
        if not self.check_factorio_bin_path():
            print('Unable to execute factorio at', self.config.factorio_binary, file=sys.stderr)
            sys.exit(-11)
        try:
            return str_to_version(subprocess.check_output([self.config.factorio_binary, '--version'],
                                                          universal_newlines=True))
        except subprocess.CalledProcessError:
            self.vprint('Unable to find local version')
        return None

    def get_local_version(self):
        version = self._get_local_version()
        print('Version of', self.config.factorio_binary, ':', version.vstring)

    def update_server(self):
        if not self.check_factorio_path(True):
            print("Unable to create directory at:", self.config.factorio_path, file=sys.stderr)
            sys.exit(-8)
        if self.is_download_needed():
            self.stop_server()
            self.download_extract_archive()
            self.start_server()
            print('Server updated successfully!')
        else:
            print('No update required')

    def is_download_needed(self):
        latest = self._get_latest_version().latest_version
        if not self.check_factorio_bin_path():
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
        url = '{0}{1}'.format(self.config.baseurl, self.latest_version_data.path)
        self.vprint('Downloading file:', url)
        path = '/tmp/factorio_headless.tar.xz'
        with urlopen(url) as fs:
            with open(path, 'wb') as f:
                self.vprint('Creation of the archive at:', path)
                f.write(fs.read())
        tar = ['tar', '-xf', path, '-C', self.config.factorio_path, '--strip-components=1']
        self.vprint("Extracting data to", self.config.factorio_path)
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
        if not self._service_file_exists():
            self.vprint('Service is not configured yet (unable to start it)')
            return
        else:
            self.vprint('Stoping service...')
        command = ['sudo', '/bin/systemctl', 'stop', self.config.factorio_service]
        sub = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        _, _ = sub.communicate()

    def start_server(self):
        if not self._service_file_exists():
            self.vprint('Service is not configured yet (unable to start it)')
            return
        else:
            self.vprint('Starting service...')
        command = ['sudo', '/bin/systemctl', 'start', self.config.factorio_service]
        sub = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        _, _ = sub.communicate()

    def create_service(self):
        check_root_permission()
        self.vprint('You have root permissions')
        check_systemd_dir()
        check_sudoer_dir()
        if not self.check_factorio_path(create_dir=False) or not self.check_factorio_bin_path():
            print("Unable to create service, file {0} does not exist or is not executable"
                  .format(self.config.factorio_binary, file=sys.stderr))
            sys.exit(-9)
        self.stop_server()
        self._write_service()
        self._manage_service_permissions()
        self._reload_daemon_service()
        print('Service successfully created')
        self.start_server()

    def _manage_service_permissions(self):
        rules = ['ALL ALL=(ALL) NOPASSWD: /bin/systemctl start {0}'.format(self.config.factorio_service),
                 'ALL ALL=(ALL) NOPASSWD: /bin/systemctl status {0}'.format(self.config.factorio_service),
                 'ALL ALL=(ALL) NOPASSWD: /bin/systemctl stop {0}'.format(self.config.factorio_service)]
        rule_path = self.config.factorio_service_rule_path
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
        service = self.config.factorio_service_path
        return os.path.isfile(service)

    def _write_service(self):
        path = self.config.factorio_service_path
        user = self.config.user
        check_user_exists(user)
        if not os.path.isfile(self.config.save_path):
            print("Save file at '{0}' does not exist or is not a file".format(self.config.save_path), file=sys.stderr)
            sys.exit(-21)
        self.vprint("Save file located at", self.config.save_path)
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
        '''.format(user, self.config.factorio_path, self.config.factorio_binary,
                   self.config.save_path, settings_command)
        with open(path, 'w') as f:
            self.vprint('Creating service file at:', path)
            f.write(service)

    def get_server_settings_path(self):
        if not self.config.config.getboolean('DEFAULT', 'custom-settings-path', fallback=False):
            self.vprint('No settings file specified')
            return None
        path = get_abs_path(self.config.config.get('DEFAULT', 'settings-path', fallback=''))
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
        sys.exit(19)


def check_sudoer_dir():
    if not os.path.isdir(SUDOER_PATH):
        print("Your system does not support sudo. Impossible to create service", file=sys.stderr)
        sys.exit(18)


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

    @property
    def version_found(self):
        return len(self.available_version) > 0


if __name__ == "__main__":
    main()
