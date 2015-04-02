# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""deactivates a tunnel - jlucena@
"""

import argparse
import sys
import time

from oauth2client.client import GoogleCredentials
from googleapiclient.discovery import build


def ParseArgs():
  """Parse args for the app, so interactive prompts can be avoided."""

  def Bool(s):
    return s.lower() in ['true', '1']

  parser = argparse.ArgumentParser()
  # Required parameters.
  parser.add_argument('--project', metavar='PROJECT_ID', required=True,
                      help='Google Cloud Platform project ID to use for this '
                         'invocation.')
  parser.add_argument('--region', metavar='REGION_NAME', required=True,
                      help='Region name to use for this invocation.')
  parser.add_argument('--tunnel', metavar='TUNNEL_NAME', required=True,
                      help='Tunnel name to use for this invocation.')
  # Optional parameters.
  parser.add_argument('--debug',
                      default=False, type=Bool,
                      help='(true/false) Enable debugging.')

  return parser.parse_args()



def name_from_url(url):
  return url.split('/')[-1]

def list_tunnels(compute, project, region, debug=False):
  result = compute.vpnTunnels().list(project=project, region=region).execute()
  if debug:
    print 'Found these tunnels in Project: %s Region: %s' % (project, region)
    print 'NAME\tGATEWAY'
    for item in result['items']:
      gateway = name_from_url(item['targetVpnGateway'])
      print '%s\t%s' % (item['name'], gateway)

  return result['items']

def get_tunnel(compute, project, region, tunnel):
  tunnel = compute.vpnTunnels().get(project=project, region=region,
                                    vpnTunnel=tunnel).execute()
  return tunnel

def list_gateways(compute, project, region, debug=False):
  result = compute.targetVpnGateways().list(
      project=project, region=region).execute()
  if debug:
    print 'Found these gateways in Project: %s Region: %s' % (project, region)
    print 'NAME\tNETWORK'
    for item in result['items']:
      print ' %s - %s' % (item['name'], item['network'])
  return result['items']

def get_gateway(compute, project, region, gateway):
  gateway = compute.targetVpnGateways().get(project=project, region=region,
                                            targetVpnGateway=gateway).execute()
  return gateway

def list_routes(compute, project, debug=False):
  result = compute.routes().list(project=project).execute()
  if debug:
    print 'Found these routes in Project: %s' % (project)
    print 'NAME\tNETWORK'
    for item in result['items']:
      network = name_from_url(item['network'])
      print '%s\t%s' % (item['name'], network)

  return result['items']

def get_routes_by_network(compute, project, network):
  routes = list_routes(compute, project)
  matches = []
  for route in routes:
    route_network = name_from_url(route['network'])
    if network == route_network:
      matches.append(route)
  return matches

def get_routes_by_network_with_tunnel(compute, project, network):
  routes_all = get_routes_by_network(compute, project, network)
  routes = []
  for route in routes:
    if route.has_key('nextHopVpnTunnel'):
      routes.append(route)
  return routes

def get_routes_by_tunnel(compute, project, region, tunnel):
  match = '%s/regions/%s/vpnTunnels/%s' % (project, region, tunnel)
  routes_all = list_routes(compute, project)
  routes = []
  for route in routes_all:
    if route.has_key('nextHopVpnTunnel'):
      token = '/'.join(route['nextHopVpnTunnel'].split('/')[-5:])
      if token == match:
        routes.append(route)
  return routes


def get_routes_to_copy(compute, project, region, tunnel, long_way=False,
                       debug=False):
  # Find all the routes that point to this tunnel. Given a single route a
  # 'describe' will do this, but not sure how this is done for multiple routes.
  routes_to_copy = []
  if long_way:
    # Get gateway for the tunnel
    tunnel_obj = get_tunnel(compute, project, region, tunnel)
    if tunnel_obj == None:
      print 'Cannot find tunnel: %s' % (tunnel)
      return

    gateway = name_from_url(tunnel_obj['targetVpnGateway'])
    if debug:
      print '--> Got Gateway %s for Tunnel %s.' % (gateway, tunnel)

    # Get network from the gateway
    gateway_obj = get_gateway(compute, project, region, gateway)
    if gateway_obj == None:
      print 'Cannot find gateway: %s' % (gateway)
      return

    network = name_from_url(gateway_obj['network'])
    if debug:
      print '--> Got Network %s for Gateway %s.' % (network, gateway)

    routes_all = get_routes_by_network(compute, project, network)
    for route in routes_all:
      if route.has_key('nextHopVpnTunnel'):
        tunnel_short = name_from_url(route['nextHopVpnTunnel'])
        if tunnel_short == tunnel:
          routes_to_copy.append(route)
    if debug:
      print '--> Got these Routes for Network %s and Tunnel %s.' % (network,
                                                                    tunnel)


  else:
    routes_to_copy = get_routes_by_tunnel(compute, project, region, tunnel)
    if debug:
      print '--> Got these Routes for Region %s and Tunnel %s.' % (region,
                                                                    tunnel)

  if debug:
    print 'NAME\tNETWORK\tnextHopVpnTunnel'
    for route in routes_to_copy:
      network_short = name_from_url(route['network'])
      print '%s\t%s\t%s' % (route['name'], network_short,
                            route['nextHopVpnTunnel'])
  
  return routes_to_copy


def clone_route(route_obj):
  route_new = {
    'name': route_obj['name'] + '-priority0',
    'network': route_obj['network'],
    'nextHopVpnTunnel': route_obj['nextHopVpnTunnel'],
    'priority': 0,
    'destRange': route_obj['destRange'],
    'description': route_obj['name'] + '|' + str(route_obj['priority']),
  }
  return route_new


def create_instance(compute, project, zone, name):
  source_disk_image = \
  'projects/debian-cloud/global/images/debian-7-wheezy-v20150320'
  machine_type = 'zones/%s/machineTypes/n1-standard-1' % zone
  startup_script = open('startup-script.sh', 'r').read()
  image_url = 'http://storage.googleapis.com/gce-demo-input/photo.jpg'
  image_caption = 'Ready for dessert?'

  config = {
      'name': name,
      'machineType': machine_type,

      # Specify the boot disk and the image to use as a source.
      'disks': [
          {
              'boot': True,
              'autoDelete': True,
              'initializeParams': {
                  'sourceImage': source_disk_image,
              }
          }
      ],

      # Specify a network interface with NAT to access the public
      # internet.
      'networkInterfaces': [{
          'network': 'global/networks/default',
          'accessConfigs': [
              {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
          ]
      }],

      # Allow the instance to access cloud storage and logging.
      'serviceAccounts': [{
          'email': 'default',
          'scopes': [
              'https://www.googleapis.com/auth/devstorage.read_write',
              'https://www.googleapis.com/auth/logging.write'
          ]
      }],

      # Metadata is readable from the instance and allows you to
      # pass configuration from deployment scripts to instances.
      'metadata': {
          'items': [{
              # Startup script is automatically executed by the
              # instance upon startup.
              'key': 'startup-script',
              'value': startup_script
          }, {
              'key': 'url',
              'value': image_url
          }, {
              'key': 'text',
              'value': image_caption
          }, {
              # Every project has a default Cloud Storage bucket that's
              # the same name as the project.
              'key': 'bucket',
              'value': project
          }]
      }
  }

  return compute.instances().insert(
      project=project,
      zone=zone,
      body=config).execute()

def delete_instance(compute, project, zone, name):
  return compute.instances().delete(
      project=project,
      zone=zone,
      instance=name).execute()


def wait_for_operation(compute, project, zone, operation):
  sys.stdout.write('Waiting for operation to finish')
  while True:
    result = compute.zoneOperations().get(
        project=project,
        zone=zone,
        operation=operation).execute()

    if result['status'] == 'DONE':
      print 'done.'
    if 'error' in result:
      raise Exception(result['error'])
      return result
    else:
      sys.stdout.write('.')
      sys.stdout.flush()
      time.sleep(1)

def wait_for_global_operation(compute, project, operation):
  sys.stdout.write('Waiting for operation to finish')
  while True:
    result = compute.globalOperations().get(
        project=project,
        operation=operation).execute()

    if result['status'] == 'DONE':
      print 'done.'
    if 'error' in result:
      raise Exception(result['error'])
      return result
    else:
      sys.stdout.write('.')
      sys.stdout.flush()
      time.sleep(1)


def run_old(project, zone, instance_name):
  credentials = GoogleCredentials.get_application_default()
  compute = build('compute', 'v1', credentials=credentials)

  print 'Creating instance.'

  operation = create_instance(compute, project, zone, instance_name)
  wait_for_operation(compute, project, zone, operation['name'])

  instances = list_instances(compute, project, zone)

  print 'Instances in project %s and zone %s:' % (project, zone)
  for instance in instances:
    print ' - ' + instance['name']

    print """
    Instance created.
    It will take a minute or two for the instance to complete work.
    Check this URL: http://storage.googleapis.com/%s/output.png
    Once the image is uploaded press enter to delete the instance.
    """ % project

    raw_input()

    print 'Deleting instance.'

    operation = delete_instance(compute, project, zone, instance_name)
    wait_for_operation(compute, project, zone, operation['name'])


def run(project, region, tunnel, debug):
  credentials = GoogleCredentials.get_application_default()
  compute = build('compute', 'v1', credentials=credentials)

  # Find all the routes you need to copy
  routes_to_copy = get_routes_to_copy(compute, project, region, tunnel,
                                      long_way=False, debug=debug)
  
  # For each of these, you need to create new route with similar properties,
  # except priority which should be 0 (and the name which can't repeat).
  for route in routes_to_copy:
    route_new = clone_route(route)
    route_created = compute.routes().insert(project=project,
                                            body=route_new).execute()
    print "--> Waiting to create route: %s" % (repr(route_created))
    wait_for_global_operation(compute, project, route_created['name'])

def main():
  print 'Make sure you have run: gcloud auth login'
  pargs = ParseArgs()
  run(pargs.project, pargs.region, pargs.tunnel, pargs.debug)


if __name__ == '__main__':
  main()
