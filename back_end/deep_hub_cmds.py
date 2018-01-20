
import boto3

def list_vpc(ec2):
    return [x['DhcpOptionsId'] for x in ec2.meta.client.describe_vpcs()['Vpcs']]

def list_ebs(ec2):
    pass

def launch_spot_instance(limit_price, ami, key_name, security_id, instance_type, security_group, availability_zone):
    client = boto3.client('ec2')
    try:
        response = client.request_spot_instances(
            DryRun=False,
            SpotPrice=limit_price,
            ClientToken='string',
            InstanceCount=1,
            Type='one-time',
            LaunchSpecification={
                'ImageId': ami,
                'KeyName': key_name,
                'SecurityGroups': [security_id],
                'InstanceType': instance_type,
                'Placement': {
                    'AvailabilityZone': availability_zone,
                },
                'EbsOptimized': False,
                'Monitoring': {
                    'Enabled': False
                },
                'SecurityGroupIds': [
                    security_id ,
                ],
                'SecurityGroups': [
                    security_group,
                ]
            }
        )
    except Exception as e:
        raise e


def mount_volume(volume_id, instance_id):
    ec2 = boto3.resource('ec2')
    v = ec2.Volume(volume_id)
    v.attach_to_instance(InstanceId=instance_id, Device='/dev/sdf', DryRun=False)

def exec_cmd(ssm_client, cmds, instance_id):
    resp = ssm_client.send_command(
        DocumentName="AWS-RunShellScript",  # One of AWS' preconfigured documents
        Parameters={'commands': cmds},
        InstanceIds=instance_id,
    )

    # return ec2.meta.client.describe_volumes()['Volumes'][1]

def get_ip_address_spot_instance(spot_request_id):
    ec2 = boto3.resource('ec2')
    response = ec2.meta.client.describe_spot_instance_requests(Filters=[{'Name': 'spot-instance-request-id', 'Values': [spot_request_id]}])



def list_security_group(vpc_id):
    pass

def availability_zones():
    pass

def get_instance_types():
    return ["p2.xlarge", "t2.nano"]

def get_public_dns_address(instance_id):
    ec2 = boto3.resource('ec2')
    instances = [x['Instances'] for x in ec2.meta.client.describe_instances()['Reservations']]
    for x in instances:
        if x[0]['InstanceId'] is instance_id:
            return x[0]['PublicDnsName']



