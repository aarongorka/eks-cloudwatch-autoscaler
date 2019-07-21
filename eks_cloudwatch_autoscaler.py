#!/usr/bin/env python3
import logging
from kubernetes import client, config, utils
import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_container_resources(core_api):
    """
    TODO:
      * return only running containers
      * associate container with node and therefore ASG
    """

    mem = 0
    cpu = 0
    pods = core_api.list_pod_for_all_namespaces().items
    for pod in pods:
        containers = [container for container in pod.spec.containers]
        for container in containers:
            mem_string = None
            cpu_string = None

            try:
                mem_string = container.resources.limits['memory']
            except TypeError:
                logging.warning(f"Pod {pod.metadata.name} in namespace {pod.metadata.namespace} has no memory limit, please apply a LimitRange")

            try:
                cpu_string = container.resources.requests['cpu']
            except TypeError:
                logging.warning(f"Pod {pod.metadata.name} in namespace {pod.metadata.namespace} has no cpu request, please apply a LimitRange")
            
            if mem_string != None:
                mem += int(mem_string.rstrip('Mi'))
            if cpu_string != None:
                cpu += int(cpu_string.rstrip('m'))

    logging.info(f'Total memory reservation is {mem}Mi')
    logging.info(f'Total CPU request is {cpu}m')
    return mem, cpu

def get_node_resources(core_api):
    """
    TODO:
      * validate that node is running
      * associate with ASG
    """

    mem = 0
    cpu = 0
    nodes = core_api.list_node().items
    for node in nodes:
        mem_ki = int(node.status.allocatable['memory'].rstrip('Ki'))
        mem += int(mem_ki / 1024)  # convert to Mi, same as container spec

        cores = int(node.status.allocatable['cpu'])
        cpu += int(cores * 1000)  # 1 vCPU == 1000m https://kubernetes.io/docs/concepts/configuration/manage-compute-resources-container/#meaning-of-cpu
    logging.info(f'Total cluster memory is {mem}Mi')
    logging.info(f'Total cluster CPU is {cpu}m')
    return mem, cpu

config.load_kube_config()
k8s_client = client.ApiClient()
core_api = client.CoreV1Api(k8s_client)

container_resources = get_container_resources(core_api)
node_resources = get_node_resources(core_api)

cpu_reservation = int(container_resources[0] / node_resources[0] * 100)
mem_reservation = int(container_resources[0] / node_resources[1] * 100)
logging.info(f'Cluster CPU reservation is {cpu_reservation}%')
logging.info(f'Cluster memory reservation is {mem_reservation}%')

def put_cw_metrics(mem, cpu, asg):
    dimensions = [{"Name": "AutoScalingGroupName", "Value": asg}]
    response = cloudwatch.put_metric_data(
        Namespace='EksAutoscaling',
        MetricData=[
            {
                "MetricName": "MemoryReservation",
                "Dimensions": dimensions,
                "Value": mem_reservation
            },
            {
                "MetricName": "CPUReservation",
                "Dimensions": dimensions,
                "Value": cpu_reservation
            }
        ]
    )
