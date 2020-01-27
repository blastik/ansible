#!/usr/bin/python
# Copyright: (c) 2018, David C Martin @blastik
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from ansible.module_utils.aws.core import AnsibleAWSModule
from ansible.module_utils.ec2 import camel_dict_to_snake_dict, AWSRetry
from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: ec2_lt_info
short_description: 
description:
  - 
version_added: "2.10"
requirements: [ boto3 ]
author: "David C. Martin (@blastik)"
options:
  name:
    description:
      - 
      - 
    type: str
    required: false
  tags:
    description:
      - >
    required: false
    type: dict
extends_documentation_fragment:
    - aws
    - ec2
'''

EXAMPLES = '''
# Note: These examples do not set authentication details, see the AWS Guide for details.
# Find all groups
- ec2_asg_info:
  register: asgs
# Find a group with matching name/prefix
- ec2_asg_info:
    name: public-webserver-asg
  register: asgs
# Find a group with matching tags
'''

RETURN = '''
---
'''

try:
    import botocore
except ImportError:
    pass    # Handled by AnsibleAWSModule

try:
    import botocore
except ImportError:
    pass    # Handled by AnsibleAWSModule


def match_asg_tags(tags_to_match, asg):
    for key, value in tags_to_match.items():
        for tag in asg['Tags']:
            if key == tag['Key'] and value == tag['Value']:
                break
        else:
            return False
    return True


def find_asgs(conn, module, name=None, tags=None):
    """
    Args:
        conn (boto3.AutoScaling.Client): Valid Boto3 ASG client.
        name (str): Optional name of the ASG you are looking for.
        tags (dict): Optional dictionary of tags and values to search for.
    Basic Usage:
        >>> name = 'public-webapp-production'
        >>> tags = { 'env': 'production' }
        >>> conn = boto3.client('autoscaling', region_name='us-west-2')
        >>> results = find_asgs(name, conn)
    Returns:
        List
        [
            {
                "auto_scaling_group_arn": (
                    "arn:aws:autoscaling:us-west-2:275977225706:autoScalingGroup:58abc686-9783-4528-b338-3ad6f1cbbbaf:"
                    "autoScalingGroupName/public-webapp-production"
                ),
                "auto_scaling_group_name": "public-webapp-production",
                "availability_zones": ["us-west-2c", "us-west-2b", "us-west-2a"],
                "created_time": "2016-02-02T23:28:42.481000+00:00",
                "default_cooldown": 300,
                "desired_capacity": 2,
                "enabled_metrics": [],
                "health_check_grace_period": 300,
                "health_check_type": "ELB",
                "instances":
                [
                    {
                        "availability_zone": "us-west-2c",
                        "health_status": "Healthy",
                        "instance_id": "i-047a12cb",
                        "launch_configuration_name": "public-webapp-production-1",
                        "lifecycle_state": "InService",
                        "protected_from_scale_in": false
                    },
                    {
                        "availability_zone": "us-west-2a",
                        "health_status": "Healthy",
                        "instance_id": "i-7a29df2c",
                        "launch_configuration_name": "public-webapp-production-1",
                        "lifecycle_state": "InService",
                        "protected_from_scale_in": false
                    }
                ],
                "launch_config_name": "public-webapp-production-1",
                "launch_configuration_name": "public-webapp-production-1",
                "load_balancer_names": ["public-webapp-production-lb"],
                "max_size": 4,
                "min_size": 2,
                "new_instances_protected_from_scale_in": false,
                "placement_group": None,
                "status": None,
                "suspended_processes": [],
                "tags":
                [
                    {
                        "key": "Name",
                        "propagate_at_launch": true,
                        "resource_id": "public-webapp-production",
                        "resource_type": "auto-scaling-group",
                        "value": "public-webapp-production"
                    },
                    {
                        "key": "env",
                        "propagate_at_launch": true,
                        "resource_id": "public-webapp-production",
                        "resource_type": "auto-scaling-group",
                        "value": "production"
                    }
                ],
                "target_group_names": [],
                "target_group_arns": [],
                "termination_policies":
                [
                    "Default"
                ],
                "vpc_zone_identifier":
                [
                    "subnet-a1b1c1d1",
                    "subnet-a2b2c2d2",
                    "subnet-a3b3c3d3"
                ]
            }
        ]
    """

    try:
        asgs_paginator = conn.get_paginator('describe_auto_scaling_groups')
        asgs = asgs_paginator.paginate().build_full_result()
    except ClientError as e:
        module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))

    if not asgs:
        return asgs
    try:
        region, ec2_url, aws_connect_kwargs = get_aws_connection_info(
            module, boto3=True)
        elbv2 = boto3_conn(module, conn_type='client', resource='elbv2',
                           region=region, endpoint=ec2_url, **aws_connect_kwargs)
    except ClientError as e:
        # This is nice to have, not essential
        elbv2 = None
    matched_asgs = []

    if name is not None:
        # if the user didn't specify a name
        name_prog = re.compile(r'^' + name)

    for asg in asgs['AutoScalingGroups']:
        if name:
            matched_name = name_prog.search(asg['AutoScalingGroupName'])
        else:
            matched_name = True

        if tags:
            matched_tags = match_asg_tags(tags, asg)
        else:
            matched_tags = True

        if matched_name and matched_tags:
            asg = camel_dict_to_snake_dict(asg)
            # compatibility with ec2_asg module
            if 'launch_configuration_name' in asg:
                asg['launch_config_name'] = asg['launch_configuration_name']
            # workaround for https://github.com/ansible/ansible/pull/25015
            if 'target_group_ar_ns' in asg:
                asg['target_group_arns'] = asg['target_group_ar_ns']
                del(asg['target_group_ar_ns'])
            if asg.get('target_group_arns'):
                if elbv2:
                    try:
                        tg_paginator = elbv2.get_paginator(
                            'describe_target_groups')
                        tg_result = tg_paginator.paginate(
                            TargetGroupArns=asg['target_group_arns']).build_full_result()
                        asg['target_group_names'] = [tg['TargetGroupName']
                                                     for tg in tg_result['TargetGroups']]
                    except ClientError as e:
                        if e.response['Error']['Code'] == 'TargetGroupNotFound':
                            asg['target_group_names'] = []
            else:
                asg['target_group_names'] = []
            matched_asgs.append(asg)

    return matched_asgs


def main():

    argument_spec = ec2_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type='str'),
            tags=dict(type='dict'),
        )
    )
    module = AnsibleModule(argument_spec=argument_spec)
    if module._name == 'ec2_asg_facts':
        module.deprecate(
            "The 'ec2_asg_facts' module has been renamed to 'ec2_asg_info'", version='2.13')

    if not HAS_BOTO3:
        module.fail_json(msg='boto3 required for this module')

    asg_name = module.params.get('name')
    asg_tags = module.params.get('tags')

    try:
        region, ec2_url, aws_connect_kwargs = get_aws_connection_info(
            module, boto3=True)
        autoscaling = boto3_conn(module, conn_type='client', resource='autoscaling',
                                 region=region, endpoint=ec2_url, **aws_connect_kwargs)
    except ClientError as e:
        module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))

    results = find_asgs(autoscaling, module, name=asg_name, tags=asg_tags)
    module.exit_json(results=results)


if __name__ == '__main__':
    main()
