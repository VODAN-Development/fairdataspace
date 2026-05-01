"""SPARQL query execution routes."""

from flask import (
    Blueprint,
    render_template,
    request,
    session,
    flash,
    redirect,
    url_for,
)

from app.routes.auth import login_required
from app.services import SPARQLClient
from app.models import SPARQLQuery, EndpointCredentials
from app.config import Config


sparql_bp = Blueprint('sparql', __name__, url_prefix='/sparql')


def _get_selection_endpoints() -> list:
    """Get SPARQL endpoints from datasets currently in the selection."""
    selection = session.get('selection', [])
    discovered = session.get('discovered_endpoints', {})

    if not selection or not discovered:
        return []

    selection_uris = {item['uri'] for item in selection}
    endpoints = []
    seen_urls = set()

    for ep_hash, ep in discovered.items():
        # Only include endpoints whose source dataset is in the selection
        if ep.get('dataset_uri') not in selection_uris:
            continue
        endpoint_url = ep.get('endpoint_url', '')
        if endpoint_url in seen_urls:
            continue
        seen_urls.add(endpoint_url)

        endpoints.append({
            'hash': ep_hash,
            'endpoint_url': endpoint_url,
            'fdp_title': ep.get('fdp_title', 'Unknown'),
            'dataset_title': ep.get('dataset_title', 'Unknown'),
        })

    return endpoints


@sparql_bp.route('/')
@login_required
def index() -> str:
    """SPARQL query landing page.

    Shows endpoints available from selection datasets.

    Returns:
        Rendered SPARQL index template.
    """
    endpoints = _get_selection_endpoints()
    selection = session.get('selection', [])

    return render_template(
        'sparql/index.html',
        endpoints=endpoints,
        selection=selection,
    )


@sparql_bp.route('/query', methods=['GET', 'POST'])
@login_required
def query() -> str:
    """SPARQL query editor and execution.

    Endpoints come from selection datasets. Credentials come from login.

    Returns:
        Rendered query form or redirect to results.
    """
    endpoints = _get_selection_endpoints()

    if not endpoints:
        selection = session.get('selection', [])
        if not selection:
            flash('Your selection is empty. Add datasets with SPARQL endpoints first.', 'warning')
            return redirect(url_for('datasets.browse'))
        else:
            flash(
                'No SPARQL endpoints found in your selection datasets. '
                'View dataset details to discover endpoints, or add datasets that have SPARQL distributions.',
                'warning'
            )
            return redirect(url_for('sparql.index'))

    if request.method == 'POST':
        query_text = request.form.get('query', '').strip()
        selected_hashes = request.form.getlist('endpoints')

        if not query_text:
            flash('Please enter a SPARQL query.', 'error')
            return render_template(
                'sparql/query.html',
                endpoints=endpoints,
                query_text='',
                selected=[],
            )

        if not selected_hashes:
            flash('Please select at least one endpoint.', 'error')
            return render_template(
                'sparql/query.html',
                endpoints=endpoints,
                query_text=query_text,
                selected=[],
            )

        # Validate query syntax
        timeout = getattr(Config, 'SPARQL_TIMEOUT', 60)
        client = SPARQLClient(timeout=timeout)
        if not client.validate_query(query_text):
            flash(
                'Invalid SPARQL query. Query must start with SELECT, CONSTRUCT, ASK, or DESCRIBE.',
                'error'
            )
            return render_template(
                'sparql/query.html',
                endpoints=endpoints,
                query_text=query_text,
                selected=selected_hashes,
            )

        # Build execution plan using login credentials for all endpoints
        user = session.get('user', {})
        discovered = session.get('discovered_endpoints', {})

        target_endpoints = []
        credentials_map = {}
        fdp_titles = {}

        for ep_hash in selected_hashes:
            ep = discovered.get(ep_hash)
            if not ep:
                continue

            endpoint_url = ep['endpoint_url']
            target_endpoints.append(endpoint_url)
            fdp_titles[endpoint_url] = ep.get('fdp_title', endpoint_url)

            # Use the login credentials for all endpoints
            credentials_map[endpoint_url] = EndpointCredentials(
                fdp_uri=ep.get('fdp_uri', ''),
                sparql_endpoint=endpoint_url,
                username=user.get('username', ''),
                password=user.get('password', ''),
            )

        # Execute federated query
        sparql_query = SPARQLQuery(
            query_text=query_text,
            target_endpoints=target_endpoints,
        )

        result = client.execute_federated(
            sparql_query, credentials_map, fdp_titles
        )

        # Store result in session for display
        session['query_result'] = result.to_dict()
        session.modified = True

        return redirect(url_for('sparql.results'))

    # GET request - show query form
    return render_template(
        'sparql/query.html',
        endpoints=endpoints,
        query_text='',
        selected=[],
    )


@sparql_bp.route('/results')
@login_required
def results() -> str:
    """Display SPARQL query results.

    Returns:
        Rendered results template or redirect if no results.
    """
    result_data = session.get('query_result')

    if not result_data:
        flash('No query results to display.', 'warning')
        return redirect(url_for('sparql.query'))

    return render_template(
        'sparql/results.html',
        result=result_data,
    )


@sparql_bp.route('/results/clear', methods=['POST'])
@login_required
def clear_results() -> str:
    """Clear stored query results.

    Returns:
        Redirect to query page.
    """
    session.pop('query_result', None)
    session.modified = True
    flash('Results cleared.', 'success')
    return redirect(url_for('sparql.query'))
