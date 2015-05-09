#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# (c) 2015, René Moser <mail@renemoser.net>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: cs_portforward
short_description: Manages port forwarding rules on Apache CloudStack based clouds.
description: Create, update and remove port forwarding rules on Apache CloudStack, Citrix CloudPlatform.
version_added: '2.0'
author: René Moser
options:
  ip_address:
    description:
      - Public IP address the rule is assigned to.
    required: true
  vm:
    description:
      - Name of virtual machine which we make the port forwarding rule for. Required if C(state=present).
    required: false
    default: null
  state:
    description:
      - State of the port forwarding rule.
    required: false
    default: 'present'
    choices: [ 'present', 'absent' ]
  protocol:
    description:
      - Protocol of the port forwarding rule.
    required: false
    default: 'tcp'
    choices: [ 'tcp', 'udp' ]
  public_port
    description:
      - Start public port for this rule.
    required: true
  public_end_port
    description:
      - End public port for this rule. If not specific, equal C(public_port).
    required: false
    default: null
  private_port
    description:
      - Start private port for this rule.
    required: true
  private_end_port
    description:
      - End private port for this rule. If not specific, equal C(private_port)
    required: false
    default: null
  open_firewall:
    description:
      - Whether the firewall rule for public port should be created, while creating the new rule.
    required: false
    default: false
  vm_guest_ip:
    description:
      - VM guest NIC secondary IP address for the port forwarding rule.
    required: false
    default: false
  project:
    description:
      - Name of the project the VM is located in.
    required: false
    default: null
  zone:
    description:
      - Name of the zone in which the virtual machine is in. If not set, default zone is used.
    required: false
    default: null
  poll_async:
    description:
      - Poll async jobs until job has finished.
    required: false
    default: true
'''

EXAMPLES = '''
---
# 1.2.3.4:80 -> web01:8080
- local_action:
    module: cs_portforward
    ip_address: 1.2.3.4
    vm: web01
    public_port: 80
    private_port: 8080


# forward SSH and open firewall
- local_action:
    module: cs_portforward
    ip_address: '{{ public_ip }}'
    vm: '{{ inventory_hostname }}'
    public_port: '{{ ansible_ssh_port }}'
    private_port: 22
    open_firewall: true


# forward DNS traffic, but do not open firewall
- local_action:
    module: cs_portforward
    ip_address: 1.2.3.4
    vm: '{{ inventory_hostname }}'
    public_port: 53
    private_port: 53
    protocol: udp
    open_firewall: true


# remove ssh port forwarding
- local_action:
    module: cs_portforward
    ip_address: 1.2.3.4
    public_port: 22
    private_port: 22
    state: absent

'''

try:
    from cs import CloudStack, CloudStackException, read_config
    has_lib_cs = True
except ImportError:
    has_lib_cs = False

class AnsibleCloudStack:

    def __init__(self, module):
        if not has_lib_cs:
            module.fail_json(msg="python library cs required: pip install cs")

        self.result = {
            'changed': False,
        }

        self.module = module
        self._connect()

        self.project = None
        self.ip_address = None
        self.zone = None
        self.vm = None
        self.os_type = None
        self.hypervisor = None
        self.capabilities = None


    def _connect(self):
        api_key = self.module.params.get('api_key')
        api_secret = self.module.params.get('secret_key')
        api_url = self.module.params.get('api_url')
        api_http_method = self.module.params.get('api_http_method')

        if api_key and api_secret and api_url:
            self.cs = CloudStack(
                endpoint=api_url,
                key=api_key,
                secret=api_secret,
                method=api_http_method
                )
        else:
            self.cs = CloudStack(**read_config())


    def _has_changed(self, want_dict, current_dict, only_keys=None):
        for key, value in want_dict.iteritems():

            # Optionally limit by a list of keys
            if only_keys and key not in only_keys:
                continue;

            if value is None:
                continue;

            if key in current_dict:

                # API returns string for int in some cases, just to make sure
                if isinstance(value, int):
                    current_dict[key] = int(current_dict[key])
                elif isinstance(value, str):
                    current_dict[key] = str(current_dict[key])

                # Only need to detect a singe change, not every item
                if value != current_dict[key]:
                    return True
        return False


    def _get_by_key(self, key=None, my_dict={}):
        if key:
            if key in my_dict:
                return my_dict[key]
            self.module.fail_json(msg="Something went wrong: %s not found" % key)
        return my_dict


    # TODO: for backward compatibility only, remove if not used anymore
    def get_project_id(self):
        return self.get_project(key='id')


    def get_project(self, key=None):
        if self.project:
            return self._get_by_key(key, self.project)

        project = self.module.params.get('project')
        if not project:
            return None

        projects = self.cs.listProjects(listall=True)
        if projects:
            for p in projects['project']:
                if project in [ p['name'], p['displaytext'], p['id'] ]:
                    self.project = p
                    return self._get_by_key(key, self.project)
        self.module.fail_json(msg="project '%s' not found" % project)


    # TODO: for backward compatibility only, remove if not used anymore
    def get_ip_address_id(self):
        return self.get_ip_address(key='id')


    def get_ip_address(self, key=None):
        if self.ip_address:
            return self._get_by_key(key, self.ip_address)

        ip_address = self.module.params.get('ip_address')
        if not ip_address:
            self.module.fail_json(msg="IP address param 'ip_address' is required")

        args = {}
        args['ipaddress'] = ip_address
        args['projectid'] = self.get_project(key='id')
        ip_addresses = self.cs.listPublicIpAddresses(**args)

        if not ip_addresses:
            self.module.fail_json(msg="IP address '%s' not found" % args['ipaddress'])

        self.ip_address = ip_addresses['publicipaddress'][0]
        return self._get_by_key(key, self.ip_address)


    # TODO: for backward compatibility only, remove if not used anymore
    def get_vm_id(self):
        return self.get_vm(key='id')


    def get_vm(self, key=None):
        if self.vm:
            return self._get_by_key(key, self.vm)

        vm = self.module.params.get('vm')
        if not vm:
            self.module.fail_json(msg="Virtual machine param 'vm' is required")

        args = {}
        args['projectid'] = self.get_project(key='id')
        args['zoneid'] = self.get_zone(key='id')
        vms = self.cs.listVirtualMachines(**args)
        if vms:
            for v in vms['virtualmachine']:
                if vm in [ v['name'], v['displayname'], v['id'] ]:
                    self.vm = v
                    return self._get_by_key(key, self.vm)
        self.module.fail_json(msg="Virtual machine '%s' not found" % vm)


    # TODO: for backward compatibility only, remove if not used anymore
    def get_zone_id(self):
        return self.get_zone(key='id')


    def get_zone(self, key=None):
        if self.zone:
            return self._get_by_key(key, self.zone)

        zone = self.module.params.get('zone')
        zones = self.cs.listZones()

        # use the first zone if no zone param given
        if not zone:
            self.zone = zones['zone'][0]
            return self._get_by_key(key, self.zone)

        if zones:
            for z in zones['zone']:
                if zone in [ z['name'], z['id'] ]:
                    self.zone = z
                    return self._get_by_key(key, self.zone)
        self.module.fail_json(msg="zone '%s' not found" % zone)


    # TODO: for backward compatibility only, remove if not used anymore
    def get_os_type_id(self):
        return self.get_os_type(key='id')


    def get_os_type(self, key=None):
        if self.os_type:
            return self._get_by_key(key, self.zone)

        os_type = self.module.params.get('os_type')
        if not os_type:
            return None

        os_types = self.cs.listOsTypes()
        if os_types:
            for o in os_types['ostype']:
                if os_type in [ o['description'], o['id'] ]:
                    self.os_type = o
                    return self._get_by_key(key, self.os_type)
        self.module.fail_json(msg="OS type '%s' not found" % os_type)


    def get_hypervisor(self):
        if self.hypervisor:
            return self.hypervisor

        hypervisor = self.module.params.get('hypervisor')
        hypervisors = self.cs.listHypervisors()

        # use the first hypervisor if no hypervisor param given
        if not hypervisor:
            self.hypervisor = hypervisors['hypervisor'][0]['name']
            return self.hypervisor

        for h in hypervisors['hypervisor']:
            if hypervisor.lower() == h['name'].lower():
                self.hypervisor = h['name']
                return self.hypervisor
        self.module.fail_json(msg="Hypervisor '%s' not found" % hypervisor)


    def get_tags(self, resource=None):
        existing_tags = self.cs.listTags(resourceid=resource['id'])
        if existing_tags:
            return existing_tags['tag']
        return []


    def _delete_tags(self, resource, resource_type, tags):
        if not 'tags' in resource:
            self.module.fail_json(msg="Error: resource has no tags.")

        existing_tags = resource['tags']
        tags_to_delete = []
        for existing_tag in existing_tags:
            if existing_tag['key'] in tags:
                if existing_tag['value'] != tags[key]:
                    tags_to_delete.append(existing_tag)
            else:
                tags_to_delete.append(existing_tag)
        if tags_to_delete:
            self.result['changed'] = True
            if not self.module.check_mode:
                args = {}
                args['resourceids']  = resource['id']
                args['resourcetype'] = resource_type
                args['tags']         = tags_to_delete
                self.cs.deleteTags(**args)


    def _create_tags(self, resource, resource_type, tags):
        tags_to_create = []
        for i, tag_entry in enumerate(tags):
            tag = {
                'key':   tag_entry['key'],
                'value': tag_entry['value'],
            }
            tags_to_create.append(tag)
        if tags_to_create:
            self.result['changed'] = True
            if not self.module.check_mode:
                args = {}
                args['resourceids']  = resource['id']
                args['resourcetype'] = resource_type
                args['tags']         = tags_to_create
                self.cs.createTags(**args)


    def ensure_tags(self, resource, resource_type=None):
        if not resource_type or not resource:
            self.module.fail_json(msg="Error: Missing resource or resource_type for tags.")

        tags = self.module.params.get('tags')
        if tags is not None:
            self._delete_tags(resource, resource_type, tags)
            self._create_tags(resource, resource_type, tags)
            resource['tags'] = self.get_tags(resource)
        return resource


    def get_capabilities(self, key=None):
        if self.capabilities:
            return self._get_by_key(key, self.capabilities)
        capabilities = self.cs.listCapabilities()
        self.capabilities = capabilities['capability']
        return self._get_by_key(key, self.capabilities)


    def _poll_job(self, job=None, key=None):
        if 'jobid' in job:
            while True:
                res = self.cs.queryAsyncJobResult(jobid=job['jobid'])
                if res['jobstatus'] != 0 and 'jobresult' in res:
                    if 'errortext' in res['jobresult']:
                        self.module.fail_json(msg="Failed: '%s'" % res['jobresult']['errortext'])
                    if key and key in res['jobresult']:
                        job = res['jobresult'][key]
                    break
                time.sleep(2)
        return job



class AnsibleCloudStackPortforwarding(AnsibleCloudStack):

    def __init__(self, module):
        AnsibleCloudStack.__init__(self, module)
        self.result = {
            'changed': False,
        }
        self.portforwarding_rule = None
        self.vm_default_nic = None


    def get_public_end_port(self):
        if not self.module.params.get('public_end_port'):
            return self.module.params.get('public_port')
        return self.module.params.get('public_end_port')


    def get_private_end_port(self):
        if not self.module.params.get('private_end_port'):
            return self.module.params.get('private_port')
        return self.module.params.get('private_end_port')


    def get_vm_guest_ip(self):
        vm_guest_ip = self.module.params.get('vm_guest_ip')
        default_nic = self.get_vm_default_nic()

        if not vm_guest_ip:
            return default_nic['ipaddress']

        for secondary_ip in default_nic['secondaryip']:
            if vm_guest_ip == secondary_ip['ipaddress']:
                return vm_guest_ip
        self.module.fail_json(msg="Secondary IP '%s' not assigned to VM" % vm_guest_ip)


    def get_vm_default_nic(self):
        if self.vm_default_nic:
            return self.vm_default_nic

        nics = self.cs.listNics(virtualmachineid=self.get_vm(key='id'))
        if nics:
            for n in nics['nic']:
                if n['isdefault']:
                    self.vm_default_nic = n
                    return self.vm_default_nic
        self.module.fail_json(msg="No default IP address of VM '%s' found" % self.module.params.get('vm'))


    def get_portforwarding_rule(self):
        if not self.portforwarding_rule:
            protocol            = self.module.params.get('protocol')
            public_port         = self.module.params.get('public_port')
            public_end_port     = self.get_public_end_port()
            private_port        = self.module.params.get('private_port')
            private_end_port    = self.get_public_end_port()

            args = {}
            args['ipaddressid'] = self.get_ip_address(key='id')
            args['projectid'] = self.get_project(key='id')
            portforwarding_rules = self.cs.listPortForwardingRules(**args)

            if portforwarding_rules and 'portforwardingrule' in portforwarding_rules:
                for rule in portforwarding_rules['portforwardingrule']:
                    if protocol == rule['protocol'] \
                        and public_port == int(rule['publicport']):
                        self.portforwarding_rule = rule
                        break
        return self.portforwarding_rule


    def present_portforwarding_rule(self):
        portforwarding_rule = self.get_portforwarding_rule()
        if portforwarding_rule:
            portforwarding_rule = self.update_portforwarding_rule(portforwarding_rule)
        else:
            portforwarding_rule = self.create_portforwarding_rule()
        return portforwarding_rule


    def create_portforwarding_rule(self):
        args = {}
        args['protocol']            = self.module.params.get('protocol')
        args['publicport']          = self.module.params.get('public_port')
        args['publicendport']       = self.get_public_end_port()
        args['privateport']         = self.module.params.get('private_port')
        args['privateendport']      = self.get_private_end_port()
        args['openfirewall']        = self.module.params.get('open_firewall')
        args['vmguestip']           = self.get_vm_guest_ip()
        args['ipaddressid']         = self.get_ip_address(key='id')
        args['virtualmachineid']    = self.get_vm(key='id')

        self.result['changed'] = True
        if not self.module.check_mode:
            portforwarding_rule = self.cs.createPortForwardingRule(**args)
            poll_async = self.module.params.get('poll_async')
            if poll_async:
                portforwarding_rule = self._poll_job(portforwarding_rule, 'portforwardingrule')
        return portforwarding_rule


    def update_portforwarding_rule(self, portforwarding_rule):
        args = {}
        args['protocol']            = self.module.params.get('protocol')
        args['publicport']          = self.module.params.get('public_port')
        args['publicendport']       = self.get_public_end_port()
        args['privateport']         = self.module.params.get('private_port')
        args['privateendport']      = self.get_private_end_port()
        args['openfirewall']        = self.module.params.get('open_firewall')
        args['vmguestip']           = self.get_vm_guest_ip()
        args['ipaddressid']         = self.get_ip_address(key='id')
        args['virtualmachineid']    = self.get_vm(key='id')

        if self._has_changed(args, portforwarding_rule):
            self.result['changed'] = True
            if not self.module.check_mode:
                # API broken in 4.2.1?, workaround using remove/create instead of update
                # portforwarding_rule = self.cs.updatePortForwardingRule(**args)
                self.absent_portforwarding_rule()
                portforwarding_rule = self.cs.createPortForwardingRule(**args)
                poll_async = self.module.params.get('poll_async')
                if poll_async:
                    portforwarding_rule = self._poll_job(portforwarding_rule, 'portforwardingrule')
        return portforwarding_rule


    def absent_portforwarding_rule(self):
        portforwarding_rule = self.get_portforwarding_rule()

        if portforwarding_rule:
            self.result['changed'] = True
            args = {}
            args['id'] = portforwarding_rule['id']

            if not self.module.check_mode:
                res = self.cs.deletePortForwardingRule(**args)
                poll_async = self.module.params.get('poll_async')
                if poll_async:
                    self._poll_job(res, 'portforwardingrule')
        return portforwarding_rule


    def get_result(self, portforwarding_rule):
        return self.result


def main():
    module = AnsibleModule(
        argument_spec = dict(
            ip_address = dict(required=True),
            protocol= dict(choices=['tcp', 'udp'], default='tcp'),
            public_port = dict(type='int', required=True),
            public_end_port = dict(type='int', default=None),
            private_port = dict(type='int', required=True),
            private_end_port = dict(type='int', default=None),
            state = dict(choices=['present', 'absent'], default='present'),
            open_firewall = dict(choices=BOOLEANS, default=False),
            vm_guest_ip = dict(default=None),
            vm = dict(default=None),
            project = dict(default=None),
            zone = dict(default=None),
            poll_async = dict(choices=BOOLEANS, default=True),
            api_key = dict(default=None),
            api_secret = dict(default=None),
            api_url = dict(default=None),
            api_http_method = dict(default='get'),
        ),
        supports_check_mode=True
    )

    if not has_lib_cs:
        module.fail_json(msg="python library cs required: pip install cs")

    try:
        acs_pf = AnsibleCloudStackPortforwarding(module)
        state = module.params.get('state')
        if state in ['absent']:
            pf_rule = acs_pf.absent_portforwarding_rule()
        else:
            pf_rule = acs_pf.present_portforwarding_rule()

        result = acs_pf.get_result(pf_rule)

    except CloudStackException, e:
        module.fail_json(msg='CloudStackException: %s' % str(e))

    module.exit_json(**result)

# import module snippets
from ansible.module_utils.basic import *
main()
