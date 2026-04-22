# Fair Data Space

A Flask-based web application for discovering datasets across [FAIR Data Points](https://www.fairdatapoint.org/) (FDPs), composing standardized data access request emails, and executing authenticated SPARQL queries.

One codebase serves multiple data spaces — each deployment picks its identity (branding, colors, default FDPs, page content) via the `DATASPACE` environment variable. See [Multi-dataspace architecture](#multi-dataspace-architecture) below.

## Overview

Data visiting (code-to-data) is an approach where queries are sent to datasets for local execution, returning only verified results. This tool handles the **requester** side of that workflow:

1. **Discover** datasets across multiple FAIR Data Points
2. **Browse and filter** datasets by theme, keyword, or free-text search
3. **Compose** standardized data access request emails grouped by contact
4. **Query** SPARQL endpoints discovered from dataset distributions

## Features

### Dataset Discovery
- Add and manage FAIR Data Point endpoints (single or index FDPs)
- Browse datasets with filtering by theme, keyword, and free-text search
- Pagination and sorting for large dataset collections
- Automatic discovery of SPARQL endpoints from DCAT distributions

### Data Access Requests
- Add datasets to a request basket
- Compose data access requests with structured metadata (name, affiliation, ORCID, purpose)
- Automatically group and generate separate emails per dataset contact
- Preview and copy composed request emails

### Authenticated SPARQL Queries
- Log in with credentials for SPARQL endpoint authentication
- Execute read-only SPARQL queries against discovered endpoints
- Client-side query federation across multiple endpoints
- View aggregated results with per-endpoint breakdown

### Admin
- Admin login at `/admin/login` for editing the home and about page content
- Dashboard configuration for scheduled aggregate queries

## Multi-dataspace architecture

Each deployment serves one data space. A data space is a directory under `dataspaces/` that bundles everything distinctive about that instance:

```
dataspaces/
├── humanitarian/           # Humanitarian Data Space
│   ├── config.py           # SITE_NAME, DEFAULT_FDPS, BRAND_LOGOS, CONTACT_EMAIL
│   ├── static/
│   │   ├── css/theme.css   # Overrides :root CSS variables (colors, fonts)
│   │   └── img/*           # Logos referenced by BRAND_LOGOS
│   └── pages/
│       ├── home.json       # Seed content for the home page
│       └── about.json      # Seed content for the about page
└── africa-health/          # Africa Health Data Space (VODAN branded)
    └── ...
```

Which one an instance serves is controlled by the `DATASPACE` environment variable. If unset, it defaults to `humanitarian`.

```bash
DATASPACE=humanitarian  docker-compose up   # Humanitarian Data Space
DATASPACE=africa-health docker-compose up   # Africa Health Data Space
```

The selected dataspace's `config.py` is loaded into Flask's config, its `static/` directory is registered at `/dataspace-static/`, and its `templates/` directory (if present) can override any base template. Page content in `pages/*.json` seeds the admin-editable content on first boot; subsequent edits persist in `app/data/admin.json`.

### Adding a new dataspace

1. Create `dataspaces/<name>/` with a `config.py`, a `static/css/theme.css` that redefines the `:root` variables, logos under `static/img/`, and seed page content under `pages/`.
2. Deploy the instance with `DATASPACE=<name>`.

No application code changes are required. See `dataspaces/humanitarian/` for a worked example.

## Installation

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
# Clone the repository
git clone https://github.com/RenVit318/fairdataspace.git
cd fairdataspace

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings (DATASPACE, SECRET_KEY, etc.)

# Run the application
flask run
```

The application will be available at `http://localhost:5000`.

### Docker

```bash
docker build -t fairdataspace .
docker run -p 5000:5000 -e DATASPACE=humanitarian -e SECRET_KEY=your-secret-key fairdataspace

# Or use docker-compose
DATASPACE=humanitarian docker-compose up
```

## Configuration

Environment variables (set in `.env` or system environment):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATASPACE` | Directory name under `dataspaces/` to load (branding, default FDPs, page content) | `humanitarian` |
| `SECRET_KEY` | Flask session secret key | Auto-generated |
| `FDP_TIMEOUT` | Timeout for FDP HTTP requests (seconds) | `30` |
| `SPARQL_TIMEOUT` | Timeout for SPARQL queries (seconds) | `60` |
| `FDP_VERIFY_SSL` | Verify SSL certificates for FDP requests | `false` |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `DASHBOARD_SPARQL_USERNAME` | Read-only user for the statistics dashboard queries | empty |
| `DASHBOARD_SPARQL_PASSWORD` | Password for the dashboard user | empty |
| `DASHBOARD_REFRESH_INTERVAL` | Dashboard refresh interval (seconds) | `86400` |

Dataspace-specific values (site name, default FDPs, logos, contact email, theme colors) live in `dataspaces/<name>/config.py` and `dataspaces/<name>/static/css/theme.css` — not in environment variables.

## Usage

### Public Flow (no login required)
1. **Add FDP endpoints** at `/fdp/add` — supports both single FDPs and index FDPs
2. **Browse datasets** at `/datasets` — filter by theme, keyword, or search
3. **Add to basket** — select datasets for your data access request
4. **Compose request** at `/request/compose` — fill in your details and query description
5. **Preview emails** — review generated emails and copy them to send

### Authenticated Flow (login required)
1. **Log in** at `/auth/login` with your SPARQL endpoint credentials
2. **Add datasets** with SPARQL endpoints to your basket
3. **View endpoint details** on dataset detail pages to discover SPARQL distributions
4. **Query endpoints** at `/sparql/query` — write and execute SPARQL SELECT queries
5. **View results** aggregated across selected endpoints

## Testing

```bash
# Run the full test suite
pytest

# Run with coverage
pytest --cov=app

# Run a specific test file
pytest tests/test_fdp_client.py
```

## Project Structure

```
fairdataspace/
├── app/
│   ├── __init__.py          # Flask app factory + dataspace loader
│   ├── config.py            # Environment-driven global configuration
│   ├── utils.py             # Shared utility functions
│   ├── models/              # Dataclasses (FDP, Dataset, Distribution, SPARQL, etc.)
│   ├── services/            # Business logic (FDP client, SPARQL client, email composer, admin)
│   ├── routes/              # Flask blueprints (main, fdp, datasets, request, auth, sparql, admin, dashboard)
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # Shared CSS + JS (dataspace overrides under dataspaces/<name>/static)
├── dataspaces/              # Per-dataspace branding, theme, default FDPs, page content
│   ├── humanitarian/
│   └── africa-health/
├── tests/
│   ├── fixtures/            # Mock RDF/Turtle data for tests
│   ├── conftest.py          # Shared pytest fixtures
│   └── test_*.py            # Test modules
├── requirements.txt         # Python dependencies
├── Dockerfile               # Container image definition
├── docker-compose.yml       # Container orchestration
└── run.py                   # Application entry point
```

## Security Notes

This application is a **proof of concept** and has known limitations:

- **Session-based storage**: All state (FDPs, datasets, basket, credentials) is stored in server-side filesystem sessions. There is no database.
- **Authentication**: The login system stores credentials in the session for reuse with SPARQL endpoints. It does not implement a user database or password hashing.
- **No CSRF protection**: Forms do not include CSRF tokens. Consider adding [Flask-WTF](https://flask-wtf.readthedocs.io/) for production use.
- **SSRF considerations**: Users can supply arbitrary FDP URLs that the server will fetch. Consider URL validation/allowlisting for production.

For production deployment, you should also:
- Set a strong `SECRET_KEY` via environment variable
- Run behind a reverse proxy (nginx/Caddy) with HTTPS
- Add rate limiting (e.g., [Flask-Limiter](https://flask-limiter.readthedocs.io/))
- Enable `SESSION_COOKIE_SECURE=True` when serving over HTTPS

## License

MIT License — see [LICENSE](LICENSE) for details.
