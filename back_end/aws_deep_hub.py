import argparse
import yaml
import boto3
import webbrowser
import functools
import random
import time

parser = argparse.ArgumentParser(description='AWS Deep Hub')
parser.add_argument('--config_file', default='', type=str, metavar='N', help='config file for launch or shutdown')
parser.add_argument('--launch', dest='launch', action='store_true', help='launches an aws deep hub notebook')
parser.add_argument('--shutdown', dest='shutdown', action='store_true', help='shutsdown an aws deep hub notebook')



def launch_spot_instance(spot_price, ami, key_name, instance_type, security_group_id, availability_zone, iam_role):
    """" returns request ID """    
    client = boto3.client('ec2')
    try:
        response = client.request_spot_instances(
            DryRun=False,
            SpotPrice=spot_price,
            ClientToken=str(random.randint(0,1000000)),
            InstanceCount=1,
            Type='one-time',
            LaunchSpecification={
                'ImageId': ami,
                'KeyName': key_name,
                'InstanceType': instance_type,
                'Placement': {
                    'AvailabilityZone': availability_zone,
                },
                'EbsOptimized': False,
                'Monitoring': {
                    'Enabled': False
                },
                'SecurityGroupIds': [
                    security_group_id ,
                ],
                'IamInstanceProfile': {
                    'Arn': iam_role ,
                    }
            }
        )
        return response['SpotInstanceRequests'][0]['SpotInstanceRequestId']
    except Exception as e:
        raise e

def check_spot_request(request_id):
    client = boto3.client('ec2')
    response = client.describe_spot_instance_requests(SpotInstanceRequestIds=[request_id])
    return response['SpotInstanceRequests'][0]['Status']['Code'] == 'fulfilled'

def get_spot_request_instance_id(request_id):
    client = boto3.client('ec2')
    response = client.describe_spot_instance_requests(SpotInstanceRequestIds=[request_id])
    if len( response['SpotInstanceRequests']) == 1:
        return response['SpotInstanceRequests'][0]['InstanceId']
    return None
    
    
def attach_volume(instance_id, volume_id):
    client = boto3.client('ec2')
    response = client.attach_volume(Device='/dev/xvdh', InstanceId=instance_id, VolumeId=volume_id)
    return response['ResponseMetadata']['HTTPStatusCode'] == 200
        
def check_volume(volume_id):    
    client = boto3.client('ec2')
    response = client.describe_volumes(VolumeIds=[volume_id])
    return response['Volumes'][0]['State'] == 'in-use'

def mount_volume(instance_id, device, mount_point):
    """" return command id """
    ssm_client = boto3.client('ssm')
    resp = ssm_client.send_command(
        DocumentName="AWS-RunShellScript", # One of AWS' preconfigured documents
        Parameters={'commands': ['sudo mount ' + device + ' ' + mount_point]},
        InstanceIds=[instance_id])
    return resp['Command']['CommandId']

def launch_nb_browser(instance_id):
    client = boto3.client('ec2')
    response = response = client.describe_instances(InstanceIds=[instance_id])
    public_dns = response['Reservations'][0]['Instances'][0]['NetworkInterfaces'][0]['Association']['PublicDnsName']
    
    # form notebook address
    address = 'https://' + public_dns  + ':8888'
    
    webbrowser.open(address)

def check_cmd(command_id, instance_id):
    ssm_client = boto3.client('ssm')
    cmi = ssm_client.get_command_invocation(CommandId=command_id, \
                                            InstanceId=instance_id)
    return cmi['Status'] == 'Success'

def is_instance_running(instance_id):
    client = boto3.client('ec2')
    response = client.describe_instances(InstanceIds=[instance_id])
    return response['Reservations'][0]['Instances'][0]['State']['Code'] == 16

def func_spin(func, timeout=5, sleep_interval=0.3):
    now = time.clock()
    while True:
        if func() :
            return True
        elif time.clock() - now > timeout:
            return False
        else:
            time.sleep(sleep_interval)    

def is_instance_visible_to_ssm(instance_id):
    ssm_client = boto3.client('ssm')
    response = ssm_client.describe_instance_information(InstanceInformationFilterList=[{ 'key' : 'InstanceIds', \
                                                                                    'valueSet' : [instance_id]}])
    return len(response['InstanceInformationList']) == 1

def main():    
    global arg
    arg = parser.parse_args()
    
    with open(arg.config_file, 'r') as f:
        config = f.read()
        
    config = yaml.load(config)
    
    print('Making spot request, config : ', config)
    # launch spot request
    request_id = launch_spot_instance(spot_price=config['spot_price'], ami=config['ami'], key_name=config['key_name'], \
                         security_group_id=config['security_group_id'], instance_type=config['instance_type'], \
                         availability_zone=config['availability_zone'], iam_role=config['iam_role'])
    
    # spin and check when its fulfilled 
    check = functools.partial(check_spot_request, request_id)
    ret = func_spin(check, timeout=10)
    
    if not ret:
        print('spot request failed!')
        return 
            
    
    # get instance id     
    instance_id = get_spot_request_instance_id(request_id)
    
    # spin and check when its fulfilled 
    check = functools.partial(is_instance_running, instance_id)
    ret = func_spin(check, timeout=10)
    
    if not ret:
        print('instance does not seem to be running!')
        return             
        
    print('Attaching volume: ', config['volume_id'])
    
    # then attach specified volume
    attach_volume(instance_id, config['volume_id'])
    
    # then check volume is attached
    check = functools.partial(check_volume, config['volume_id'])
    
    ret = func_spin(check, timeout=10)
    
    if not ret:
        print('volume attach failed!')
        return 

    # then check volume is attached
    check = functools.partial(is_instance_visible_to_ssm, instance_id)
    
    ret = func_spin(check, timeout=60, sleep_interval=1.5)
    
    if not ret:
        print('instance not found by ssm!')
        return 
    
    device = None
    if 'p' in config['instance_type']:
        device = '/dev/xvdf'
    elif 'm5d' in config['instance_type']:
        device = '/dev/nvme2n1'
    elif 'm5' in config['instance_type']:
        device = '/dev/nvme1n1'
    
    mount_point = '/home/ubuntu/work'
    print('mounting {}, to point {} for instance {}'.format(device, mount_point, instance_id))
    
    command_id = mount_volume(instance_id, device, mount_point)

    # then check volume is attached
    check = functools.partial(check_cmd, command_id, instance_id)
    
    ret = func_spin(check, timeout=10)
    
    if not ret:
        print('mount failed!')
        return 
    
    launch_nb_browser(instance_id)
    
if __name__=='__main__':
    main()