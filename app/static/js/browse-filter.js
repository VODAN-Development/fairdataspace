/* Browse page interactivity:
   - Instant client-side filter (search box, theme/source chips, sidebar facets).
   - AJAX add / remove for individual datasets — no page reload, no scroll loss.
   - "Add all visible" bulk action.
   - Updates the nav badge count in place. */
(function () {
    'use strict';

    var searchInput = document.getElementById('browse-search');
    var listContainer = document.getElementById('dataset-list');
    var scopeCountEl = document.getElementById('scope-count');
    var visibleCountEl = document.getElementById('visible-count');
    var emptyEl = document.getElementById('empty-filtered');
    var addAllBtn = document.getElementById('add-all-visible');
    var navBadge = document.querySelector('.nav-selection .badge');
    var navLink = document.querySelector('.nav-selection');
    if (!listContainer) return;

    var rows = Array.prototype.slice.call(listContainer.querySelectorAll('.dataset-row'));
    var totalRows = rows.length;

    var init = window.__browseFilters || {};
    var state = {
        q: (init.q || '').toLowerCase(),
        theme: init.theme || '',
        source: init.source || '',
        app: init.app || '',
        endpoint: init.endpoint || ''
    };

    function setChipActive(group, value) {
        document.querySelectorAll('.chip-row[data-chip-group="' + group + '"] .chip').forEach(function (el) {
            el.classList.toggle('chip-active', (el.dataset.value || '') === (value || ''));
        });
    }

    function setFacetActive(group, value) {
        document.querySelectorAll('.filter-facet[data-facet-group="' + group + '"] .facet-item').forEach(function (el) {
            el.classList.toggle('is-active', (el.dataset.value || '') === (value || ''));
        });
    }

    if (searchInput) searchInput.value = state.q;
    setChipActive('theme', state.theme);
    setChipActive('source', state.source);
    setFacetActive('app', state.app);
    setFacetActive('endpoint', state.endpoint);

    function rowMatches(row) {
        if (state.q) {
            var hay = [
                row.dataset.title,
                row.dataset.description,
                row.dataset.keywords,
                row.dataset.themeLabels,
                row.dataset.fdpTitle
            ].join(' ');
            var terms = state.q.split(/\s+/);
            for (var i = 0; i < terms.length; i++) {
                if (terms[i] && hay.indexOf(terms[i]) === -1) return false;
            }
        }
        if (state.theme) {
            var themes = (row.dataset.themes || '').split('|');
            if (themes.indexOf(state.theme) === -1) return false;
        }
        if (state.source && row.dataset.fdp !== state.source) return false;
        if (state.app && row.dataset.application !== state.app) return false;
        if (state.endpoint && row.dataset.hasEndpoint !== state.endpoint) return false;
        return true;
    }

    function syncUrl() {
        var url = new URL(window.location.href);
        ['q', 'theme', 'source', 'app', 'endpoint'].forEach(function (key) {
            if (state[key]) url.searchParams.set(key, state[key]);
            else url.searchParams.delete(key);
        });
        window.history.replaceState(null, '', url.toString());
    }

    function visibleRows() {
        return rows.filter(function (r) { return !r.hidden; });
    }

    function applyFilters() {
        var visible = 0;
        rows.forEach(function (row) {
            var match = rowMatches(row);
            row.hidden = !match;
            if (match) visible++;
        });
        document.querySelectorAll('.source-group').forEach(function (group) {
            var anyVisible = Array.prototype.some.call(
                group.querySelectorAll('.dataset-row'),
                function (r) { return !r.hidden; }
            );
            group.hidden = !anyVisible;
        });
        if (scopeCountEl) scopeCountEl.textContent = String(visible);
        if (visibleCountEl) visibleCountEl.textContent = String(visible);
        if (emptyEl) emptyEl.hidden = visible !== 0 || totalRows === 0;
        if (addAllBtn) addAllBtn.disabled = visible === 0;
        syncUrl();
    }

    var debounceTimer;
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(function () {
                state.q = searchInput.value.toLowerCase().trim();
                applyFilters();
            }, 150);
        });
    }

    document.querySelectorAll('.chip-row[data-chip-group]').forEach(function (group) {
        var name = group.dataset.chipGroup;
        group.addEventListener('click', function (e) {
            var btn = e.target.closest('.chip');
            if (!btn) return;
            state[name] = btn.dataset.value || '';
            setChipActive(name, state[name]);
            applyFilters();
        });
    });

    document.querySelectorAll('.filter-facet[data-facet-group]').forEach(function (group) {
        var name = group.dataset.facetGroup;
        group.addEventListener('click', function (e) {
            var btn = e.target.closest('.facet-item');
            if (!btn) return;
            state[name] = btn.dataset.value || '';
            setFacetActive(name, state[name]);
            applyFilters();
        });
    });

    // ---------- Selection AJAX ----------
    function setNavBadge(count) {
        if (count > 0) {
            if (!navBadge && navLink) {
                navBadge = document.createElement('span');
                navBadge.className = 'badge';
                navLink.appendChild(navBadge);
            }
            if (navBadge) navBadge.textContent = String(count);
        } else if (navBadge && navBadge.parentNode) {
            navBadge.parentNode.removeChild(navBadge);
            navBadge = null;
        }
    }

    function postForm(form) {
        var fd = new FormData(form);
        return fetch(form.action, {
            method: 'POST',
            body: fd,
            headers: { 'X-Requested-With': 'fetch' }
        }).then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        });
    }

    listContainer.addEventListener('submit', function (e) {
        var form = e.target.closest('form[data-action="add"], form[data-action="remove"]');
        if (!form) return;
        e.preventDefault();
        var card = form.closest('.dataset-row');
        var action = form.dataset.action;
        // Optimistic toggle so the user sees immediate feedback.
        if (action === 'add') {
            card.classList.add('in-selection');
        } else {
            card.classList.remove('in-selection');
        }
        postForm(form).then(function (data) {
            if (typeof data.selection_count === 'number') setNavBadge(data.selection_count);
        }).catch(function (err) {
            // Revert optimistic change on error.
            if (action === 'add') card.classList.remove('in-selection');
            else card.classList.add('in-selection');
            console.error('Selection update failed:', err);
        });
    });

    if (addAllBtn) {
        addAllBtn.addEventListener('click', function () {
            var visible = visibleRows().filter(function (r) { return !r.classList.contains('in-selection'); });
            if (visible.length === 0) return;
            var fd = new FormData();
            visible.forEach(function (row) {
                var form = row.querySelector('form[data-action="add"]');
                if (!form) return;
                // Extract uri_hash from the form action: /datasets/<hash>/add-to-selection
                var m = form.action.match(/\/datasets\/([^\/]+)\/add-to-selection/);
                if (m) fd.append('uri_hashes', m[1]);
            });
            addAllBtn.disabled = true;
            var origText = addAllBtn.textContent;
            addAllBtn.textContent = 'Adding…';
            fetch('/datasets/add-multiple-to-selection', {
                method: 'POST',
                body: fd,
                headers: { 'X-Requested-With': 'fetch' }
            }).then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            }).then(function (data) {
                visible.forEach(function (row) { row.classList.add('in-selection'); });
                if (typeof data.selection_count === 'number') setNavBadge(data.selection_count);
                addAllBtn.textContent = '✓ Added ' + (data.added || 0);
                setTimeout(function () {
                    addAllBtn.textContent = origText;
                    addAllBtn.disabled = false;
                }, 1500);
            }).catch(function (err) {
                addAllBtn.textContent = origText;
                addAllBtn.disabled = false;
                console.error('Bulk add failed:', err);
            });
        });
    }

    applyFilters();
})();
