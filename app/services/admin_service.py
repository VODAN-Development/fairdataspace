"""Admin data management - credentials and page content stored on disk."""

import json
import os
import threading

from werkzeug.security import generate_password_hash, check_password_hash

_lock = threading.Lock()

# Persistent JSON file that holds admin credentials and editable page content.
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
_ADMIN_FILE = os.path.join(_DATA_DIR, 'admin.json')

# Default page content used on first run.
_DEFAULT_PAGES = {
    'home': {
        'hero_title': 'Humanitarian Data Space',
        'hero_subtitle': 'Find, explore, and request access to humanitarian datasets \u2014 all in one place',
        'intro_title': 'What does this platform do?',
        'intro_body': (
            'The Humanitarian Data Space helps researchers and humanitarian organizations discover '
            'datasets that are relevant to their work. Many valuable datasets exist across different '
            'data repositories, but finding and accessing them can be difficult. This platform '
            'brings them together.'
        ),
        'steps_title': 'How it works',
        'step1_title': 'Connect to a data source',
        'step1_body': 'Add the URL of a data repository. The platform will automatically discover all datasets it contains.',
        'step2_title': 'Find relevant datasets',
        'step2_body': 'Browse, search, and filter the discovered datasets to find the ones that match your needs.',
        'step3_title': 'Request or query',
        'step3_body': 'Add datasets to your basket and compose a data access request, or run queries directly on available endpoints.',
    },
    'about': {
        'section1_title': 'The Humanitarian Data Space',
        'section1_body': (
            'The Humanitarian Data Space is an innovative initiative developed by the Europe External '
            'Programme with Africa (EEPA) to collect, manage, and share sensitive data related to '
            'vulnerable communities impacted by conflicts and humanitarian crises. This initiative aims '
            'to enhance data visibility, ownership, and accessibility, ensuring that the voices of '
            'marginalized groups are heard and considered.\n\n'
            'The primary mission of the Humanitarian Data Space is to create a secure, federated '
            'environment where data can be accessed under well-defined conditions. By employing the '
            'FAIR-OLR (Findable, Accessible, Interoperable, Reusable \u2013 with Ownership, Localisation, '
            'and Regulatory compliance) principles, the initiative seeks to empower local stakeholders, '
            'human rights organizations, and healthcare professionals to use data effectively while '
            'maintaining control and ownership.\n\n'
            'The Humanitarian Data Space links data through FAIR Data Points (FDP), which are under '
            'the control of their respective organizations. The Data Space creates an overview of the '
            'data available in these FDPs. This website enables users to make requests for queries on '
            'those datasets. The request will go to the contact point on the FDP and will be approved '
            'or denied from there.'
        ),
        'partners_title': 'Partners',
        'partners_body': 'VODAN-Africa\nAfrican University Network on FAIR Open Science (AUN-FOS)\nTangaza University',
        'contact_title': 'Contact',
        'contact_body': 'For questions or more information, please reach out to the team at HDS@eepa.be.',
    },
}


def _read_data():
    """Read the admin JSON file, returning a dict."""
    if not os.path.exists(_ADMIN_FILE):
        return {}
    with open(_ADMIN_FILE, 'r') as f:
        return json.load(f)


def _write_data(data):
    """Atomically write the admin JSON file."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _ADMIN_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _ADMIN_FILE)


def _ensure_admin():
    """Create the default admin account if none exists yet."""
    with _lock:
        data = _read_data()
        if 'admin' not in data:
            data['admin'] = {
                'username': 'admin',
                'password_hash': generate_password_hash('admin'),
            }
            _write_data(data)
        if 'pages' not in data:
            data['pages'] = _DEFAULT_PAGES
            _write_data(data)
    return data


def verify_admin(username, password):
    """Return True if username/password match the stored admin credentials."""
    data = _ensure_admin()
    admin = data.get('admin', {})
    if username != admin.get('username'):
        return False
    return check_password_hash(admin['password_hash'], password)


def change_admin_password(new_password):
    """Update the admin password (stores hash, never plaintext)."""
    with _lock:
        data = _ensure_admin()
        data['admin']['password_hash'] = generate_password_hash(new_password)
        _write_data(data)


def get_page_content(page_key):
    """Return the editable content dict for a given page, or defaults."""
    data = _ensure_admin()
    pages = data.get('pages', _DEFAULT_PAGES)
    return pages.get(page_key, _DEFAULT_PAGES.get(page_key, {}))


def save_page_content(page_key, content):
    """Save edited page content."""
    with _lock:
        data = _ensure_admin()
        if 'pages' not in data:
            data['pages'] = dict(_DEFAULT_PAGES)
        data['pages'][page_key] = content
        _write_data(data)


def get_all_page_keys():
    """Return a list of editable page keys."""
    return list(_DEFAULT_PAGES.keys())


def get_default_fields(page_key):
    """Return the field names for a given page (used to build the edit form)."""
    return _DEFAULT_PAGES.get(page_key, {})
