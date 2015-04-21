# Deactivate Tunnel

This python command-line application uses the
[Google Python API Client Library](https://developers.google.com/api-client-library/python/).



## Pre-requisites

1. Create a project on the [Google Developers Console](https://console.developers.google.com) and [enable billing](https://console.developers.google.com/project/_/settings).
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
                            [--sleep SLEEP] [--restore] [--noop] [--debug]
```

The application will:


## Products
- [Google Compute Engine](https://developers.google.com/compute)


## Contributing changes

* See [CONTRIBUTING.md](CONTRIBUTING.md)


## Licensing

* See [LICENSE](LICENSE)
