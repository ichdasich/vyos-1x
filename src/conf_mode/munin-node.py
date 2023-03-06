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

from netifaces import interfaces
from socket import gethostname
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

config_file = r'/etc/munin/munin-node.conf'
plugin_path = r'/etc/munin/plugins/'
systemd_override = r'/run/systemd/system/munin-node.service.d/10-override.conf'

def get_config(config=None):
    if config:
        conf = config
    else:
        conf = Config()

    base = ['service', 'munin-node']
    if not conf.exists(base):
        return None

    munin-node = conf.get_config_dict(base, key_mangling=('-', '_'), get_first_key=True)
    # Node_name default is dynamic thus we can not use defaults()
    if 'node-ame' not in munin-node:
        munin-node['node-name'] = gethostname()
    # Do not know how to overwrite default from include
    if 'port' not in munin-node:
        munin-node['port'] = '4949'

    # Munin uses a regex to allow-list servers
    munin-node['munin-server-regex'] = '^'+munin-node['munin-server'].replace('.','\.')+'$'

    # We have gathered the dict representation of the CLI, but there are default
    # options which we need to update into the dictionary retrived.
    default_values = defaults(base)
    munin-node = dict_merge(default_values, munin-node)
    return munin-node

def verify(munin-node):
    # bail out early - looks like removal from running config
    if not munin-node:
        return None

    return None

def generate(munin-node):
    # cleanup any available configuration file
    # files will be recreated on demand
    for i in glob(config_file + '*') + glob(plugin_path + '*'):
        os.unlink(i)

    if os.path.isfile(systemd_override):
        os.unlink(systemd_override)

    # bail out early - looks like removal from running config
    if munin-node is None:
        return None

    render(config_file, 'munin-node/munin-node.conf.j2', munin-node)

    # Create plugin symlinks
    os.symlink('/usr/share/munin/plugins/cpu','/etc/munin/plugins/cpu')
    os.symlink('/usr/share/munin/plugins/cpuspeed','/etc/munin/plugins/cpuspeed')
    os.symlink('/usr/share/munin/plugins/df','/etc/munin/plugins/df')
    os.symlink('/usr/share/munin/plugins/df_inode','/etc/munin/plugins/df_inode')
    os.symlink('/usr/share/munin/plugins/diskstats','/etc/munin/plugins/diskstats')
    os.symlink('/usr/share/munin/plugins/entropy','/etc/munin/plugins/entropy')
    os.symlink('/usr/share/munin/plugins/forks','/etc/munin/plugins/forks')
    os.symlink('/usr/share/munin/plugins/fw_conntrack','/etc/munin/plugins/fw_conntrack')
    os.symlink('/usr/share/munin/plugins/fw_forwarded_local','/etc/munin/plugins/fw_forwarded_local')
    os.symlink('/usr/share/munin/plugins/fw_packets','/etc/munin/plugins/fw_packets')
    os.symlink('/usr/share/munin/plugins/interrupts','/etc/munin/plugins/interrupts')
    os.symlink('/usr/share/munin/plugins/irqstats','/etc/munin/plugins/irqstats')
    os.symlink('/usr/share/munin/plugins/load','/etc/munin/plugins/load')
    os.symlink('/usr/share/munin/plugins/memory','/etc/munin/plugins/memory')
    os.symlink('/usr/share/munin/plugins/netstat','/etc/munin/plugins/netstat')
    os.symlink('/usr/share/munin/plugins/open_files','/etc/munin/plugins/open_files')
    os.symlink('/usr/share/munin/plugins/open_inodes','/etc/munin/plugins/open_inodes')
    os.symlink('/usr/share/munin/plugins/processes','/etc/munin/plugins/processes')
    os.symlink('/usr/share/munin/plugins/proc_pri','/etc/munin/plugins/proc_pri')
    os.symlink('/usr/share/munin/plugins/sensors_','/etc/munin/plugins/sensors_temp')
    os.symlink('/usr/share/munin/plugins/sensors_','/etc/munin/plugins/sensors_volt')
    os.symlink('/usr/share/munin/plugins/swap','/etc/munin/plugins/swap')
    os.symlink('/usr/share/munin/plugins/threads','/etc/munin/plugins/threads')
    os.symlink('/usr/share/munin/plugins/uptime','/etc/munin/plugins/uptime')
    os.symlink('/usr/share/munin/plugins/users','/etc/munin/plugins/users')
    os.symlink('/usr/share/munin/plugins/vmstat','/etc/munin/plugins/vmstat')

    for interface in interfaces():
        os.symlink('/usr/share/munin/plugins/if_','/etc/munin/plugins/if_'+interface)
    os.symlink('/usr/share/munin/plugins/if_err_','retc/munin/plugins/if_err_'+interface)

    # Create overwrite file
    if not os.path.isdir(systemd_override.replace('10-override.conf','')):
        os.makedirs(systemd_override.replace('10-override.conf',''))

    render(systemd_override, 'munin-node/override.conf.j2', munin-node)

    return None

def apply(munin-node):
    # stop all services first - then we will decide
    call('systemctl stop munin-node.service')

    # bail out early - e.g. service deletion
    if munin-node is None:
        return None

    call(f'systemctl restart munin-node.service')

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
