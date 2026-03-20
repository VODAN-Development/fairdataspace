"""FDP management routes."""

from flask import Blueprint, render_template, request, session, flash, redirect, url_for

from app.config import Config
from app.routes.admin import admin_required
from app.services import FDPClient, FDPConnectionError, FDPParseError, FDPTimeoutError
from app.utils import get_uri_hash

fdp_bp = Blueprint('fdp', __name__, url_prefix='/fdp')


@fdp_bp.route('/')
def list_fdps():
    """Public read-only list of configured FDPs."""
    fdps = session.get('fdps', {})
    is_admin = session.get('is_admin', False)
    return render_template('fdp/list.html', fdps=fdps, is_admin=is_admin)


@fdp_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add():
    """Add a new FDP endpoint."""
    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        is_index = request.form.get('is_index') == 'on'

        if not url:
            flash('Please enter a valid URL.', 'error')
            return render_template('fdp/add.html')

        # Validate URL format
        if not url.startswith(('http://', 'https://')):
            flash('URL must start with http:// or https://', 'error')
            return render_template('fdp/add.html', url=url, is_index=is_index)

        # Check if already added
        uri_hash = get_uri_hash(url)
        if uri_hash in session.get('fdps', {}):
            flash('This FDP is already configured.', 'warning')
            return redirect(url_for('fdp.list_fdps'))

        # Try to fetch FDP metadata
        client = FDPClient(timeout=Config.FDP_TIMEOUT, verify_ssl=Config.FDP_VERIFY_SSL)

        try:
            if is_index:
                # Fetch index FDP and discover linked FDPs
                fdps = client.fetch_all_from_index(url)
                added_count = 0

                for fdp in fdps:
                    fdp_hash = get_uri_hash(fdp.uri)
                    if fdp_hash not in session.get('fdps', {}):
                        if 'fdps' not in session:
                            session['fdps'] = {}
                        session['fdps'][fdp_hash] = fdp.to_dict()
                        added_count += 1

                session.modified = True

                if added_count > 0:
                    flash(f'Successfully added {added_count} FDP(s).', 'success')
                else:
                    flash('No new FDPs to add.', 'info')
            else:
                # Fetch single FDP
                fdp = client.fetch_fdp(url)

                if 'fdps' not in session:
                    session['fdps'] = {}

                session['fdps'][uri_hash] = fdp.to_dict()
                session.modified = True

                flash(f'Successfully added FDP: {fdp.title}', 'success')

            return redirect(url_for('fdp.list_fdps'))

        except FDPConnectionError as e:
            flash(f'Could not connect to the FAIR Data Point. Please check the URL.', 'error')
            return render_template('fdp/add.html', url=url, is_index=is_index)
        except FDPParseError as e:
            flash('Could not parse the FDP metadata. The endpoint may not be a valid FDP.', 'error')
            return render_template('fdp/add.html', url=url, is_index=is_index)
        except FDPTimeoutError as e:
            flash('Request timed out. Please try again.', 'error')
            return render_template('fdp/add.html', url=url, is_index=is_index)

    return render_template('fdp/add.html')


@fdp_bp.route('/<uri_hash>/refresh', methods=['POST'])
@admin_required
def refresh(uri_hash: str):
    """Refresh FDP metadata."""
    fdps = session.get('fdps', {})

    if uri_hash not in fdps:
        flash('FDP not found.', 'error')
        return redirect(url_for('fdp.list_fdps'))

    fdp_data = fdps[uri_hash]
    uri = fdp_data['uri']

    client = FDPClient(timeout=Config.FDP_TIMEOUT)

    try:
        fdp = client.fetch_fdp(uri)
        session['fdps'][uri_hash] = fdp.to_dict()
        session.modified = True
        flash(f'Successfully refreshed FDP: {fdp.title}', 'success')
    except FDPConnectionError:
        session['fdps'][uri_hash]['status'] = 'error'
        session['fdps'][uri_hash]['error_message'] = 'Could not connect'
        session.modified = True
        flash('Could not connect to the FDP.', 'error')
    except FDPParseError:
        session['fdps'][uri_hash]['status'] = 'error'
        session['fdps'][uri_hash]['error_message'] = 'Could not parse metadata'
        session.modified = True
        flash('Could not parse the FDP metadata.', 'error')
    except FDPTimeoutError:
        session['fdps'][uri_hash]['status'] = 'error'
        session['fdps'][uri_hash]['error_message'] = 'Request timed out'
        session.modified = True
        flash('Request timed out.', 'error')

    return redirect(url_for('fdp.list_fdps'))


@fdp_bp.route('/<uri_hash>/remove', methods=['POST'])
@admin_required
def remove(uri_hash: str):
    """Remove an FDP from the configuration."""
    fdps = session.get('fdps', {})

    if uri_hash not in fdps:
        flash('FDP not found.', 'error')
        return redirect(url_for('fdp.list_fdps'))

    fdp_title = fdps[uri_hash].get('title', 'Unknown')
    del session['fdps'][uri_hash]
    session.modified = True

    # Also clear datasets cache since FDPs changed
    session['datasets_cache'] = []

    flash(f'Removed FDP: {fdp_title}', 'success')
    return redirect(url_for('fdp.list_fdps'))
