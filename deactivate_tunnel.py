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
  parser.add_argument('--revert',
                      default=False, action='store_const', const=True,
                      help='Reactivates any routes originally deactivated '
                      'by this script.')
  parser.add_argument('--noop',
                      default=False, action='store_const', const=True,
                      help='Does not actually create or remove any routes.')
  parser.add_argument('--debug',
                      default=False, action='store_const', const=True,
                      help='Enable debugging when set.')

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


def insert_route(compute, project, route):
  route_new = compute.routes().insert(project=project, body=route).execute()
  return route_new


def delete_route(compute, project, route):
  route_deleted = compute.routes().delete(project=project,
                                          route=route).execute()
  return route_deleted


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


def get_routes_by_tunnel(compute, project, region, tunnel, revert):
  match = '%s/regions/%s/vpnTunnels/%s' % (project, region, tunnel)
  routes_all = list_routes(compute, project)
  routes = []
  for route in routes_all:
    if route.has_key('nextHopVpnTunnel'):
      token = '/'.join(route['nextHopVpnTunnel'].split('/')[-5:])
      if token == match and revert == is_route_we_created(route):
        routes.append(route)
  return routes


def get_routes_to_copy(compute, project, region, tunnel, revert, long_way=False,
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
        if tunnel_short == tunnel and revert == is_route_we_created(route):
          routes_to_copy.append(route)
    if debug:
      print '--> Got these Routes for Network %s and Tunnel %s.' % (network,
                                                                    tunnel)

  else:
    routes_to_copy = get_routes_by_tunnel(compute, project, region, tunnel,
                                          revert)
    if debug:
      print '--> Got these Routes for Project: %s Region: %s Tunnel: %s.' % (
          project, region, tunnel)

  if debug:
    template = '{0:24} {1:24} {2:100}'
    print template.format('NAME', 'NETWORK', 'nextHopVpnTunnel')
    for route in routes_to_copy:
      network_short = name_from_url(route['network'])
      print template.format(route['name'], network_short,
                            route['nextHopVpnTunnel'])

  return routes_to_copy


def is_route_we_created(route):
  found = False
  if 'description' in route.keys():
    try:
      original = json.loads(route['description'])
      if APP_NAME in original.keys():
        found = True
    except ValueError:
      pass
  return found


def clone_route(route):
  if is_route_we_created(route):
    original = json.loads(route['description'])
    route_cloned = {
        'name': original['name'],
        'network': route['network'],
        'nextHopVpnTunnel': route['nextHopVpnTunnel'],
        'priority': original['priority'],
        'destRange': route['destRange'],
        'description': original['description'],
    }
  else:
    original = {
        APP_NAME: 1,
        'name': route['name'],
        'priority': route['priority'],
        'description': route['description'],
    }
    route_cloned = {
        'name': route['name'] + '-priority0',
        'network': route['network'],
        'nextHopVpnTunnel': route['nextHopVpnTunnel'],
        'priority': 0,
        'destRange': route['destRange'],
        'description': json.dumps(original, separators=(',', ':')),
    }
  return route_cloned


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


def run(project, region, tunnel, revert, sleep, debug, noop):
  credentials = GoogleCredentials.get_application_default()
  compute = build('compute', 'v1', credentials=credentials)
  operations = []

  # Find all the routes you need to clone.
  routes_to_copy = get_routes_to_copy(compute, project, region, tunnel, revert,
                                      long_way=False, debug=debug)

  # For each of these, you need to create new route with similar properties,
  # except priority which should be 0 (and the name which can't repeat).

  if debug:
    print '--> Requested the creation of these routes:'
  for route in routes_to_copy:
    route_cloned = clone_route(route)
    if not noop:
      route_created = insert_route(compute, project, route_cloned)
    else:
      route_created = route_cloned
    operations.append(route_created['name'])
    if debug:
      print '%s\t%s' % (route_created['name'], repr(route_created))

  # Wait for these new routes to be established
  if not noop:
    wait_for_global_operation(compute, project, operations)
  operations = []

  # Sleep if you need to for additional time.
  if sleep > 0:
    sleep_seconds(sleep)

  # Now that the original routes have been cloned at a lower priority, we can
  # delete them.
  if debug:
    print '--> Requested the deletion of these routes:'
  for route in routes_to_copy:
    if not noop:
      route_deleted = delete_route(compute, project, route['name'])
    else:
      route_deleted = route
    operations.append(route_deleted['name'])
    if debug:
      print '%s\t%s' % (route_deleted['name'], repr(route_deleted))

  # Wait for these old routes to be removed.
  if not noop:
    wait_for_global_operation(compute, project, operations)
  operations = []


def main():
  # print 'Make sure you have run: gcloud auth login'
  pargs = ParseArgs()
  run(pargs.project, pargs.region, pargs.tunnel, pargs.revert, pargs.sleep,
      pargs.debug,
      pargs.noop)


if __name__ == '__main__':
  main()
