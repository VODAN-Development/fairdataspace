"""Admin routes - login, dashboard, page content editing."""

from functools import wraps

from flask import (
    Blueprint,
    render_template,
    request,
    session,
    flash,
    redirect,
    url_for,
)

from app.services.admin_service import (
    verify_admin,
    change_admin_password,
    get_page_content,
    save_page_content,
    get_all_page_keys,
    get_default_fields,
)
from app.services import dashboard_service

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Decorator that requires an active admin session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Administrator login required.', 'warning')
            return redirect(url_for('admin.login', next=request.url))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('is_admin'):
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('admin/login.html')

        if verify_admin(username, password):
            session['is_admin'] = True
            session['admin_username'] = username
            session.modified = True
            flash(f'Welcome, {username}!', 'success')

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/') and not next_page.startswith('//'):
                return redirect(next_page)
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid administrator credentials.', 'error')
            return render_template('admin/login.html')

    return render_template('admin/login.html')


@admin_bp.route('/logout', methods=['POST'])
def logout():
    session.pop('is_admin', None)
    session.pop('admin_username', None)
    session.modified = True
    flash('Logged out of admin panel.', 'success')
    return redirect(url_for('main.index'))


@admin_bp.route('/')
@admin_required
def dashboard():
    page_keys = get_all_page_keys()
    return render_template('admin/dashboard.html', page_keys=page_keys)


@admin_bp.route('/pages/<page_key>', methods=['GET', 'POST'])
@admin_required
def edit_page(page_key):
    defaults = get_default_fields(page_key)
    if not defaults:
        flash('Unknown page.', 'error')
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        content = {}
        for field_name in defaults:
            content[field_name] = request.form.get(field_name, '').strip()
        save_page_content(page_key, content)
        flash(f'Page "{page_key}" updated successfully.', 'success')
        return redirect(url_for('admin.dashboard'))

    content = get_page_content(page_key)
    return render_template(
        'admin/edit_page.html',
        page_key=page_key,
        content=content,
        defaults=defaults,
    )


@admin_bp.route('/password', methods=['GET', 'POST'])
@admin_required
def change_password():
    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()

        if not new_password or len(new_password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('admin/change_password.html')

        if new_password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('admin/change_password.html')

        change_admin_password(new_password)
        flash('Password changed successfully.', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/change_password.html')


@admin_bp.route('/dashboard-config', methods=['GET', 'POST'])
@admin_required
def dashboard_config():
    if request.method == 'POST':
        raw = request.form.get('endpoints', '')
        manual_endpoints = []
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if '|' in line:
                url_part, label_part = line.split('|', 1)
                manual_endpoints.append({
                    'url': url_part.strip(),
                    'label': label_part.strip(),
                    'enabled': True,
                    'discovered': False,
                })
            else:
                manual_endpoints.append({
                    'url': line.strip(),
                    'label': line.strip(),
                    'enabled': True,
                    'discovered': False,
                })
        # Preserve discovered endpoints, replace manual ones
        config = dashboard_service.get_config()
        discovered = [ep for ep in config.get('endpoints', []) if ep.get('discovered', False)]
        config['endpoints'] = manual_endpoints + discovered
        dashboard_service.save_config(config)
        flash(f'Saved {len(manual_endpoints)} manual endpoint(s).', 'success')
        return redirect(url_for('admin.dashboard_config'))

    config = dashboard_service.get_config()
    status = dashboard_service.get_refresh_status()
    # Only show manual endpoints in the textarea
    manual = [ep for ep in config.get('endpoints', []) if not ep.get('discovered', False)]
    lines = []
    for ep in manual:
        label = ep.get('label', '')
        if label and label != ep['url']:
            lines.append(f"{ep['url']} | {label}")
        else:
            lines.append(ep['url'])
    endpoint_text = '\n'.join(lines)

    return render_template(
        'admin/dashboard_config.html',
        config=config,
        status=status,
        endpoint_text=endpoint_text,
    )


@admin_bp.route('/dashboard-refresh', methods=['POST'])
@admin_required
def dashboard_refresh():
    import threading
    thread = threading.Thread(target=dashboard_service.refresh_all, daemon=True)
    thread.start()
    flash('Dashboard refresh started. This may take a minute.', 'info')
    return redirect(url_for('admin.dashboard_config'))
