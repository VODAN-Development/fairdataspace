"""Dataset browsing routes."""

import logging

from flask import Blueprint, current_app, render_template, request, session, flash, redirect, url_for

from app.config import Config
from app.models import Dataset, ContactPoint, Distribution
from app.services import FDPClient, DatasetService
from app.services.admin_service import get_page_content
from app.services.dataset_service import application_key
from app.utils import get_uri_hash

logger = logging.getLogger(__name__)

datasets_bp = Blueprint('datasets', __name__, url_prefix='/datasets')


def dataset_from_dict(data: dict) -> Dataset:
    """Reconstruct Dataset from dictionary."""
    contact_data = data.get('contact_point')
    contact_point = None
    if contact_data:
        contact_point = ContactPoint(
            name=contact_data.get('name'),
            email=contact_data.get('email'),
            url=contact_data.get('url'),
        )

    raw_dists = data.get('distributions', [])
    distributions = []
    for d in raw_dists:
        if isinstance(d, dict):
            distributions.append(Distribution.from_dict(d))
        elif isinstance(d, str):
            distributions.append(Distribution(uri=d))

    return Dataset(
        uri=data['uri'],
        title=data['title'],
        catalog_uri=data['catalog_uri'],
        catalog_title=data.get('catalog_title'),
        catalog_homepage=data.get('catalog_homepage'),
        fdp_uri=data['fdp_uri'],
        fdp_title=data['fdp_title'],
        description=data.get('description'),
        publisher=data.get('publisher'),
        creator=data.get('creator'),
        issued=None,
        modified=None,
        themes=data.get('themes', []),
        theme_labels=data.get('theme_labels', []),
        keywords=data.get('keywords', []),
        contact_point=contact_point,
        landing_page=data.get('landing_page'),
        distributions=distributions,
    )


def _get_cached_datasets() -> list:
    """Return the dataset dicts in the cache visible to this session."""
    cache = current_app.fdp_cache
    fdp_uris = session.get('fdp_uris', [])
    return cache.get_datasets_for_fdps(fdp_uris)


@datasets_bp.route('/')
def browse():
    """Render the full cached dataset list for client-side filtering.

    URL params (?q, ?theme, ?app, ?source, ?endpoint) hydrate the JS filter
    state on load so shared URLs restore the same view; they are NOT applied
    server-side. Every cached dataset lands in the DOM and `browse-filter.js`
    hides/shows rows as the user interacts.
    """
    datasets_dicts = _get_cached_datasets()
    datasets = [dataset_from_dict(d) for d in datasets_dicts]

    client = FDPClient(timeout=Config.FDP_TIMEOUT, verify_ssl=Config.FDP_VERIFY_SSL)
    service = DatasetService(client)

    datasets.sort(key=lambda d: (d.title or '').lower())

    themes = service.get_available_themes(datasets)
    applications = service.get_available_applications(datasets)
    sources = service.get_available_sources(datasets)

    selection = session.get('selection', [])
    selection_uris = {item['uri'] for item in selection}

    cache_info = current_app.fdp_cache.get_cache_info()
    browse_intro = get_page_content('browse_intro')

    # Group datasets by source FDP so the list renders with source headers.
    source_errors = (cache_info or {}).get('errors', {}) if cache_info else {}
    grouped_datasets = []
    seen_fdps = {}
    for ds in datasets:
        key = ds.fdp_uri or ''
        if key not in seen_fdps:
            seen_fdps[key] = {
                'fdp_uri': ds.fdp_uri,
                'fdp_title': ds.fdp_title or ds.fdp_uri,
                'online': key not in source_errors,
                'items': [],
            }
            grouped_datasets.append(seen_fdps[key])
        seen_fdps[key]['items'].append(ds)

    # Filter hydration (JS reads on load).
    filters = {
        'q': request.args.get('q', '').strip(),
        'theme': request.args.get('theme', '').strip(),
        'app': request.args.get('app', '').strip(),
        'source': request.args.get('source', '').strip(),
        'endpoint': request.args.get('endpoint', '').strip(),
    }

    return render_template(
        'datasets/browse.html',
        datasets=datasets,
        grouped_datasets=grouped_datasets,
        themes=themes,
        applications=applications,
        sources=sources,
        scope_total_datasets=len(datasets),
        scope_total_sources=len(sources),
        selection_uris=selection_uris,
        filters=filters,
        browse_intro=browse_intro,
        get_uri_hash=get_uri_hash,
        cache_info=cache_info,
    )


@datasets_bp.route('/refresh', methods=['POST'])
def refresh():
    """Force a cache refresh for every FDP known to this session."""
    fdp_uris = session.get('fdp_uris', [])

    if not fdp_uris:
        flash('No FDPs configured. Add an FDP first.', 'warning')
        return redirect(url_for('datasets.browse'))

    cache = current_app.fdp_cache
    errors = 0
    for uri in fdp_uris:
        entry = cache.fetch_and_cache_fdp(uri)
        if entry is None or entry.error:
            errors += 1

    datasets = cache.get_datasets_for_fdps(fdp_uris)
    if errors:
        flash(
            f'Refreshed with {errors} error(s); cache holds {len(datasets)} dataset(s).',
            'warning',
        )
    else:
        flash(f'Successfully refreshed {len(datasets)} dataset(s).', 'success')

    return redirect(url_for('datasets.browse'))


@datasets_bp.route('/<uri_hash>')
def detail(uri_hash: str):
    """Show dataset detail view, served entirely from cache."""
    datasets_dicts = _get_cached_datasets()

    dataset_dict = None
    for d in datasets_dicts:
        if get_uri_hash(d['uri']) == uri_hash:
            dataset_dict = d
            break

    if not dataset_dict:
        flash('Dataset not found.', 'error')
        return redirect(url_for('datasets.browse'))

    dataset = dataset_from_dict(dataset_dict)
    _store_discovered_endpoints(dataset)

    # Find siblings — other cached datasets in the same application.
    siblings_by_fdp: dict = {}
    target_key = application_key(dataset)
    if target_key:
        for d in datasets_dicts:
            if application_key(d) != target_key:
                continue
            if d['uri'] == dataset.uri:
                continue
            fdp_title = d.get('fdp_title') or d.get('fdp_uri') or ''
            siblings_by_fdp.setdefault(fdp_title, []).append({
                'uri': d['uri'],
                'uri_hash': get_uri_hash(d['uri']),
                'title': d['title'],
                'fdp_title': fdp_title,
            })

    selection = session.get('selection', [])
    in_selection = any(item['uri'] == dataset.uri for item in selection)
    selection_uris = {item['uri'] for item in selection}

    return render_template(
        'datasets/detail.html',
        dataset=dataset,
        uri_hash=uri_hash,
        in_selection=in_selection,
        siblings_by_fdp=siblings_by_fdp,
        selection_uris=selection_uris,
    )


@datasets_bp.route('/add-application-to-selection', methods=['POST'])
def add_application_to_selection():
    """Add every cached dataset matching the given application key to the selection."""
    target_key = (request.form.get('app_key') or request.form.get('homepage') or '').strip()
    if not target_key:
        flash('No application selected.', 'error')
        return redirect(url_for('datasets.browse'))

    datasets_dicts = _get_cached_datasets()
    selection = session.get('selection', [])
    existing_uris = {item['uri'] for item in selection}

    added = 0
    for d in datasets_dicts:
        if application_key(d) != target_key:
            continue
        if d['uri'] in existing_uris:
            continue
        uri_hash = get_uri_hash(d['uri'])
        selection.append({
            'uri': d['uri'],
            'uri_hash': uri_hash,
            'title': d['title'],
            'fdp_title': d['fdp_title'],
            'catalog_uri': d.get('catalog_uri'),
            'catalog_title': d.get('catalog_title'),
            'catalog_homepage': d.get('catalog_homepage'),
            'contact_point': d.get('contact_point'),
        })
        existing_uris.add(d['uri'])
        added += 1

    session['selection'] = selection
    session.modified = True

    if request.headers.get('X-Requested-With') == 'fetch':
        return {'added': added, 'selection_count': len(selection)}, 200

    if added:
        flash(f'Added {added} dataset(s) from this application to your selection.', 'success')
    else:
        flash('All datasets for this application are already in your selection.', 'info')

    next_url = request.form.get('next') or request.referrer
    if not next_url or not next_url.startswith('/') or next_url.startswith('//'):
        next_url = url_for('datasets.browse')
    return redirect(next_url)


@datasets_bp.route('/add-multiple-to-selection', methods=['POST'])
def add_multiple_to_selection():
    """Bulk-add a list of datasets (by uri_hash) to the selection.

    Used by the browse page's 'Add all visible' button via fetch.
    """
    hashes = request.form.getlist('uri_hashes') or request.form.getlist('uri_hashes[]')
    if not hashes:
        return {'error': 'no uri_hashes provided'}, 400

    datasets_dicts = _get_cached_datasets()
    by_hash = {get_uri_hash(d['uri']): d for d in datasets_dicts}

    selection = session.get('selection', [])
    existing_uris = {item['uri'] for item in selection}

    added = 0
    added_uris = []
    for h in hashes:
        d = by_hash.get(h)
        if not d or d['uri'] in existing_uris:
            continue
        _store_discovered_endpoints(dataset_from_dict(d))
        selection.append({
            'uri': d['uri'],
            'uri_hash': h,
            'title': d['title'],
            'fdp_title': d['fdp_title'],
            'catalog_uri': d.get('catalog_uri'),
            'catalog_title': d.get('catalog_title'),
            'catalog_homepage': d.get('catalog_homepage'),
            'contact_point': d.get('contact_point'),
        })
        existing_uris.add(d['uri'])
        added += 1
        added_uris.append(d['uri'])

    session['selection'] = selection
    session.modified = True

    return {'added': added, 'selection_count': len(selection), 'added_uris': added_uris}, 200


def _store_discovered_endpoints(dataset: Dataset) -> None:
    """Store discovered SPARQL endpoints in session for later credential config."""
    if 'discovered_endpoints' not in session:
        session['discovered_endpoints'] = {}

    for dist in dataset.distributions:
        if not dist.is_sparql_endpoint:
            continue
        url = dist.endpoint_url or dist.access_url
        if not url:
            continue
        endpoint_key = get_uri_hash(url)
        session['discovered_endpoints'][endpoint_key] = {
            'endpoint_url': url,
            'dataset_uri': dataset.uri,
            'dataset_title': dataset.title,
            'fdp_uri': dataset.fdp_uri,
            'fdp_title': dataset.fdp_title,
            'distribution_title': dist.title,
        }

    session.modified = True


@datasets_bp.route('/<uri_hash>/add-to-selection', methods=['POST'])
def add_to_selection(uri_hash: str):
    """Add a dataset to the request selection."""
    datasets_dicts = _get_cached_datasets()

    dataset_dict = None
    for d in datasets_dicts:
        if get_uri_hash(d['uri']) == uri_hash:
            dataset_dict = d
            break

    if not dataset_dict:
        flash('Dataset not found.', 'error')
        return redirect(url_for('datasets.browse'))

    selection = session.get('selection', [])
    is_xhr = request.headers.get('X-Requested-With') == 'fetch'
    already = any(item['uri'] == dataset_dict['uri'] for item in selection)
    if already:
        if not is_xhr:
            flash('Dataset is already in your selection.', 'info')
    else:
        # Full dataset (with distributions) comes from cache — no extra HTTP.
        _store_discovered_endpoints(dataset_from_dict(dataset_dict))

        selection.append({
            'uri': dataset_dict['uri'],
            'uri_hash': uri_hash,
            'title': dataset_dict['title'],
            'fdp_title': dataset_dict['fdp_title'],
            'catalog_uri': dataset_dict.get('catalog_uri'),
            'catalog_title': dataset_dict.get('catalog_title'),
            'catalog_homepage': dataset_dict.get('catalog_homepage'),
            'contact_point': dataset_dict.get('contact_point'),
        })
        session['selection'] = selection
        session.modified = True
        if not is_xhr:
            flash(f'Added "{dataset_dict["title"]}" to your selection.', 'success')

    if is_xhr:
        return {'added': not already, 'selection_count': len(selection)}, 200

    next_url = request.form.get('next') or request.referrer
    if not next_url or not next_url.startswith('/') or next_url.startswith('//'):
        next_url = url_for('datasets.browse')
    return redirect(next_url)


@datasets_bp.route('/<uri_hash>/remove-from-selection', methods=['POST'])
def remove_from_selection(uri_hash: str):
    """Remove a dataset from the request selection."""
    selection = session.get('selection', [])
    is_xhr = request.headers.get('X-Requested-With') == 'fetch'

    new_selection = [item for item in selection if item.get('uri_hash') != uri_hash]
    removed = len(new_selection) != len(selection)

    if removed:
        session['selection'] = new_selection
        session.modified = True
        if not is_xhr:
            flash('Removed dataset from selection.', 'success')
    elif not is_xhr:
        flash('Dataset not found in selection.', 'error')

    if is_xhr:
        return {'removed': removed, 'selection_count': len(new_selection)}, 200

    next_url = request.form.get('next') or request.referrer
    if not next_url or not next_url.startswith('/') or next_url.startswith('//'):
        next_url = url_for('datasets.browse')
    return redirect(next_url)
