#!/usr/bin/env python3
#
# Copyright (C) 2019 VyOS maintainers and contributors
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
#
#

import sys
import os

import jinja2

import vyos.defaults
from vyos.config import Config
from vyos.util import dict_search
from vyos import ConfigError

config_file = '/etc/nginx/sites-available/default'

# Please be careful if you edit the template.
config_tmpl = """

### Autogenerated by https.py ###
# Default server configuration
#
server {
        listen 80 default_server;
        listen [::]:80 default_server;
        server_name _;
        return 301 https://$server_name$request_uri;
}

{% for server in server_block_list %}
server {

        # SSL configuration
        #
{% if server.address == '*' %}
        listen 443 ssl;
        listen [::]:443 ssl;
{% else %}
        listen {{ server.address }}:{{ server.port }} ssl;
{% endif %}

{% for name in server.name %}
        server_name {{ name }};
{% endfor %}

{% if server.vyos_cert %}
        include {{ server.vyos_cert.conf }};
{% else %}
        #
        # Self signed certs generated by the ssl-cert package
        # Don't use them in a production server!
        #
        include snippets/snakeoil.conf;
{% endif %}

        # proxy settings for HTTP API, if enabled; 503, if not
        location ~ /(retrieve|configure|config-file|image) {
{% if server.api %}
                proxy_pass http://localhost:{{ server.api.port }};
                proxy_read_timeout 600;
                proxy_buffering off;
{% else %}
                return 503;
{% endif %}
        }

        error_page 501 502 503 =200 @50*_json;

        location @50*_json {
                default_type application/json;
                return 200 '{"error": "Start service in configuration mode: set service https api"}';
        }

}

{% endfor %}
"""

default_server_block = {
    'address'   : '*',
    'name'      : ['_'],
    # api       :
    # vyos_cert :
    # le_cert   :
}

def get_config():
    server_block_list = []
    conf = Config()
    if not conf.exists('service https'):
        return None
    else:
        conf.set_level('service https')

    if conf.exists('listen-address'):
        for addr in conf.list_nodes('listen-address'):
            server_block = {'address' : addr}
            server_block['port'] = '443'
            server_block['name'] = ['_']
            if conf.exists('listen-address {0} listen-port'.format(addr)):
                port = conf.return_value('listen-address {0} listen-port'.format(addr))
                server_block['port'] = port
            if conf.exists('listen-address {0} server-name'.format(addr)):
                names = conf.return_values('listen-address {0} server-name'.format(addr))
                server_block['name'] = names[:]
            server_block_list.append(server_block)

    if not server_block_list:
        server_block_list.append(default_server_block)

    vyos_cert_data = {}
    if conf.exists('certificates'):
        if conf.exists('certificates system-generated-certificate'):
            vyos_cert_data = vyos.defaults.vyos_cert_data
    if vyos_cert_data:
        for block in server_block_list:
            block['vyos_cert'] = vyos_cert_data

    api_data = {}
    if conf.exists('api'):
        api_data = vyos.defaults.api_data
        if conf.exists('api port'):
            port = conf.return_value('api port')
            api_data['port'] = port
    if api_data:
        for block in server_block_list:
            block['api'] = api_data

    https = {'server_block_list' : server_block_list}
    return https

def verify(https):
    # Verify API server settings, if present
    if 'api' in https:
        keys = dict_search('api.keys.id', https)
        gql_auth_type = dict_search('api.graphql.authentication.type', https)

        # If "api graphql" is not defined and `gql_auth_type` is None,
        # there's certainly no JWT auth option, and keys are required
        jwt_auth = (gql_auth_type == "token")

        # Check for incomplete key configurations in every case
        valid_keys_exist = False
        if keys:
            for k in keys:
                if 'key' not in keys[k]:
                    raise ConfigError(f'Missing HTTPS API key string for key id "{k}"')
                else:
                    valid_keys_exist = True

        # If only key-based methods are enabled,
        # fail the commit if no valid key configurations are found
        if (not valid_keys_exist) and (not jwt_auth):
            raise ConfigError('At least one HTTPS API key is required unless GraphQL token authentication is enabled')

    return None


def generate(https):
    if https is None:
        return None

    if 'server_block_list' not in https or not https['server_block_list']:
        https['server_block_list'] = [default_server_block]

    tmpl = jinja2.Template(config_tmpl, trim_blocks=True)
    config_text = tmpl.render(https)
    with open(config_file, 'w') as f:
        f.write(config_text)

    return None

def apply(https):
    if https is not None:
        os.system('sudo systemctl restart nginx.service')
    else:
        os.system('sudo systemctl stop nginx.service')

if __name__ == '__main__':
    try:
        c = get_config()
        verify(c)
        generate(c)
        apply(c)
    except ConfigError as e:
        print(e)
        sys.exit(1)
