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

""" Deactivates all the routes in a VPN tunnel by setting their priority to 0.
"""


import argparse
import json
import sys
import time

from oauth2client.client import GoogleCredentials
from googleapiclient.discovery import build


APP_NAME = 'deactivate_tunnel'


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
  parser.add_argument('--sleep',
                      default=0, type=int,
                      help='Seconds to sleep before removing old routes.')
  parser.add_argument('--noop',
                      default=False, type=Bool,
                      help='Does not actually create or remove any routes.')
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
        # Check the description to see that it is not indeed one that we have
        # already created.
        if 'description' in route.keys():
          try:
            description = json.loads(route['description'])
            if APP_NAME in description.keys():
              # Skip it.
              continue
          except ValueError:
            pass
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
  description = {
      APP_NAME: 1,
      'name': route_obj['name'],
      'priority': route_obj['priority'],
  }
  route_new = {
      'name': route_obj['name'] + '-priority0',
      'network': route_obj['network'],
      'nextHopVpnTunnel': route_obj['nextHopVpnTunnel'],
      'priority': 0,
      'destRange': route_obj['destRange'],
      'description': json.dumps(description, separators=(',', ':')),
  }
  return route_new


def wait_for_global_operation(compute, project, operations):
  sys.stdout.write('Waiting for operation(s) to finish')
  results = []
  for operation in operations:
    while True:
      result = compute.globalOperations().get(
          project=project,
          operation=operation).execute()

      if result['status'] == 'DONE':
        if 'error' in result:
          raise Exception(result['error'])
        results.append(result)
        break
      else:
        sys.stdout.write('.')
        sys.stdout.flush()
        time.sleep(1)
  sys.stdout.write('done.\n')
  return results


def sleep_seconds(seconds):
  sys.stdout.write('Sleeping an additional %d seconds' % seconds)
  for _ in range(0, seconds):
    sys.stdout.write('.')
    sys.stdout.flush()
    time.sleep(1)
  sys.stdout.write('done.\n')


def run(project, region, tunnel, debug, sleep, noop):
  credentials = GoogleCredentials.get_application_default()
  compute = build('compute', 'v1', credentials=credentials)

  # Find all the routes you need to copy
  routes_to_copy = get_routes_to_copy(compute, project, region, tunnel,
                                      long_way=False, debug=debug)

  # For each of these, you need to create new route with similar properties,
  # except priority which should be 0 (and the name which can't repeat).
  operations = []
  for route in routes_to_copy:
    route_new = clone_route(route)
    if not noop:
      route_created = compute.routes().insert(project=project,
                                              body=route_new).execute()
    else:
      route_created = {'name': route_new}
    operations.append(route_created['name'])
    if debug:
      print '--> Requested the creation of route: %s' % (repr(route_created))

  # Wait for these new routes to be established
  if not noop:
    wait_for_global_operation(compute, project, operations)

  # Sleep if you need to for additional time.
  if sleep > 0:
    sleep_seconds(sleep)


def main():
  # print 'Make sure you have run: gcloud auth login'
  pargs = ParseArgs()
  run(pargs.project, pargs.region, pargs.tunnel, pargs.debug, pargs.sleep,
      pargs.noop)


if __name__ == '__main__':
  main()
