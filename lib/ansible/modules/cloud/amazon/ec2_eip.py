#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['stableinterface'],
                    'supported_by': 'community'}

from ansible.module_utils.ec2 import camel_dict_to_snake_dict
from ansible.module_utils.aws.core import AnsibleAWSModule

DOCUMENTATION = '''
---
module: ec2_eip
short_description: manages EC2 elastic IP (EIP) addresses.
description:
    - This module can allocate or release an EIP.
    - This module can associate/disassociate an EIP with instances or network interfaces.
version_added: "1.4"
author: "Rick Mendes (@rickmendes) <rmendes@illumina.com>"
options:
  device_id:
    description:
      - The id of the device for the EIP. Can be an EC2 Instance id or Elastic Network Interface (ENI) id.
    required: false
    aliases: [ instance_id ]
    version_added: "2.0"
  public_ip:
    description:
      - The IP address of a previously allocated EIP.
      - If present and device is specified, the EIP is associated with the device.
      - If absent and device is specified, the EIP is disassociated from the device.
    aliases: [ ip ]
  state:
    description:
      - If present, allocate an EIP or associate an existing EIP with a device.
      - If absent, disassociate the EIP from the device and optionally release it.
    choices: ['present', 'absent']
    default: present
  in_vpc:
    description:
      - Allocate an EIP inside a VPC or not. Required if specifying an ENI.
    default: 'no'
    type: bool
    version_added: "1.4"
  reuse_existing_ip_allowed:
    description:
      - Reuse an EIP that is not associated to a device (when available), instead of allocating a new one.
    default: 'no'
    type: bool
    version_added: "1.6"
  release_on_disassociation:
    description:
      - whether or not to automatically release the EIP when it is disassociated
    default: 'no'
    type: bool
    version_added: "2.0"
  private_ip_address:
    description:
      - The primary or secondary private IP address to associate with the Elastic IP address.
    version_added: "2.3"
  allow_reassociation:
    description:
      -  Specify this option to allow an Elastic IP address that is already associated with another
         network interface or instance to be re-associated with the specified instance or interface.
    default: 'no'
    type: bool
    version_added: "2.5"
notes:
   - There may be a delay between the time the EIP is assigned and when
     the cloud instance is reachable via the new address. Use wait_for and
     pause to delay further playbook execution until the instance is reachable,
     if necessary.
   - This module returns multiple changed statuses on disassociation or release.
     It returns an overall status based on any changes occurring. It also returns
     individual changed statuses for disassociation and release.
requirements:
    - boto3
    - botocore
extends_documentation_fragment:
    - aws
    - ec2
'''

EXAMPLES = '''
# Note: These examples do not set authentication details, see the AWS Guide for details.

- name: associate an elastic IP with an instance using awscli 'production' profile
  ec2_eip:
    profile: production
    device_id: i-1212f003
    ip: 93.184.216.119

- name: associate an elastic IP with a device
  ec2_eip:
    device_id: eni-c8ad70f3
    ip: 93.184.216.119

- name: associate an elastic IP with a device and allow reassociation
  ec2_eip:
    device_id: eni-c8ad70f3
    public_ip: 93.184.216.119
    allow_reassociation: yes

- name: disassociate an elastic IP from an instance
  ec2_eip:
    device_id: i-1212f003
    ip: 93.184.216.119
    state: absent

- name: disassociate an elastic IP with a device
  ec2_eip:
    device_id: eni-c8ad70f3
    ip: 93.184.216.119
    state: absent

- name: allocate a new elastic IP and associate it with an instance
  ec2_eip:
    device_id: i-1212f003

- name: allocate a new elastic IP without associating it to anything
  ec2_eip:
    state: present
  register: eip

- name: allocate a new elastic IP inside a VPC in us-west-2
  ec2_eip:
    region: us-west-2
    in_vpc: yes
    state: present
  register: eip
'''

RETURN = '''
allocation_id:
  description: allocation_id of the elastic ip
  returned: success
  type: str
  sample: eipalloc-51aa3a6c
domain:
  description: if we are on a vpc or not (standard)
  returned: success
  type: str
  sample: vpc
association_id:
  description: association id when associating an eip
  returned: success
  type: str
  sample: eipassoc-089c444456f4923
public_ip:
  description: an elastic ip address
  returned: success
  type: str
  sample: 52.88.159.209
public_ipv4_pool:
  description: describes the specified IPv4 address pools
  returned: success
  type: str
  sample: amazon
response_metadata:
  description: aws response metadata
  returned: always
  type: dict
  sample:
    http_headers:
      content-length: 1490
      content-type: text/xml
      date: Tue, 07 Feb 2017 16:43:04 GMT
      server: AmazonEC2
    http_status_code: 200
    request_id: 7f436dea-ed54-11e6-a04c-ab2372a1f14d
    retry_attempts: 0
'''


try:
    import botocore
except ImportError:
    pass    # Handled by AnsibleAWSModule


class EIPException(Exception):
    pass


def associate_ip_and_device(ec2, address, private_ip_address, device_id, allow_reassociation, check_mode, is_aninstance=True):
    if address_is_associated_with_device(ec2, address, device_id, is_aninstance):
        changed = False
        return changed

    if isinstance(address, list):
        address = address[0]

    # If we're in check mode, nothing else to do
    if not check_mode:
        if is_aninstance:
            if address.get('Domain') == "vpc":
                if private_ip_address:
                    response = ec2.associate_address(InstanceId=device_id,
                                                     AllocationId=address.get(
                                                         'AllocationId'),
                                                     PrivateIpAddress=private_ip_address,
                                                     AllowReassociation=allow_reassociation)
                else:
                    response = ec2.associate_address(InstanceId=device_id,
                                                     AllocationId=address.get(
                                                         'AllocationId'),
                                                     AllowReassociation=allow_reassociation)
            else:
                response = ec2.associate_address(InstanceId=device_id,
                                                 PublicIp=address.get(
                                                     'PublicIp'),
                                                 PrivateIpAddress=private_ip_address,
                                                 AllowReassociation=allow_reassociation)
        else:
            if private_ip_address:
                response = ec2.associate_address(NetworkInterfaceId=device_id,
                                                 AllocationId=address.get(
                                                     'AllocationId'),
                                                 PrivateIpAddress=private_ip_address,
                                                 AllowReassociation=allow_reassociation)
            else:
                response = ec2.associate_address(NetworkInterfaceId=device_id,
                                                 AllocationId=address.get(
                                                     'AllocationId'),
                                                 AllowReassociation=allow_reassociation)

    changed = True

    return response, changed


def disassociate_ip_and_device(ec2, address, device_id, check_mode, is_aninstance=True):
    # If we're in check mode, nothing else to do
    if not check_mode:
        if address.get('Domain') == 'vpc':
            response = ec2.disassociate_address(
                AssociationId=address.get('AssociationId'))
        else:
            response = ec2.disassociate_address(
                PublicIp=address.get('PublicIp'))

    changed = True
    return response, changed


def _find_address_by_ip(ec2, public_ip):
    addresses = ec2.describe_addresses(PublicIps=[public_ip])
    address = next(iter(addresses.values()))
    if address:
        return address[0]


def _find_address_by_device_id(ec2, device_id, is_aninstance=True):
    if is_aninstance:
        device_filter = {'Name': 'instance-id', 'Values': [device_id]}
        addresses = ec2.describe_addresses(Filters=[device_filter])
    else:
        network_filter = {
            'Name': 'network-interface-id', 'Values': [device_id]}
        addresses = ec2.describe_addresses(Filters=[network_filter])

    address = next(iter(addresses.values()))
    if address:
        return address[0]


def find_address(ec2, public_ip, device_id, is_aninstance=True):
    # Find an existing Elastic IP address
    if public_ip:
        return _find_address_by_ip(ec2, public_ip)
    elif device_id and is_aninstance:
        return _find_address_by_device_id(ec2, device_id)
    elif device_id:
        return _find_address_by_device_id(ec2, device_id, is_aninstance=False)


def address_is_associated_with_device(ec2, address, device_id, module, is_aninstance=True):
    # Check if the elastic IP is currently associated with the device

    if device_id.startswith('eni-'):
        is_aninstance = False

    if isinstance(address, list):
        address = address[0]

    address = ec2.describe_addresses(PublicIps=[address.get('PublicIp')])

    if address:
        if is_aninstance:
            return address and address.get('InstanceId') == device_id
        else:
            return address and address.get('NetworkInterfaceId') == device_id

    return False


def allocate_address(ec2, domain, reuse_existing_ip_allowed):
    # Allocate a new elastic IP address (when needed) and return it
    if reuse_existing_ip_allowed:
        domain_filter = {'domain': domain or 'standard'}
        all_addresses = ec2.describe_addresses(Filters=[domain_filter])

        if domain == 'vpc':
            unassociated_addresses = [a for a in all_addresses
                                      if not a.association_id]
        else:
            unassociated_addresses = [a for a in all_addresses
                                      if not a.instance_id]
        if unassociated_addresses:
            return unassociated_addresses[0], False

    if not domain:
        domain = 'standard'

    response = ec2.allocate_address(Domain=domain)
    changed = True

    return response, changed


def release_address(ec2, address, check_mode):
    # Release a previously allocated elastic IP address

    # If we're in check mode, nothing else to do
    if check_mode:
        changed = False
        response = None
    else:
        response = ec2.release_address(
            AllocationId=address.get('AllocationId'))
        changed = True

    return response, changed


def find_device(ec2, module, device_id, is_aninstance=True):
    # Attempt to find the EC2 instance and return it

    if is_aninstance:
        reservations = ec2.describe_instances(
            InstanceIds=[device_id])
        if reservations:
            instances = next(iter(reservations.values()))
            if instances:
                return instances[0]
    else:
        eni_interfaces = ec2.describe_network_interfaces(
            NetworkInterfaceIds=[device_id])
        if eni_interfaces:
            interfaces = next(iter(eni_interfaces.values()))
            if interfaces:
                return interfaces[0]

    raise EIPException("could not find instance " + device_id)


def ensure_present(ec2, module, domain, address, private_ip_address, device_id,
                   reuse_existing_ip_allowed, allow_reassociation, check_mode, is_aninstance=True):

    # Return the EIP object since we've been given a public IP

    if not address:
        if check_mode:
            changed = True
            return changed

        address, changed = allocate_address(ec2, domain,
                                            reuse_existing_ip_allowed)

    if device_id:
        # Allocate an IP for instance since no public_ip was provided
        if is_aninstance:
            instance = find_device(ec2, module, device_id)
            if reuse_existing_ip_allowed:
                if instance.get('VpcId') and len(instance.get('VpcId')) > 0 and domain is None:
                    raise EIPException(
                        "You must set 'in_vpc' to true to associate an instance with an existing ip in a vpc")
            # Associate address object (provided or allocated) with instance
            response, changed = associate_ip_and_device(ec2, address, private_ip_address, device_id, allow_reassociation,
                                                        check_mode)

        else:
            instance = find_device(ec2, module, device_id, is_aninstance=False)
            # Associate address object (provided or allocated) with instance
            response, changed = associate_ip_and_device(ec2, address, private_ip_address, device_id, allow_reassociation,
                                                        check_mode, is_aninstance=False)

        if instance.get('VpcId'):
            domain = 'vpc'

    return response, changed


def ensure_absent(ec2, domain, address, device_id, check_mode, is_aninstance=True):
    if not address:
        changed = False
        return response, changed

    # disassociating address from instance
    if device_id:
        if is_aninstance:
            response, changed = disassociate_ip_and_device(
                ec2, address, device_id, check_mode)
        else:
            response, changed = disassociate_ip_and_device(
                ec2, address, device_id, check_mode, is_aninstance=False)
    # releasing address
    else:
        response, changed = release_address(ec2, address, check_mode)

    return response, changed


def main():
    argument_spec = dict(
        device_id=dict(required=False, aliases=['instance_id']),
        public_ip=dict(required=False, aliases=['ip']),
        state=dict(required=False, default='present',
                   choices=['present', 'absent']),
        in_vpc=dict(required=False, type='bool', default=False),
        reuse_existing_ip_allowed=dict(required=False, type='bool',
                                       default=False),
        release_on_disassociation=dict(
            required=False, type='bool', default=False),
        allow_reassociation=dict(type='bool', default=False),
        wait_timeout=dict(default=300, type='int'),
        private_ip_address=dict(required=False, default=None, type='str')
    ))

    module = AnsibleAWSModule(argument_spec=argument_spec,
                              supports_check_mode=True,
                              required_together=[
                                  ['device_id', 'private_ip_address'],
                              ],
                              )

    ec2 = module.client('ec2')

    device_id = module.params.get('device_id')
    instance_id = module.params.get('instance_id')
    public_ip = module.params.get('public_ip')
    private_ip_address = module.params.get('private_ip_address')
    state = module.params.get('state')
    in_vpc = module.params.get('in_vpc')
    domain = 'vpc' if in_vpc else None
    reuse_existing_ip_allowed = module.params.get('reuse_existing_ip_allowed')
    release_on_disassociation = module.params.get('release_on_disassociation')
    allow_reassociation = module.params.get('allow_reassociation')

    changed = False
    response = {}

    if instance_id:
        device_id = instance_id
        an_instance = True
    else:
        if device_id:
            an_instance = None
            if device_id.startswith('i-'):
                an_instance = True
            elif device_id.startswith('eni-'):
                if not in_vpc:
                    module.fail_json(
                        msg="If you are specifying an ENI, in_vpc must be true")
                an_instance = False

    try:
        if device_id:
            address = find_address(
                ec2, public_ip, device_id, is_aninstance=an_instance)
        else:
            address = find_address(ec2, public_ip, None)

        if state == 'present':
            if device_id:
                response, changed = ensure_present(ec2, module, domain, address, private_ip_address, device_id,
                                                   reuse_existing_ip_allowed, allow_reassociation,
                                                   module.check_mode, is_aninstance=an_instance)
            else:
                response, changed = allocate_address(ec2, domain,
                                                     reuse_existing_ip_allowed)
        else:
            if device_id:
                response, changed = ensure_absent(
                    ec2, domain, address, device_id, module.check_mode, is_aninstance=an_instance)
                if release_on_disassociation and changed:
                    response, changed = release_address(
                        ec2, address, module.check_mode)
            else:
                response, changed = release_address(
                    ec2, address, module.check_mode)

    except botocore.exceptions.BotoCoreError as e:
        raise

    result = dict(changed=changed, **camel_dict_to_snake_dict(response))

    module.exit_json(**result)


if __name__ == '__main__':
    main()
