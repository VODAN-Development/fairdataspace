"""Main routes for the fairdataspace application."""

from flask import Blueprint, current_app, redirect, render_template, session, url_for

from app.services.admin_service import get_page_content

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Render the landing page."""
    fdp_uris = session.get('fdp_uris', [])
    fdp_count = len(fdp_uris)
    selection_count = len(session.get('selection', []))

    cache = current_app.fdp_cache
    datasets = cache.get_datasets_for_fdps(fdp_uris)
    # None means "no datasets in cache yet" so the template shows an em dash.
    distribution_count = (
        sum(len(ds.get('distributions') or []) for ds in datasets)
        if datasets else None
    )
    content = get_page_content('home')

    return render_template(
        'index.html',
        fdp_count=fdp_count,
        selection_count=selection_count,
        distribution_count=distribution_count,
        page=content,
    )


@main_bp.route('/about')
def about():
    """Render the about page."""
    content = get_page_content('about')
    return render_template('about.html', page=content)


@main_bp.route('/selection/')
def selection_alias():
    """Shareable shortcut to the selection page."""
    return redirect(url_for('request.selection'))
