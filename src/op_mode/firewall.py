#!/usr/bin/env python3
#
# Copyright (C) 2021 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import ipaddress
import json
import re
import tabulate

from vyos.config import Config
from vyos.utils.process import cmd
from vyos.utils.dict import dict_search_args

def get_config_firewall(conf, family=None, hook=None, priority=None):
    config_path = ['firewall']
    if family:
        config_path += [family]
        if hook:
            config_path += [hook]
            if priority:
                config_path += [priority]

    firewall = conf.get_config_dict(config_path, key_mangling=('-', '_'),
                                get_first_key=True, no_tag_node_value_mangle=True)

    return firewall

def get_nftables_details(family, hook, priority):
    if family == 'ipv6':
        suffix = 'ip6'
        name_prefix = 'NAME6_'
        aux='IPV6_'
    elif family == 'ipv4':
        suffix = 'ip'
        name_prefix = 'NAME_'
        aux=''
    else:
        suffix = 'bridge'
        name_prefix = 'NAME_'
        aux=''

    if hook == 'name' or hook == 'ipv6-name':
        command = f'sudo nft list chain {suffix} vyos_filter {name_prefix}{priority}'
    else:
        up_hook = hook.upper()
        command = f'sudo nft list chain {suffix} vyos_filter VYOS_{aux}{up_hook}_{priority}'

    try:
        results = cmd(command)
    except:
        return {}

    out = {}
    for line in results.split('\n'):
        comment_search = re.search(rf'{priority}[\- ](\d+|default-action)', line)
        if not comment_search:
            continue

        rule = {}
        rule_id = comment_search[1]
        counter_search = re.search(r'counter packets (\d+) bytes (\d+)', line)
        if counter_search:
            rule['packets'] = counter_search[1]
            rule['bytes'] = counter_search[2]

        rule['conditions'] = re.sub(r'(\b(counter packets \d+ bytes \d+|drop|reject|return|log)\b|comment "[\w\-]+")', '', line).strip()
        out[rule_id] = rule
    return out

def output_firewall_name(family, hook, priority, firewall_conf, single_rule_id=None):
    print(f'\n---------------------------------\n{family} Firewall "{hook} {priority}"\n')

    details = get_nftables_details(family, hook, priority)
    rows = []

    if 'rule' in firewall_conf:
        for rule_id, rule_conf in firewall_conf['rule'].items():
            if single_rule_id and rule_id != single_rule_id:
                continue

            if 'disable' in rule_conf:
                continue

            row = [rule_id, rule_conf['action'], rule_conf['protocol'] if 'protocol' in rule_conf else 'all']
            if rule_id in details:
                rule_details = details[rule_id]
                row.append(rule_details.get('packets', 0))
                row.append(rule_details.get('bytes', 0))
                row.append(rule_details['conditions'])
            rows.append(row)

    if 'default_action' in firewall_conf and not single_rule_id:
        row = ['default', firewall_conf['default_action'], 'all']
        if 'default-action' in details:
            rule_details = details['default-action']
            row.append(rule_details.get('packets', 0))
            row.append(rule_details.get('bytes', 0))
        rows.append(row)

    if rows:
        header = ['Rule', 'Action', 'Protocol', 'Packets', 'Bytes', 'Conditions']
        print(tabulate.tabulate(rows, header) + '\n')

def output_firewall_name_statistics(family, hook, prior, prior_conf, single_rule_id=None):
    print(f'\n---------------------------------\n{family} Firewall "{hook} {prior}"\n')

    details = get_nftables_details(family, hook, prior)
    rows = []

    if 'rule' in prior_conf:
        for rule_id, rule_conf in prior_conf['rule'].items():
            if single_rule_id and rule_id != single_rule_id:
                continue

            if 'disable' in rule_conf:
                continue

            # Get source
            source_addr = dict_search_args(rule_conf, 'source', 'address')
            if not source_addr:
                source_addr = dict_search_args(rule_conf, 'source', 'group', 'address_group')
                if not source_addr:
                    source_addr = dict_search_args(rule_conf, 'source', 'group', 'network_group')
                    if not source_addr:
                        source_addr = dict_search_args(rule_conf, 'source', 'group', 'domain_group')
                        if not source_addr:
                            source_addr = dict_search_args(rule_conf, 'source', 'fqdn')
                            if not source_addr:
                                source_addr = dict_search_args(rule_conf, 'source', 'geoip', 'country_code')
                                if source_addr:
                                    source_addr = str(source_addr)[1:-1].replace('\'','')
                                    if 'inverse_match' in dict_search_args(rule_conf, 'source', 'geoip'):
                                        source_addr = 'NOT ' + str(source_addr)
                                if not source_addr:
                                    source_addr = 'any'

            # Get destination
            dest_addr = dict_search_args(rule_conf, 'destination', 'address')
            if not dest_addr:
                dest_addr = dict_search_args(rule_conf, 'destination', 'group', 'address_group')
                if not dest_addr:
                    dest_addr = dict_search_args(rule_conf, 'destination', 'group', 'network_group')
                    if not dest_addr:
                        dest_addr = dict_search_args(rule_conf, 'destination', 'group', 'domain_group')
                        if not dest_addr:
                            dest_addr = dict_search_args(rule_conf, 'destination', 'fqdn')
                            if not dest_addr:
                                dest_addr = dict_search_args(rule_conf, 'destination', 'geoip', 'country_code')
                                if dest_addr:
                                    dest_addr = str(dest_addr)[1:-1].replace('\'','')
                                    if 'inverse_match' in dict_search_args(rule_conf, 'destination', 'geoip'):
                                        dest_addr = 'NOT ' + str(dest_addr)
                                if not dest_addr:
                                    dest_addr = 'any'

            # Get inbound interface
            iiface = dict_search_args(rule_conf, 'inbound_interface', 'interface_name')
            if not iiface:
                iiface = dict_search_args(rule_conf, 'inbound_interface', 'interface_group')
                if not iiface:
                    iiface = 'any'

            # Get outbound interface
            oiface = dict_search_args(rule_conf, 'outbound_interface', 'interface_name')
            if not oiface:
                oiface = dict_search_args(rule_conf, 'outbound_interface', 'interface_group')
                if not oiface:
                    oiface = 'any'

            row = [rule_id]
            if rule_id in details:
                rule_details = details[rule_id]
                row.append(rule_details.get('packets', 0))
                row.append(rule_details.get('bytes', 0))
            else:
                row.append('0')
                row.append('0')
            row.append(rule_conf['action'])
            row.append(source_addr)
            row.append(dest_addr)
            row.append(iiface)
            row.append(oiface)
            rows.append(row)


    if hook in ['input', 'forward', 'output']:
        row = ['default']
        row.append('N/A')
        row.append('N/A')
        if 'default_action' in prior_conf:
            row.append(prior_conf['default_action'])
        else:
            row.append('accept')
        row.append('any')
        row.append('any')
        row.append('any')
        row.append('any')
        rows.append(row)

    elif 'default_action' in prior_conf and not single_rule_id:
        row = ['default']
        if 'default-action' in details:
            rule_details = details['default-action']
            row.append(rule_details.get('packets', 0))
            row.append(rule_details.get('bytes', 0))
        else:
            row.append('0')
            row.append('0')
        row.append(prior_conf['default_action'])
        row.append('any')   # Source
        row.append('any')   # Dest
        row.append('any')   # inbound-interface
        row.append('any')   # outbound-interface
        rows.append(row)

    if rows:
        header = ['Rule', 'Packets', 'Bytes', 'Action', 'Source', 'Destination', 'Inbound-Interface', 'Outbound-interface']
        print(tabulate.tabulate(rows, header) + '\n')

def show_firewall():
    print('Rulesets Information')

    conf = Config()
    firewall = get_config_firewall(conf)

    if not firewall:
        return

    for family in ['ipv4', 'ipv6', 'bridge']:
        if family in firewall:
            for hook, hook_conf in firewall[family].items():
                for prior, prior_conf in firewall[family][hook].items():
                    output_firewall_name(family, hook, prior, prior_conf)

def show_firewall_family(family):
    print(f'Rulesets {family} Information')

    conf = Config()
    firewall = get_config_firewall(conf)

    if not firewall or family not in firewall:
        return

    for hook, hook_conf in firewall[family].items():
        for prior, prior_conf in firewall[family][hook].items():
            output_firewall_name(family, hook, prior, prior_conf)

def show_firewall_name(family, hook, priority):
    print('Ruleset Information')

    conf = Config()
    firewall = get_config_firewall(conf, family, hook, priority)
    if firewall:
        output_firewall_name(family, hook, priority, firewall)

def show_firewall_rule(family, hook, priority, rule_id):
    print('Rule Information')

    conf = Config()
    firewall = get_config_firewall(conf, family, hook, priority)
    if firewall:
        output_firewall_name(family, hook, priority, firewall, rule_id)

def show_firewall_group(name=None):
    conf = Config()
    firewall = get_config_firewall(conf)

    if 'group' not in firewall:
        return

    def find_references(group_type, group_name):
        out = []
        family = []
        if group_type in ['address_group', 'network_group']:
            family = ['ipv4']
        elif group_type == 'ipv6_address_group':
            family = ['ipv6']
            group_type = 'address_group'
        elif group_type == 'ipv6_network_group':
            family = ['ipv6']
            group_type = 'network_group'
        else:
            family = ['ipv4', 'ipv6']

        for item in family:
            for name_type in ['name', 'ipv6_name', 'forward', 'input', 'output']:
                if item in firewall:
                    if name_type not in firewall[item]:
                        continue
                    for priority, priority_conf in firewall[item][name_type].items():
                        if priority not in firewall[item][name_type]:
                            continue
                        if 'rule' not in priority_conf:
                            continue
                        for rule_id, rule_conf in priority_conf['rule'].items():
                            source_group = dict_search_args(rule_conf, 'source', 'group', group_type)
                            dest_group = dict_search_args(rule_conf, 'destination', 'group', group_type)
                            in_interface = dict_search_args(rule_conf, 'inbound_interface', 'interface_group')
                            out_interface = dict_search_args(rule_conf, 'outbound_interface', 'interface_group')
                            if source_group:
                                if source_group[0] == "!":
                                    source_group = source_group[1:]
                                if group_name == source_group:
                                    out.append(f'{item}-{name_type}-{priority}-{rule_id}')
                            if dest_group:
                                if dest_group[0] == "!":
                                    dest_group = dest_group[1:]
                                if group_name == dest_group:
                                    out.append(f'{item}-{name_type}-{priority}-{rule_id}')
                            if in_interface:
                                if in_interface[0] == "!":
                                    in_interface = in_interface[1:]
                                if group_name == in_interface:
                                    out.append(f'{item}-{name_type}-{priority}-{rule_id}')
                            if out_interface:
                                if out_interface[0] == "!":
                                    out_interface = out_interface[1:]
                                if group_name == out_interface:
                                    out.append(f'{item}-{name_type}-{priority}-{rule_id}')
        return out

    header = ['Name', 'Type', 'References', 'Members']
    rows = []

    for group_type, group_type_conf in firewall['group'].items():
        for group_name, group_conf in group_type_conf.items():
            if name and name != group_name:
                continue

            references = find_references(group_type, group_name)
            row = [group_name, group_type, '\n'.join(references) or 'N/D']
            if 'address' in group_conf:
                row.append("\n".join(sorted(group_conf['address'])))
            elif 'network' in group_conf:
                row.append("\n".join(sorted(group_conf['network'], key=ipaddress.ip_network)))
            elif 'mac_address' in group_conf:
                row.append("\n".join(sorted(group_conf['mac_address'])))
            elif 'port' in group_conf:
                row.append("\n".join(sorted(group_conf['port'])))
            elif 'interface' in group_conf:
                row.append("\n".join(sorted(group_conf['interface'])))
            else:
                row.append('N/D')
            rows.append(row)

    if rows:
        print('Firewall Groups\n')
        print(tabulate.tabulate(rows, header))

def show_summary():
    print('Ruleset Summary')

    conf = Config()
    firewall = get_config_firewall(conf)

    if not firewall:
        return

    header = ['Ruleset Hook', 'Ruleset Priority', 'Description', 'References']
    v4_out = []
    v6_out = []
    br_out = []

    if 'ipv4' in firewall:
        for hook, hook_conf in firewall['ipv4'].items():
            for prior, prior_conf in firewall['ipv4'][hook].items():
                description = prior_conf.get('description', '')
                v4_out.append([hook, prior, description])

    if 'ipv6' in firewall:
        for hook, hook_conf in firewall['ipv6'].items():
            for prior, prior_conf in firewall['ipv6'][hook].items():
                description = prior_conf.get('description', '')
                v6_out.append([hook, prior, description])

    if 'bridge' in firewall:
        for hook, hook_conf in firewall['bridge'].items():
            for prior, prior_conf in firewall['bridge'][hook].items():
                description = prior_conf.get('description', '')
                br_out.append([hook, prior, description])

    if v6_out:
        print('\nIPv6 Ruleset:\n')
        print(tabulate.tabulate(v6_out, header) + '\n')

    if v4_out:
        print('\nIPv4 Ruleset:\n')
        print(tabulate.tabulate(v4_out, header) + '\n')

    if br_out:
        print('\nBridge Ruleset:\n')
        print(tabulate.tabulate(br_out, header) + '\n')

    show_firewall_group()

def show_statistics():
    print('Rulesets Statistics')

    conf = Config()
    firewall = get_config_firewall(conf)

    if not firewall:
        return

    for family in ['ipv4', 'ipv6', 'bridge']:
        if family in firewall:
            for hook, hook_conf in firewall[family].items():
                for prior, prior_conf in firewall[family][hook].items():
                    output_firewall_name_statistics(family, hook,prior, prior_conf)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--action', help='Action', required=False)
    parser.add_argument('--name', help='Firewall name', required=False, action='store', nargs='?', default='')
    parser.add_argument('--family', help='IP family', required=False, action='store', nargs='?', default='')
    parser.add_argument('--hook', help='Firewall hook', required=False, action='store', nargs='?', default='')
    parser.add_argument('--priority', help='Firewall priority', required=False, action='store', nargs='?', default='')
    parser.add_argument('--rule', help='Firewall Rule ID', required=False)
    parser.add_argument('--ipv6', help='IPv6 toggle', action='store_true')

    args = parser.parse_args()

    if args.action == 'show':
        if not args.rule:
            show_firewall_name(args.family, args.hook, args.priority)
        else:
            show_firewall_rule(args.family, args.hook, args.priority, args.rule)
    elif args.action == 'show_all':
        show_firewall()
    elif args.action == 'show_family':
        show_firewall_family(args.family)
    elif args.action == 'show_group':
        show_firewall_group(args.name)
    elif args.action == 'show_statistics':
        show_statistics()
    elif args.action == 'show_summary':
        show_summary()
