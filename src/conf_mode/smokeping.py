#!/usr/bin/env python3
#
# Copyright (C) 2018-2020 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import stat
import pwd

from copy import deepcopy
from glob import glob
from sys import exit

from vyos.base import Warning
from vyos.config import Config
from vyos.configdict import dict_merge
from vyos.configverify import verify_vrf
from vyos.template import render
from vyos.template import is_ipv4
from vyos.util import call
from vyos.util import chmod_400
from vyos.validate import is_addr_assigned
from vyos.xml import defaults
from vyos import ConfigError
from vyos import airbag
airbag.enable()

config_file = r'/etc/default/smokeping'
secret_file = r'/etc/smokeping/clientsecrets.conf'

def get_config(config=None):
    if config:
        conf = config
    else:
        conf = Config()

    base = ['service', 'smokeping']
    if not conf.exists(base):
        return None

    smokeping = conf.get_config_dict(base, key_mangling=('-', '_'), get_first_key=True)
    # We have gathered the dict representation of the CLI, but there are default
    # options which we need to update into the dictionary retrived.
    default_values = defaults(base)
    smokeping = dict_merge(default_values, smokeping)
    return smokeping

def verify(smokeping):
    # bail out early - looks like removal from running config
    if not smokeping:
        return None

    # Configuring allowed clients without a server makes no sense
    if 'instrumentation_url' not in smokeping:
        raise ConfigError('Instrumentation URL must be configured!')

    if 'client_name' not in smokeping:
        raise ConfigError('Client name must be configured!')

    if 'client_secret' not in smokeping:
        raise ConfigError('Client name must be configured!')

    return None

def generate(smokeping):
    # cleanup any available configuration file
    # files will be recreated on demand
    for i in glob(config_file + '*') + glob(secret_file + '*'):
        os.unlink(i)

    # bail out early - looks like removal from running config
    if smokeping is None:
        return None

    render(config_file, 'smokeping/default.j2', config)
    render(secret_file, 'smokeping/clientsecrets.j2', config)

    # Smokeping is very particular about the secret file's permissions
    chmod_400(secret_file)
    smokeping_uid = pwd.getpwnam('smokeping').pw_uid
    smokeping_gid = pwd.getpwnam('smokeping').pw_gid
    os.chown(secret_file, smokeping_uid, smokeping_gid)

    return None

def apply(smokeping):
    # stop all services first - then we will decide
    call('systemctl stop smokeping.service')

    # bail out early - e.g. service deletion
    if smokeping is None:
        return None

    call(f'systemctl restart smokeping.service')

    return None

if __name__ == '__main__':
    try:
        c = get_config()
        verify(c)
        generate(c)
        apply(c)
    except ConfigError as e:
        print(e)
        exit(1)
