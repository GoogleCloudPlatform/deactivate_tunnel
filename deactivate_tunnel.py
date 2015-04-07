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

"""Deactivates all the routes in a VPN tunnel by setting their priority to 0.

1. The input parameters you need are the project, tunnel name, region.
2. Find all the routes that point to this tunnel. 
3. For each of these, you need to create new route with similar properties,
except priority which should be 0.
4. Sleep a bit (1 min, but configurable).
5. Delete all the routes you found in step #2.

You can also restore any routes previously deactivated by this script by using
the --restore flag.


Note: be sure to run the following before running this script:
 $ gcloud auth login

"""


import argparse
import json
import sys
import time

from oauth2client.client import ApplicationDefaultCredentialsError
from oauth2client.client import GoogleCredentials
from googleapiclient.discovery import build

# The name of this script. This is used to indicate which routes were created
# by this script, so that they can be restored.
APP_NAME = 'deactivate_tunnel'

# This string will be appended to a route name when it's being deactivated.
CLONE_POSTFIX = '-p0'


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
  parser.add_argument('--restore',
                      default=False, action='store_const', const=True,
                      help='Restores any routes previously deactivated '
                      'by this script.')
  parser.add_argument('--noop',
                      default=False, action='store_const', const=True,
                      help='Does not actually create or delete routes.')
  parser.add_argument('--debug',
                      default=False, action='store_const', const=True,
                      help='Enable debugging when set.')

  return parser.parse_args()


def name_from_url(url):
  """ Returns the right most value from a path."""
  return url.split('/')[-1]


def list_routes(compute, project, debug=False):
  """ Returns a list of all routes for the given project."""
  routes = compute.routes().list(project=project).execute()
  if debug:
    print '--> Listing all Routes for Project: %s.' % (project)
    template = '{0:24} {1:24} {2:100}'
    print template.format('NAME', 'NETWORK', 'TUNNEL')
    for route in routes['items']:
      print template.format(route['name'], name_from_url(route['network']),
                            name_from_url(route.get('nextHopVpnTunnel', '/')))
  return routes['items']


def get_routes_by_tunnel(compute, project, region, tunnel, restore, debug):
  """ Filters all routes to a specific project, region and tunnel."""
  match = '%s/regions/%s/vpnTunnels/%s' % (project, region, tunnel)
  routes_all = list_routes(compute, project, debug)
  routes = []
  for route in routes_all:
    if route.has_key('nextHopVpnTunnel'):
      token = '/'.join(route['nextHopVpnTunnel'].split('/')[-5:])
      if token == match and restore == is_route_we_created(route):
        routes.append(route)
  return routes


def insert_route(compute, project, route):
  """ Inserts a new route asynchronously."""
  route_new = compute.routes().insert(project=project, body=route).execute()
  return route_new


def delete_route(compute, project, route):
  """ Deletes an existing route asynchronously."""
  route_deleted = compute.routes().delete(project=project,
                                          route=route).execute()
  return route_deleted


def get_routes_to_clone(compute, project, region, tunnel, restore, debug=False):
  """ Returns all routes that match the project, region and tunnel."""
  routes_to_clone = get_routes_by_tunnel(compute, project, region, tunnel,
                                         restore, debug)
  print '--> Found these Routes for Project: %s Region: %s Tunnel: %s.' % (
      project, region, tunnel)

  template = '{0:24} {1:24} {2:100}'
  print template.format('NAME', 'NETWORK', 'TUNNEL')
  for route in routes_to_clone:
    print template.format(route['name'], name_from_url(route['network']),
                          name_from_url(route['nextHopVpnTunnel']))
    if debug:
      print '%s' % repr(route)

  return routes_to_clone


def is_route_we_created(route):
  """ Returns true if the route was one that was created by this script."""
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
  """ Clones a route from an existing on that we may have created before."""
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
        'description': route.get('description', ''),
    }
    route_cloned = {
        'name': route['name'] + CLONE_POSTFIX,
        'network': route['network'],
        'nextHopVpnTunnel': route['nextHopVpnTunnel'],
        'priority': 0,
        'destRange': route['destRange'],
        'description': json.dumps(original, separators=(',', ':')),
    }
  return route_cloned


def wait_for_global_operation(compute, project, operations):
  """ Returns when all operations have completed (with success or error). """
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
  """ Sleeps for the given number of seconds."""
  sys.stdout.write('Sleeping an additional %d seconds' % seconds)
  for _ in range(0, seconds):
    sys.stdout.write('.')
    sys.stdout.flush()
    time.sleep(1)
  sys.stdout.write('done.\n')


def run(compute, project, region, tunnel, restore, sleep, debug, noop):
  """ Executes the route cloning logic."""
  # Find all the routes you need to clone.
  routes_to_clone = get_routes_to_clone(compute, project, region, tunnel,
                                        restore, debug)

  # For each of these existing routes make a clone of their settings and request
  # that they be created.
  print '--> Requesting the creation of these routes:'
  template = '{0:24} {1:24} {2:100}'
  print template.format('NAME', 'ORIGINAL NAME', 'TARGET LINK')
  operations = []
  for route in routes_to_clone:
    route_cloned = clone_route(route)
    if not noop:
      route_created = insert_route(compute, project, route_cloned)
    else:
      route_created = route_cloned.copy()
      route_created['targetLink'] = 'N/A'
    operations.append(route_created['name'])
    print template.format(route_cloned['name'], route['name'],
                          route_created['targetLink'])
    if debug:
      print '%s' % repr(route_created)

  # Wait for these new routes to be established.
  if not noop:
    wait_for_global_operation(compute, project, operations)
  operations = []

  # Sleep for any additional time if you were requested to do so.
  if sleep > 0:
    sleep_seconds(sleep)

  # Delete the original routes that we were asked to clone.
  print '--> Requesting the deletion of these routes:'
  print 'NAME'
  for route in routes_to_clone:
    if not noop:
      route_deleted = delete_route(compute, project, route['name'])
    else:
      route_deleted = route
    operations.append(route_deleted['name'])
    print '%s' % (route['name'])
    if debug:
      print '%s' % repr(route_deleted)

  # Wait for these old routes to be removed.
  if not noop:
    wait_for_global_operation(compute, project, operations)
  operations = []


def main():
  # TODO(jlucena): Check that gcloud auth login has been run and message
  # accordingly
  pargs = ParseArgs()

  credentials = None
  try:
    credentials = GoogleCredentials.get_application_default()
  except ApplicationDefaultCredentialsError:
    print 'Please authenticate first using:'
    print ' $ gcloud auth login'
    return
  compute = build('compute', 'v1', credentials=credentials)


  run(compute, pargs.project, pargs.region, pargs.tunnel, pargs.restore,
      pargs.sleep, pargs.debug, pargs.noop)


if __name__ == '__main__':
  main()
