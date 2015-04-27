# Deactivate Tunnel

This python command-line application that uses the
[Google Python API Client Library](https://developers.google.com/api-client-library/python/)
to deactivate a VPN tunnel. This is done as follows:

1. All existing routes over the tunnel are cloned changing their name and
setting their priority to 2000 (the higher the value, the lower the priority).
2. The original routes are then deleted, leaving only the cloned routes in
place.

Traffic should then move to routes with a higher priority over a different
tunnel. Routes on the other side of the tunnel will need to be similarly
deprioritized in order for prevent incoming traffic from passing through 
the tunnel (through a similar process scripted against that specific gateway).

Once this occurs, there is no longer any traffic flowing over this
tunnel and it can be considered deactivated for the purposes of maintenance
or other changes.

After maintenance has been performed this application can be used to restore
the routes on this tunnel back to their original name and priority. (Routes
on the other side of the tunnel can be restored as well).

## Pre-requisites

1. Access to a project on the
[Google Developers Console](https://console.developers.google.com)
that uses the [VPN](https://cloud.google.com/compute/docs/vpn) feature.
2. Install the [Google Cloud SDK](https://cloud.google.com/sdk/)

```bash
curl https://sdk.cloud.google.com | bash
gcloud auth login
gcloud config set project your-project-id
```
3. Install dependencies using [pip](https://pypi.python.org/pypi/pip)

```bash
pip install -r requirements.txt
```

## Running the application

```bash
python deactivate_tunnel.py

usage: deactivate_tunnel.py [-h] --project PROJECT_ID --region REGION_NAME
                            --tunnel TUNNEL_NAME [--priority PRIORITY]
                            [--sleep SLEEP] [--restore] [--noop] [--v]

Deactivates a VPN tunnel on the Google Cloud Platform

optional arguments:
  -h, --help            show this help message and exit
  --project PROJECT_ID  Required - Google Cloud Platform project ID to use for
                        this invocation.
  --region REGION_NAME  Required - Region name to use for this invocation.
  --tunnel TUNNEL_NAME  Required - Tunnel name to use for this invocation.
  --priority PRIORITY   The priority to set the new routes it creates. The
                        default is 2000.
  --sleep SLEEP         Seconds to sleep before removing old routes.
  --restore             Restores any routes previously deactivated by this
                        script.
  --noop                Shows what would happen but does not actually create
                        or delete routes.
  --v                   Displays verbose output and debugging.
```

The application will deactivate the tunnel as follows:
 1. Find all routes for the given `--project`, `--region` and `--tunnel`.
 2. For each of these routes, clone the route giving it a new name and
`--priority`.
 3. Sleep for any optional `--sleep` time that was provided.
 4. Delete the original routes that were cloned.
 5. Sleep again for any optional `--sleep` time that was provided.

To reactivate the tunnel the application can be used as follows:
 1. The `--restore` option can then be used to reactivate a tunnel by reverting
    the cloned routes back to their original name an priority and then deleting
    the clones.

## Products
- [Google Compute Engine](https://developers.google.com/compute)


## Contributing changes

* See [CONTRIBUTING.md](CONTRIBUTING.md)


## Licensing

* See [LICENSE](LICENSE)
